"""Offline regression for immutable attempt deadlines and native lease clocks.

SQLite triggers model the historical immutable-column boundary. Session-clock
projection uses a real timezone conversion, with no native DB or Provider I/O.
"""
import ast
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3
from zoneinfo import ZoneInfo

import pytest

from lib import connection, edition_features, native_agent_api, task_continuity
from lib.continuity_state import ContinuityError
from .test_v502_native_dispatch import enqueue_channel, enqueue_native, execution, ingress, ledger, worker


def protect_attempt_deadline(db):
    db.executescript("""
        CREATE TRIGGER immutable_task_deadline
        BEFORE UPDATE OF LEASE_EXPIRES_AT ON CX_TASK_CONTINUITY_ATTEMPTS
        BEGIN SELECT RAISE(ABORT, 'Task continuity identity and history are immutable'); END;
    """)
    db.commit()


@pytest.mark.parametrize('channel', [False, True])
@pytest.mark.parametrize('session_zone', ['UTC', 'America/New_York', 'Asia/Shanghai'])
def test_native_claim_inserts_exact_utc_deadline_under_immutable_history(worker, monkeypatch, channel, session_zone):
    db = worker.db
    protect_attempt_deadline(db)
    now = datetime(2026, 10, 29, 8, 30, 0, 123456)
    deadline = now + timedelta(minutes=5)
    zone = ZoneInfo(session_zone)
    local_deadline = deadline.replace(tzinfo=timezone.utc).astimezone(zone).replace(tzinfo=None)
    monkeypatch.setattr(task_continuity, '_now', lambda: now)
    monkeypatch.setattr(native_agent_api, '_lease_deadline_sql', lambda: "'" + local_deadline.isoformat(sep=' ') + "'")
    projected = []
    def project(value):
        projected.append(value)
        return datetime.fromisoformat(value).replace(tzinfo=zone).astimezone(timezone.utc).replace(tzinfo=None).isoformat(sep=' ')
    db.create_function('session_deadline_utc', 1, project)
    monkeypatch.setattr(connection, 'session_timestamp_utc_expression', lambda expression: 'session_deadline_utc(' + expression + ')')
    key = enqueue_channel(worker) if channel else enqueue_native(worker)
    claimed = native_agent_api.claim_runtime('worker', 'node', 1)
    assert len(claimed) == 1 and claimed[0]['execution_id'] == key
    assert execution(worker, key)['status'] == 'CLAIMED'
    assert projected == [local_deadline.isoformat(sep=' ')]
    assert task_continuity._utc_naive(claimed[0]['lease_expires_at_utc']) == deadline
    attempt = db.execute('SELECT * FROM CX_TASK_CONTINUITY_ATTEMPTS').fetchone()
    lease = db.execute('SELECT * FROM CX_TASK_CONTINUITY_LEASES').fetchone()
    assert task_continuity._utc_naive(attempt['lease_expires_at']) == deadline
    assert task_continuity._utc_naive(lease['lease_expires_at']) == deadline
    assert attempt['status'] == 'SENDING' and lease['status'] == 'ACTIVE'
    mapping = db.execute('SELECT * FROM CX_PROCESSING_NATIVE_ATTEMPTS').fetchone()
    assert mapping['task_attempt_id'] == attempt['attempt_id']
    assert mapping['native_fencing_token'] == claimed[0]['fencing_token']
    assert not worker.sends
    # An idempotent claim keeps the original deadline even if its caller now
    # offers a later deadline. No immutable history rewrite is permitted.
    replay = connection.execute_transaction_callback(lambda tx: task_continuity.claim_attempt(
        tx, continuity_id=attempt['continuity_id'], worker_id='worker', business_key=key,
        request_digest=attempt['request_digest'], lease_expires_at=now + timedelta(minutes=10)))
    assert replay['replayed'] is True and replay['attempt_id'] == attempt['attempt_id']
    assert task_continuity._utc_naive(replay['lease_expires_at']) == deadline
    with pytest.raises(sqlite3.IntegrityError, match='immutable'):
        db.execute('UPDATE CX_TASK_CONTINUITY_ATTEMPTS SET LEASE_EXPIRES_AT=LEASE_EXPIRES_AT')
    db.rollback()
    assert len(db.execute('SELECT * FROM CX_TASK_CONTINUITY_ATTEMPTS').fetchall()) == 1
    assert not worker.sends


@pytest.mark.parametrize('aware', [False, True])
def test_explicit_task_deadline_is_frozen_at_initial_insert(worker, monkeypatch, aware):
    now = datetime(2026, 10, 29, 8, 30, 0, 100001)
    expected = now + timedelta(seconds=299, microseconds=499999)
    offered = expected.replace(tzinfo=timezone.utc).astimezone(ZoneInfo('America/New_York')) if aware else expected
    monkeypatch.setattr(task_continuity, '_now', lambda: now)
    protect_attempt_deadline(worker.db)
    key = enqueue_native(worker)
    link = worker.db.execute('SELECT * FROM CX_TASK_CONTINUITY_LINKS WHERE LINK_ID=?', (key,)).fetchone()
    attempt = connection.execute_transaction_callback(lambda tx: task_continuity.claim_attempt(
        tx, continuity_id=link['continuity_id'], worker_id='worker', business_key=key,
        request_digest=link['request_digest'], lease_expires_at=offered))
    assert attempt['lease_expires_at'] == expected
    stored = worker.db.execute('SELECT LEASE_EXPIRES_AT FROM CX_TASK_CONTINUITY_ATTEMPTS').fetchone()
    assert task_continuity._utc_naive(stored['lease_expires_at']) == expected
    assert not worker.sends


@pytest.mark.parametrize('offset', [0, -1, 3600.000001])
def test_absolute_task_deadline_rejects_expired_or_unbounded_values_before_writes(monkeypatch, offset):
    now = datetime(2026, 10, 29, 8, 30)
    monkeypatch.setattr(task_continuity, '_now', lambda: now)
    monkeypatch.setattr(edition_features, 'MODEL_RUNTIME_CONTEXT_ENABLED', False, raising=False)
    with pytest.raises(ContinuityError, match='within one hour'):
        task_continuity.claim_attempt(object(), continuity_id='chain', worker_id='worker', business_key='key',
            request_digest='a' * 64, lease_expires_at=now + timedelta(seconds=offset))


@pytest.mark.parametrize('deadline', ['2026-10-29T08:35:00Z', 1793262900, True])
def test_absolute_task_deadline_requires_a_datetime_before_writes(monkeypatch, deadline):
    monkeypatch.setattr(edition_features, 'MODEL_RUNTIME_CONTEXT_ENABLED', False, raising=False)
    with pytest.raises(ContinuityError, match='absolute datetime'):
        task_continuity.claim_attempt(object(), continuity_id='chain', worker_id='worker', business_key='key',
            request_digest='a' * 64, lease_expires_at=deadline)


def test_relative_task_deadline_keeps_existing_bound(worker, monkeypatch):
    now = datetime(2026, 10, 29, 8, 30)
    monkeypatch.setattr(task_continuity, '_now', lambda: now)
    key = enqueue_native(worker)
    link = worker.db.execute('SELECT * FROM CX_TASK_CONTINUITY_LINKS WHERE LINK_ID=?', (key,)).fetchone()
    result = connection.execute_transaction_callback(lambda tx: task_continuity.claim_attempt(
        tx, continuity_id=link['continuity_id'], worker_id='worker', business_key=key,
        request_digest=link['request_digest'], lease_seconds=9000))
    assert result['lease_expires_at'] == now + timedelta(hours=1)
    assert not worker.sends


@pytest.mark.parametrize('backend', ['pg', 'oracle', 'yashandb'])
def test_native_deadline_projection_is_owned_by_selected_adapter_without_driver_import(backend):
    # Load just this pure SQL primitive from actual source; importing a native
    # adapter would activate a driver and configuration in an offline test.
    root = Path(__file__).resolve().parents[2]
    path = root / 'adapters' / backend / 'connection.py'
    if not path.is_file():
        package = root / 'scripts'
        path = package / 'database_adapters' / backend / 'connection.py'
        if not path.is_file():
            path = package / 'lib' / 'connection.py'
            tree = ast.parse(path.read_text())
            dialect = next((ast.literal_eval(node.value) for node in tree.body if isinstance(node, ast.Assign)
                and any(isinstance(target, ast.Name) and target.id == 'DATABASE_DIALECT' for target in node.targets)), None)
            if dialect not in {backend, 'postgresql' if backend == 'pg' else backend}:
                pytest.skip('This product does not ship the selected adapter')
    tree = ast.parse(path.read_text())
    node = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'session_timestamp_utc_expression')
    namespace = {}
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), 'exec'), namespace)
    expression = namespace[node.name]('e.LEASE_EXPIRES_AT')
    assert 'e.LEASE_EXPIRES_AT' in expression
    if backend == 'pg':
        assert "current_setting('TimeZone')" in expression and expression.endswith("AT TIME ZONE 'UTC'")
    else:
        assert 'SESSIONTIMEZONE' in expression and expression.startswith('SYS_EXTRACT_UTC(FROM_TZ(')
