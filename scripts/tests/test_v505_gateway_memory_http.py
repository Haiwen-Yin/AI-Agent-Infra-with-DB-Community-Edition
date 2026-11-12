"""HTTP handler semantics and safe handled-failure correlation diagnostics."""
import asyncio
import importlib

import pytest
from fastapi import HTTPException
from starlette.requests import Request


@pytest.fixture
def web(monkeypatch):
    app = importlib.import_module('web_app')
    monkeypatch.setattr(app, '_gateway_context', lambda *args, **kwargs: dict(
        agent_id='test-agent',instance_id='test-instance',fencing_token=1,security_domain_id='domain'))
    return app


def test_knowledge_permission_is_403_without_retry(web, monkeypatch):
    def denied(*args, **kwargs):
        raise PermissionError('Private diagnostic must not reach the client')
    monkeypatch.setattr(web.knowledge_api, 'create_knowledge', denied)
    with pytest.raises(HTTPException) as exc:
        web.gateway_knowledge_create(web.GatewayKnowledgeBody(title='Title',content='Content',reason='Handler verification'), None)
    assert exc.value.status_code == 403
    assert 'Private diagnostic' not in str(exc.value.detail)


def test_business_scope_denial_precedes_instance_creation(web, monkeypatch):
    from lib import agent_permissions
    monkeypatch.setattr(web.agent_gateway_api, 'authenticate_client_secret', lambda *args: {'credential_id':'credential'})
    monkeypatch.setattr(agent_permissions, 'require_business_scopes', lambda *args: (_ for _ in ()).throw(PermissionError('Denied scope')))
    monkeypatch.setattr(web.agent_gateway_api, 'create_instance', lambda *args, **kwargs: pytest.fail('Denied token must not create an instance'))
    with pytest.raises(HTTPException) as exc:
        web.gateway_token(web.GatewayTokenBody(agent_id='agent',client_secret='synthetic',security_domain_id='domain',scopes=['knowledge.write']))
    assert exc.value.status_code == 403


def test_knowledge_envelope_and_missing_read(web, monkeypatch):
    monkeypatch.setattr(web.knowledge_api, 'get_knowledge', lambda *args, **kwargs: {'title':'Retained fact'})
    assert web.gateway_knowledge_get('123',None) == {'knowledge':{'title':'Retained fact'}}
    monkeypatch.setattr(web.knowledge_api, 'get_knowledge', lambda *args, **kwargs: None)
    with pytest.raises(HTTPException) as exc:
        web.gateway_knowledge_get('missing',None)
    assert exc.value.status_code == 404


def test_handled_service_failure_logs_only_safe_correlation(web, caplog):
    request = Request({'type':'http','method':'POST','scheme':'http','server':('localhost',80),
                       'path':'/api/gateway/knowledge','query_string':b'','headers':[],
                       'state':{'correlation_id':'cx_safe_failure'}})
    try:
        raise RuntimeError('password=private-diagnostic-content')
    except RuntimeError as cause:
        error = HTTPException(503,'Agent knowledge creation service unavailable')
        error.__cause__ = cause
    with caplog.at_level('WARNING'):
        response = asyncio.run(web.governed_http_error(request,error))
    assert response.status_code == 503
    assert 'cx_safe_failure' in caplog.text and 'RuntimeError' in caplog.text
    assert 'password=' not in caplog.text and 'private-diagnostic-content' not in response.body.decode()


def test_gateway_memory_obeys_memory_capability(web):
    assert web._path_capability('/api/gateway/memory') == 'memory'
    assert web._path_capability('/api/agent-gateway/memory/MF-example') == 'memory'
