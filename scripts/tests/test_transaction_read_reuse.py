"""Exercise actual adapter helpers without drivers, credentials or databases.

The finite pool reproduces transaction-bound authorization contention. It also
checks that borrowing never crosses an identity, execution context or lifetime.
"""
from __future__ import annotations

import ast
import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from contextvars import ContextVar, copy_context
from pathlib import Path
from types import SimpleNamespace
import threading

import pytest

from lib import continuity_work, identity_api, package_layout
from lib.transaction_reads import TransactionReads, connection_identity


ROOT = Path(__file__).resolve().parents[2]
BACKENDS = package_layout.databases(ROOT)


class ExpectedFailure(RuntimeError):
    pass


class Cursor:
    def __init__(self, connection, dictionary=False):
        self.connection = connection
        self.dictionary = dictionary
        self.rowcount = 1
        self.description = []
        self.rows = []
        self.closed = False

    def execute(self, sql, params):
        upper = sql.upper()
        if "FAIL_READ" in upper:
            raise ExpectedFailure("synthetic read failure")
        if "SELECT PRINCIPAL_TYPE, STATUS, PERMISSION_VERSION" in upper:
            rows = [{"principal_type": "HUMAN", "status": "ACTIVE", "permission_version": 1}]
        elif "SELECT ROLE_CODE" in upper:
            rows = [{"role_code": "SYSTEM_ADMIN"}]
        elif "SELECT PERMISSION_VERSION" in upper:
            rows = [{"permission_version": 1}]
        elif "SELECT STATUS" in upper:
            rows = [{"status": "ACTIVE"}]
        elif "SELECT MEMBERSHIP_TIER" in upper:
            rows = [{"membership_tier": "MEMBER"}]
        elif "PROBE_VALUE" in upper:
            rows = [{"probe_value": self.connection.number, "payload": self.connection.payload}]
        else:
            rows = []
        self.description = [(name.upper(),) for name in (rows[0] if rows else {"value": None})]
        self.rows = rows if self.dictionary else [tuple(row.values()) for row in rows]

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def close(self):
        self.closed = True

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


class Connection:
    def __init__(self, number, identity):
        self.number = number
        self.identity = identity
        self.payload = object()
        self.commits = 0
        self.rollbacks = 0
        self.cursors = []

    def cursor(self, cursor_factory=None):
        cursor = Cursor(self, dictionary=cursor_factory is not None)
        self.cursors.append(cursor)
        return cursor

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


class Adapter:
    def __init__(self, backend, ceiling=5):
        self.slots = threading.BoundedSemaphore(ceiling)
        self.lock = threading.Lock()
        self.connections = []
        self.exhaustions = 0
        self.active = 0
        self.peak = 0
        database = SimpleNamespace(user="OWNER_A", dsn="synthetic/SERVICE_A", host="synthetic", port=1, dbname="DB_A")
        self.config = ContextVar("synthetic_config", default=SimpleNamespace(database=database, agent=SimpleNamespace(mode="admin")))
        self.agent = ContextVar("synthetic_agent", default=None)
        self.credentials = ContextVar("synthetic_credentials", default={})
        path = package_layout.adapter_file(ROOT, backend, "connection.py")
        tree = ast.parse(path.read_text(encoding="utf-8"))
        selected = {"execute", "execute_query", "execute_query_one", "execute_transaction_callback", "_Transaction",
                    "_transaction_read_identity", "_convert_params"}
        nodes = [node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name in selected]
        namespace = {"get_connection_for_agent": self.connection, "get_config": self.config.get,
                     "get_current_agent_id": self.agent.get, "_load_agent_eu_creds": self.credentials.get,
                     "connection_identity": connection_identity,
                     "RealDictCursor": object()}
        module = ast.Module(body=[ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0), *nodes], type_ignores=[])
        ast.fix_missing_locations(module)
        exec(compile(module, str(path), "exec"), namespace)
        namespace["_transaction_reads"] = TransactionReads(namespace["_transaction_read_identity"])
        self.api = SimpleNamespace(**namespace)
        self.reads = namespace["_transaction_reads"]

    @contextmanager
    def connection(self):
        if not self.slots.acquire(timeout=0.2):
            with self.lock:
                self.exhaustions += 1
            raise ExpectedFailure("finite pool exhausted")
        try:
            with self.lock:
                connection = Connection(len(self.connections) + 1, self.api._transaction_read_identity())
                self.connections.append(connection)
                self.active += 1
                self.peak = max(self.peak, self.active)
            try:
                yield connection
            finally:
                with self.lock:
                    self.active -= 1
        finally:
            self.slots.release()


@pytest.fixture(params=BACKENDS)
def adapter(request):
    return Adapter(request.param)


def test_finite_pool_authorization_does_not_acquire_nested_slot(adapter, monkeypatch):
    monkeypatch.setattr(identity_api, "connection", adapter.api)
    entered = threading.Barrier(5)

    def worker(_):
        def callback(tx):
            entered.wait(timeout=5)
            continuity_work._authorize(tx, "SYNTHETIC_READER", "DEFAULT", write=False)
            assert adapter.api.execute_query_one("SELECT PROBE_VALUE")["probe_value"] == tx.conn.number
        adapter.api.execute_transaction_callback(callback)

    with ThreadPoolExecutor(max_workers=5) as executor:
        list(executor.map(worker, range(5)))
    assert len(adapter.connections) == adapter.peak == 5
    assert adapter.active == adapter.exhaustions == 0
    assert all((conn.commits, conn.rollbacks) == (1, 0) for conn in adapter.connections)
    assert all(cursor.closed for conn in adapter.connections for cursor in conn.cursors)


@pytest.mark.parametrize("payload", [object(), {"nested": ["unchanged", 1]}], ids=["lob-sentinel", "dictionary"])
def test_inner_reads_preserve_payload_and_outer_transaction_boundary(adapter, payload):
    def callback(tx):
        tx.conn.payload = payload
        rows = adapter.api.execute_query("SELECT PROBE_VALUE")
        one = adapter.api.execute_query_one("SELECT PROBE_VALUE")
        assert rows[0]["payload"] is one["payload"] is tx.conn.payload
        assert rows[0]["probe_value"] == tx.conn.number
        assert (tx.conn.commits, tx.conn.rollbacks) == (0, 0)
        with pytest.raises(ExpectedFailure):
            adapter.api.execute_query("SELECT FAIL_READ")
        assert (tx.conn.commits, tx.conn.rollbacks) == (0, 0)
    adapter.api.execute_transaction_callback(callback)
    assert len(adapter.connections) == 1
    assert (adapter.connections[0].commits, adapter.connections[0].rollbacks) == (1, 0)


@pytest.mark.parametrize("change", ["agent_to_owner", "agent_to_agent", "mode", "owner", "database"])
def test_identity_change_never_borrows_outer_connection(adapter, change):
    def callback(tx):
        if change.startswith("agent_"):
            variable, value = adapter.agent, None if change == "agent_to_owner" else "AGENT_B"
        else:
            config = adapter.config.get()
            database = SimpleNamespace(**vars(config.database))
            mode = config.agent.mode
            if change == "mode":
                mode = "standalone"
            elif change == "owner":
                database.user = "OWNER_B"
            else:
                database.dbname = "DB_B"
            variable, value = adapter.config, SimpleNamespace(database=database, agent=SimpleNamespace(mode=mode))
        token = variable.set(value)
        try:
            assert adapter.api.execute_query_one("SELECT PROBE_VALUE")["probe_value"] != tx.conn.number
        finally:
            variable.reset(token)
        assert adapter.api.execute_query_one("SELECT PROBE_VALUE")["probe_value"] == tx.conn.number
        assert (tx.conn.commits, tx.conn.rollbacks) == (0, 0)
    token = adapter.agent.set("AGENT_A" if change.startswith("agent_") else None)
    try:
        adapter.api.execute_transaction_callback(callback)
    finally:
        adapter.agent.reset(token)
    assert adapter.connections[0].commits == 1


@pytest.mark.parametrize("field", ["agent_id", "username", "dsn", "host", "port", "dbname"])
def test_agent_credential_identity_change_uses_independent_connection(adapter, field):
    config = adapter.config.get()
    configured = adapter.config.set(SimpleNamespace(database=config.database, agent=SimpleNamespace(mode="agent")))
    credentials = adapter.credentials.set({"agent_id": "AGENT_A", "username": "AGENT_A_LOGIN", "dsn": "HOST_A:1/DB_A",
                                           "host": "HOST_A", "port": 1, "dbname": "DB_A"})
    def callback(tx):
        changed = adapter.credentials.set({**adapter.credentials.get(), field: "DIFFERENT"})
        try:
            assert adapter.api.execute_query_one("SELECT PROBE_VALUE")["probe_value"] != tx.conn.number
        finally:
            adapter.credentials.reset(changed)
        assert adapter.api.execute_query_one("SELECT PROBE_VALUE")["probe_value"] == tx.conn.number
        assert (tx.conn.commits, tx.conn.rollbacks) == (0, 0)
    try:
        adapter.api.execute_transaction_callback(callback)
    finally:
        adapter.credentials.reset(credentials)
        adapter.config.reset(configured)


def test_failed_callback_restores_scope_and_rolls_back_only_outer_transaction(adapter):
    copied = []
    def callback(tx):
        copied.append(copy_context())
        assert adapter.api.execute_query_one("SELECT PROBE_VALUE")["probe_value"] == tx.conn.number
        raise ExpectedFailure("synthetic callback failure")
    with pytest.raises(ExpectedFailure):
        adapter.api.execute_transaction_callback(callback)
    outer = adapter.connections[0]
    assert (outer.commits, outer.rollbacks) == (0, 1)
    assert all(cursor.closed for cursor in outer.cursors)
    assert copied[0].run(adapter.api.execute_query_one, "SELECT PROBE_VALUE")["probe_value"] != outer.number
    assert adapter.api.execute_query_one("SELECT PROBE_VALUE")["probe_value"] != outer.number


def test_identity_binding_failure_closes_cursor_and_rolls_back(adapter, monkeypatch):
    monkeypatch.setattr(adapter.reads, "_identity", lambda: (_ for _ in ()).throw(ExpectedFailure("identity unavailable")))
    # Connection acquisition does not depend on the binding callback.
    with pytest.raises(ExpectedFailure):
        adapter.api.execute_transaction_callback(lambda tx: pytest.fail("must not start callback"))
    assert len(adapter.connections) == 1
    assert (adapter.connections[0].commits, adapter.connections[0].rollbacks) == (0, 1)
    assert all(cursor.closed for cursor in adapter.connections[0].cursors)


def test_nested_scope_and_writer_keep_independent_transaction_boundaries(adapter):
    def callback(tx):
        def inner(inner_tx):
            assert inner_tx.conn is not tx.conn
            assert adapter.api.execute_query_one("SELECT PROBE_VALUE")["probe_value"] == inner_tx.conn.number
            raise ExpectedFailure("nested callback failure")
        with pytest.raises(ExpectedFailure):
            adapter.api.execute_transaction_callback(inner)
        assert adapter.api.execute_query_one("SELECT PROBE_VALUE")["probe_value"] == tx.conn.number
        adapter.api.execute("UPDATE SYNTHETIC SET VALUE=1")
        assert (tx.conn.commits, tx.conn.rollbacks) == (0, 0)
    adapter.api.execute_transaction_callback(callback)
    assert [(conn.commits, conn.rollbacks) for conn in adapter.connections] == [(1, 0), (0, 1), (1, 0)]


def test_copied_thread_context_never_shares_connection(adapter):
    def callback(tx):
        copied = copy_context()
        with ThreadPoolExecutor(max_workers=1) as executor:
            row = executor.submit(copied.run, adapter.api.execute_query_one, "SELECT PROBE_VALUE").result(timeout=5)
        assert row["probe_value"] != tx.conn.number
        assert adapter.api.execute_query_one("SELECT PROBE_VALUE")["probe_value"] == tx.conn.number
    adapter.api.execute_transaction_callback(callback)


def test_async_child_task_never_shares_synchronous_transaction_connection(adapter):
    async def run():
        def callback(tx):
            async def child():
                return adapter.api.execute_query_one("SELECT PROBE_VALUE")
            return tx.conn.number, asyncio.create_task(child())
        # Child tasks execute only after the synchronous callback has released
        # its connection; inherited inactive bindings must stay unusable.
        outer_number, task = adapter.api.execute_transaction_callback(callback)
        assert (await task)["probe_value"] != outer_number
        with adapter.connection() as connection:
            with adapter.reads.bind(connection):
                # Also exercise an active copied binding in a different task.
                assert adapter.api.execute_query_one("SELECT PROBE_VALUE")["probe_value"] == connection.number
                child = asyncio.create_task(async_read())
                assert (await child)["probe_value"] != connection.number
    async def async_read():
        return adapter.api.execute_query_one("SELECT PROBE_VALUE")
    asyncio.run(run())
