"""Real Native/Channel/Task code through independent DBs and loopback HTTP.

The existing Native credential, Worker, typed Task/provider projection and
processing adapters execute unchanged. SQLite policies and the Provider remain
synthetic; this is not native-database or real-LLM release acceptance.
"""
import json
import base64
import hashlib
from datetime import datetime,timedelta,timezone
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

import pytest

from lib import identity_api,model_dispatch,model_credentials,native_runtime,processing_recovery,processing_native
from lib import model_coordinator_common as common,model_coordinator_origin as origin,model_endpoint_capacity as capacity
from lib import managed_inputs,provider_capability_probes,content_security,connection
from lib.agent_extension_schema import TABLES
from lib.continuity_state import ContinuityError
from .test_v502_model_capacity import ledger
from .test_v502_ingress_credentials import ingress
from .test_v502_native_dispatch import worker,enqueue_native,enqueue_channel,execution,native_values,native_block,native_retry,channel_reply
from .test_v502_remote_model_coordinator import peer,rows

_OPEN_CONTROLLED=model_dispatch.open_controlled
_ORIGIN_DISPATCH=processing_recovery.on_origin_dispatch
_INSPECT_MESSAGES=content_security.inspect_messages


@pytest.fixture
def native_peer(worker,peer,monkeypatch):
    """Use the complete Native fixture as a separate fourth installation DB."""
    native_path=Path(worker.db.execute('PRAGMA database_list').fetchone()['file'])
    peer.paths['native']=native_path
    worker.db.execute('ALTER TABLE CX_LLM_PROVIDER_PROFILES ADD COLUMN PROFILE_KEY TEXT')
    worker.db.execute("UPDATE CX_LLM_PROVIDER_PROFILES SET PROFILE_KEY='native'")
    worker.db.commit()
    with peer.install('central'):
        binding=common.register_binding('admin',dict(group_id=peer.group,expected_group_version=2,policy_revision=1,
            origin_id='installation-a',installation_key='product-a',credential_id='credential-a',profile_id='provider',profile_version=1,
            origin_profile_id='profile',origin_profile_version=1,reason='Actual Native installation enrollment',idempotency_key='native-binding'))['binding_id']
    url=peer.url+'/api/model-gateway/coordinator/'+binding
    worker.db.execute("UPDATE CX_LLM_PROVIDER_PROFILES SET PROVIDER_URL=?,API_KEY_CIPHER=? WHERE PROFILE_ID='profile'",
        (url,json.dumps({'api_key':'cxgw_synthetic_a'})))
    worker.db.commit()
    with peer.install('native'):
        common.register_route('admin',dict(profile_id='profile',profile_version=1,coordinator_url=url,binding_id=binding,
            group_id=peer.group,policy_revision=1,origin_id='installation-a',installation_key='product-a',
            coordinator_profile_id='provider',coordinator_profile_version=1,reason='Actual Native registered immutable route',idempotency_key='native-route'))
    # Restore the production transport and processing hook replaced by the
    # parent fixtures' intentionally synthetic transport/source harnesses.
    monkeypatch.setattr(model_dispatch,'open_controlled',_OPEN_CONTROLLED)
    monkeypatch.setattr(processing_recovery,'on_origin_dispatch',_ORIGIN_DISPATCH)
    def access(actor,action,**kwargs):
        value=worker.db.execute('SELECT DECISION FROM TEST_PERMISSIONS WHERE ACTOR_ID=? AND ACTION_NAME=?',(actor,action)).fetchone()
        return {'decision':value['decision'] if value else 'ALLOW'}
    monkeypatch.setattr(identity_api,'effective_access',access)
    peer.worker=worker
    peer.native_binding=binding
    yield peer


@pytest.mark.parametrize('channel',[False,True])
def test_actual_native_and_channel_worker_cross_registered_origin_and_charge_original_task_budget(native_peer,channel):
    state=native_peer
    with state.install('native'):
        key=enqueue_channel(state.worker) if channel else enqueue_native(state.worker)
        result=native_runtime.execute_one('worker','node')
        assert result['status']=='COMPLETED',result
        assert execution(state.worker,key)['status']=='COMPLETED'
        assert native_values(state.worker,'SELECT REQUESTS_USED,STEPS_USED,TOKENS_USED FROM CX_PROCESSING_BUDGETS')==(1,1,12)
        assert native_values(state.worker,'SELECT STATUS FROM CX_TASK_CONTINUITY_ATTEMPTS')==('SUCCEEDED',)
        if channel:assert 'synthetic approved fact' in channel_reply(state.worker)['body_text']
        receipt=rows(state,'native','CX_MODEL_ORIGIN_RECEIPTS')[0]
        assert receipt['source_id']==key and receipt['source_kind']==('CHANNEL' if channel else 'NATIVE')
        assert receipt['status']=='COMPLETED' and receipt['original_credential_digest']==state.worker.digest
        call=state.worker.db.execute('SELECT * FROM CX_PROCESSING_NATIVE_CALLS').fetchone()
        mapped=state.worker.db.execute('SELECT * FROM CX_PROCESSING_NATIVE_ATTEMPTS').fetchone()
        assert receipt['source_attempt_id']==call['source_attempt_id'] and call['task_attempt_id']==mapped['task_attempt_id']
        assert receipt['origin_fencing_token']==mapped['native_fencing_token']
        assert rows(state,'native','CX_MODEL_ORIGIN_OBSERVATIONS')[0]['total_tokens']==12
        assert native_runtime.execute_one('worker','node')['status']=='IDLE'
    assert rows(state,'native','CX_MODEL_ADMISSIONS')==[]
    assert len(rows(state,'central','CX_MODEL_USAGE'))==1 and state.sends==1


@pytest.mark.parametrize('mutation',[
    "UPDATE CX_WEB_SESSIONS SET REVOKED_AT=CURRENT_TIMESTAMP",
    "UPDATE CX_RUNTIME_EXECUTIONS SET FENCING_TOKEN=FENCING_TOKEN+1",
    "INSERT INTO TEST_PERMISSIONS VALUES('origin-a','agents.operate','DENY')",
])
def test_actual_native_final_original_authorization_denies_after_remote_reservation(native_peer,monkeypatch,mutation):
    state=native_peer
    original=origin._peer
    def revoke(*args,**kwargs):
        value=original(*args,**kwargs)
        if args[1]=='/reservations':
            state.worker.db.execute(mutation);state.worker.db.commit()
        return value
    monkeypatch.setattr(origin,'_peer',revoke)
    with state.install('native'):
        key=enqueue_native(state.worker)
        result=native_runtime.execute_one('worker','node')
        assert result['status']=='FAILED',result
        assert execution(state.worker,key)['output_json'] is None
        assert rows(state,'native','CX_MODEL_ORIGIN_RECEIPTS')[0]['status']=='KNOWN_NO_SEND'
    assert state.sends==0 and rows(state,'central','CX_MODEL_ADMISSIONS')[0]['status']=='CANCELLED'


@pytest.mark.parametrize('mutation',[
    "UPDATE CX_CHANNEL_MESSAGES SET BODY_TEXT='changed original source' WHERE MESSAGE_ID='message'",
    "UPDATE CX_CHANNEL_MEMBERS SET STATUS='REVOKED' WHERE PRINCIPAL_ID='origin-a'",
    "UPDATE CX_PORTAL_KNOWLEDGE_POLICY SET ALLOW_MODEL_SUPPLEMENT='N'",
])
def test_actual_channel_final_source_authorization_denies_after_remote_reservation(native_peer,monkeypatch,mutation):
    state=native_peer
    original=origin._peer
    def revoke(*args,**kwargs):
        value=original(*args,**kwargs)
        if args[1]=='/reservations':
            state.worker.db.execute(mutation);state.worker.db.commit()
        return value
    monkeypatch.setattr(origin,'_peer',revoke)
    with state.install('native'):
        key=enqueue_channel(state.worker)
        result=native_runtime.execute_one('worker','node')
        assert result['status']=='FAILED',result
        assert execution(state.worker,key)['output_json'] is None
        assert rows(state,'native','CX_MODEL_ORIGIN_RECEIPTS')[0]['status']=='KNOWN_NO_SEND'
    assert state.sends==0 and rows(state,'central','CX_MODEL_ADMISSIONS')[0]['status']=='CANCELLED'


def test_actual_native_unknown_requires_remote_explicit_resolution_before_local_task_resolution(native_peer):
    state=native_peer
    state.mode='disconnect'
    with state.install('native'):
        key=enqueue_native(state.worker)
        result=native_runtime.execute_one('worker','node')
        assert result['status']=='UNOBSERVED',result
        receipt=rows(state,'native','CX_MODEL_ORIGIN_RECEIPTS')[0]
        assert receipt['status']=='UNKNOWN'
        assert native_values(state.worker,'SELECT STATUS FROM CX_TASK_CONTINUITY_ATTEMPTS')==('UNOBSERVED',)
        assert native_runtime.execute_one('replacement','node')['status']=='IDLE'
        block,target=native_block(state.worker,key)
        local=dict(expected_version=block['version'],target=target.model_dump(),mode='OPERATOR_RESOLUTION',outcome='FAILED',
            reason='Exact remote termination is required first',idempotency_key='local-resolution')
        with pytest.raises(ContinuityError):processing_recovery.reconcile_decision('admin',block['block_id'],local)
        before=rows(state,'native','CX_MODEL_ORIGIN_OBSERVATIONS')
        request=dict(expected_version=receipt['version'],reason='Read registered coordinator termination',idempotency_key='native-origin-read')
        assert origin.reconcile_receipt('origin-a',receipt['origin_receipt_id'],request)['status']=='UNKNOWN'
    with state.install('central'):
        admitted=capacity.read_admission('origin-a',receipt['admission_id'])
        capacity.observe_completion('admin',admitted['admission_id'],dict(expected_version=admitted['version'],attempt_id=admitted['attempt_id'],
            fencing_token=admitted['fencing_token'],evidence_digest='e'*64,evidence_kind='OPERATOR_CONFIRMATION',finish_code='VERIFIED_TERMINATED',
            reason='Explicit synthetic remote operator termination',idempotency_key='central-native-terminated'),reconcile=True)
    with state.install('native'):
        resolved=origin.reconcile_receipt('origin-a',receipt['origin_receipt_id'],request)
        assert resolved['status']=='RESOLVED' and resolved['resolution']['request_complete']=='N'
        assert rows(state,'native','CX_MODEL_ORIGIN_OBSERVATIONS')==before
        assert rows(state,'native','CX_MODEL_ORIGIN_RECEIPTS')[0]['status']=='UNKNOWN'
        assert processing_recovery.reconcile_decision('admin',block['block_id'],local)['status']=='FAILED'
        assert execution(state.worker,key)['status']=='FAILED'
        assert native_values(state.worker,'SELECT STATUS FROM CX_TASK_CONTINUITY_ATTEMPTS')==('FAILED',)
        retry=native_retry(state.worker,key)
        assert processing_recovery.dispatch_retry('origin-a',retry['recovery_id'])['status']=='QUEUED'
        assert state.sends==1
    state.mode='complete';state.entered.clear();state.hold.clear()
    def execute_retry():
        with state.install('native'):return native_runtime.execute_one('worker-2','node')
    with ThreadPoolExecutor(max_workers=1) as pool:
        active=pool.submit(execute_retry)
        try:
            assert state.entered.wait(5)
            recovery=rows(state,'native','CX_PROCESSING_RECOVERY_STATES')[0]
            assert recovery['status']=='DISPATCHED' and recovery['admission_id'] is None
            assert {value['status'] for value in rows(state,'native','CX_MODEL_ORIGIN_RECEIPTS')}=={'UNKNOWN','DISPATCHING'}
        finally:state.hold.set()
        assert active.result(5)['status']=='COMPLETED'
    with state.install('native'):
        assert execution(state.worker,key)['status']=='COMPLETED'
        assert native_values(state.worker,'SELECT REQUESTS_USED,STEPS_USED,TOKENS_USED FROM CX_PROCESSING_BUDGETS')==(2,2,12)
        assert rows(state,'native','CX_MODEL_ORIGIN_OBSERVATIONS')[0]==before[0]
        assert {value['status'] for value in rows(state,'native','CX_MODEL_ORIGIN_RECEIPTS')}=={'UNKNOWN','COMPLETED'}
    assert rows(state,'native','CX_MODEL_ADMISSIONS')==[] and state.sends==2 and state.maximum==1


@pytest.fixture
def managed_peer(native_peer,monkeypatch):
    state=native_peer
    encoded=provider_capability_probes._image_probe()
    png=base64.b64decode(encoded)
    with state.install('native'):
        state.worker.db.execute("INSERT INTO CX_MANAGED_INPUT_ASSETS(ASSET_ID,OWNER_ID,SECURITY_DOMAIN_ID,FILE_NAME,MEDIA_TYPE,BYTE_COUNT,"
            "CONTENT_DIGEST,CONTENT_CIPHER,STATUS) VALUES('png','origin-a','domain','pixel.png','image/png',?,?,?,'ACTIVE')",
            (len(png),hashlib.sha256(png).hexdigest(),state.worker.encode({'content':encoded})))
        state.worker.db.commit()
    with state.db(state.paths['central']) as db:
        db.execute('CREATE TABLE CX_PROVIDER_CAP_PROBES('+TABLES['CX_PROVIDER_CAP_PROBES']['definition']+')')
    for installation,profile in (('native','profile'),('central','provider')):
        with state.db(state.paths[installation]) as db:
            db.execute("INSERT INTO CX_PROVIDER_CAP_PROBES(PROBE_ID,PROFILE_ID,PROFILE_VERSION,MODEL_ID,API_DIALECT,CAPABILITY_KEY,STATUS,"
                "PARAMETER_DIGEST,SCHEMA_DIGEST,EXPIRES_AT,ACTOR_ID) VALUES('png-probe',?,1,'model','CHAT_COMPLETIONS','IMAGE_INPUT','VERIFIED',?,?,?,'origin-a')",
                (profile,'a'*64,'a'*64,(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat()))
    # Keep the actual bounded managed-image shape validator, including its
    # prohibition on public URLs. Policy text inspection remains synthetic.
    monkeypatch.setattr(content_security,'inspect_messages',_INSPECT_MESSAGES)
    return state


def managed_query(state):
    with state.install('native'),model_credentials.server_session(state.worker.session):
        return managed_inputs.query('origin-a','png','profile','Describe the supplied image.')


def test_actual_managed_owned_png_crosses_registered_origin_only_with_independent_central_capability(managed_peer):
    state=managed_peer
    result=managed_query(state)
    assert result['status']=='SUCCEEDED' and result['result']['content']=='A synthetic approved fact.'
    receipt=rows(state,'native','CX_MODEL_ORIGIN_RECEIPTS')[0]
    assert receipt['source_kind']=='EXTERNAL' and receipt['source_id']==receipt['source_attempt_id']==result['use_id']
    assert receipt['status']=='COMPLETED'
    assert rows(state,'native','CX_MANAGED_ASSET_USES')[0]['status']=='SUCCEEDED'
    assert rows(state,'native','CX_MODEL_ORIGIN_OBSERVATIONS')[0]['total_tokens']==12 and state.sends==1


@pytest.mark.parametrize('mutation',[
    "UPDATE CX_PROVIDER_CAP_PROBES SET STATUS='REVOKED'",
    "UPDATE CX_PROVIDER_CAP_PROBES SET EXPIRES_AT='2000-01-01'",
    "UPDATE CX_PROVIDER_CAP_PROBES SET MODEL_ID='different-model'",
    "UPDATE CX_PROVIDER_CAP_PROBES SET PROFILE_VERSION=2",
])
def test_remote_png_cannot_expand_central_profile_capability_from_origin_attestation(managed_peer,mutation):
    state=managed_peer
    with state.db(state.paths['central']) as db:db.execute(mutation)
    result=managed_query(state)
    assert result['status']=='FAILED' and result['result'] is None
    assert rows(state,'native','CX_MODEL_ORIGIN_RECEIPTS')[0]['status']=='KNOWN_NO_SEND'
    assert rows(state,'central','CX_MODEL_ADMISSIONS')[0]['status']=='CANCELLED' and state.sends==0


def test_actual_managed_png_asset_revocation_after_remote_reservation_prevents_send(managed_peer,monkeypatch):
    state=managed_peer
    original=origin._peer
    def revoke(*args,**kwargs):
        result=original(*args,**kwargs)
        if args[1]=='/reservations':
            state.worker.db.execute("UPDATE CX_MANAGED_INPUT_ASSETS SET STATUS='REVOKED',VERSION=VERSION+1")
            state.worker.db.commit()
        return result
    monkeypatch.setattr(origin,'_peer',revoke)
    assert managed_query(state)['status']=='FAILED'
    assert rows(state,'native','CX_MODEL_ORIGIN_RECEIPTS')[0]['status']=='KNOWN_NO_SEND' and state.sends==0


def test_managed_png_transport_cannot_replace_original_asset_data_with_public_url(managed_peer,monkeypatch):
    state=managed_peer
    actual=native_runtime._provider_messages
    def public_url(messages):
        selected=json.loads(json.dumps(actual(messages)))
        for message in selected:
            if isinstance(message.get('content'),list):message['content'][1]['image_url']['url']='https://unregistered.invalid/image.png'
        return selected
    monkeypatch.setattr(native_runtime,'_provider_messages',public_url)
    result=managed_query(state)
    assert result['status']=='FAILED' and result['result'] is None and state.sends==0
    assert rows(state,'native','CX_MODEL_ORIGIN_RECEIPTS')==[]
