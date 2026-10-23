"""Offline tests of real adapter source; no native drivers/network/DDL execution."""
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import sys
import threading
import types

import pytest

from lib import native_identity
from lib.package_layout import adapter_file, databases

ROOT = Path(__file__).resolve().parents[2]
BACKENDS = databases(ROOT)


class SQL:
    def __init__(self, text):
        self.text = text

    def format(self, *items):
        return SQL(self.text.format(*(str(item) for item in items)))

    def __str__(self):
        return self.text


def _module(monkeypatch, name, **items):
    module = types.ModuleType(name)
    module.__dict__.update(items)
    monkeypatch.setitem(sys.modules, name, module)
    return module


def _load(monkeypatch, backend, kind):
    name = 'native_revoke_test_' + backend
    package = _module(monkeypatch, name, __path__=[])
    cfg = types.SimpleNamespace(
        agent=types.SimpleNamespace(mode='standalone'),
        database=types.SimpleNamespace(user='fixture_owner', dbname='fixture_database',
                                       host='fixture.invalid', port=5433, dsn='fixture.invalid/fixture_database'))
    _module(monkeypatch, name + '.config', get_config=lambda: cfg,
            DatabaseConfig=type('DatabaseConfig', (), {}), AgentModeConfig=type('AgentModeConfig', (), {}))
    if backend == 'oracle':
        _module(monkeypatch, 'oracledb', defaults=types.SimpleNamespace(fetch_lobs=True),
                Connection=type('Connection', (), {}), ConnectionPool=type('ConnectionPool', (), {}), Error=Exception)
    elif backend == 'yashandb':
        _module(monkeypatch, 'yaspy', Connection=type('Connection', (), {}))
    else:
        pool = _module(monkeypatch, 'psycopg2.pool', ThreadedConnectionPool=type('Pool', (), {}))
        _module(monkeypatch, 'psycopg2.extras', RealDictCursor=type('Cursor', (), {}))
        _module(monkeypatch, 'psycopg2', pool=pool,
                errors=types.SimpleNamespace(InsufficientPrivilege=type('InsufficientPrivilege', (Exception,), {})),
                sql=types.SimpleNamespace(SQL=SQL, Identifier=lambda value: SQL('"' + value.replace('"', '""') + '"')))
    if kind == 'agent_api':
        names = ('execute', 'execute_query', 'execute_query_one', 'execute_insert_returning_id',
                 'sanitize_row', 'get_connection', 'execute_plsql')
        connection = _module(monkeypatch, name + '.connection', **{key: lambda *a, **k: None for key in names})
        connection.get_current_agent_id = lambda: None
        connection.evictions = []
        connection.evict_agent_connections = lambda agent_id, **kw: (
            connection.evictions.append((agent_id, kw)) or {'closed': 2, 'failed': 0})
        package.connection = connection
        for extra in ('agent_extension_schema', 'agent_integration_bindings'):
            _module(monkeypatch, name + '.' + extra, TABLES=())
    module = _module(monkeypatch, name + '.' + kind, __package__=name)
    path = adapter_file(ROOT, backend, kind + '.py')
    module.__file__ = str(path)
    exec(compile(path.read_bytes(), str(path), 'exec'), module.__dict__)
    setattr(package, kind, module)
    module.test_config = cfg
    return module, package


class NativeFixture:
    """Synthetic catalog/DDL emulator; never opens a database connection."""
    def __init__(self, module, backend):
        self.module, self.backend = module, backend
        self.agent_id = 'AGENT_native_fixture'
        self.username = (module._agent_role_name(self.agent_id, 'fixture_database') if backend == 'pg'
                         else module._database_user_name(self.agent_id))
        self.principal = ('DISABLED', 2, 'ACTIVE', 'WORKER')
        self.count = 1
        self.mapping = self.username
        self.locked = False
        self.exists = True
        self.privileged = False
        self.fail_ddl = False
        self.fail_catalog = False
        self.statements = []
        self.commits = self.rollbacks = 0
        self.rows = []

    @contextmanager
    def connection(self):
        yield self

    def cursor(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, statement, params=None):
        text = str(statement)
        self.statements.append((text, params))
        upper = text.upper()
        if upper.startswith('ALTER '):
            if self.fail_ddl:
                raise RuntimeError('ORA-01031 private synthetic credential payload')
            self.locked = True
            self.rows = []
        elif 'SESSION_USER' in upper:
            self.rows = [('fixture_owner', 'fixture_database')]
        elif 'P.PERMISSION_VERSION' in upper:
            self.rows = [self.principal] if self.principal else []
        elif 'COUNT(*)' in upper:
            self.rows = [(self.count,)]
        elif 'SELECT ROLE_NAME' in upper or 'SELECT DB_USERNAME' in upper:
            self.rows = [(self.mapping,)] if self.mapping else []
        elif 'FROM PG_ROLES' in upper or 'ACCOUNT_STATUS' in upper:
            if self.fail_catalog:
                raise RuntimeError('ORA-01031 private synthetic credential payload')
            self.rows = ([(not self.locked, self.privileged, False, False, False)] if self.backend == 'pg'
                         else [('LOCKED' if self.locked else 'OPEN',)]) if self.exists else []
        elif 'FOR UPDATE' in upper:
            self.rows = [(self.agent_id,)]
        else:
            raise AssertionError('Unexpected synthetic query: ' + text)

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return list(self.rows)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


@pytest.fixture(params=BACKENDS)
def native(request, monkeypatch):
    module, package = _load(monkeypatch, request.param, 'agent_api')
    fixture = NativeFixture(module, request.param)
    module.get_connection = fixture.connection
    return module, package, fixture


def test_snapshot_is_exact_readonly_and_contains_no_credential(native):
    module, _, fixture = native
    value = module.native_identity_snapshot(fixture.agent_id)
    assert value['schema'] == 'native-agent-identity/v1'
    assert value['mapping_state'] == value['native_state'] == 'OBSERVED'
    assert value['username'] == fixture.username and value['login_enabled'] is True
    assert len(value['database_fingerprint']) == len(value['snapshot_digest']) == 64
    assert all(text.startswith('SELECT ') for text, _ in fixture.statements)
    assert all('SYSTEM_CONFIG' not in text.upper() and 'PG_AUTHID' not in text.upper() for text, _ in fixture.statements)
    if fixture.backend != 'pg':
        account_queries = [text for text, _ in fixture.statements if 'SELECT ACCOUNT_STATUS' in text]
        assert account_queries == ['SELECT ACCOUNT_STATUS FROM SYS.CX_AGENT_ACCOUNT_STATUS WHERE USERNAME=:native_name']
        assert not any('FROM DBA_USERS' in text or 'FROM DBA_END_USERS' in text for text, _ in fixture.statements)
    assert 'password' not in json.dumps(value).lower()
    assert fixture.commits == 0


def test_pending_snapshot_observed_but_revoke_refused(native):
    module, package, fixture = native
    fixture.principal = ('PENDING', 2, 'ACTIVE', 'WORKER')
    assert module.native_identity_snapshot(fixture.agent_id)['native_state'] == 'OBSERVED'
    result = module.revoke_native_identity(fixture.agent_id, reason='synthetic test')
    assert result['status'] == 'PENDING' and result['error_code'] == 'PRINCIPAL_NOT_DISABLED'
    assert package.connection.evictions == [] and not fixture.locked


@pytest.mark.parametrize('case', ['legacy', 'system', 'collision', 'catalog_unavailable', 'active'])
def test_revoke_fails_closed_without_native_ddl(native, case):
    module, package, fixture = native
    if case == 'legacy': fixture.principal = None
    elif case == 'system': fixture.principal = ('DISABLED', 2, 'ACTIVE', 'SYSTEM')
    elif case == 'collision': fixture.count = 2
    elif case == 'catalog_unavailable': fixture.fail_catalog = True
    elif case == 'active': fixture.principal = ('ACTIVE', 2, 'ACTIVE', 'WORKER')
    result = module.revoke_native_identity(fixture.agent_id, reason='synthetic test')
    assert result['status'] == 'PENDING'
    assert not any(text.startswith('ALTER ') for text, _ in fixture.statements)
    assert not package.connection.evictions
    assert 'private synthetic' not in json.dumps(result)


def test_exact_revoke_keeps_shared_roles_and_reports_session_unknown(native):
    module, package, fixture = native
    value = module.native_identity_snapshot(fixture.agent_id)
    result = module.revoke_native_identity(fixture.agent_id, snapshot=value, reason='synthetic test')
    assert result['status'] == 'COMPLETE' and result['new_connections_blocked'] is True
    assert result['existing_sessions_closed'] is result['business_access_blocked'] is None
    assert result['local_connections_closed'] == 2
    assert package.connection.evictions == [(fixture.agent_id, {'revoke': True})]
    ddl = [text for text, _ in fixture.statements if text.startswith('ALTER ')]
    expected = {'oracle': f'ALTER END USER "{fixture.username}" ACCOUNT LOCK',
                'pg': f'ALTER ROLE "{fixture.username}" NOLOGIN',
                'yashandb': f'ALTER USER "{fixture.username}" ACCOUNT LOCK CONTAINER=CURRENT'}
    assert ddl == [expected[fixture.backend]]
    assert not any('DROP ' in text or 'GRANT ' in text or 'PASSWORD' in text for text, _ in fixture.statements)
    again = module.revoke_native_identity(fixture.agent_id, reason='idempotent synthetic retry')
    assert again['status'] == 'COMPLETE'
    assert len([text for text, _ in fixture.statements if text.startswith('ALTER ')]) == 1


def test_stale_snapshot_never_changes_a_native_identity(native):
    module, package, fixture = native
    old = module.native_identity_snapshot(fixture.agent_id)
    fixture.principal = ('DISABLED', 3, 'ACTIVE', 'WORKER')
    result = module.revoke_native_identity(fixture.agent_id, snapshot=old, reason='synthetic stale version')
    assert result['error_code'] == 'NATIVE_SNAPSHOT_CHANGED'
    assert not fixture.locked and not package.connection.evictions


def test_snapshot_from_another_database_is_rejected(native):
    module, package, fixture = native
    old = module.native_identity_snapshot(fixture.agent_id)
    old['database_fingerprint'] = 'f' * 64
    result = module.revoke_native_identity(fixture.agent_id, snapshot=old, reason='synthetic wrong target')
    assert result['error_code'] == 'NATIVE_SNAPSHOT_CHANGED'
    assert not fixture.locked and not package.connection.evictions


def test_native_management_never_runs_under_agent_or_wrong_owner_context(native):
    module, package, fixture = native
    package.connection.get_current_agent_id = lambda: fixture.agent_id
    assert module.native_identity_snapshot(fixture.agent_id)['native_state'] == 'UNAVAILABLE'
    assert not fixture.statements
    package.connection.get_current_agent_id = lambda: None
    module.test_config.database.user = 'another_owner'
    result = module.revoke_native_identity(fixture.agent_id, reason='synthetic wrong owner')
    assert result['status'] == 'PENDING' and not fixture.locked


def test_state_change_before_native_step_does_not_evict_or_lock(native, monkeypatch):
    module, package, fixture = native
    snapshot = module.native_identity_snapshot
    calls = []
    def changing(*args, **kwargs):
        calls.append(True)
        if len(calls) == 2:
            fixture.principal = ('ACTIVE', 3, 'ACTIVE', 'WORKER')
        return snapshot(*args, **kwargs)
    monkeypatch.setattr(module, 'native_identity_snapshot', changing)
    result = module.revoke_native_identity(fixture.agent_id, reason='synthetic concurrent reactivation')
    assert result['status'] == 'PARTIAL'
    assert not package.connection.evictions and not fixture.locked


def test_successful_lock_with_unavailable_verification_stays_partial(native, monkeypatch):
    module, _, fixture = native
    execute = fixture.execute
    def lose_verification(statement, params=None):
        execute(statement, params)
        if str(statement).startswith('ALTER '): fixture.fail_catalog = True
    monkeypatch.setattr(fixture, 'execute', lose_verification)
    result = module.revoke_native_identity(fixture.agent_id, reason='synthetic post-check failure')
    assert fixture.locked and result['status'] == 'PARTIAL'
    assert result['new_connections_blocked'] is None


def test_local_close_failure_is_partial_even_when_new_login_disabled(native):
    module, package, fixture = native
    package.connection.evict_agent_connections = lambda *args, **kwargs: {'closed': 1, 'failed': 1}
    result = module.revoke_native_identity(fixture.agent_id, reason='synthetic close failure')
    assert result['new_connections_blocked'] is True and result['status'] == 'PARTIAL'
    assert result['local_connection_close_failures'] == 1


def test_permission_failure_is_partial_and_redacted(native):
    module, _, fixture = native
    fixture.fail_ddl = True
    result = module.revoke_native_identity(fixture.agent_id, reason='synthetic denial')
    assert result['status'] == 'PARTIAL' and result['error_code'] == 'ORA-01031'
    assert result['new_connections_blocked'] is None
    assert 'private synthetic' not in json.dumps(result)
    assert result['existing_sessions_closed'] is None
    if fixture.backend == 'pg': assert fixture.rollbacks == 1


class LocalConnection:
    def __init__(self, fail=False):
        self.closed = False
        self.fail = fail

    def close(self):
        if self.fail: raise RuntimeError('synthetic close failure')
        self.closed = True

    def rollback(self): pass
    def cursor(self): return self
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def execute(self, *args, **kwargs): pass


@pytest.mark.parametrize('backend', BACKENDS)
def test_evict_only_one_agent_and_reports_failed_close(backend, monkeypatch):
    module, _ = _load(monkeypatch, backend, 'connection')
    target, failed, other = LocalConnection(), LocalConnection(fail=True), LocalConnection()
    module._end_user_connections.update({(1, 'agent-a'): target, (2, 'agent-a'): failed, (1, 'agent-b'): other})
    assert module.evict_agent_connections('agent-a', revoke=True) == {'closed': 1, 'failed': 1}
    assert target.closed and not other.closed
    assert module._end_user_connections[(1, 'agent-b')] is other
    assert [conn for key, conn in module._end_user_connections.items() if key[1] == 'agent-a'] == [failed]
    assert 'agent-a' in module._revoked_end_users
    failed.fail = False
    assert module.evict_agent_connections('agent-a', revoke=True) == {'closed': 1, 'failed': 0}
    assert list(module._end_user_connections) == [(1, 'agent-b')]


@pytest.mark.parametrize('backend', BACKENDS)
@pytest.mark.parametrize('mode', ['agent', 'standalone'])
def test_inflight_connect_cannot_repopulate_revoked_agent_cache(backend, mode, monkeypatch):
    module, _ = _load(monkeypatch, backend, 'connection')
    entered, release = threading.Event(), threading.Event()
    conn = LocalConnection()
    def connect(*args, **kwargs):
        entered.set()
        assert release.wait(3), 'Synthetic connector was not released'
        return conn
    module.test_config.agent.mode = mode
    module._get_end_user_password = lambda *args: 'synthetic-not-a-credential'
    module._load_agent_eu_creds = lambda: {'agent_id': 'agent-a', 'username': 'synthetic_agent',
                                          'password': 'synthetic-not-a-credential', 'dsn': 'fixture.invalid'}
    if backend == 'pg':
        module._connect_with_credentials = connect
    elif backend == 'oracle': module.oracledb.connect = connect
    else: module.yaspy.Connection = connect
    outcome = []
    def worker():
        try:
            if backend == 'pg':
                with module._independent_agent_connection({}, 'agent-a'):
                    outcome.append('YIELDED')
            else:
                outcome.append(module.get_end_user_connection('agent-a'))
        except RuntimeError:
            outcome.append('REFUSED')
    thread = threading.Thread(target=worker)
    thread.start()
    try:
        assert entered.wait(3)
        module.evict_agent_connections('agent-a', revoke=True)
    finally:
        release.set()
        thread.join(3)
    assert not thread.is_alive() and conn.closed
    assert module._end_user_connections == {}
    assert outcome == (['REFUSED'] if backend == 'pg' else [None])


def test_error_codes_never_retain_native_message():
    error = RuntimeError('private synthetic credential message')
    error.pgcode = '42501'
    assert native_identity.failure_code(error) == 'SQLSTATE_42501'
    assert native_identity.failure_code(RuntimeError('private synthetic credential')) == 'NATIVE_IDENTITY_UNAVAILABLE'


class OffboardTransaction:
    def __init__(self):
        self.executed = []
        self.role = 'WORKER'

    def query_one(self, statement, params):
        return {'agent_role': self.role} if 'AGENT_REGISTRY' in statement else {'principal_id': 'agent-a', 'status': 'ACTIVE'}

    def execute(self, statement, params):
        self.executed.append((statement, params))
        return 1


def _offboard(monkeypatch, *, native_failure=False, audit_failure=False):
    from lib import identity_api, agent_api
    tx = OffboardTransaction()
    commits, native_calls = [], []
    monkeypatch.setattr(identity_api, '_require', lambda *args: None)
    monkeypatch.setattr(identity_api, '_agent_visible_to', lambda *args: True)
    monkeypatch.setattr(identity_api, '_dialect', lambda: 'pg')
    def transaction(work):
        if audit_failure and commits:
            raise RuntimeError('synthetic final audit failure')
        result = work(tx)
        commits.append(True)
        return result
    monkeypatch.setattr(identity_api.connection, 'execute_transaction_callback', transaction)
    def revoke(agent_id, **kwargs):
        assert commits == [True], 'Native mutation must follow the committed normal disable'
        assert any(params.get('action_name') == 'AGENT_NATIVE_REVOKE_PENDING' for _, params in tx.executed)
        native_calls.append(agent_id)
        if native_failure: raise RuntimeError('ORA-01031 private synthetic credential')
        return {'status': 'COMPLETE', 'new_connections_blocked': True, 'existing_sessions_closed': None}
    monkeypatch.setattr(agent_api, 'revoke_native_identity', revoke, raising=False)
    return identity_api, tx, commits, native_calls


def test_normal_offboard_commits_pending_then_revokes_and_audits(monkeypatch):
    api, tx, commits, calls = _offboard(monkeypatch)
    result = api.offboard_agent('human-a', 'agent-a', reason='synthetic offboard')
    assert calls == ['agent-a'] and len(commits) == 2
    assert result['native_identity_revocation']['status'] == 'COMPLETE'
    assert result['native_identity_revocation']['audit_status'] == 'RECORDED'
    assert any('PERMISSION_VERSION=PERMISSION_VERSION+1' in sql for sql, _ in tx.executed)
    history = [params for sql, params in tx.executed if 'CX_AGENT_OWNERSHIP_HISTORY' in sql]
    assert history[0]['credential_rotated'] is False


@pytest.mark.parametrize('case', ['native_failure', 'audit_failure'])
def test_normal_offboard_never_reports_full_native_success_on_failure(monkeypatch, case):
    api, _, _, _ = _offboard(monkeypatch, **{case: True})
    result = api.offboard_agent('human-a', 'agent-a', reason='synthetic offboard')
    assert result['native_identity_revocation']['status'] == 'PARTIAL'
    assert 'private synthetic' not in json.dumps(result)


def test_system_managed_disposition_retains_native_identity(monkeypatch):
    api, _, _, calls = _offboard(monkeypatch)
    result = api.offboard_agent('human-a', 'agent-a', owner_type='SYSTEM_MANAGED', reason='synthetic retention')
    assert result['status'] == 'ACTIVE'
    assert result['native_identity_revocation']['status'] == 'SKIPPED' and calls == []


def test_system_registry_and_system_ids_cannot_be_offboarded(monkeypatch):
    api, tx, commits, calls = _offboard(monkeypatch)
    with pytest.raises(api.IdentityError, match='System Agents'):
        api.offboard_agent('human-a', 'SYSTEM_PLATFORM_ADMIN_AGENT', reason='synthetic rejection')
    assert not commits and not tx.executed
    tx.role = 'SYSTEM'
    with pytest.raises(api.IdentityError, match='System Agents'):
        api.offboard_agent('human-a', 'agent-a', reason='synthetic rejection')
    assert not tx.executed and not calls
