"""Synthetic relational/native-number and in-memory transport regressions.

The SQLite fixture returns Decimal numbers like the native adapter. No native
database, HTTP peer or model endpoint is contacted by these tests.
"""
from copy import deepcopy
from decimal import Decimal
import json
import socket
import sqlite3
from types import SimpleNamespace

import pytest

from lib import config,edition_features,model_dispatch,native_runtime,provider_capability_probes
from lib import model_coordinator as coordinator,model_coordinator_origin as origin
from lib import model_endpoint_capacity as capacity
from lib.agent_extension_contracts import digest
from .test_v502_model_capacity import ledger


@pytest.fixture
def numeric_ledger(ledger,monkeypatch):
    db,group_id,clock,path=ledger
    # Emulate native numeric results and a driver's support for Decimal binds.
    # The adapter registration is restored by monkeypatch after this fixture.
    monkeypatch.setitem(sqlite3.adapters,(Decimal,sqlite3.PrepareProtocol),str)
    db.row_factory=lambda cursor,values:{
        column[0].lower():Decimal(value) if type(value) is int else value
        for column,value in zip(cursor.description,values)}
    monkeypatch.setattr(edition_features,'MODEL_RUNTIME_CONTEXT_ENABLED',True)
    monkeypatch.setattr(socket,'socket',lambda *args,**kwargs:pytest.fail('No HTTP/socket transport is allowed'))
    monkeypatch.setattr(native_runtime.urllib.request,'urlopen',lambda *args,**kwargs:pytest.fail('Uncontrolled send'))
    monkeypatch.setattr(config,'get_config',lambda:SimpleNamespace(llm=config.LLMConfig(request_timeout_seconds=180)))
    monkeypatch.setattr(provider_capability_probes,'apply_parameters',lambda profile,payload:payload)
    return db,group_id,clock,path


@pytest.mark.parametrize('native_version',[1,Decimal('1'),Decimal('1.000')],ids=['int','decimal','scaled-decimal'])
@pytest.mark.parametrize('pre_reserved',[False,True],ids=['direct-native','coordinator-reserved'])
def test_native_version_reuses_exact_admission_and_reaches_one_synthetic_open(numeric_ledger,monkeypatch,native_version,pre_reserved):
    db,group_id,_,_=numeric_ledger
    profile=dict(profile_id='profile',version=native_version,model_id='model',provider_url='http://model.test:12345/v1')
    original_profile=deepcopy(profile)
    messages=[dict(role='user',content='Synthetic offline fixture.')]
    payload=dict(model='model',messages=messages,stream=False)
    source_kind='GATEWAY' if pre_reserved else 'NATIVE'
    source_id='coordinator-request' if pre_reserved else 'native-execution'
    source_attempt='origin-receipt' if pre_reserved else 'native-attempt'
    reserved=None
    if pre_reserved:
        value=coordinator._admission(dict(origin_id='installation-a'),profile,{},dict(
            coordinator_request_id=source_id,origin_receipt_id=source_attempt,
            payload_digest=digest(payload),credential_digest='b'*64))
        reserved=capacity.admit('origin-a',group_id,value)
        assert reserved['status']=='RESERVED' and reserved['attempt_id'] is None
    sends=[]
    class Response:
        def __enter__(self):return self
        def __exit__(self,*args):return False
        def read(self,maximum):
            return json.dumps(dict(model='model',choices=[dict(message=dict(content='Synthetic complete.'),finish_reason='stop')],
                usage=dict(prompt_tokens=8,completion_tokens=4,total_tokens=12))).encode()
    def synthetic_open(request,*,timeout):
        sends.append(dict(url=request.full_url,payload=json.loads(request.data)))
        record=db.execute('SELECT * FROM CX_MODEL_ADMISSIONS').fetchone()
        assert record['status']=='DISPATCHING' and type(record['profile_version']) is Decimal
        if reserved:assert record['admission_id']==reserved['admission_id']
        return Response()
    monkeypatch.setattr(model_dispatch,'open_controlled',synthetic_open)
    authorizations=[]
    def authorize(tx,record):
        authorizations.append(record['admission_id'])
        assert int(record['profile_version'])==1
    with model_dispatch.authenticated_context('origin-a',source_kind,source_id,source_attempt,credential_digest='b'*64,
            worker_key='worker-a',origin_id='installation-a',allow_wait=False,reauthorize=authorize):
        result=native_runtime._call_llm(profile,messages)
    record=db.execute('SELECT * FROM CX_MODEL_ADMISSIONS').fetchone()
    assert record['status']=='COMPLETED' and result['request_id']==record['admission_id']
    assert result['request_complete'] is True and result['usage']['total_tokens']==12
    assert sends==[dict(url=profile['provider_url']+'/chat/completions',payload=payload)]
    assert authorizations==[record['admission_id']]
    assert db.execute('SELECT COUNT(*) AS n FROM CX_MODEL_ADMISSIONS').fetchone()['n']==1
    assert db.execute('SELECT COUNT(*) AS n FROM CX_MODEL_CAP_ATTEMPTS').fetchone()['n']==1
    assert db.execute("SELECT COUNT(*) AS n FROM CX_MODEL_CAP_REQUESTS WHERE OPERATION='MODEL_CAP_ADMIT'").fetchone()['n']==1
    if reserved:assert record['admission_id']==reserved['admission_id']
    assert profile==original_profile and type(profile['version']) is type(native_version)


@pytest.mark.parametrize('bad_version',[Decimal('1.5'),1.0,'1',True])
def test_controlled_dispatch_rejects_nonintegral_or_coercible_revision_before_admission(numeric_ledger,monkeypatch,bad_version):
    db,_,_,_=numeric_ledger
    profile=dict(profile_id='profile',version=bad_version,model_id='model',provider_url='http://model.test:12345/v1')
    monkeypatch.setattr(model_dispatch,'open_controlled',lambda *args,**kwargs:pytest.fail('Invalid native version sent'))
    with model_dispatch.authenticated_context('origin-a','NATIVE','execution','attempt',credential_digest='b'*64,
            worker_key='worker-a',reauthorize=lambda tx,record:None):
        with pytest.raises(ValueError,match='native database revision must be a positive integer'):
            with model_dispatch.dispatch(profile,dict(model='model',messages=[],stream=False)):
                pytest.fail('Invalid native version admitted')
    assert db.execute('SELECT COUNT(*) AS n FROM CX_MODEL_ADMISSIONS').fetchone()['n']==0


@pytest.mark.parametrize('native_number',[int,Decimal],ids=['int','decimal'])
def test_remote_prepare_canonicalizes_native_profile_and_route_revisions_without_mutating_inputs(monkeypatch,native_number):
    profile=dict(profile_id='profile',version=native_number(1),model_id='model')
    route=dict(route_id='route',version=native_number(2),installation_key='installation',group_id='group',
        policy_revision=native_number(1),coordinator_profile_id='central-profile',coordinator_profile_version=native_number(1))
    original=deepcopy((profile,route))
    context=SimpleNamespace(actor='actor',credential_digest='b'*64,source_kind='GATEWAY',source_id='source',
        source_attempt_id='attempt',worker_key='worker')
    payload=dict(model='model',messages=[],stream=False)
    captured={}
    class Transaction:
        def query_one(self,sql,params):
            if 'AND SOURCE_KIND=' in sql:return None
            return dict(captured,version=native_number(1),status='PREPARED')
        def execute(self,sql,params):captured.update(params)
    def local(tx,ctx,current,current_route,payload_digest,current_payload):
        assert type(current['version']) is int and current['version']==1
        return current,(1,2000000)
    monkeypatch.setattr(origin,'_local',local)
    monkeypatch.setattr(origin.connection,'execute_transaction_callback',lambda callback:callback(Transaction()))
    monkeypatch.setattr(origin.capacity,'_now_ms',lambda tx:1000000)
    monkeypatch.setattr(origin.identity_api,'_audit_tx',lambda *args:None)
    monkeypatch.setattr(origin,'identifier',lambda prefix:'receipt')
    receipt=origin.prepare(profile,payload,context,route)
    expected_authority=digest(dict(actor='actor',credential='b'*64,source='source',attempt='attempt',worker='worker',
        fence=1,profile='profile',version=1,route='route',route_version=2))
    assert receipt['authority_digest']==expected_authority
    envelope=origin._envelope(receipt,route)
    assert envelope.origin_profile_version==envelope.profile_version==1
    assert type(captured['profile_version']) is int
    assert captured['fingerprint']==digest(envelope.model_dump(mode='json'))
    assert (profile,route)==original
    assert type(profile['version']) is type(route['version']) is native_number
