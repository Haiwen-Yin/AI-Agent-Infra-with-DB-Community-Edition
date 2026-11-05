"""Independent SQLite installations and real loopback Gateway/Provider HTTP.

This proves transport/relational contracts with synthetic authorities and
responses, not native database, real LLM, or release acceptance.
"""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime,timedelta,timezone
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
import multiprocessing
import os
import re
import socket
import sqlite3
from threading import Event,Lock,Thread
import time
from types import SimpleNamespace
import urllib.request
import urllib.error

from fastapi import FastAPI,HTTPException
import pytest
import uvicorn

from lib import connection,edition_features,identity_api,native_runtime,model_dispatch,model_endpoint_capacity as capacity
from lib import model_endpoint_schema,model_coordinator_schema
from lib import model_coordinator as coordinator,model_coordinator_common as common,model_coordinator_origin as origin,model_coordinator_http
from lib import model_coordinator_observations as observations
from lib import processing_recovery
from lib import provider_capability_probes,content_security,connection_crypto,model_usage_api
from lib.agent_extension_contracts import digest
from lib.continuity_state import ContinuityConflict
from lib.model_coordinator_contracts import DispatchProof


BASE_SCHEMA='''
CREATE TABLE CX_PRINCIPALS(PRINCIPAL_ID TEXT PRIMARY KEY,STATUS TEXT);
CREATE TABLE CX_LLM_PROVIDER_PROFILES(PROFILE_ID TEXT PRIMARY KEY,VERSION INTEGER,PROFILE_KEY TEXT,MODEL_ID TEXT,
    PROVIDER_URL TEXT,API_KEY_CIPHER TEXT,STATUS TEXT);
CREATE TABLE CX_MODEL_GATEWAY_CREDENTIALS(CREDENTIAL_ID TEXT PRIMARY KEY,CREATED_BY TEXT,TOKEN_DIGEST TEXT UNIQUE,
    SCOPES_JSON TEXT,STATUS TEXT,EXPIRES_AT TIMESTAMP);
CREATE TABLE CX_MODEL_REQUESTS(REQUEST_ID TEXT PRIMARY KEY,ACTOR_PRINCIPAL_ID TEXT,AGENT_ID TEXT,PROFILE_ID TEXT,MODEL_ID TEXT,
    STATUS TEXT,IDEMPOTENCY_KEY TEXT,INPUT_DIGEST TEXT,CORRELATION_ID TEXT,CREDENTIAL_ID TEXT,COMPLETED_AT TIMESTAMP,ERROR_CATEGORY TEXT);
CREATE TABLE CX_MODEL_USAGE(USAGE_ID TEXT PRIMARY KEY,REQUEST_ID TEXT UNIQUE REFERENCES CX_MODEL_REQUESTS(REQUEST_ID),
    ACTOR_PRINCIPAL_ID TEXT,AGENT_ID TEXT,PROVIDER_KEY TEXT,MODEL_ID TEXT,PROMPT_TOKENS INTEGER,COMPLETION_TOKENS INTEGER,
    CACHED_TOKENS INTEGER,REASONING_TOKENS INTEGER,TOTAL_TOKENS INTEGER,USAGE_PROVENANCE TEXT,COST TEXT,CURRENCY TEXT,
    PRICING_VERSION TEXT,STATUS TEXT,LATENCY_MS INTEGER,IDEMPOTENCY_KEY TEXT);
CREATE TABLE CX_MODEL_PRICING(PRICE_ID TEXT,PRICING_VERSION TEXT,CURRENCY TEXT,INPUT_PER_MILLION TEXT,OUTPUT_PER_MILLION TEXT,
    CACHE_PER_MILLION TEXT,REASONING_PER_MILLION TEXT,PROVIDER_KEY TEXT,MODEL_ID TEXT,STATUS TEXT,EFFECTIVE_FROM TIMESTAMP,EFFECTIVE_TO TIMESTAMP);
CREATE TABLE CX_DOMAIN_MEMBERS(PRINCIPAL_ID TEXT,SECURITY_DOMAIN_ID TEXT,STATUS TEXT,VALID_UNTIL TIMESTAMP);
CREATE TABLE CX_ORGANIZATION_MEMBERS(PRINCIPAL_ID TEXT,ORGANIZATION_ID TEXT,STATUS TEXT,VALID_UNTIL TIMESTAMP);
CREATE TABLE CX_MODEL_QUOTA_POLICIES(POLICY_ID TEXT,POLICY_KEY TEXT,VERSION INTEGER,SCOPE_TYPE TEXT,SCOPE_ID TEXT,METRIC TEXT,
    LIMIT_VALUE TEXT,CURRENCY TEXT,ENFORCEMENT TEXT,WINDOW_TYPE TEXT,RESERVATION_VALUE TEXT,INCOMPLETE_POLICY TEXT,
    STATUS TEXT,EFFECTIVE_FROM TIMESTAMP,EFFECTIVE_TO TIMESTAMP);
CREATE TABLE CX_MODEL_QUOTA_RESERVATIONS(RESERVATION_ID TEXT,REQUEST_ID TEXT,POLICY_ID TEXT,WINDOW_START TIMESTAMP,WINDOW_END TIMESTAMP,
    RESERVED_VALUE TEXT,STATUS TEXT,WARNING TEXT,EXPIRES_AT TIMESTAMP,SETTLED_VALUE TEXT,UPDATED_AT TIMESTAMP);
CREATE TABLE CX_MODEL_REPLAY_SNAPSHOTS(REQUEST_ID TEXT PRIMARY KEY,RESPONSE_CIPHER TEXT,RESPONSE_DIGEST TEXT,KEY_REFERENCE TEXT,
    BYTE_COUNT INTEGER,EXPIRES_AT TIMESTAMP);
CREATE TABLE CX_RUNTIME_EXECUTIONS(EXECUTION_ID TEXT PRIMARY KEY,WORKER_ID TEXT,FENCING_TOKEN INTEGER,LEASE_EXPIRES_AT TIMESTAMP,STATUS TEXT);
CREATE TABLE CX_TASK_CONTINUITY_ATTEMPTS(ATTEMPT_ID TEXT,CONTINUITY_ID TEXT,FENCING_TOKEN INTEGER,LEASE_EXPIRES_AT TIMESTAMP,STATUS TEXT);
CREATE TABLE CX_TASK_CONTINUITY_LEASES(CONTINUITY_ID TEXT,LEASE_OWNER TEXT,STATUS TEXT,FENCING_TOKEN INTEGER,LEASE_EXPIRES_AT TIMESTAMP);
CREATE TABLE SOURCE_AUTH(SOURCE_ID TEXT PRIMARY KEY,ACTOR_ID TEXT,CREDENTIAL_DIGEST TEXT,PAYLOAD_DIGEST TEXT,STATUS TEXT);
CREATE TABLE AUDIT(ACTOR_ID TEXT,ACTION_NAME TEXT,RESOURCE_ID TEXT);
'''


@pytest.fixture
def peer(tmp_path,monkeypatch):
    paths={name:tmp_path/(name+'.sqlite') for name in ('central','a','b')}
    selected=ContextVar('synthetic_installation_database',default=paths['central'])
    transaction_depth=ContextVar('synthetic_origin_transaction_depth',default=0)
    def db(path=None):
        value=sqlite3.connect(path or selected.get(),timeout=10,check_same_thread=False)
        value.row_factory=lambda cursor,values:{item[0].lower():content for item,content in zip(cursor.description,values)}
        value.execute('PRAGMA foreign_keys=ON')
        return value
    def sql(value):return re.sub(r'FETCH FIRST (:[A-Za-z0-9_]+|[0-9]+) ROWS ONLY',r'LIMIT \1',value.replace(' FOR UPDATE',''))
    class Transaction:
        def __init__(self,conn):self.db=conn
        def query(self,statement,params):return [dict(item) for item in self.db.execute(sql(statement),params)]
        def query_one(self,statement,params):
            values=self.query(statement,params);return values[0] if values else None
        def execute(self,statement,params):
            # Oracle/YashanDB reject extra named binds. Exercise that boundary.
            binds=re.sub(r"'(?:[^']|'')*'",'',statement)
            assert set(re.findall(r':([A-Za-z0-9_]+)',binds))==set(params)
            return self.db.execute(sql(statement),params).rowcount
    def transaction(callback):
        key=transaction_depth.set(transaction_depth.get()+1)
        try:
            with db() as conn:
                conn.execute('BEGIN IMMEDIATE')
                return callback(Transaction(conn))
        finally:transaction_depth.reset(key)
    def query(statement,params):
        with db() as conn:return Transaction(conn).query(statement,params)
    @contextmanager
    def install(name):
        key=selected.set(paths[name])
        try:yield
        finally:selected.reset(key)
    for path in paths.values():
        with db(path) as conn:
            conn.executescript(BASE_SCHEMA)
            for statement in model_endpoint_schema.schema_statements('pg')+model_coordinator_schema.schema_statements('pg'):
                conn.execute(statement.replace('CREATE TABLE ','CREATE TABLE IF NOT EXISTS ',1))
            conn.execute("INSERT INTO CX_PRINCIPALS VALUES('admin','ACTIVE')")
    monkeypatch.setattr(connection,'execute_transaction_callback',transaction)
    monkeypatch.setattr(connection,'execute_query',query)
    monkeypatch.setattr(connection,'execute_query_one',lambda statement,params:next(iter(query(statement,params)),None))
    monkeypatch.setattr(connection,'execute',lambda statement,params:transaction(lambda tx:tx.execute(statement,params)))
    monkeypatch.setattr(connection,'DATABASE_DIALECT','sqlite')
    monkeypatch.setattr(edition_features,'MODEL_RUNTIME_CONTEXT_ENABLED',True)
    monkeypatch.setattr(capacity,'_now_ms',lambda tx:int(time.time()*1000))
    def access(actor,action='platform.manage',**kwargs):
        if action in {'platform.manage','model_gateway.manage'} and actor!='admin':raise PermissionError('Denied')
        return {'decision':'ALLOW'}
    monkeypatch.setattr(capacity,'authorize',access)
    monkeypatch.setattr(identity_api,'effective_access',access)
    monkeypatch.setattr(identity_api,'_audit_tx',lambda tx,actor,action,family,resource,outcome,reason:tx.execute(
        'INSERT INTO AUDIT VALUES(:actor,:action_name,:resource)',dict(actor=actor,action_name=action,resource=resource)))
    monkeypatch.setattr(connection_crypto,'encrypt_section',lambda value:json.dumps(value))
    monkeypatch.setattr(connection_crypto,'decrypt_section',lambda value:json.loads(value))
    monkeypatch.setattr(provider_capability_probes,'request_parameters',lambda *_: {})
    monkeypatch.setattr(content_security,'inspect_messages',lambda *args,**kwargs:None)
    monkeypatch.setattr(content_security,'enforce',lambda *args,**kwargs:dict(ruleset_digest='synthetic-rules',decision='ALLOW'))
    # These HTTP peers use synthetic source authorities instead of native
    # Task projections. Actual native/Task adapters have their own integration
    # tests; this fixture never certifies production business authorization.
    monkeypatch.setattr(processing_recovery,'on_origin_dispatch',lambda tx,receipt:None,raising=False)
    # This synthetic installation has no native business projections. Its
    # original durable SOURCE_AUTH row is also the trusted current read policy.
    monkeypatch.setattr(origin,'authorize_receipt_read',_authorize_synthetic_receipt)
    state=SimpleNamespace(paths=paths,db=db,install=install,hold=Event(),entered=Event(),lock=Lock(),sends=0,active=0,maximum=0,mode='complete',failures=[],payloads=[],transaction_depth=transaction_depth)
    failed=model_usage_api._forward_failure
    def observe_failure(*args,**kwargs):
        state.failures.append((type(args[-1]).__name__,str(args[-1])))
        return failed(*args,**kwargs)
    monkeypatch.setattr(model_usage_api,'_forward_failure',observe_failure)
    state.hold.set()
    class Provider(BaseHTTPRequestHandler):
        protocol_version='HTTP/1.1'
        def log_message(self,*args):pass
        def do_POST(self):
            body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            state.payloads.append(body)
            with state.lock:state.sends+=1;state.active+=1;state.maximum=max(state.maximum,state.active)
            state.entered.set()
            try:
                assert state.hold.wait(10)
                if state.mode=='disconnect':self.close_connection=True;return
                value={'model':'model','choices':[{'message':{'content':'A synthetic approved fact.'},'finish_reason':'stop'}],
                    'usage':{'prompt_tokens':8,'completion_tokens':4,'total_tokens':12}}
                raw=json.dumps(value).encode()
                if body.get('stream'):
                    raw=('data: '+json.dumps({'model':'model','choices':[{'delta':{'content':'A synthetic approved fact.'},'finish_reason':None}]})+'\n\n'
                         +'data: '+json.dumps({'model':'model','choices':[{'delta':{},'finish_reason':'stop'}]})+'\n\n'
                         +'data: '+json.dumps({'model':'model','choices':[],'usage':value['usage']})+'\n\ndata: [DONE]\n\n').encode()
                self.send_response(200);self.send_header('Content-Type','text/event-stream' if body.get('stream') else 'application/json')
                self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
            finally:
                with state.lock:state.active-=1
    provider=ThreadingHTTPServer(('127.0.0.1',0),Provider)
    provider_thread=Thread(target=provider.serve_forever,daemon=True);provider_thread.start()
    provider_url=f'http://127.0.0.1:{provider.server_port}/v1'
    with install('central'):
        with db() as conn:
            conn.execute("INSERT INTO CX_LLM_PROVIDER_PROFILES VALUES('provider',1,'provider','model',?,NULL,'ACTIVE')",(provider_url,))
            for name in ('a','b'):
                conn.execute("INSERT INTO CX_PRINCIPALS VALUES(?,'ACTIVE')",('origin-'+name,))
                raw='cxgw_synthetic_'+name
                conn.execute("INSERT INTO CX_MODEL_GATEWAY_CREDENTIALS VALUES(?,?,?,?, 'ACTIVE',NULL)",
                    ('credential-'+name,'origin-'+name,common.token_digest(raw),json.dumps(['model.forward','profile:provider'])))
        group=capacity.create_group('admin',dict(resource_key='one-physical-provider',coordinator_id='selected-central-db',reason='Synthetic shared resource',idempotency_key='group'))
        state.group=group['group_id']
        for name in ('a','b'):
            capacity.register_origin('admin',state.group,dict(origin_id='installation-'+name,principal_id='origin-'+name,installation_key='product-'+name,
                reason='Authenticated independent installation',idempotency_key='origin-'+name))
        capacity.register_alias('admin',state.group,dict(endpoint_url=provider_url,profile_id='provider',expected_version=1,
            reason='One actual inference resource',idempotency_key='alias'))
        state.bindings={}
        for name in ('a','b'):
            state.bindings[name]=common.register_binding('admin',dict(group_id=state.group,expected_group_version=2,policy_revision=1,
                origin_id='installation-'+name,installation_key='product-'+name,credential_id='credential-'+name,
                profile_id='provider',profile_version=1,origin_profile_id='local-profile',origin_profile_version=1,
                reason='Explicit scoped machine enrollment',idempotency_key='binding-'+name))['binding_id']
    app=FastAPI()
    def guard(action):
        def deny():raise HTTPException(403)
        return deny
    model_coordinator_http.install(app,schema_owner_context=lambda:install('central'),require_action=guard)
    listener=socket.socket();listener.bind(('127.0.0.1',0));listener.listen()
    state.url=f'http://127.0.0.1:{listener.getsockname()[1]}'
    server=uvicorn.Server(uvicorn.Config(app,log_level='error',lifespan='off'))
    server_thread=Thread(target=lambda:server.run(sockets=[listener]),daemon=True);server_thread.start()
    for _ in range(100):
        if server.started:break
        time.sleep(.01)
    assert server.started
    state.profiles={}
    for name in ('a','b'):
        route_url=state.url+'/api/model-gateway/coordinator/'+state.bindings[name]
        profile=dict(profile_id='local-profile',version=1,profile_key='local',model_id='model',provider_url=route_url,
            api_key_cipher=json.dumps({'api_key':'cxgw_synthetic_'+name}),status='ACTIVE')
        state.profiles[name]=profile
        with install(name):
            with db() as conn:
                conn.execute("INSERT INTO CX_PRINCIPALS VALUES(?,'ACTIVE')",('local-user-'+name,))
                conn.execute("INSERT INTO CX_LLM_PROVIDER_PROFILES VALUES('local-profile',1,'local','model',?,?,'ACTIVE')",(route_url,profile['api_key_cipher']))
                conn.execute("INSERT INTO CX_RUNTIME_EXECUTIONS VALUES(?,?,7,?,'CLAIMED')",
                    ('execution-'+name,'worker-'+name,(datetime.now(timezone.utc)+timedelta(minutes=5)).isoformat()))
            common.register_route('admin',dict(profile_id='local-profile',profile_version=1,coordinator_url=route_url,
                binding_id=state.bindings[name],group_id=state.group,policy_revision=1,origin_id='installation-'+name,
                installation_key='product-'+name,coordinator_profile_id='provider',coordinator_profile_version=1,
                reason='Explicit immutable local route',idempotency_key='route'))
    @contextmanager
    def context(name,attempt='first',*,stream=False,output_limit=None):
        messages=[dict(role='user',content='Read the approved synthetic fact.')]
        payload=dict(model='model',messages=messages,stream=stream,**({'stream_options':{'include_usage':True}} if stream else {}))
        if output_limit is not None:payload['max_tokens']=output_limit
        with install(name):
            with db() as conn:
                conn.execute("INSERT OR IGNORE INTO SOURCE_AUTH VALUES(?,?,?,?,'ACTIVE')",
                    ('execution-'+name,'local-user-'+name,name*64,digest(payload)))
            def reauthorize(tx,record):
                source=tx.query_one('SELECT * FROM SOURCE_AUTH WHERE SOURCE_ID=:source',{'source':'execution-'+name})
                if (not source or source['status']!='ACTIVE' or source['actor_id']!='local-user-'+name
                        or source['credential_digest']!=name*64 or source['payload_digest']!=record['input_digest']):
                    raise PermissionError('The original synthetic source or credential was revoked')
            with model_dispatch.authenticated_context('local-user-'+name,'NATIVE','execution-'+name,'attempt-'+name+'-'+attempt,
                    credential_digest=name*64,reauthorize=reauthorize,worker_key='worker-'+name,allow_wait=False):
                yield payload
    def call(name,attempt='first',*,stream=False,budgeted=False):
        from lib import answer_context
        selection=dict(policy_revision='whole-reference-v1',stage='PREPARED_ANSWER_MESSAGES',
            budget=dict(token_budget=32768,byte_budget=131072,output_reserve=4096)) if budgeted else None
        with context(name,attempt,stream=stream,output_limit=4096 if budgeted else None) as payload:
            with answer_context.dispatch_budget(selection):
                return native_runtime._stream_llm(profile=state.profiles[name],messages=payload['messages'],on_delta=lambda _:None) if stream else native_runtime._call_llm(state.profiles[name],payload['messages'])
    def stage(name='a'):
        with context(name) as payload:
            route=origin.selected_route(state.profiles[name])
            receipt=origin.prepare(state.profiles[name],payload,model_dispatch._context.get(),route)
            envelope=origin._envelope(receipt,route)
        with install('central'):
            remote=coordinator.reserve('cxgw_synthetic_'+name,state.bindings[name],envelope)
        now=int(time.time()*1000)
        proof=DispatchProof(envelope=envelope,coordinator_request_id=remote['coordinator_request_id'],
            admission_id=remote['admission_id'],reservation_version=remote['reservation_version'],fencing_token=remote['fencing_token'],
            authorized_at_ms=now,expires_at_ms=now+common.PROOF_MS)
        return payload,proof,remote
    state.call,state.context,state.stage=call,context,stage
    try:yield state
    finally:
        state.hold.set();server.should_exit=True;server_thread.join(10);listener.close();provider.shutdown();provider.server_close();provider_thread.join(5)


def rows(peer,name,table):
    with peer.db(peer.paths[name]) as db:return [dict(value) for value in db.execute('SELECT * FROM '+table)]


def test_two_independent_origin_databases_share_actual_coordinator_http_capacity(peer):
    peer.hold.clear()
    with ThreadPoolExecutor(max_workers=2) as pool:
        first=pool.submit(peer.call,'a')
        assert peer.entered.wait(5)
        try:
            with pytest.raises(model_dispatch.ModelNotDispatched):peer.call('b')
        finally:peer.hold.set()
        assert peer.sends==peer.maximum==1
        assert rows(peer,'b','CX_MODEL_ORIGIN_RECEIPTS')[0]['status']=='KNOWN_NO_SEND'
        peer.hold.set()
        assert first.result(5)['content']=='A synthetic approved fact.'
    assert peer.call('b','second')['content']=='A synthetic approved fact.'
    assert peer.sends==2 and peer.maximum==1
    assert len(rows(peer,'central','CX_MODEL_ADMISSIONS'))==3
    assert rows(peer,'a','CX_MODEL_ADMISSIONS')==rows(peer,'b','CX_MODEL_ADMISSIONS')==[]
    requests=rows(peer,'central','CX_MODEL_COORD_REQUESTS')
    assert {item['actor_id'] for item in requests}=={'origin-a','origin-b'}
    assert {item['origin_actor_id'] for item in requests}=={'local-user-a','local-user-b'}
    assert len(rows(peer,'central','CX_MODEL_USAGE'))==2
    assert len(rows(peer,'central','CX_MODEL_RUNTIME_OBSERVATIONS'))==2
    for name in ('a','b'):
        observed=rows(peer,name,'CX_MODEL_ORIGIN_OBSERVATIONS')
        assert len(observed)==1 and observed[0]['total_tokens']==12 and observed[0]['request_complete']=='Y'
        assert observed[0]['provider_ms'] is not None and observed[0]['total_ms'] is not None
        assert rows(peer,name,'CX_MODEL_USAGE')==[]


def test_remote_origin_stream_uses_existing_native_complete_stream_contract(peer):
    try:result=peer.call('a',stream=True)
    except Exception:pytest.fail(repr(peer.failures))
    assert result['content']=='A synthetic approved fact.'
    assert peer.sends==1 and rows(peer,'a','CX_MODEL_ORIGIN_RECEIPTS')[0]['status']=='COMPLETED'


@pytest.mark.parametrize('stream',[False,True])
def test_answer_budget_and_exact_output_limit_survive_actual_coordinator_http(peer,stream):
    result=peer.call('a',stream=stream,budgeted=True)
    assert peer.sends==1 and peer.payloads[0]['max_tokens']==4096
    assert peer.payloads[0]['stream'] is stream
    receipt=result['provider_input_budget']
    import hashlib
    raw=json.dumps(peer.payloads[0],ensure_ascii=False).encode()
    assert receipt['input_digest']==hashlib.sha256(raw).hexdigest()
    assert receipt['input_bytes']==len(raw)
    assert result['usage_observation']=='PROVIDER_REPORTED'
    assert receipt['scope']=='SERIALIZED_INPUT_NOT_PROVIDER_REPORTED_USAGE'


@pytest.mark.parametrize('mutation',[
    "UPDATE SOURCE_AUTH SET STATUS='REVOKED'",
    "UPDATE SOURCE_AUTH SET CREDENTIAL_DIGEST='replaced'",
    "UPDATE CX_PRINCIPALS SET STATUS='REVOKED' WHERE PRINCIPAL_ID='local-user-a'",
    "UPDATE CX_RUNTIME_EXECUTIONS SET FENCING_TOKEN=8",
    "UPDATE CX_RUNTIME_EXECUTIONS SET LEASE_EXPIRES_AT='2000-01-01'",
    "DELETE FROM CX_RUNTIME_EXECUTIONS",
    "UPDATE CX_MODEL_COORD_ROUTES SET STATUS='REVOKED',VERSION=2",
    "UPDATE CX_LLM_PROVIDER_PROFILES SET VERSION=2",
    "UPDATE CX_LLM_PROVIDER_PROFILES SET PROVIDER_URL='http://127.0.0.1:1/direct'",
    "UPDATE CX_LLM_PROVIDER_PROFILES SET API_KEY_CIPHER='{}'",
])
def test_last_origin_transaction_denies_revoked_or_fenced_source_after_central_reservation(peer,monkeypatch,mutation):
    original=origin._peer
    def intercept(*args,**kwargs):
        value=original(*args,**kwargs)
        if args[1]=='/reservations':
            with peer.db(peer.paths['a']) as db:db.execute(mutation)
        return value
    monkeypatch.setattr(origin,'_peer',intercept)
    with pytest.raises(model_dispatch.ModelNotDispatched):peer.call('a')
    assert peer.sends==0
    assert rows(peer,'a','CX_MODEL_ORIGIN_RECEIPTS')[0]['status']=='KNOWN_NO_SEND'
    assert rows(peer,'central','CX_MODEL_ADMISSIONS')[0]['status']=='CANCELLED'


@pytest.mark.parametrize('mutation',[
    "UPDATE CX_MODEL_GATEWAY_CREDENTIALS SET STATUS='REVOKED' WHERE CREDENTIAL_ID='credential-a'",
    "UPDATE CX_MODEL_GATEWAY_CREDENTIALS SET SCOPES_JSON='[]' WHERE CREDENTIAL_ID='credential-a'",
    "UPDATE CX_MODEL_CAP_ORIGINS SET STATUS='REVOKED' WHERE ORIGIN_ID='installation-a'",
    "UPDATE CX_MODEL_COORD_BINDINGS SET VERSION=2 WHERE ORIGIN_ID='installation-a'",
    "UPDATE CX_LLM_PROVIDER_PROFILES SET VERSION=2",
])
def test_central_rechecks_original_enrollment_before_provider_send(peer,mutation):
    payload,proof,remote=peer.stage()
    with peer.install('central'):
        with peer.db() as db:db.execute(mutation)
        with pytest.raises(PermissionError):coordinator.complete('cxgw_synthetic_a',peer.bindings['a'],common.encode_proof(proof,'cxgw_synthetic_a'),payload)
    assert peer.sends==0


@pytest.mark.parametrize('field,value',[
    ('payload_digest','f'*64),('origin_actor_id','forged-local-actor'),('origin_profile_version',2),
    ('profile_version',2),('policy_revision',2),('origin_fencing_token',8),('worker_key','different-worker'),
])
def test_signed_proof_cannot_change_frozen_original_envelope(peer,field,value):
    payload,proof,remote=peer.stage()
    proof=proof.model_copy(update={'envelope':proof.envelope.model_copy(update={field:value})})
    with peer.install('central'):
        with pytest.raises(PermissionError):coordinator.complete('cxgw_synthetic_a',peer.bindings['a'],common.encode_proof(proof,'cxgw_synthetic_a'),payload)
    assert peer.sends==0


@pytest.mark.parametrize('field,value',[
    ('expires_at_ms',1),('authorized_at_ms',1),('fencing_token',99),('reservation_version',99),('admission_id','different-admission'),
])
def test_expired_or_fenced_proof_never_sends(peer,field,value):
    payload,proof,remote=peer.stage()
    proof=proof.model_copy(update={field:value})
    with peer.install('central'):
        with pytest.raises((PermissionError,model_dispatch.ModelNotDispatched)):
            coordinator.complete('cxgw_synthetic_a',peer.bindings['a'],common.encode_proof(proof,'cxgw_synthetic_a'),payload)
    assert peer.sends==0


def test_completed_proof_replays_same_snapshot_inside_current_authorization_transaction(peer,monkeypatch):
    from lib import model_governance_api
    payload,proof,remote=peer.stage()
    encoded=common.encode_proof(proof,'cxgw_synthetic_a')
    with peer.install('central'):
        first=coordinator.complete('cxgw_synthetic_a',peer.bindings['a'],encoded,payload)
        actual=model_governance_api.replay_snapshot
        def replay(request_id,*,transaction=None):
            assert transaction is not None
            return actual(request_id,transaction=transaction)
        monkeypatch.setattr(model_governance_api,'replay_snapshot',replay)
        second=coordinator.complete('cxgw_synthetic_a',peer.bindings['a'],encoded,payload)
        assert second=={**first,'replayed':True}
        with peer.db() as db:db.execute("UPDATE CX_MODEL_GATEWAY_CREDENTIALS SET STATUS='REVOKED' WHERE CREDENTIAL_ID='credential-a'")
        with pytest.raises(PermissionError):coordinator.complete('cxgw_synthetic_a',peer.bindings['a'],encoded,payload)
    assert peer.sends==1
    assert len(rows(peer,'central','CX_MODEL_USAGE'))==1


def test_unknown_provider_disconnect_retains_shared_occupancy_and_never_automatically_resends(peer):
    peer.mode='disconnect'
    with pytest.raises(Exception) as failed:peer.call('a')
    assert not getattr(failed.value,'model_not_dispatched',False)
    assert rows(peer,'a','CX_MODEL_ORIGIN_RECEIPTS')[0]['status']=='UNKNOWN'
    assert rows(peer,'central','CX_MODEL_COORD_REQUESTS')[0]['status']=='UNKNOWN'
    assert rows(peer,'central','CX_MODEL_ADMISSIONS')[0]['status']=='UNKNOWN'
    observed=rows(peer,'a','CX_MODEL_ORIGIN_OBSERVATIONS')[0]
    assert observed['result_state']=='UNKNOWN' and observed['request_complete']=='N'
    assert all(observed[field] is None for field in observations.COUNTS)
    with pytest.raises(ContinuityConflict) as repeated:peer.call('a')
    assert repeated.value.code=='UNKNOWN_SEND' and not getattr(repeated.value,'model_not_dispatched',False)
    with pytest.raises(model_dispatch.ModelNotDispatched):peer.call('b')
    assert peer.sends==1


def test_status_is_read_only_and_survives_profile_and_policy_revision_change(peer):
    payload,proof,remote=peer.stage()
    with peer.install('central'):
        with peer.db() as db:
            db.execute('UPDATE CX_LLM_PROVIDER_PROFILES SET VERSION=2')
            db.execute('UPDATE CX_MODEL_CAP_GROUPS SET VERSION=3,CURRENT_REVISION=2')
            db.execute('INSERT INTO CX_MODEL_CAP_REVISIONS SELECT GROUP_ID,2,CAPACITY,QUEUE_MS,SOCKET_MS,IDLE_MS,OVERALL_MS,'
                'RESERVATION_MS,CREATED_BY,REASON,CREATED_AT_MS FROM CX_MODEL_CAP_REVISIONS WHERE REVISION_NO=1')
        tables=('CX_MODEL_COORD_REQUESTS','CX_MODEL_ADMISSIONS','CX_MODEL_CAP_ATTEMPTS','CX_MODEL_CAP_REQUESTS','AUDIT')
        before={table:rows(peer,'central',table) for table in tables}
        assert coordinator.read_request('cxgw_synthetic_a',peer.bindings['a'],remote['coordinator_request_id'])['status']=='RESERVED'
        with pytest.raises(PermissionError):coordinator.read_request('cxgw_synthetic_b',peer.bindings['a'],remote['coordinator_request_id'])
        assert before=={table:rows(peer,'central',table) for table in tables}
    assert peer.sends==0


def test_final_origin_audit_failure_rolls_back_authorization_and_cancels_unused_reservation(peer,monkeypatch):
    audit=identity_api._audit_tx
    def fail(tx,actor,action,*args):
        if action=='MODEL_ORIGIN_FINAL_AUTH':raise RuntimeError('Synthetic audit failure')
        return audit(tx,actor,action,*args)
    monkeypatch.setattr(identity_api,'_audit_tx',fail)
    with pytest.raises(model_dispatch.ModelNotDispatched):peer.call('a')
    receipt=rows(peer,'a','CX_MODEL_ORIGIN_RECEIPTS')[0]
    assert receipt['status']=='KNOWN_NO_SEND' and receipt['proof_digest'] is None
    assert rows(peer,'central','CX_MODEL_ADMISSIONS')[0]['status']=='CANCELLED'
    assert peer.sends==0


@pytest.mark.parametrize('source_kind',['NATIVE','CHANNEL','RETROSPECTIVE','EVALUATION'])
def test_worker_sources_without_original_durable_attempt_never_borrow_synchronous_fence(peer,source_kind):
    with peer.install('a'):
        with peer.db() as db:db.execute('DELETE FROM CX_RUNTIME_EXECUTIONS')
        context=SimpleNamespace(source_kind=source_kind,source_id='execution-a',source_attempt_id='attempt-a-first',worker_key='worker-a')
        with pytest.raises(PermissionError):connection.execute_transaction_callback(lambda tx:origin._source_fence(tx,context))
    assert peer.sends==0


@pytest.mark.parametrize('mutation',[
    "UPDATE CX_TASK_CONTINUITY_LEASES SET FENCING_TOKEN=8",
    "UPDATE CX_TASK_CONTINUITY_LEASES SET LEASE_EXPIRES_AT='2000-01-01'",
    "UPDATE CX_TASK_CONTINUITY_ATTEMPTS SET LEASE_EXPIRES_AT='2000-01-01'",
    "UPDATE CX_TASK_CONTINUITY_LEASES SET LEASE_OWNER='replacement'",
])
def test_task_receipt_requires_same_live_attempt_and_current_lease_fence(peer,mutation):
    with peer.install('a'):
        with peer.db() as db:
            expiry=(datetime.now(timezone.utc)+timedelta(minutes=5)).isoformat()
            db.execute("INSERT INTO CX_TASK_CONTINUITY_ATTEMPTS VALUES('task-attempt','task',7,?,'SENDING')",(expiry,))
            db.execute("INSERT INTO CX_TASK_CONTINUITY_LEASES VALUES('task','worker-a','ACTIVE',7,?)",(expiry,))
            db.execute(mutation)
        context=SimpleNamespace(source_kind='RETROSPECTIVE',source_id='task',source_attempt_id='task-attempt',worker_key='worker-a')
        with pytest.raises(PermissionError):connection.execute_transaction_callback(lambda tx:origin._source_fence(tx,context))


def test_duplicate_reservation_and_concurrent_same_proof_never_create_a_second_send(peer):
    payload,proof,remote=peer.stage()
    with peer.install('central'):
        again=coordinator.reserve('cxgw_synthetic_a',peer.bindings['a'],proof.envelope)
        assert again['coordinator_request_id']==remote['coordinator_request_id'] and again['admission_id']==remote['admission_id']
    peer.hold.clear()
    def complete():
        with peer.install('central'):
            return coordinator.complete('cxgw_synthetic_a',peer.bindings['a'],common.encode_proof(proof,'cxgw_synthetic_a'),payload)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first=pool.submit(complete)
        try:
            assert peer.entered.wait(5)
            with pytest.raises(ContinuityConflict) as repeated:complete()
            assert repeated.value.code=='UNKNOWN_SEND' and not getattr(repeated.value,'model_not_dispatched',False)
        finally:peer.hold.set()
        assert first.result(5)['choices'][0]['message']['content']=='A synthetic approved fact.'
    assert peer.sends==1 and len(rows(peer,'central','CX_MODEL_ADMISSIONS'))==1


def _independent_origin_process(path,profile,name,result,foreign_config):
    """A fresh process with its own DB connections, facade and Origin context."""
    def sql(value):return re.sub(r'FETCH FIRST (:[A-Za-z0-9_]+|[0-9]+) ROWS ONLY',r'LIMIT \1',value.replace(' FOR UPDATE',''))
    class Transaction:
        def __init__(self,db):self.db=db
        def query(self,statement,params):return [dict(item) for item in self.db.execute(sql(statement),params)]
        def query_one(self,statement,params):return next(iter(self.query(statement,params)),None)
        def execute(self,statement,params):return self.db.execute(sql(statement),params).rowcount
    def db():
        conn=sqlite3.connect(path,timeout=10)
        conn.row_factory=lambda cursor,values:{item[0].lower():content for item,content in zip(cursor.description,values)}
        conn.execute('PRAGMA foreign_keys=ON')
        return conn
    def transaction(callback):
        with db() as conn:
            conn.execute('BEGIN IMMEDIATE')
            return callback(Transaction(conn))
    def query(statement,params):
        with db() as conn:return Transaction(conn).query(statement,params)
    with pytest.MonkeyPatch.context() as patch:
        # The selected adapter has already been imported by spawn. Keep the
        # deliberately unusable ambient config for the actual Origin call.
        patch.setenv('CX_CONFIG_PATH',foreign_config)
        patch.setattr(connection,'execute_transaction_callback',transaction)
        patch.setattr(connection,'execute_query',query)
        patch.setattr(connection,'execute_query_one',lambda statement,params:next(iter(query(statement,params)),None))
        patch.setattr(connection,'execute',lambda statement,params:transaction(lambda tx:tx.execute(statement,params)))
        patch.setattr(connection,'DATABASE_DIALECT','sqlite')
        patch.setattr(capacity,'_now_ms',lambda tx:int(time.time()*1000))
        patch.setattr(edition_features,'MODEL_RUNTIME_CONTEXT_ENABLED',True)
        patch.setattr(connection_crypto,'decrypt_section',lambda value:json.loads(value))
        # Spawned package tests inherit the native harness's encrypted config.
        # This synthetic Origin uses JSON fixture secrets, so its local socket
        # setting must not invoke native configuration/key discovery. Capacity
        # and all actual HTTP deadlines still come from the synthetic ledger.
        patch.setattr(native_runtime,'request_timeout_seconds',lambda:180)
        patch.setattr(provider_capability_probes,'request_parameters',lambda *_:{})
        patch.setattr(content_security,'inspect_messages',lambda *args,**kwargs:None)
        patch.setattr(content_security,'enforce',lambda *args,**kwargs:dict(ruleset_digest='synthetic-rules',decision='ALLOW'))
        patch.setattr(processing_recovery,'on_origin_dispatch',lambda tx,receipt:None,raising=False)
        patch.setattr(identity_api,'_audit_tx',lambda tx,actor,action,family,resource,outcome,reason:tx.execute(
            'INSERT INTO AUDIT VALUES(:actor,:action_name,:resource)',dict(actor=actor,action_name=action,resource=resource)))
        def reauthorize(tx,record):
            source=tx.query_one('SELECT * FROM SOURCE_AUTH WHERE SOURCE_ID=:source',{'source':'execution-'+name})
            if (not source or source['status']!='ACTIVE' or source['credential_digest']!=name*64
                    or source['actor_id']!='local-user-'+name or source['payload_digest']!=record['input_digest']):
                raise PermissionError('Synthetic source authorization denied')
        try:
            with model_dispatch.authenticated_context('local-user-'+name,'NATIVE','execution-'+name,'process-'+name,
                    credential_digest=name*64,reauthorize=reauthorize,worker_key='worker-'+name,allow_wait=False):
                value=native_runtime._call_llm(profile,[dict(role='user',content='Read the approved synthetic fact.')])
            result.send({'status':'COMPLETED','content':value['content']})
        except Exception as exc:
            result.send({'status':'KNOWN_NO_SEND' if getattr(exc,'model_not_dispatched',False) else 'UNCONFIRMED',
                'code':getattr(exc,'code',type(exc).__name__)})
        finally:result.close()


def test_independent_origin_processes_share_one_http_coordinator_and_one_actual_provider_slot(peer,monkeypatch):
    # Spawn (not fork): the clients inherit no server threads or Python mocks.
    # Preserve a package harness's ambient config boundary in this regression:
    # the synthetic child must not decrypt or connect using that native config.
    foreign_config=peer.paths['a'].parent/'unrelated-encrypted-host-config.json'
    foreign_config.write_text(json.dumps({'database':{'_encrypted':'synthetic-native-ciphertext-not-json'}}))
    monkeypatch.setenv('CX_CONFIG_PATH',str(foreign_config))
    # A unified package selects its adapter while importing this module in a
    # spawned child, before its target function can install synthetic patches.
    # Supply only a non-secret selector at that bootstrap boundary; the child
    # restores the unusable config before exercising the real Origin route.
    selector_config=peer.paths['a'].parent/'spawn-backend-selector.json'
    selector_config.write_text(json.dumps({'database':{'type':os.environ.get('CX_DATABASE_DIALECT') or 'pg'}}))
    process=multiprocessing.get_context('spawn')
    for name in ('a','b'):
        with peer.context(name):pass
    first_reader,first_writer=process.Pipe(duplex=False)
    second_reader,second_writer=process.Pipe(duplex=False)
    first=process.Process(target=_independent_origin_process,args=(str(peer.paths['a']),peer.profiles['a'],'a',first_writer,str(foreign_config)))
    second=process.Process(target=_independent_origin_process,args=(str(peer.paths['b']),peer.profiles['b'],'b',second_writer,str(foreign_config)))
    peer.hold.clear()
    with monkeypatch.context() as bootstrap:
        bootstrap.setenv('CX_CONFIG_PATH',str(selector_config))
        first.start()
    try:
        entered=peer.entered.wait(10)
        assert entered, first_reader.recv() if first_reader.poll(1) else {'status':'NO_PROVIDER_OBSERVATION','exit_code':first.exitcode}
        with monkeypatch.context() as bootstrap:
            bootstrap.setenv('CX_CONFIG_PATH',str(selector_config))
            second.start()
        second.join(10)
        assert second.exitcode==0 and second_reader.poll(1)
        assert second_reader.recv()['status']=='KNOWN_NO_SEND'
        assert peer.sends==peer.maximum==1
    finally:
        peer.hold.set();first.join(10)
        for client in (first,second):
            if client.is_alive():client.terminate();client.join(3)
        first_writer.close();second_writer.close()
    assert first.exitcode==0 and first_reader.poll(1)
    assert first_reader.recv()=={'status':'COMPLETED','content':'A synthetic approved fact.'}
    assert rows(peer,'a','CX_MODEL_ADMISSIONS')==rows(peer,'b','CX_MODEL_ADMISSIONS')==[]
    assert peer.maximum==1


@pytest.mark.parametrize('stage',['usage','replay'])
def test_completed_accounting_or_replay_failure_exposes_safe_facts_without_answer_and_never_resends(peer,monkeypatch,stage):
    from lib import model_governance_api
    from lib.model_results import ModelResultError
    payload,proof,remote=peer.stage()
    def reject(*args,**kwargs):raise RuntimeError('Synthetic private storage detail')
    monkeypatch.setattr(model_usage_api if stage=='usage' else model_governance_api,
        '_write_usage' if stage=='usage' else 'finalize_replayable_success',reject)
    with peer.install('central'):
        with pytest.raises(ModelResultError) as failed:
            coordinator.complete('cxgw_synthetic_a',peer.bindings['a'],common.encode_proof(proof,'cxgw_synthetic_a'),payload)
        assert failed.value.request_complete
        assert failed.value.observation['usage']['total_tokens']==12
        assert set(failed.value.observation)=={'model','request_complete','usage','usage_observation','usage_field_provenance'}
        assert 'synthetic approved fact' not in repr(failed.value.observation)
        assert 'private storage' not in str(failed.value)
        assert failed.value.model_ledger_failed==(stage=='usage')
        assert coordinator.read_request('cxgw_synthetic_a',peer.bindings['a'],remote['coordinator_request_id'])['status']=='COMPLETED'
    assert rows(peer,'central','CX_MODEL_ADMISSIONS')[0]['status']=='COMPLETED'
    assert rows(peer,'central','CX_MODEL_REQUESTS')[0]['status']=='FAILED'
    assert len(rows(peer,'central','CX_MODEL_USAGE'))==(0 if stage=='usage' else 1)
    assert peer.sends==1


def test_http_machine_auth_and_enrollment_cannot_be_replaced_by_foreign_actor_claim(peer):
    payload,proof,remote=peer.stage()
    endpoint=peer.url+'/api/model-gateway/coordinator/'+peer.bindings['a']+'/reservations'
    for credential,status in [('',401),('cxgw_synthetic_b',403),('cxgw_unknown',403)]:
        request=urllib.request.Request(endpoint,data=json.dumps(proof.envelope.model_dump(mode='json')).encode(),
            headers={'Content-Type':'application/json',**({'Authorization':'Bearer '+credential} if credential else {})})
        with pytest.raises(urllib.error.HTTPError) as failed:urllib.request.urlopen(request,timeout=5)
        assert failed.value.code==status
        assert failed.value.headers.get('X-Chuanxu-Coordinator-No-Send') is None
    with peer.install('central'):
        with peer.db() as db:
            db.execute("INSERT INTO CX_MODEL_GATEWAY_CREDENTIALS VALUES('replacement','origin-a',?,?, 'ACTIVE',NULL)",
                (common.token_digest('cxgw_replacement'),json.dumps(['model.forward','profile:provider'])))
        with pytest.raises(PermissionError):coordinator.reserve('cxgw_replacement',peer.bindings['a'],proof.envelope)
    assert peer.sends==0


def test_registration_rejects_invalid_machine_scopes_before_creating_enrollment(peer):
    with peer.install('central'):
        with peer.db() as db:db.execute("UPDATE CX_MODEL_GATEWAY_CREDENTIALS SET SCOPES_JSON='[\"model.forward\",\"profile:other\"]' WHERE CREDENTIAL_ID='credential-a'")
        with pytest.raises(PermissionError):common.register_binding('admin',dict(group_id=peer.group,expected_group_version=2,policy_revision=1,
            origin_id='installation-a',installation_key='product-a',credential_id='credential-a',profile_id='provider',profile_version=1,
            origin_profile_id='local-profile',origin_profile_version=1,reason='Rejected unrelated scopes',idempotency_key='invalid-scopes'))
    assert len(rows(peer,'central','CX_MODEL_COORD_BINDINGS'))==2 and peer.sends==0


def test_origin_observations_read_actual_usage_under_current_original_source_authorization(peer):
    peer.call('a')
    def authorize(tx,actor,source):
        value=tx.query_one('SELECT * FROM SOURCE_AUTH WHERE SOURCE_ID=:source',{'source':source})
        if not value or value['status']!='ACTIVE' or value['actor_id']!=actor:raise PermissionError('Source unavailable')
    with peer.install('a'):
        result=observations.read_for_source('local-user-a','NATIVE','execution-a',authorize_source=authorize)
        assert len(result)==1 and result[0]['total_tokens']==12 and result[0]['source_attempt_id']=='attempt-a-first'
        assert result[0]['result_state']=='COMPLETED' and result[0]['usage_provenance']=='PROVIDER_REPORTED'
        receipt=rows(peer,'a','CX_MODEL_ORIGIN_RECEIPTS')[0]
        assert origin.read_receipt('local-user-a',receipt['origin_receipt_id'])['observation']['total_tokens']==12
        with pytest.raises(PermissionError):observations.read_for_source('local-user-b','NATIVE','execution-a',authorize_source=authorize)
        with peer.db() as db:db.execute("UPDATE SOURCE_AUTH SET STATUS='REVOKED'")
        with pytest.raises(PermissionError):observations.read_for_source('local-user-a','NATIVE','execution-a',authorize_source=authorize)
        with pytest.raises(PermissionError):origin.read_receipt('local-user-a',receipt['origin_receipt_id'])
    assert peer.sends==1 and rows(peer,'a','CX_MODEL_USAGE')==[]


def test_origin_observation_insert_failure_rolls_back_completed_local_receipt_and_preserves_no_resend(peer,monkeypatch):
    def fail(*args):raise RuntimeError('Synthetic observation store failure')
    monkeypatch.setattr(observations,'persist',fail)
    with pytest.raises(Exception) as failed:peer.call('a')
    assert getattr(failed.value,'model_ledger_failed',False)
    assert rows(peer,'a','CX_MODEL_ORIGIN_RECEIPTS')[0]['status']=='DISPATCHING'
    assert rows(peer,'a','CX_MODEL_ORIGIN_OBSERVATIONS')==[]
    assert rows(peer,'central','CX_MODEL_COORD_REQUESTS')[0]['status']=='COMPLETED'
    with pytest.raises(ContinuityConflict) as repeated:peer.call('a')
    assert repeated.value.code=='UNKNOWN_SEND' and not getattr(repeated.value,'model_not_dispatched',False)
    assert peer.sends==1


def test_completed_central_rejection_retains_measured_usage_in_original_origin_receipt(peer,monkeypatch):
    from lib.model_results import ModelResultError
    def fail(*args,**kwargs):raise RuntimeError('Synthetic accounting store failure')
    monkeypatch.setattr(model_usage_api,'_write_usage',fail)
    with pytest.raises(ModelResultError) as failed:peer.call('a')
    assert failed.value.request_complete and failed.value.observation['usage']['total_tokens']==12
    assert 'content' not in failed.value.observation and 'tool_calls' not in failed.value.observation
    observed=rows(peer,'a','CX_MODEL_ORIGIN_OBSERVATIONS')[0]
    assert observed['request_complete']=='Y' and observed['result_state']=='REJECTED' and observed['total_tokens']==12
    assert rows(peer,'a','CX_MODEL_USAGE')==[] and peer.sends==1


def test_unobserved_origin_receipt_does_not_invent_zero_usage(peer):
    payload,proof,remote=peer.stage()
    receipt=rows(peer,'a','CX_MODEL_ORIGIN_RECEIPTS')[0]
    with peer.install('a'):
        assert origin.read_receipt('local-user-a',receipt['origin_receipt_id'])['observation'] is None
    assert peer.sends==0


def _unknown_and_operator_resolution(peer,*,resolve=True):
    peer.mode='disconnect'
    with pytest.raises(Exception):peer.call('a')
    receipt=rows(peer,'a','CX_MODEL_ORIGIN_RECEIPTS')[0]
    if resolve:
        with peer.install('central'):
            admitted=capacity.read_admission('origin-a',receipt['admission_id'])
            capacity.observe_completion('admin',admitted['admission_id'],dict(expected_version=admitted['version'],attempt_id=admitted['attempt_id'],
                fencing_token=admitted['fencing_token'],evidence_digest='e'*64,evidence_kind='OPERATOR_CONFIRMATION',
                finish_code='OPERATOR_CONFIRMED_TERMINATED',reason='Synthetic independently verified termination',idempotency_key='operator-resolved'),reconcile=True)
    return receipt,dict(expected_version=receipt['version'],reason='Read exact registered coordinator evidence',idempotency_key='origin-resolved')


def _authorize_synthetic_receipt(tx,actor,receipt):
    value=tx.query_one('SELECT * FROM SOURCE_AUTH WHERE SOURCE_ID=:source',{'source':receipt['source_id']})
    if (not value or value['status']!='ACTIVE' or value['actor_id']!=actor or receipt['actor_id']!=actor
            or value['credential_digest']!=receipt['original_credential_digest'] or value['payload_digest']!=receipt['payload_digest']):
        raise PermissionError('The original synthetic source or credential was revoked')


def test_explicit_remote_resolution_records_exact_terminal_evidence_without_approving_unknown_output(peer,monkeypatch):
    receipt,request=_unknown_and_operator_resolution(peer)
    original_observations=rows(peer,'a','CX_MODEL_ORIGIN_OBSERVATIONS')
    with peer.install('central'):
        central=coordinator.read_request('cxgw_synthetic_a',peer.bindings['a'],receipt['coordinator_request_id'])
        assert central['status']=='UNKNOWN' and not central['request_complete']
        assert central['transport_resolution']['evidence_kind']=='OPERATOR_CONFIRMATION'
    original=origin._peer
    def bounded(*args,**kwargs):
        assert peer.transaction_depth.get()==0
        assert kwargs.get('method')=='GET' and '/requests/' in args[1]
        return original(*args,**kwargs)
    monkeypatch.setattr(origin,'_peer',bounded)
    with peer.install('a'):
        result=origin.reconcile_receipt('local-user-a',receipt['origin_receipt_id'],request,authorize_source=_authorize_synthetic_receipt)
        assert result['status']=='RESOLVED' and not result['content_approved'] and not result['replay_allowed']
        assert result['resolution']['request_complete']=='N'
        assert result['resolution']['resolution_kind']=='TRANSPORT_TERMINATED'
        assert connection.execute_transaction_callback(lambda tx:origin.resolution_for_receipt(tx,receipt))
        again=origin.reconcile_receipt('local-user-a',receipt['origin_receipt_id'],request,authorize_source=_authorize_synthetic_receipt)
        assert again['replayed'] and again['resolution']==result['resolution']
    assert rows(peer,'a','CX_MODEL_ORIGIN_RECEIPTS')[0]['status']=='UNKNOWN'
    assert rows(peer,'a','CX_MODEL_ORIGIN_OBSERVATIONS')==original_observations
    assert len(rows(peer,'a','CX_MODEL_ORIGIN_RESOLUTIONS'))==1 and peer.sends==1


def test_explicit_remote_read_preserves_unknown_until_central_transport_really_terminates(peer):
    receipt,request=_unknown_and_operator_resolution(peer,resolve=False)
    before=rows(peer,'a','CX_MODEL_ORIGIN_RECEIPTS')
    with peer.install('a'):
        result=origin.reconcile_receipt('local-user-a',receipt['origin_receipt_id'],request,authorize_source=_authorize_synthetic_receipt)
    assert result['status']=='UNKNOWN' and result['resolution'] is None
    assert rows(peer,'a','CX_MODEL_ORIGIN_RESOLUTIONS')==[] and rows(peer,'a','CX_MODEL_ORIGIN_RECEIPTS')==before
    assert rows(peer,'central','CX_MODEL_ADMISSIONS')[0]['status']=='UNKNOWN' and peer.sends==1


@pytest.mark.parametrize('mutation',[
    "UPDATE SOURCE_AUTH SET STATUS='REVOKED'",
    "UPDATE SOURCE_AUTH SET CREDENTIAL_DIGEST='replacement'",
    "UPDATE CX_MODEL_COORD_ROUTES SET STATUS='REVOKED',VERSION=2",
])
def test_remote_resolution_final_transaction_rechecks_source_credential_and_frozen_route(peer,monkeypatch,mutation):
    receipt,request=_unknown_and_operator_resolution(peer)
    original=origin._peer
    def revoke(*args,**kwargs):
        value=original(*args,**kwargs)
        with peer.db(peer.paths['a']) as db:db.execute(mutation)
        return value
    monkeypatch.setattr(origin,'_peer',revoke)
    with peer.install('a'):
        with pytest.raises(PermissionError):origin.reconcile_receipt('local-user-a',receipt['origin_receipt_id'],request,authorize_source=_authorize_synthetic_receipt)
    assert rows(peer,'a','CX_MODEL_ORIGIN_RESOLUTIONS')==[] and peer.sends==1


def test_remote_resolution_rejects_replacement_central_credential_and_foreign_local_receipt(peer):
    receipt,request=_unknown_and_operator_resolution(peer)
    with peer.install('a'):
        with pytest.raises(PermissionError):origin.reconcile_receipt('local-user-b',receipt['origin_receipt_id'],request,authorize_source=_authorize_synthetic_receipt)
    with peer.db(peer.paths['central']) as db:db.execute("UPDATE CX_MODEL_GATEWAY_CREDENTIALS SET STATUS='REVOKED' WHERE CREDENTIAL_ID='credential-a'")
    with peer.install('a'):
        with pytest.raises(urllib.error.HTTPError):origin.reconcile_receipt('local-user-a',receipt['origin_receipt_id'],request,authorize_source=_authorize_synthetic_receipt)
    assert rows(peer,'a','CX_MODEL_ORIGIN_RESOLUTIONS')==[] and peer.sends==1


@pytest.mark.parametrize('field,value',[('admission_id','foreign-admission'),('fencing_token',99),('origin_receipt_id','foreign-receipt'),('envelope_digest','f'*64)])
def test_remote_resolution_rejects_mismatched_peer_terminal_evidence(peer,monkeypatch,field,value):
    receipt,request=_unknown_and_operator_resolution(peer)
    original=origin._peer
    def mismatch(*args,**kwargs):
        response=original(*args,**kwargs)
        response['transport_resolution'][field]=value
        return response
    monkeypatch.setattr(origin,'_peer',mismatch)
    with peer.install('a'):
        with pytest.raises(PermissionError):origin.reconcile_receipt('local-user-a',receipt['origin_receipt_id'],request,authorize_source=_authorize_synthetic_receipt)
    assert rows(peer,'a','CX_MODEL_ORIGIN_RESOLUTIONS')==[] and peer.sends==1


def test_explicit_resolution_of_unused_cancelled_reservation_is_known_no_send_without_zero_usage(peer):
    payload,proof,remote=peer.stage()
    with peer.install('central'):coordinator.cancel_reservation('cxgw_synthetic_a',peer.bindings['a'],remote['coordinator_request_id'])
    with peer.install('a'):
        def uncertain(tx):
            receipt=origin._receipt(tx,proof.envelope.origin_receipt_id)
            origin._state(tx,receipt,'UNKNOWN','SYNTHETIC_LOCAL_EXIT',coordinator_request_id=remote['coordinator_request_id'],
                admission_id=remote['admission_id'],remote_fencing_token=remote['fencing_token'],remote_reservation_version=remote['reservation_version'])
            return receipt
        receipt=connection.execute_transaction_callback(uncertain)
        result=origin.reconcile_receipt('local-user-a',receipt['origin_receipt_id'],dict(expected_version=receipt['version'],
            reason='Verify exact cancelled unused reservation',idempotency_key='unused-resolution'),authorize_source=_authorize_synthetic_receipt)
        assert result['resolution']['resolution_kind']=='KNOWN_NO_SEND'
        assert result['resolution']['attempt_id'] is None and result['resolution']['fencing_token']==remote['fencing_token']
        assert result['resolution']['request_complete']=='N' and not result['content_approved']
        assert origin.read_receipt('local-user-a',receipt['origin_receipt_id'])['observation'] is None
    assert rows(peer,'a','CX_MODEL_ORIGIN_RECEIPTS')[0]['status']=='UNKNOWN'
    assert peer.sends==0


def test_remote_resolution_audit_failure_rolls_back_receipt_and_resolution_together(peer,monkeypatch):
    receipt,request=_unknown_and_operator_resolution(peer)
    before=rows(peer,'a','CX_MODEL_ORIGIN_RECEIPTS')
    audit=identity_api._audit_tx
    def fail(tx,actor,action,*args):
        if action=='MODEL_ORIGIN_RECONCILE':raise RuntimeError('Synthetic audit failure')
        return audit(tx,actor,action,*args)
    monkeypatch.setattr(identity_api,'_audit_tx',fail)
    with peer.install('a'):
        with pytest.raises(RuntimeError):origin.reconcile_receipt('local-user-a',receipt['origin_receipt_id'],request,authorize_source=_authorize_synthetic_receipt)
    assert rows(peer,'a','CX_MODEL_ORIGIN_RESOLUTIONS')==[] and rows(peer,'a','CX_MODEL_ORIGIN_RECEIPTS')==before
    assert peer.sends==1


def test_repeated_explicit_resolution_still_rechecks_current_original_credential(peer):
    receipt,request=_unknown_and_operator_resolution(peer)
    with peer.install('a'):
        assert origin.reconcile_receipt('local-user-a',receipt['origin_receipt_id'],request,authorize_source=_authorize_synthetic_receipt)['status']=='RESOLVED'
        with peer.db() as db:db.execute("UPDATE SOURCE_AUTH SET STATUS='REVOKED'")
        with pytest.raises(PermissionError):origin.reconcile_receipt('local-user-a',receipt['origin_receipt_id'],request,authorize_source=_authorize_synthetic_receipt)
    assert len(rows(peer,'a','CX_MODEL_ORIGIN_RESOLUTIONS'))==1 and peer.sends==1


def test_central_quota_rejection_is_confirmed_no_send_without_inventing_usage(peer,monkeypatch):
    from lib import model_governance_api
    def deny(*args,**kwargs):raise model_governance_api.ModelGovernanceError('Synthetic quota rejection')
    monkeypatch.setattr(model_governance_api,'reserve_quota',deny)
    with pytest.raises(model_dispatch.ModelNotDispatched):peer.call('a')
    assert rows(peer,'central','CX_MODEL_REQUESTS')[0]['status']=='FAILED'
    assert rows(peer,'central','CX_MODEL_REQUESTS')[0]['error_category']=='NOT_DISPATCHED'
    assert rows(peer,'central','CX_MODEL_COORD_REQUESTS')[0]['status']=='KNOWN_NO_SEND'
    assert rows(peer,'central','CX_MODEL_ADMISSIONS')[0]['status']=='CANCELLED'
    assert rows(peer,'central','CX_MODEL_USAGE')==rows(peer,'a','CX_MODEL_ORIGIN_OBSERVATIONS')==[]
    assert rows(peer,'a','CX_MODEL_ORIGIN_RECEIPTS')[0]['status']=='KNOWN_NO_SEND' and peer.sends==0
