"""Origin reconciliation with native rows and an entirely in-memory peer.

No HTTP client, socket, database driver, key store or model endpoint is used.
The real reconciliation, local receipt/route/Profile reads, closed contracts,
full-row comparison and resolution lookup run against a transactional ledger.
"""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import re
import socket
from types import SimpleNamespace

import pytest

from lib import connection, model_coordinator_origin as origin, model_dispatch
from lib.agent_extension_contracts import canonical
from lib.continuity_state import ContinuityConflict


BIG = 2**53 + 17
STAMP = datetime(2026, 10, 29, 3, 15, 0, 123456)


@pytest.fixture
def native_origin(monkeypatch):
    state = SimpleNamespace(
        receipt=dict(
            origin_receipt_id='receipt-original', route_id='route-original', route_version=1,
            actor_id='original-user', original_credential_digest='a'*64,
            source_kind='GATEWAY', source_id='source-original', source_attempt_id='source-original',
            worker_key='gateway:source-original', origin_fencing_token=1,
            origin_lease_until_ms=BIG + 1000, authority_digest='b'*64,
            profile_id='profile-original', profile_version=1, model_id='model-original',
            payload_digest='c'*64, idempotency_key='dispatch-original', envelope_digest='d'*64,
            coordinator_request_id='central-original', admission_id='admission-original',
            remote_fencing_token=3, remote_reservation_version=2,
            authorized_at_ms=BIG, proof_expires_at_ms=BIG + 100,
            proof_digest='e'*64, status='UNKNOWN', version=7,
            finish_code='CLIENT_CLOSED', created_at_ms=BIG,
        ),
        resolutions=[], audits=[], source_active=True, audit_failure=False,
        in_transaction=False, source_checks=0, peer_reads=0, after_peer=None,
    )
    gateway_credential = 'cxgw_offline_native_receipt_fixture'
    state.profile = dict(profile_id='profile-original', version=1, profile_key='original',
        provider_url='http://coordinator.invalid/api/model-gateway/coordinator/binding-original',
        model_id='model-original', api_key_cipher='offline-unused-cipher', status='ACTIVE')
    state.route = dict(route_id='route-original', version=1, profile_id='profile-original',
        profile_version=1, status='ACTIVE', credential_digest=origin.common.token_digest(gateway_credential),
        coordinator_url=state.profile['provider_url'])
    resolution = dict(coordinator_request_id='central-original', origin_receipt_id='receipt-original',
        envelope_digest='d'*64, admission_id='admission-original', admission_version=4,
        central_status='COMPLETED', admission_status='COMPLETED', attempt_id='attempt-original',
        fencing_token=3, resolution_kind='TRANSPORT_TERMINATED', evidence_id='evidence-original',
        evidence_kind='COMPLETE_RESPONSE', evidence_digest='f'*64, evidence_at_ms=BIG + 500,
        request_complete='Y')
    state.remote = dict(coordinator_request_id='central-original', origin_receipt_id='receipt-original',
        admission_id='admission-original', envelope_digest='d'*64, status='COMPLETED',
        admission_status='COMPLETED', transport_resolution=resolution)
    state.request = dict(expected_version=7, reason='Read exact original completed transport',
        idempotency_key='resolution-original')

    class Transaction:
        def query_one(self, sql, params):
            assert state.in_transaction
            if 'FROM CX_PRINCIPALS ' in sql:
                assert params == {'actor': 'original-user'}
                return {'status': 'ACTIVE'}
            if 'FROM CX_MODEL_ORIGIN_RECEIPTS ' in sql:
                assert params == {'receipt': 'receipt-original'}
                return deepcopy(state.receipt)
            if 'FROM CX_MODEL_COORD_ROUTES ' in sql:
                assert params == {'route': 'route-original'}
                return deepcopy(state.route)
            if 'FROM CX_LLM_PROVIDER_PROFILES ' in sql:
                assert params == {'profile': 'profile-original'}
                return deepcopy(state.profile)
            if 'FROM CX_MODEL_ORIGIN_RESOLUTIONS ' in sql:
                if 'REQUESTED_BY=:actor' in sql:
                    assert params == {'actor': 'original-user', 'key': 'resolution-original'}
                    found = next((value for value in state.resolutions
                        if value['requested_by'] == params['actor'] and value['idempotency_key'] == params['key']), None)
                    return {'request_digest': found['request_digest']} if found else None
                assert params == {'receipt': 'receipt-original'}
                return deepcopy(state.resolutions[0]) if state.resolutions else None
            raise AssertionError('Unexpected local query: ' + sql)

        def execute(self, sql, params):
            assert state.in_transaction
            assert sql.startswith('INSERT INTO CX_MODEL_ORIGIN_RESOLUTIONS(')
            assert set(re.findall(r':([A-Za-z_][A-Za-z0-9_]*)', sql)) == set(params)
            assert not state.resolutions
            state.resolutions.append(deepcopy(params))
            return 1

    def transaction(callback):
        assert not state.in_transaction
        staged_before = deepcopy((state.resolutions, state.audits))
        state.in_transaction = True
        try:
            return callback(Transaction())
        except BaseException:
            state.resolutions, state.audits = staged_before
            raise
        finally:
            state.in_transaction = False

    def authorize(tx, actor, receipt):
        assert state.in_transaction and isinstance(tx, Transaction)
        state.source_checks += 1
        if (not state.source_active or actor != 'original-user'
                or receipt['actor_id'] != actor or receipt['source_kind'] != 'GATEWAY'
                or receipt['source_id'] != 'source-original'
                or receipt['source_attempt_id'] != receipt['source_id']
                or receipt['worker_key'] != 'gateway:source-original'
                or receipt['original_credential_digest'] != 'a'*64
                or receipt['payload_digest'] != 'c'*64):
            raise PermissionError('Original source or credential is unavailable')

    def peer(route, path, credential, context, *, method):
        assert not state.in_transaction
        assert route == state.route and path == '/requests/central-original' and method == 'GET'
        assert credential == gateway_credential and context.actor == 'original-user'
        state.peer_reads += 1
        if state.after_peer:
            state.after_peer()
        return deepcopy(state.remote)

    def audit(tx, actor, action, resource_type, resource_id, outcome, reason):
        assert state.in_transaction and isinstance(tx, Transaction)
        assert len(state.resolutions) == 1
        assert (actor, action, resource_type, resource_id, outcome) == (
            'original-user', 'MODEL_ORIGIN_RECONCILE', 'MODEL_REQUEST', 'receipt-original', 'ALLOW')
        state.audits.append((actor, action, resource_id))
        if state.audit_failure:
            raise RuntimeError('Required audit could not commit')

    def forbidden(*args, **kwargs):
        pytest.fail('This regression must not perform network or native database I/O')

    monkeypatch.setattr(socket, 'socket', forbidden)
    monkeypatch.setattr(socket, 'create_connection', forbidden)
    monkeypatch.setattr(origin.urllib.request, 'urlopen', forbidden)
    for name in ('execute', 'execute_query', 'execute_query_one'):
        monkeypatch.setattr(connection, name, forbidden)
    monkeypatch.setattr(connection, 'execute_transaction_callback', transaction)
    monkeypatch.setattr(origin.common, 'secret', lambda profile: gateway_credential)
    monkeypatch.setattr(origin, '_peer', peer)
    monkeypatch.setattr(origin.capacity, '_now_ms', lambda tx: BIG + 1000)
    monkeypatch.setattr(origin.identity_api, '_audit_tx', audit)
    state.authorize = authorize
    state.reconcile = lambda: origin.reconcile_receipt('original-user', 'receipt-original',
        state.request, authorize_source=authorize)
    return state


NATIVE_VALUES = [
    pytest.param({'created_at': STAMP, 'updated_at': STAMP + timedelta(microseconds=1)}, id='naive-datetime'),
    pytest.param({'created_at': STAMP.replace(tzinfo=timezone.utc)}, id='aware-datetime'),
    pytest.param({'created_at_ms': Decimal(BIG), 'origin_lease_until_ms': Decimal(BIG + 1000),
        'version': Decimal(7)}, id='exact-decimal-above-2pow53'),
    pytest.param({'created_at': STAMP, 'created_at_ms': Decimal(BIG),
        'authorized_at_ms': Decimal(BIG)}, id='mixed-native-scalars'),
]


@pytest.mark.parametrize('native_values', NATIVE_VALUES)
def test_native_values_resolve_once_and_replay_without_another_peer_read(native_origin, native_values):
    state = native_origin
    state.receipt.update(native_values)
    before = deepcopy(state.receipt)
    result = state.reconcile()
    assert result['status'] == 'RESOLVED' and not result['replayed']
    assert result['content_approved'] is result['replay_allowed'] is False
    replay = state.reconcile()
    assert replay['replayed'] and replay['resolution'] == result['resolution']
    assert state.receipt == before and state.receipt['status'] == 'UNKNOWN'
    assert state.peer_reads == 1 and state.source_checks == 3
    assert len(state.resolutions) == len(state.audits) == 1


@pytest.mark.parametrize('field,initial,changed', [
    ('created_at', STAMP, STAMP + timedelta(microseconds=1)),
    ('updated_at', STAMP, STAMP + timedelta(microseconds=1)),
    ('created_at_ms', Decimal(BIG), Decimal(BIG + 1)),
    ('origin_lease_until_ms', Decimal(BIG), Decimal(BIG + 1)),
    ('finish_code', 'CLIENT_CLOSED', 'REMOTE_TERMINATED'),
    ('extra_retained_native_column', STAMP, STAMP + timedelta(microseconds=1)),
])
def test_complete_native_row_detects_a_single_changed_value(native_origin, field, initial, changed):
    state = native_origin
    state.receipt[field] = initial
    state.after_peer = lambda: state.receipt.update({field: changed})
    with pytest.raises(ContinuityConflict) as failure:
        state.reconcile()
    assert failure.value.code == 'STALE_VERSION'
    assert state.receipt[field] == changed
    assert not state.resolutions and not state.audits
    assert state.peer_reads == 1 and state.source_checks == 2


@pytest.mark.parametrize('operation', ['add', 'remove'])
def test_native_row_comparison_does_not_drop_columns(native_origin, operation):
    state = native_origin
    state.receipt['created_at_ms'] = Decimal(BIG)
    if operation == 'remove':
        state.receipt['retained_column'] = None
        state.after_peer = lambda: state.receipt.pop('retained_column')
    else:
        state.after_peer = lambda: state.receipt.update(retained_column=None)
    with pytest.raises(ContinuityConflict) as failure:
        state.reconcile()
    assert failure.value.code == 'STALE_VERSION'
    assert not state.resolutions and not state.audits


@pytest.mark.parametrize('revocation', ['source', 'credential', 'route'])
def test_final_transaction_rechecks_current_original_authority(native_origin, revocation):
    state = native_origin
    state.receipt['created_at_ms'] = Decimal(BIG)
    if revocation == 'source':
        state.after_peer = lambda: setattr(state, 'source_active', False)
    elif revocation == 'credential':
        state.after_peer = lambda: state.receipt.update(original_credential_digest='0'*64)
    else:
        state.after_peer = lambda: state.route.update(status='REVOKED')
    denied = model_dispatch.ModelNotDispatched if revocation == 'route' else PermissionError
    with pytest.raises(denied):
        state.reconcile()
    assert not state.resolutions and not state.audits
    assert state.peer_reads == 1 and state.source_checks == 2


def test_missing_terminal_evidence_preserves_the_native_unknown_row(native_origin):
    state = native_origin
    state.receipt.update(created_at=STAMP, created_at_ms=Decimal(BIG))
    state.remote.update(status='UNKNOWN', transport_resolution=None)
    before = deepcopy(state.receipt)
    result = state.reconcile()
    assert result == dict(status='UNKNOWN', resolution=None, replayed=False,
        content_approved=False, replay_allowed=False)
    assert state.receipt == before and not state.resolutions and not state.audits
    assert state.peer_reads == 1 and state.source_checks == 2


def test_required_audit_failure_rolls_back_then_retry_and_replay_append_once(native_origin):
    state = native_origin
    state.receipt.update(created_at=STAMP, created_at_ms=Decimal(BIG))
    before = deepcopy(state.receipt)
    state.audit_failure = True
    with pytest.raises(RuntimeError, match='Required audit could not commit'):
        state.reconcile()
    assert not state.resolutions and not state.audits and state.receipt == before
    state.audit_failure = False
    assert state.reconcile()['status'] == 'RESOLVED'
    assert state.reconcile()['replayed'] is True
    assert len(state.resolutions) == len(state.audits) == 1
    assert state.peer_reads == 2 and state.receipt == before
    state.source_active = False
    with pytest.raises(PermissionError):
        state.reconcile()
    assert state.peer_reads == 2 and len(state.resolutions) == len(state.audits) == 1


@pytest.mark.parametrize('native', [STAMP, Decimal(BIG)])
def test_public_json_canonicalizer_remains_strict(native):
    with pytest.raises(TypeError):
        canonical({'native': native})
