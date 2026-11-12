"""Public recovery errors and portable client's bounded renewal lifecycle."""
from datetime import datetime, timedelta
import importlib.util
from pathlib import Path
from unittest.mock import Mock

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
import pytest

from lib import agent_gateway_api as gateway, agent_permissions, agent_framework_adapters as adapters


@pytest.fixture
def http(monkeypatch):
    import web_app as web
    app = FastAPI()
    app.add_exception_handler(HTTPException, web.governed_http_error)
    for path in ('/api/gateway/token','/api/gateway/instances','/api/gateway/heartbeat'):
        route = next(r for r in web.app.routes if getattr(r,'path',None) == path)
        app.add_api_route(path, route.endpoint, methods=['POST'])
    now = datetime(2026,11,12,12)
    state = dict(status='ACTIVE', agent_status='ACTIVE', revoked_at=None,
                 lease_expires_at=now+timedelta(seconds=40), db_clock=now,
                 instance_id='instance', fencing_token=1, security_domain_id='domain')
    def query(sql,args=None):
        if 'CX_RUNTIME_ISOLATION_CONTRACTS' in sql:
            return None
        if 'CX_AGENT_ACCESS_TOKENS' in sql:
            return {'expires_at':now+timedelta(seconds=300)}
        if 'CX_AGENT_INSTANCES' in sql:
            return dict(state) if args.get('instance_id') == 'instance' else None
        if 'CX_PRINCIPALS' in sql:
            return {'principal_id':'agent','status':'ACTIVE'}
        return None
    execute = Mock(return_value=1)
    monkeypatch.setattr(gateway.connection,'execute_query_one',query)
    monkeypatch.setattr(gateway.connection,'execute',execute)
    monkeypatch.setattr(gateway,'authenticate_client_secret',lambda *args: {'credential_id':'credential'} if args[1]=='synthetic' else None)
    monkeypatch.setattr(gateway,'_compliance_allows',lambda *args:True)
    monkeypatch.setattr(gateway,'_digest',lambda *args:'synthetic-digest')
    monkeypatch.setattr(agent_permissions,'require_business_scopes',lambda *args:None)
    monkeypatch.setattr(web.platform_agent_pool,'discover_agent_endpoint',lambda *args:{})
    monkeypatch.setattr(web,'_gateway_context',lambda *args,**kwargs:{'agent_id':'agent','instance_id':'instance'})
    return TestClient(app),state,execute,web


def token_body(**extra):
    return dict(agent_id='agent',client_secret='synthetic',instance_id='instance',scopes=['knowledge.read'],**extra)


def test_expired_instance_is_actionable_conflict_and_cannot_mint_token(http):
    client,state,writes,_=http
    state['lease_expires_at']=state['db_clock']
    result=client.post('/api/gateway/token',json=token_body())
    assert result.status_code==409
    assert result.json()['code']=='INSTANCE_LEASE_EXPIRED'
    assert result.json()['recovery_action']=='CREATE_INSTANCE_WITH_REGISTERED_CREDENTIAL'
    assert result.json()['retryable'] is False and result.json()['correlation_id']
    writes.assert_not_called()


@pytest.mark.parametrize('change,code',[
    ({'status':'REVOKED'},'INSTANCE_UNAVAILABLE'),
    ({'revoked_at':datetime(2026,11,12)},'INSTANCE_UNAVAILABLE'),
    ({'agent_status':'SUSPENDED'},'AGENT_NOT_ACTIVE')])
def test_blocked_instance_is_not_recoverable_expiry(http,change,code):
    client,state,writes,_=http;state.update(change)
    result=client.post('/api/gateway/token',json=token_body())
    assert result.status_code==403 and result.json()['code']==code
    writes.assert_not_called()


def test_missing_binding_is_validation_failure_after_authentication(http):
    client,_,writes,_=http
    body=token_body();body.pop('instance_id')
    result=client.post('/api/gateway/token',json=body)
    assert result.status_code==422 and result.json()['code']=='DOMAIN_REQUIRED'
    body['client_secret']='incorrect'
    result=client.post('/api/gateway/token',json=body)
    assert result.status_code==401 and result.json()['code']=='AGENT_CREDENTIAL_INVALID'
    writes.assert_not_called()


def test_scope_denial_precedes_creation_and_has_distinct_code(http,monkeypatch):
    client,_,writes,_=http
    def deny(*args): raise PermissionError('Do not expose private grants')
    monkeypatch.setattr(agent_permissions,'require_business_scopes',deny)
    result=client.post('/api/gateway/token',json=token_body())
    assert result.status_code==403 and result.json()['code']=='SCOPE_DENIED'
    assert 'private grants' not in result.text
    writes.assert_not_called()


@pytest.mark.parametrize('channel',['','channel'])
def test_domain_minimum_still_blocks_lower_classification(http,monkeypatch,channel):
    client,_,writes,_=http
    def query(sql,args=None):
        if 'CX_PRINCIPALS' in sql:
            return {'principal_id':'agent','status':'ACTIVE'}
        return {'security_domain_id':'domain','classification':'INTERNAL' if channel else 'RESTRICTED',
                'domain_classification':'RESTRICTED'}
    monkeypatch.setattr(gateway.connection,'execute_query_one',query)
    body=token_body();body.pop('instance_id');body['security_domain_id']='domain'
    if channel:body['channel_id']=channel
    result=client.post('/api/gateway/token',json=body)
    assert result.status_code==403 and result.json()['code']=='CLASSIFICATION_DENIED'
    writes.assert_not_called()


def test_token_refresh_reports_separate_lease_without_renewing_it(http):
    client,state,writes,_=http
    result=client.post('/api/gateway/token',json=token_body())
    assert result.status_code==200
    assert result.json()['expires_in']==300 and result.json()['lease_expires_in']==40
    assert result.json()['heartbeat_after_seconds']==13
    assert all('INSERT INTO CX_AGENT_ACCESS_TOKENS' in c.args[0] for c in writes.call_args_list)


def test_database_failures_are_service_errors_without_driver_details(http,monkeypatch):
    client,_,_,_=http
    monkeypatch.setattr(gateway,'instance_lease',Mock(side_effect=RuntimeError('password=private')))
    response=client.post('/api/gateway/token',json=token_body())
    assert response.status_code==503 and 'private' not in response.text


def test_instance_endpoint_accepts_bearer_only_body_and_rejects_other_identity(http,monkeypatch):
    client,_,_,_=http
    create=Mock(return_value={'instance_id':'new','agent_id':'agent'})
    monkeypatch.setattr(gateway,'create_instance',create)
    assert client.post('/api/gateway/instances',json={'security_domain_id':'domain'}).status_code==200
    assert create.call_args.args==('agent',)
    assert client.post('/api/gateway/instances',json={'agent_id':'other','security_domain_id':'domain'}).status_code==403
    assert create.call_count==1


def test_adapter_forced_new_uses_one_decision_and_preserves_binding():
    request=adapters.build_token_request('agent','synthetic-secret',instance_id='old',
        new_instance=True,security_domain_id='domain',scopes=['knowledge.read'])
    assert 'instance_id' not in request['body'] and request['body']['security_domain_id']=='domain'
    with pytest.raises(adapters.FrameworkAdapterError):
        adapters.build_token_request('agent','synthetic-secret',instance_id='old',new_instance=True)


@pytest.fixture
def portable():
    root=Path(__file__).resolve().parents[1]
    path=root/'scripts/agent_gateway_session.py'
    if not path.exists(): path=root/'agent_gateway_session.py'
    spec=importlib.util.spec_from_file_location('portable_gateway_session',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def client_fixture(module, fail=None):
    calls=[];clock=[0.0]
    def transport(method,path,body,token):
        calls.append((path,body,token))
        if path.endswith('/heartbeat'):
            return 200,dict(success=True,instance_id='old',lease_expires_in=300)
        if body.get('instance_id')=='old' and fail:
            return fail,dict(code='INSTANCE_LEASE_EXPIRED' if fail==409 else 'SCOPE_DENIED',message='Rejected')
        return 200,dict(agent_id='agent',instance_id=body.get('instance_id') or 'new',
            access_token='private-token',scopes=body['scopes'],expires_in=300,lease_expires_in=300)
    client=module.AgentSession('http://synthetic.test','agent','private-secret',instance_id='old',
        security_domain_id='domain',transport=transport,clock=lambda:clock[0])
    return client,calls,clock


def test_portable_recovery_retries_only_explicit_expiry_and_retains_binding(portable):
    client,calls,_=client_fixture(portable,409)
    result=client.token(['knowledge.read'])
    assert len(calls)==2 and calls[0][1]['instance_id']=='old'
    assert 'instance_id' not in calls[1][1] and calls[1][1]['security_domain_id']=='domain'
    assert client.instance_id=='new' and 'access_token' not in result


def test_portable_denial_is_not_scope_probe_or_new_instance(portable):
    client,calls,_=client_fixture(portable,403)
    with pytest.raises(portable.SessionError) as exc:client.token(['knowledge.read'])
    assert exc.value.code=='SCOPE_DENIED' and len(calls)==1 and client.instance_id=='old'


def test_portable_maintains_heartbeat_then_refreshes_same_instance(portable):
    client,calls,clock=client_fixture(portable)
    client.token(['memory.read']);clock[0]=101;client.maintain()
    assert [c[0] for c in calls]==['/api/gateway/token','/api/gateway/heartbeat','/api/gateway/token']
    assert client.instance_id=='old'


def test_portable_unknown_outcome_does_not_retry_or_overwrite_identity(portable):
    client,calls,_=client_fixture(portable)
    def fail(*args):
        calls.append(args)
        raise portable.SessionError('TRANSPORT_OUTCOME_UNKNOWN','Reconcile')
    client._transport=fail
    with pytest.raises(portable.SessionError):client.token(['knowledge.read'],new_instance=True)
    assert len(calls)==1 and client.instance_id=='old'
