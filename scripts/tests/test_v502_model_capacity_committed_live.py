"""Opt-in native capacity/coordinator tests on one exact classified package DB.

All identities, row locks, clocks, immutable triggers and transactions are real.
The sole Provider is a local synthetic HTTP server. Coordinator envelopes model
an enrolled Origin attestation; these cases do not certify foreign Origin source
authorization or real LLM quality. Immutable fixture records remain as evidence.
"""
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
from threading import Barrier, Event, Lock, Thread
import time
from types import SimpleNamespace

import pytest

from lib import connection, identity_api, native_agent_api, model_usage_api
from lib import model_endpoint_capacity as capacity, model_endpoint_schema
from lib import model_coordinator as coordinator, model_coordinator_common as common
from lib.agent_extension_contracts import digest
from lib.continuity_state import ContinuityConflict
from lib.model_coordinator_contracts import DispatchProof
from .release_target import classified_current_target

pytestmark = pytest.mark.skipif(os.environ.get('CX_V502_NATIVE_MODEL_LIVE') != '1',
    reason='explicit classified v5.0.2 native model-capacity acceptance required')


@pytest.fixture
def native(record_property):
    assert classified_current_target(), 'Native mutation requires the exact classified package target'
    from lib.product_identity import read_manifest
    assert read_manifest()['version'] == '5.0.2'
    assert connection.DATABASE_DIALECT in {'pg', 'postgresql', 'oracle', 'yashandb', 'yashan'}
    assert connection.get_current_agent_id() is None
    humans = connection.execute_query("SELECT PRINCIPAL_ID FROM CX_PRINCIPALS WHERE PRINCIPAL_TYPE='HUMAN' AND STATUS='ACTIVE'")
    actor = next((str(item['principal_id']) for item in humans
        if identity_api.effective_access(str(item['principal_id']), 'model_gateway.manage')['decision'] == 'ALLOW'
        and identity_api.effective_access(str(item['principal_id']), 'model_gateway.forward')['decision'] == 'ALLOW'), None)
    assert actor, 'Native acceptance needs a current authorized Human administrator'
    key = 'v502-native-' + secrets.token_hex(10)
    state = SimpleNamespace(actor=actor, key=key, sends=0, active=0, maximum=0,
        mode='complete', entered=Event(), release=Event(), lock=Lock(), admissions=[], credentials=[])
    state.release.set()
    class Provider(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'
        def log_message(self, *_args):
            pass
        def do_POST(self):
            json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            with state.lock:
                state.sends += 1
                state.active += 1
                state.maximum = max(state.maximum, state.active)
            state.entered.set()
            try:
                if not state.release.wait(30):
                    self.close_connection = True
                    return
                if state.mode == 'disconnect':
                    self.close_connection = True
                    return
                raw = json.dumps(dict(model='native-fixture-model', choices=[dict(index=0,
                    message=dict(role='assistant', content='The approved fixture is complete.'), finish_reason='stop')],
                    usage=dict(prompt_tokens=8, completion_tokens=4, total_tokens=12))).encode()
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)
            finally:
                with state.lock:
                    state.active -= 1
    provider = ThreadingHTTPServer(('127.0.0.1', 0), Provider)
    thread = Thread(target=provider.serve_forever, daemon=True)
    thread.start()
    state.url = f'http://127.0.0.1:{provider.server_port}/v1/' + key
    state.profile = native_agent_api.upsert_llm_profile(actor, key, state.url, 'native-fixture-model', '',
        'Explicit native acceptance uses only this local synthetic Provider')['profile_id']
    state.group = capacity.create_group(actor, dict(resource_key=key, coordinator_id=key,
        policy=dict(reservation_ms=120000), reason='Classified native loopback acceptance', idempotency_key=key))['group_id']
    state.origin = key + '-origin'
    capacity.register_origin(actor, state.group, dict(origin_id=state.origin, principal_id=actor,
        installation_key=key, reason='Explicit native fixture Origin', idempotency_key=key + '-origin'))
    capacity.register_alias(actor, state.group, dict(endpoint_url=state.url, profile_id=state.profile,
        expected_version=1, reason='Unique loopback fixture resource', idempotency_key=key + '-alias'))
    credential = model_usage_api.issue_gateway_credential(actor, key, ['model.forward', 'profile:' + state.profile])
    state.raw, state.credential = credential['token'], credential['credential_id']
    state.credentials.append(state.credential)
    state.binding = common.register_binding(actor, dict(group_id=state.group, expected_group_version=2, policy_revision=1,
        origin_id=state.origin, installation_key=key, credential_id=state.credential, profile_id=state.profile,
        profile_version=1, origin_profile_id=key + '-foreign-profile', origin_profile_version=1,
        reason='Native central enrollment, synthetic foreign attestation', idempotency_key=key + '-binding'))['binding_id']
    record_property('native_fixture_group', state.group)
    record_property('native_fixture_profile', state.profile)
    record_property('provider_kind', 'SYNTHETIC_LOOPBACK_ONLY')
    try:
        yield state
    finally:
        connection.set_agent_context(None)
        state.release.set()
        provider.shutdown()
        provider.server_close()
        thread.join(timeout=5)
        assert state.active == 0, 'Fixture Provider still has an active request'
        # Preserve immutable requests and audit. Drain only this fixture group;
        # an UNKNOWN row is retained and is not fabricated into completion.
        current = capacity.read_group(actor, state.group)
        capacity.revise_group(actor, state.group, dict(expected_version=current['version'],
            policy=dict(reservation_ms=120000), status='DRAINING',
            reason='Native fixture finished; retain immutable test evidence', idempotency_key=key + '-drain'))
        for credential_id in state.credentials:
            model_usage_api.revoke_gateway_credential(actor, credential_id, 'Native fixture completed')


def admission(state, suffix):
    return dict(origin_id=state.origin, profile_id=state.profile, profile_version=1, model_id='native-fixture-model',
        endpoint_url=state.url, input_digest=digest({'fixture': state.key, 'suffix': suffix}),
        credential_digest=common.token_digest(state.raw), source_kind='GATEWAY',
        source_id=state.key + '-source-' + suffix, source_attempt_id=state.key + '-attempt-' + suffix,
        reason='Native capacity lifecycle fixture; no Provider send', idempotency_key=state.key + '-admit-' + suffix)


def claim(state, value, suffix='dispatch'):
    return dict(expected_version=value['version'], fencing_token=value['fencing_token'], worker_key=state.key,
        credential_digest=common.token_digest(state.raw), reason='Native final credential check', idempotency_key=state.key + '-' + suffix)


def authorize_credential(state):
    def check(tx, _record):
        common.authenticated_binding(tx, state.raw, state.binding)
    return check


def observation(state, value, kind='COMPLETE_RESPONSE', suffix='observe'):
    return dict(expected_version=value['version'], attempt_id=value['attempt_id'], fencing_token=value['fencing_token'],
        evidence_digest=digest({'fixture': state.key, 'kind': kind}), evidence_kind=kind,
        finish_code='NATIVE_FIXTURE_' + kind, reason='Exact synthetic lifecycle evidence on native ledger',
        idempotency_key=state.key + '-' + suffix)


def envelope(state, suffix):
    payload = dict(model='native-fixture-model', messages=[dict(role='user', content='Complete the approved fixture.')], stream=False)
    now = connection.execute_transaction_callback(capacity._now_ms)
    value = dict(origin_receipt_id=state.key + '-receipt-' + suffix, installation_key=state.key,
        origin_actor_id=state.key + '-foreign-user', source_kind='EXTERNAL', source_id=state.key + '-source-' + suffix,
        source_attempt_id=state.key + '-attempt-' + suffix, worker_key=state.key, origin_fencing_token=1,
        origin_lease_until_ms=now + 120000, authority_digest=digest({'synthetic_attestation': state.key}),
        origin_profile_id=state.key + '-foreign-profile', origin_profile_version=1, group_id=state.group,
        policy_revision=1, profile_id=state.profile, profile_version=1, model_id='native-fixture-model',
        payload_digest=digest(payload), idempotency_key=state.key + '-request-' + suffix)
    return value, payload


def proof(state, value, reserved):
    now = connection.execute_transaction_callback(capacity._now_ms)
    return common.encode_proof(DispatchProof(envelope=value,
        coordinator_request_id=reserved['coordinator_request_id'], admission_id=reserved['admission_id'],
        reservation_version=reserved['reservation_version'], fencing_token=reserved['fencing_token'],
        authorized_at_ms=now, expires_at_ms=now + common.PROOF_MS), state.raw)


def test_native_concurrent_admissions_share_one_real_capacity_slot(native, record_property):
    barrier = Barrier(2)
    def send(suffix):
        barrier.wait(timeout=30)
        return capacity.admit(native.actor, native.group, admission(native, suffix))
    with ThreadPoolExecutor(max_workers=2) as pool:
        values = list(pool.map(send, ('first', 'second')))
    assert sorted(item['status'] for item in values) == ['QUEUED', 'RESERVED']
    rows = connection.execute_query('SELECT STATUS FROM CX_MODEL_ADMISSIONS WHERE GROUP_ID=:group_id', {'group_id': native.group})
    assert sum(item['status'] in capacity.OCCUPIED for item in rows) == 1
    assert native.sends == 0
    record_property('native_concurrent_admissions', 2)


def test_native_group_for_update_blocks_an_independent_admission(native):
    locked, release, started = Event(), Event(), Event()
    def holder():
        def hold(tx):
            assert tx.query_one('SELECT GROUP_ID FROM CX_MODEL_CAP_GROUPS WHERE GROUP_ID=:group_id FOR UPDATE', {'group_id': native.group})
            locked.set()
            assert release.wait(30), 'Native lock holder was not released'
        connection.execute_transaction_callback(hold)
    def contender():
        started.set()
        return capacity.admit(native.actor, native.group, admission(native, 'locked'))
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(holder)
        try:
            assert locked.wait(30)
            second = pool.submit(contender)
            assert started.wait(30)
            time.sleep(0.25)
            assert not second.done(), 'Native FOR UPDATE did not serialize the independent writer'
        finally:
            release.set()
        first.result(timeout=30)
        assert second.result(timeout=30)['status'] == 'RESERVED'
    assert native.sends == 0


def test_native_credential_revocation_waits_for_the_original_authorization_transaction(native):
    checked, release, revoking = Event(), Event(), Event()
    def authorize():
        def hold(tx):
            binding, credential, *_rest = common.authenticated_binding(tx, native.raw, native.binding)
            assert credential['credential_id'] == native.credential and binding['binding_id'] == native.binding
            checked.set()
            assert release.wait(30)
        connection.execute_transaction_callback(hold)
    def revoke():
        revoking.set()
        return model_usage_api.revoke_gateway_credential(native.actor, native.credential, 'Native revoke race')
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(authorize)
        try:
            assert checked.wait(30)
            second = pool.submit(revoke)
            assert revoking.wait(30)
            time.sleep(0.25)
            assert not second.done(), 'Native credential revoke bypassed the authorization row lock'
        finally:
            release.set()
        first.result(timeout=30)
        assert second.result(timeout=30)['status'] == 'REVOKED'
    with pytest.raises(PermissionError):
        connection.execute_transaction_callback(lambda tx: common.authenticated_binding(tx, native.raw, native.binding))
    assert native.sends == 0


def test_native_revoked_original_credential_is_rejected_before_a_durable_attempt(native):
    reserved = capacity.admit(native.actor, native.group, admission(native, 'revoke'))
    model_usage_api.revoke_gateway_credential(native.actor, native.credential, 'Native pre-dispatch revoke')
    result = capacity.begin_dispatch(native.actor, reserved['admission_id'], claim(native, reserved),
        reauthorize=authorize_credential(native))
    assert result['status'] == 'REJECTED' and result['attempt_id'] is None and result['dispatch_authorized'] is False
    assert native.sends == 0


def test_native_unknown_survives_a_new_process_and_keeps_capacity_until_exact_resolution(native):
    reserved = capacity.admit(native.actor, native.group, admission(native, 'unknown'))
    sent = capacity.begin_dispatch(native.actor, reserved['admission_id'], claim(native, reserved),
        reauthorize=authorize_credential(native))
    unknown = capacity.cancel_admission(native.actor, sent['admission_id'], dict(expected_version=sent['version'],
        reason='Synthetic possible-send boundary remains unknown', idempotency_key=native.key + '-cancel'))
    assert unknown['status'] == 'UNKNOWN' and unknown['occupies_capacity']
    # A fresh Python interpreter and native connection read the committed row.
    code = ('import json,sys; from lib import model_endpoint_capacity as c; '
            'r=c.read_admission(sys.argv[1],sys.argv[2]); '
            'print(json.dumps({k:r[k] for k in ("status","occupies_capacity","attempt_id")}))')
    child = subprocess.run([sys.executable, '-B', '-c', code, native.actor, unknown['admission_id']],
        cwd=Path(native_agent_api.__file__).resolve().parents[2], env=os.environ.copy(), capture_output=True, text=True, timeout=30)
    assert child.returncode == 0, 'Fresh native observation process failed; inspect private acceptance output'
    retained = json.loads(child.stdout.strip().splitlines()[-1])
    assert retained == {key: unknown[key] for key in ('status', 'occupies_capacity', 'attempt_id')}
    second = capacity.admit(native.actor, native.group, admission(native, 'waiting'))
    assert second['status'] == 'QUEUED'
    with pytest.raises(ContinuityConflict):
        capacity.observe_completion(native.actor, unknown['admission_id'], observation(native, unknown,
            kind='OPERATOR_CONFIRMATION', suffix='foreign-evidence') | {'attempt_id': native.key + '-foreign'}, reconcile=True)
    complete = capacity.observe_completion(native.actor, unknown['admission_id'], observation(native, unknown,
        kind='OPERATOR_CONFIRMATION', suffix='resolve'), reconcile=True)
    assert complete['status'] == 'COMPLETED' and not complete['occupies_capacity']
    assert capacity.read_admission(native.actor, second['admission_id'], reserve=True)['status'] == 'RESERVED'
    assert native.sends == 0


def test_native_owner_cannot_rewrite_admission_identity_or_attempt_fence(native):
    reserved = capacity.admit(native.actor, native.group, admission(native, 'immutable'))
    sent = capacity.begin_dispatch(native.actor, reserved['admission_id'], claim(native, reserved),
        reauthorize=authorize_credential(native))
    with pytest.raises(Exception):
        connection.execute('UPDATE CX_MODEL_ADMISSIONS SET INPUT_DIGEST=:fingerprint WHERE ADMISSION_ID=:admission_id',
            {'fingerprint': 'f' * 64, 'admission_id': sent['admission_id']})
    with pytest.raises(Exception):
        connection.execute('UPDATE CX_MODEL_CAP_ATTEMPTS SET FENCING_TOKEN=FENCING_TOKEN+1 WHERE ATTEMPT_ID=:attempt_id',
            {'attempt_id': sent['attempt_id']})
    exact = capacity.read_admission(native.actor, sent['admission_id'])
    assert exact['attempt_id'] == sent['attempt_id'] and exact['fencing_token'] == sent['fencing_token']
    assert native.sends == 0


def test_native_agent_login_cannot_read_or_write_any_model_runtime_control_table(native):
    import hashlib
    setup_path = Path(os.environ.get('CX_V502_NATIVE_AGENT_SETUP', ''))
    assert setup_path.is_file(), 'Select the exact retained native enrollment/activation setup receipt'
    assert setup_path.stat().st_mode & 0o077 == 0
    setup = json.loads(setup_path.read_text())
    facts_path = Path(os.environ['CX_RELEASE_TEST_CLASSIFICATION'])
    facts = json.loads(facts_path.read_text())
    binding = setup['binding']
    assert setup['schema'] == 'chuanxu-v502-native-agent-setup/v1' and setup['passed'] is True
    assert binding['classification_sha256'] == hashlib.sha256(facts_path.read_bytes()).hexdigest()
    assert binding['config_sha256'] == hashlib.sha256(Path(os.environ['CX_CONFIG_PATH']).read_bytes()).hexdigest()
    assert binding['database_target'] == facts['target'] and binding['target'] == facts['key'] and binding['track'] == facts['track']
    manifest = Path(native_agent_api.__file__).resolve().parents[2] / 'package-files.sha256'
    assert binding['package_manifest_sha256'] == hashlib.sha256(manifest.read_bytes()).hexdigest()
    agent = setup['agent_id']
    assert agent == 'V502_NATIVE_' + setup['invocation'].upper()
    enrolled = connection.execute_query_one('SELECT PRINCIPAL_ID,STATUS FROM CX_PRINCIPALS WHERE PRINCIPAL_ID=:agent_id', {'agent_id': agent})
    assert enrolled and enrolled['status'] == 'ACTIVE'
    from lib import agent_api
    current = agent_api.native_identity_snapshot(agent)
    assert current['mapping_state'] == current['native_state'] == 'OBSERVED' and current['login_enabled'] is True
    assert current['database_fingerprint'] == setup['native_identity']['database_fingerprint']
    assert current['username'] == setup['native_identity']['username'] and current['native_privileged'] is False
    tables = [statement.split('CREATE TABLE ', 1)[1].split(' ', 1)[0]
              for statement in model_endpoint_schema.schema_statements('pg')]
    assert len(tables) == 18
    connection.set_agent_context(agent)
    try:
        with connection.get_connection_for_agent() as session:
            with session.cursor() as cursor:
                cursor.execute('SELECT 1' + connection.scalar_select_suffix())
                assert cursor.fetchone()[0] == 1
        for table in tables:
            with pytest.raises(Exception):
                connection.execute_query('SELECT * FROM ' + table + ' WHERE 1=0')
            with pytest.raises(Exception):
                connection.execute('DELETE FROM ' + table + ' WHERE 1=0')
    finally:
        connection.set_agent_context(None)
    assert native.sends == 0


def test_native_central_coordinator_sends_once_and_replays_encrypted_snapshot(native, record_property):
    value, payload = envelope(native, 'complete')
    reserved = coordinator.reserve(native.raw, native.binding, value)
    assert reserved['status'] == 'RESERVED'
    signed = proof(native, value, reserved)
    result = coordinator.complete(native.raw, native.binding, signed, payload)
    assert result['choices'][0]['message']['content'] == 'The approved fixture is complete.'
    assert result['usage']['total_tokens'] == 12
    replayed = coordinator.complete(native.raw, native.binding, signed, payload)
    assert replayed.get('replayed') is True
    assert {key: item for key, item in replayed.items() if key != 'replayed'} == result
    assert native.sends == native.maximum == 1
    actual = coordinator.read_request(native.raw, native.binding, reserved['coordinator_request_id'])
    assert actual['request_complete'] is True and actual['admission_status'] == 'COMPLETED'
    assert actual['transport_resolution']['evidence_kind'] == 'COMPLETE_RESPONSE'
    record_property('actual_loopback_provider_sends', native.sends)


def test_native_central_disconnect_stays_unknown_and_blocks_second_attestation(native):
    native.mode = 'disconnect'
    value, payload = envelope(native, 'disconnect')
    reserved = coordinator.reserve(native.raw, native.binding, value)
    signed = proof(native, value, reserved)
    with pytest.raises(ContinuityConflict, match='reconciled'):
        coordinator.complete(native.raw, native.binding, signed, payload)
    actual = coordinator.read_request(native.raw, native.binding, reserved['coordinator_request_id'])
    assert actual['status'] == actual['admission_status'] == 'UNKNOWN' and not actual['request_complete']
    with pytest.raises(ContinuityConflict):
        coordinator.complete(native.raw, native.binding, signed, payload)
    later, _ = envelope(native, 'later')
    refused = coordinator.reserve(native.raw, native.binding, later)
    assert refused['status'] == 'KNOWN_NO_SEND' and refused['admission_status'] == 'CANCELLED'
    assert native.sends == native.maximum == 1


def test_native_central_revocation_after_reservation_never_calls_provider(native):
    value, payload = envelope(native, 'revoke')
    reserved = coordinator.reserve(native.raw, native.binding, value)
    signed = proof(native, value, reserved)
    model_usage_api.revoke_gateway_credential(native.actor, native.credential, 'Revoke after central reservation')
    with pytest.raises(PermissionError):
        coordinator.complete(native.raw, native.binding, signed, payload)
    row = capacity.read_admission(native.actor, reserved['admission_id'])
    assert row['status'] == 'RESERVED' and row['attempt_id'] is None
    assert native.sends == 0
