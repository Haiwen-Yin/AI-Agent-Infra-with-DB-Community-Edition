"""Origin diagnostics use current typed source reads, never recovery authority."""
from contextlib import nullcontext
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from lib import connection, continuity_execution_links, continuity_retrospectives as retros
from lib import edition_features, governed_model_turns as turns, native_runtime
from lib import model_coordinator_http, model_coordinator_origin as origin
from lib import processing_recovery as recovery, processing_runtime as adapter
from lib import answer_quality as quality


@pytest.fixture
def native_read(monkeypatch):
    state = SimpleNamespace(allowed=True, reads=[], observations=0)
    state.receipt = dict(origin_receipt_id='MOR_original', actor_id='reader', source_kind='NATIVE',
        source_id='EXE_original', source_attempt_id='NMA_original', worker_key='completed-worker',
        origin_fencing_token=7, status='COMPLETED', version=2, profile_id='original-profile',
        profile_version=1, coordinator_request_id='MCR_original', admission_id='MAD_original',
        remote_fencing_token=1, finish_code='COMPLETED')
    mapped = dict(source_kind='NATIVE', worker_id='completed-worker', native_fencing_token=7,
        continuity_id='TC_original', task_attempt_id='TA_original')

    class Transaction:
        def query_one(self, sql, params):
            if 'CX_PROCESSING_NATIVE_CALLS' in sql:
                if params == {'attempt': 'NMA_original', 'execution': 'EXE_original'}:
                    return mapped
                return None
            if 'CX_MODEL_ORIGIN_OBSERVATIONS' in sql:
                state.observations += 1
                return dict(total_tokens=12)
            raise AssertionError('Unexpected query')

    state.tx = Transaction()
    monkeypatch.setattr(connection, 'execute_transaction_callback', lambda callback: callback(state.tx))
    monkeypatch.setattr(origin.work, '_lock_actor', lambda *args: None)
    monkeypatch.setattr(origin, '_receipt', lambda *args: dict(state.receipt))
    monkeypatch.setattr(origin, 'resolution_for_receipt', lambda *args: None)
    monkeypatch.setattr(recovery, '_link', lambda *args: dict(actor_id='reader'))

    def read_execution(actor, execution, *, transaction):
        assert transaction is state.tx
        state.reads.append((actor, execution))
        if not state.allowed:
            raise PermissionError('Execution is unavailable')
        return dict(status='COMPLETED')

    monkeypatch.setattr(native_runtime, 'get_execution', read_execution)
    return state


@pytest.mark.parametrize('status', ['COMPLETED', 'UNKNOWN', 'DISPATCHING', 'KNOWN_NO_SEND'])
def test_native_receipt_read_uses_current_source_without_a_dispatch_lease(native_read, status):
    native_read.receipt['status'] = status
    result = origin.read_receipt('reader', 'MOR_original')
    assert result['observation']['total_tokens'] == 12
    assert native_read.reads == [('reader', 'EXE_original')]


def test_revoked_native_source_is_denied_before_observations_are_loaded(native_read):
    native_read.allowed = False
    with pytest.raises(PermissionError):
        origin.read_receipt('reader', 'MOR_original')
    assert native_read.observations == 0


@pytest.mark.parametrize('field,value', [
    ('actor_id', 'another-reader'), ('source_kind', 'CHANNEL'),
    ('source_attempt_id', 'NMA_unrelated'), ('worker_key', 'another-worker'),
    ('origin_fencing_token', 8), ('source_id', 'EXE_unrelated'),
])
def test_receipt_cannot_substitute_another_original_event(native_read, field, value):
    native_read.receipt[field] = value
    with pytest.raises(PermissionError):
        origin.read_receipt('reader', 'MOR_original')
    assert not native_read.reads and native_read.observations == 0


@pytest.mark.parametrize('kind', ['PORTAL', 'GATEWAY', 'PROBE', 'EXTERNAL', 'UNKNOWN'])
def test_missing_durable_typed_source_adapter_fails_closed(native_read, kind):
    native_read.receipt.update(source_kind=kind, source_id='opaque-source')
    with pytest.raises(PermissionError):
        origin.read_receipt('reader', 'MOR_original')
    assert not native_read.reads and native_read.observations == 0


def test_http_read_denies_revocation_without_returning_protected_identifiers(native_read, monkeypatch):
    native_read.allowed = False
    monkeypatch.setattr(edition_features, 'MODEL_RUNTIME_CONTEXT_ENABLED', True)
    app = FastAPI()
    model_coordinator_http.install(app, schema_owner_context=nullcontext,
        require_action=lambda action: lambda: {'principal_id': 'reader'})
    with TestClient(app) as client:
        response = client.get('/api/model-gateway/origin-requests/MOR_original')
    assert response.status_code == 403
    assert response.json() == {'code': 'COORDINATOR_AUTHORIZATION_DENIED'}
    assert 'EXE_original' not in response.text and 'MAD_original' not in response.text
    assert native_read.observations == 0


@pytest.mark.parametrize('kind,source,link_kind', [
    ('RETROSPECTIVE', 'RJ_original', 'RUNTIME'),
    ('EVALUATION', 'AQR_original', 'DIAGNOSTIC'),
    ('NATIVE', 'MTU_original', 'RUNTIME'),
])
def test_terminal_task_sources_keep_current_read_checks_without_recovery_status(monkeypatch, kind, source, link_kind):
    state = SimpleNamespace(allowed=True, reads=[], domains=[])
    original = dict(continuity_id='TC_original', link_id=source + ':FINAL' if source.startswith('MTU_') else source,
        actor_id='reader', security_domain_id='DOMAIN_original', canonical_task_id='TASK_original', link_kind=link_kind)
    frozen = dict(continuity_id='TC_original', target_kind='RUNTIME', target_id=original['link_id'],
        target_revision='revision', input_digest='a' * 64, business_key='business-original')
    attempt = dict(attempt_id='TA_original', continuity_id='TC_original', fencing_token=3, status='SUCCEEDED')
    job = dict(created_by='reader', actor_id='reader', continuity_id='TC_original')

    class Transaction:
        def query_one(self, sql, params):
            if 'CX_TASK_CONTINUITY_ATTEMPTS' in sql:
                return attempt
            if 'CX_PROCESSING_TARGETS' in sql:
                return frozen
            if 'CX_RETROSPECTIVE_JOBS' in sql or 'CX_ANSWER_QUALITY_RUNS' in sql:
                return job
            raise AssertionError('Unexpected query')

    tx = Transaction()
    monkeypatch.setattr(recovery, '_link', lambda *args: original)
    monkeypatch.setattr(adapter, '_original', lambda *args: original)
    monkeypatch.setattr(adapter, '_same_job', lambda *args: None)
    monkeypatch.setattr(recovery, '_validate_target', lambda current, target: original)
    monkeypatch.setattr(origin.work, '_authorize', lambda current, actor, domain, *, write: state.domains.append((domain, write)))
    monkeypatch.setattr(continuity_execution_links, 'authorize', lambda *args: None)

    def current_source(*args):
        state.reads.append(kind)
        if not state.allowed:
            raise PermissionError('Source unavailable')

    monkeypatch.setattr(retros, '_refs', current_source)
    monkeypatch.setattr(quality, '_authority', lambda *args: None)
    monkeypatch.setattr(quality, '_sources', current_source)
    monkeypatch.setattr(turns, '_root', lambda *args, **kwargs: job)
    monkeypatch.setattr(turns, '_authorize_read', current_source)
    receipt = dict(source_kind=kind, source_id=source, source_attempt_id='TA_original', origin_fencing_token=3)
    origin.authorize_receipt_read(tx, 'reader', receipt)
    assert state.reads == [kind] and state.domains == [('DOMAIN_original', False)]
    state.allowed = False
    with pytest.raises(PermissionError):
        origin.authorize_receipt_read(tx, 'reader', receipt)
