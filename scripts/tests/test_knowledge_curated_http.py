"""HTTP DTO/service checks; genuine session/CSRF/browser acceptance is separate."""
from contextlib import nullcontext

from fastapi import FastAPI,HTTPException
from fastapi.testclient import TestClient
import pytest

from lib import agent_extension_http,continuity_http,knowledge_curated,agent_source_sync,continuity_client,continuity_cli
import httpx
import json
from .test_knowledge_curated import document,request
from .test_v501_context_assets import store,configuration
from .test_continuity_candidates import candidate_db
from .test_continuity_handoff import fixture
from .test_continuity_work import database


@pytest.fixture
def http(store):
    app=FastAPI();state=dict(actor='owner',allowed=True,actions=[])
    def guard(action):
        def session():
            state['actions'].append(action)
            if not state['allowed']:raise HTTPException(403,'Denied')
            return dict(principal_id=state['actor'])
        return session
    agent_extension_http.install(app,guard)
    continuity_http.install_routes(app,guard,nullcontext)
    continuity_http.install_routes(app,guard,nullcontext,prefix='/api/agent-gateway/continuity')
    with TestClient(app) as client:
        yield client,state,store[0]


def configure(client,doc):
    typed=knowledge_curated.Document.model_validate(doc)
    value=configuration()
    value.update(endpoint=knowledge_curated.URN_PREFIX+knowledge_curated.manifest_digest([typed]),
        paths=[doc['path']],content_types=['text/markdown'])
    response=client.post('/api/agent-extensions/sources',json=value)
    assert response.status_code==200
    return response.json()['source_id']


def test_http_import_is_typed_actor_bound_pending_and_replayable(http):
    client,state,db=http;doc=document();source=configure(client,doc)
    path='/api/agent-extensions/sources/'+source+'/curated-import'
    assert client.post(path,json=dict(request([doc]),actor='outsider')).status_code==422
    state['allowed']=False
    assert client.post(path,json=request([doc])).status_code==403
    assert db.execute('SELECT COUNT(*) FROM CX_AGENT_SOURCE_REVISIONS').fetchone()[0]==0
    state['allowed']=True;state['actor']='agent'
    result=client.post(path,json=request([doc]));assert result.status_code==200
    assert state['actions'][-1]=='knowledge.write'
    body=result.json();assert not body['automatic_publication']
    assert body['provenance']=='CURATOR_SUPPLIED_NOT_REMOTE_FETCHED'
    candidate=client.get('/api/artifact-candidates/'+body['imports'][0]['candidate_id']).json()
    assert candidate['proposed_by']=='agent' and candidate['status']=='PENDING'
    assert not candidate['intake_preview']['publication_eligible']
    assert db.execute('SELECT COUNT(*) FROM ENTITIES').fetchone()[0]==0
    assert client.post(path,json=request([doc])).json()['replayed']
    assert db.execute('SELECT COUNT(*) FROM CX_ARTIFACT_CANDIDATES').fetchone()[0]==1


def test_http_rejects_unreviewed_documents_and_rolls_back_sanitized_audit_error(http,monkeypatch):
    client,state,db=http;doc=document();source=configure(client,doc)
    path='/api/agent-extensions/sources/'+source+'/curated-import'
    bad=dict(doc,origin=dict(doc['origin'],context_reviewed=False))
    assert client.post(path,json=request([bad])).status_code==422
    original=agent_source_sync.identity_api._audit_tx
    def fail(tx,actor,action,*args):
        if action=='SOURCE_CURATED_IMPORT':raise RuntimeError('Private driver details and credential material')
        return original(tx,actor,action,*args)
    monkeypatch.setattr(agent_source_sync.identity_api,'_audit_tx',fail)
    response=client.post(path,json=request([doc]))
    assert response.status_code==503 and 'credential' not in response.text
    for table in ('CX_AGENT_SOURCE_REVISIONS','CX_ARTIFACT_CANDIDATES','CX_KNOWLEDGE_INTAKE'):
        assert db.execute('SELECT COUNT(*) FROM '+table).fetchone()[0]==0


def test_typed_mcp_cli_transport_reaches_the_same_curated_ingress(http,monkeypatch,capsys):
    client,state,db=http;doc=document();source=configure(client,doc)
    state['actor']='agent'
    monkeypatch.setenv('CX_CONTINUITY_GATEWAY_URL','http://testserver/api/agent-gateway/continuity')
    monkeypatch.setenv('CX_AGENT_ACCESS_TOKEN','fixture-token')
    monkeypatch.setenv('CX_AGENT_INSTANCE_ID','fixture-instance')
    monkeypatch.setenv('AI_AGENT_ID','agent')
    calls=[]
    def dispatch(req):
        calls.append(req)
        assert req.headers['x-agent-id']=='agent'
        assert req.headers['authorization']=='Bearer fixture-token'
        response=client.request(req.method,req.url.path,content=req.content,headers=dict(req.headers))
        return httpx.Response(response.status_code,json=response.json())
    transport=httpx.MockTransport(dispatch)
    loaded=continuity_client.call('agent',dict(operation='source_read',request=dict(source_id=source)),transport=transport)
    assert loaded['source_id']==source
    value=dict(operation='source_curated_import',request=dict(request([doc]),source_id=source))
    imported=continuity_client.call('agent',value,transport=transport)
    assert not imported['automatic_publication']
    assert state['actions'][-1]=='knowledge.write'
    import io
    monkeypatch.setattr('sys.stdin',io.StringIO(json.dumps(value)))
    assert continuity_cli.main(['call'],transport=transport)==0
    assert json.loads(capsys.readouterr().out)['replayed']
    assert len(calls)==3 and db.execute('SELECT COUNT(*) FROM CX_ARTIFACT_CANDIDATES').fetchone()[0]==1
    assert db.execute('SELECT COUNT(*) FROM ENTITIES').fetchone()[0]==0
    # Typed source provenance is not an identity, review or publication grant.
    before=len(calls)
    for extra in ({'actor':'owner'},{'trusted':True},{'automatic_publication':True}):
        with pytest.raises(continuity_client.ContinuityClientError,match='INVALID_REQUEST'):
            continuity_client.call('agent',dict(value,request=dict(value['request'],**extra)),transport=transport)
    assert len(calls)==before
