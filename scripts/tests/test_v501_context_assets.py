"""Relational context/asset/sync unit harness; not vendor acceptance evidence."""
import base64
import hashlib
import json
import socket
from datetime import datetime, timedelta, timezone
import pytest

from lib import context_selection as selection, continuity_assembly as assembly, agent_assets as assets
from lib import agent_source_sync as sync, agent_directory as directory, task_continuity, continuity_candidates as candidates
from lib.continuity_contracts import AssemblyRequest
from lib.continuity_state import ContinuityConflict, ContinuityError
from .test_continuity_candidates import candidate_db
from .test_continuity_handoff import fixture
from .test_continuity_work import database


@pytest.fixture
def store(candidate_db, monkeypatch):
    db, source = candidate_db
    db.execute("ALTER TABLE CX_PRINCIPALS ADD COLUMN PERMISSION_VERSION INTEGER DEFAULT 1")
    db.execute("UPDATE CX_PRINCIPALS SET PRINCIPAL_TYPE='AGENT' WHERE PRINCIPAL_ID='agent'")
    db.execute("CREATE TABLE AGENT_REGISTRY(AGENT_ID TEXT PRIMARY KEY)")
    db.execute("INSERT INTO AGENT_REGISTRY VALUES('agent')")
    db.execute("CREATE TABLE TASK_PLANS(PLAN_ID TEXT PRIMARY KEY,AGENT_ID TEXT,GOAL TEXT,STATUS TEXT,PRIORITY INTEGER,STRATEGY TEXT)")
    for statement in (assembly.schema_statements('pg')+task_continuity.schema_statements('oracle')+
                      selection.schema_statements('pg')+assets.schema_statements('pg')+sync.schema_statements('pg')):
        db.execute(statement)
    db.commit()
    monkeypatch.setattr(assets.identity_api, '_agent_visible_to', lambda actor, agent: actor in {'owner', 'agent'})
    monkeypatch.setattr(assets.identity_api, '_limit_clause', lambda key: ' LIMIT :' + key)
    monkeypatch.setattr(sync, 'encrypt_section', lambda value: json.dumps(value))
    monkeypatch.setattr(sync, 'decrypt_section', lambda value: json.loads(value))
    return db, source


def configuration(**changes):
    return dict(security_domain_id='domain', agent_id='agent', kind='DOCUMENT', endpoint='https://docs.example.org/guide',
                reason='Configure an authorized documentation source', idempotency_key='source', **changes)


def fetched(text='Knowledge about database maintenance.', version='"v1"'):
    return {'status':200, 'content_type':'text/plain', 'body':text.encode(), 'etag':version}


def imported(store, *, text='Knowledge about database maintenance.'):
    db,_=store
    source=sync.configure('owner',configuration())['source_id']
    job=sync.enqueue('owner',source,{'reason':'Import configured source','idempotency_key':'sync'})['job_id']
    result=sync.run('owner',job,get=lambda *a,**k:fetched(text))
    row=db.execute('SELECT REVISION_ID,CONTENT_DIGEST FROM CX_AGENT_SOURCE_REVISIONS').fetchone()
    reference={'family':'SOURCE','entity_id':source,'revision_id':row[0],'content_digest':row[1]}
    return source,job,reference,result


def context(**changes):
    return dict(request_id='context-request',security_domain_id='domain',purpose='Current task context',
                idempotency_key='context') | changes


def test_sync_is_a_canonical_task_and_independently_reviewed_candidate(store):
    db,_=store
    source,job,reference,result=imported(store)
    assert result['status']=='SUCCEEDED' and result['imports']
    assert db.execute('SELECT COUNT(*) FROM TASK_PLANS').fetchone()[0]==1
    assert db.execute('SELECT STATUS FROM CX_ARTIFACT_CANDIDATES').fetchone()[0]=='PENDING'
    assert db.execute('SELECT COUNT(*) FROM ENTITIES').fetchone()[0]==0
    assert db.execute('SELECT CHECKPOINT_DIGEST FROM CX_AGENT_SOURCES').fetchone()[0]
    assert db.execute('SELECT LEASE_OWNER FROM CX_TASK_CONTINUITY_LEASES').fetchone()[0].startswith('source-sync:')
    assert db.execute('SELECT COUNT(*) FROM CX_PRINCIPALS WHERE PRINCIPAL_ID LIKE ?',('source-sync:%',)).fetchone()[0]==0
    assert sync.run('owner',job,get=lambda *a,**k:pytest.fail('A completed task must not fetch again'))['status']=='SUCCEEDED'
    candidate=candidates.read_candidate('owner',result['imports'][0]['candidate_id'])
    assert candidate['payload']['sources']==[reference]


def test_sync_repeated_version_deduplicates_evidence_and_candidate(store):
    db,_=store
    source,job,reference,result=imported(store)
    next_job=sync.enqueue('owner',source,{'reason':'Check same version','idempotency_key':'sync-next'})['job_id']
    sync.run('owner',next_job,get=lambda *a,**k:fetched())
    assert db.execute('SELECT COUNT(*) FROM CX_AGENT_SOURCE_REVISIONS').fetchone()[0]==1
    assert db.execute('SELECT COUNT(*) FROM CX_ARTIFACT_CANDIDATES').fetchone()[0]==1
    assert db.execute('SELECT COUNT(*) FROM CX_AGENT_SYNC_IMPORTS').fetchone()[0]==2


def test_audit_failure_rolls_back_source_facts_candidates_and_checkpoint(store,monkeypatch):
    db,_=store
    source=sync.configure('owner',configuration())['source_id']
    job=sync.enqueue('owner',source,{'reason':'Import','idempotency_key':'sync'})['job_id']
    original=sync.identity_api._audit_tx
    def audit(tx,actor,action,*args):
        if action=='SOURCE_SYNC_COMMITTED':
            raise RuntimeError('Audit unavailable')
        return original(tx,actor,action,*args)
    monkeypatch.setattr(sync.identity_api,'_audit_tx',audit)
    with pytest.raises(RuntimeError,match='Audit unavailable'):
        sync.run('owner',job,get=lambda *a,**k:fetched())
    for table in ('CX_AGENT_SOURCE_REVISIONS','CX_AGENT_SYNC_IMPORTS','CX_ARTIFACT_CANDIDATES'):
        assert db.execute('SELECT COUNT(*) FROM '+table).fetchone()[0]==0
    assert db.execute('SELECT CHECKPOINT_DIGEST FROM CX_AGENT_SOURCES').fetchone()[0] is None


def test_revocation_between_fetch_and_import_blocks_every_write(store):
    db,_=store
    source=sync.configure('owner',configuration())['source_id']
    job=sync.enqueue('owner',source,{'reason':'Import','idempotency_key':'sync'})['job_id']
    def fetch(*a,**k):
        sync.change_state('owner',source,{'expected_version':1,'status':'REVOKED','reason':'Revoke source','idempotency_key':'revoke'})
        return fetched()
    with pytest.raises(PermissionError):
        sync.run('owner',job,get=fetch)
    assert db.execute('SELECT COUNT(*) FROM CX_AGENT_SOURCE_REVISIONS').fetchone()[0]==0
    assert db.execute('SELECT STATUS FROM CX_AGENT_SYNC_JOBS').fetchone()[0]=='BLOCKED'


def test_known_read_failure_has_bounded_retry_on_same_task(store):
    db,_=store
    source=sync.configure('owner',configuration(max_attempts=2))['source_id']
    job=sync.enqueue('owner',source,{'reason':'Import','idempotency_key':'sync'})['job_id']
    def unavailable(*a,**k):
        raise TimeoutError('Read timeout')
    with pytest.raises(TimeoutError):
        sync.run('owner',job,get=unavailable)
    assert db.execute('SELECT STATUS FROM CX_AGENT_SYNC_JOBS').fetchone()[0]=='PENDING'
    assert db.execute('SELECT STATUS FROM CX_TASK_CONTINUITY_LINKS').fetchone()[0]=='WAITING'
    result=sync.run('owner',job,get=lambda *a,**k:fetched())
    assert result['attempt_count']==2 and result['status']=='SUCCEEDED'
    assert db.execute('SELECT COUNT(*) FROM TASK_PLANS').fetchone()[0]==1


def test_retry_budget_stops_and_missing_source_is_not_a_deletion(store):
    db,_=store
    source=sync.configure('owner',configuration(max_attempts=1))['source_id']
    job=sync.enqueue('owner',source,{'reason':'Import','idempotency_key':'sync'})['job_id']
    with pytest.raises(ContinuityError,match='deletion is not inferred'):
        sync.run('owner',job,get=lambda *a,**k:{**fetched(),'status':404})
    assert db.execute('SELECT STATUS FROM CX_AGENT_SOURCES').fetchone()[0]=='ACTIVE'
    with pytest.raises(ContinuityConflict):
        sync.run('owner',job,get=lambda *a,**k:pytest.fail('Closed job cannot fetch'))


def test_metadata_query_excludes_unrelated_source_before_body_loading(store,monkeypatch):
    source,job,reference,result=imported(store)
    original=assembly.resolve
    monkeypatch.setattr(assembly,'resolve',lambda *a,**k:pytest.fail('Unrelated source body must not be loaded'))
    built=assembly.assemble('owner',context(query_text='quantum gravity',sources=[reference]))
    record=assembly.read_assembly('owner',built['assembly_id'])
    assert record['item_count']==0 and record['representations'][0]['selection_reason']=='NO_RELEVANCE'
    assert assembly.confirmed_complete_sources('owner',built['assembly_id'])==[]


def test_model_budget_reserves_system_tools_output_and_reports_method(store):
    source,job,reference,result=imported(store)
    built=assembly.assemble('owner',context(mandatory_sources=[reference],context_window=160,output_reserve=20,
                                          system_text='system',tool_text='tools',model_name='qwopus3.6-35b-a3b-coder-mtp',token_budget=100))
    value=assembly.read_assembly('owner',built['assembly_id'])
    assert value['token_count_method']=='UTF8_UPPER_BOUND'
    assert value['budget']['system_tokens']==6 and value['budget']['tool_tokens']==5
    assert value['budget']['source_budget']==100
    with pytest.raises(ContinuityConflict,match='reserves'):
        assembly.assemble('owner',context(context_window=10,output_reserve=9,system_text='large',idempotency_key='invalid'))


def test_partial_delivery_cannot_suppress_later_source_injection(store):
    source,job,reference,result=imported(store,text='Database source text. '*20)
    built=assembly.assemble('owner',context(sources=[reference],allow_partial=True,token_budget=40))
    current=assembly.read_assembly('owner',built['assembly_id'])
    assert len(current['text'].encode())==40
    assert current['representations'][0]['representation']=='PARTIAL'
    assembly.consume('owner',built['assembly_id'],lambda text:'model answer')
    assert assembly.read_assembly('owner',built['assembly_id'])['representations'][0]['delivery_status']=='CONFIRMED'
    assert assembly.confirmed_complete_sources('owner',built['assembly_id'])==[]


def test_complete_and_unobserved_receipts_have_distinct_suppression(store):
    source,job,reference,result=imported(store)
    built=assembly.assemble('owner',context(mandatory_sources=[reference]))
    assert assembly.confirmed_complete_sources('owner',built['assembly_id'])==[]
    assembly.consume('owner',built['assembly_id'],lambda text:'answer')
    assert assembly.confirmed_complete_sources('owner',built['assembly_id'])==[reference]
    failed=assembly.assemble('owner',context(mandatory_sources=[reference],idempotency_key='unknown'))
    with pytest.raises(TimeoutError):
        assembly.consume('owner',failed['assembly_id'],lambda text:(_ for _ in ()).throw(TimeoutError('Unknown send')))
    value=assembly.read_assembly('owner',failed['assembly_id'])
    assert value['status']=='UNOBSERVED' and value['representations'][0]['delivery_status']=='UNOBSERVED'
    assert assembly.confirmed_complete_sources('owner',failed['assembly_id'])==[]


def test_mandatory_context_is_not_silently_truncated(store):
    db,_=store
    source,job,reference,result=imported(store)
    with pytest.raises(ContinuityConflict,match='mandatory'):
        assembly.assemble('owner',context(mandatory_sources=[reference],token_budget=1,allow_partial=True))
    assert db.execute('SELECT COUNT(*) FROM CX_CONTEXT_ASSEMBLIES').fetchone()[0]==0


def test_binding_uses_existing_source_authority_and_exact_revision(store):
    db,_=store
    source,job,reference,result=imported(store)
    value={'security_domain_id':'domain','agent_id':'agent','source':reference,'purpose':'Answer documentation questions','reason':'Explicit binding','idempotency_key':'bind'}
    binding=assets.bind('owner',value)
    assert assets.bind('owner',value)['replayed']
    loaded=assets.load('owner',binding['binding_id'])
    assert loaded['source']==reference and not loaded['binding_grants_authority']
    built=assets.assemble('owner',[binding['binding_id']],context())
    assert assembly.read_assembly('owner',built['assembly_id'])['item_count']==1
    sync.change_state('owner',source,{'expected_version':1,'status':'REVOKED','reason':'Source authority removed','idempotency_key':'revoke'})
    with pytest.raises(PermissionError):
        assets.load('owner',binding['binding_id'])
    with pytest.raises(PermissionError):
        assembly.read_assembly('owner',built['assembly_id'])
    assert db.execute('SELECT STATUS FROM CX_AGENT_ASSET_BINDINGS').fetchone()[0]=='ACTIVE'


@pytest.mark.parametrize('session_offset', [-4, 8])
def test_utc_asset_expiry_rejects_load_and_frozen_assembly_in_other_session_zone(store, monkeypatch, session_offset):
    db, _ = store
    _, _, reference, _ = imported(store)
    clock = [datetime.now(timezone.utc)]
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return clock[0].astimezone(tz) if tz else clock[0].replace(tzinfo=None)
    monkeypatch.setattr(assets, 'datetime', Clock)
    db.create_function('current_timestamp', 0,
                       lambda: (clock[0].replace(tzinfo=None) + timedelta(hours=session_offset)).isoformat(sep=' '))
    binding = assets.bind('owner', dict(security_domain_id='domain', agent_id='agent', source=reference,
        purpose='Time-limited source', reason='Bind exact source until UTC expiry', idempotency_key='expiring',
        valid_until=clock[0] + timedelta(hours=1)))['binding_id']
    assert assets.load('owner', binding)['source'] == reference
    built = assets.assemble('owner', [binding], context())
    clock[0] += timedelta(hours=1, seconds=1)
    with pytest.raises(PermissionError, match='expired'):
        assets.load('owner', binding)
    with pytest.raises(PermissionError, match='expired'):
        assets.load('owner', binding, metadata_only=True)
    assert assets.list_bindings('owner', 'domain', 'agent')['items'] == []
    with pytest.raises(PermissionError):
        assembly.read_assembly('owner', built['assembly_id'])
    assert db.execute('SELECT STATUS FROM CX_AGENT_SOURCES').fetchone()[0] == 'ACTIVE'


def test_asset_binding_state_and_revision_checks_are_atomic(store):
    db,_=store
    source,job,reference,result=imported(store)
    value={'security_domain_id':'domain','agent_id':'agent','source':reference,'purpose':'Question context','reason':'Bind','idempotency_key':'bind'}
    binding=assets.bind('owner',value)['binding_id']
    revised=assets.revise('owner',binding,{**value,'expected_version':1,'priority':90,'idempotency_key':'revise'})
    assert revised['version']==2 and assets.load('owner',binding)['priority']==90
    with pytest.raises(ContinuityConflict):
        assets.change_state('owner',binding,{'expected_version':1,'status':'PAUSED','reason':'Stale update','idempotency_key':'stale'})
    assets.change_state('owner',binding,{'expected_version':2,'status':'REVOKED','reason':'Retire binding','idempotency_key':'revoke'})
    with pytest.raises(PermissionError):
        assets.load('owner',binding)
    assert db.execute('SELECT COUNT(*) FROM CX_AGENT_ASSET_REVISIONS').fetchone()[0]==2


def test_asset_assembly_accepts_the_typed_http_request(store):
    db,_=store
    source,job,reference,result=imported(store)
    binding=assets.bind('owner',{'security_domain_id':'domain','agent_id':'agent','source':reference,
        'purpose':'Typed HTTP assembly','reason':'Bind source for assembly','idempotency_key':'typed-bind'})['binding_id']
    request=AssemblyRequest.model_validate(context(idempotency_key='typed-http-assembly'))
    built=assets.assemble('owner',[binding],request)
    assert assembly.read_assembly('owner',built['assembly_id'])['item_count']==1
    assert assets.assemble('owner',[binding],request)['assembly_id']==built['assembly_id']
    assert db.execute('SELECT COUNT(*) FROM CX_CONTEXT_ASSET_USES').fetchone()[0]==1


def test_frozen_asset_assembly_rechecks_binding_and_target_before_send(store):
    db,_=store
    source,job,reference,result=imported(store)
    value={'security_domain_id':'domain','agent_id':'agent','source':reference,'purpose':'Question context','reason':'Bind','idempotency_key':'bind'}
    binding=assets.bind('owner',value)['binding_id']
    built=assets.assemble('owner',[binding],context())
    assets.revise('owner',binding,{**value,'expected_version':1,'priority':90,'idempotency_key':'revise'})
    with pytest.raises(ContinuityConflict,match='binding changed'):
        assembly.consume('owner',built['assembly_id'],lambda text:pytest.fail('Stale binding cannot be sent'))
    assert db.execute('SELECT COUNT(*) FROM CX_CONTEXT_INPUT_USES').fetchone()[0]==0
    built=assets.assemble('owner',[binding],context(idempotency_key='next-assembly'))
    db.execute("UPDATE CX_DOMAIN_MEMBERS SET STATUS='REVOKED' WHERE PRINCIPAL_ID='agent'")
    db.commit()
    with pytest.raises(PermissionError):
        assembly.read_assembly('owner',built['assembly_id'])


def test_lease_expiry_during_fetch_keeps_checkpoint_and_candidates_unchanged(store):
    db,_=store
    source=sync.configure('owner',configuration())['source_id']
    job=sync.enqueue('owner',source,{'reason':'Import','idempotency_key':'sync'})['job_id']
    def expired(*a,**k):
        db.execute("UPDATE CX_TASK_CONTINUITY_LEASES SET LEASE_EXPIRES_AT='2000-01-01 00:00:00'")
        db.execute("UPDATE CX_TASK_CONTINUITY_ATTEMPTS SET LEASE_EXPIRES_AT='2000-01-01 00:00:00'")
        db.commit()
        return fetched()
    with pytest.raises(ContinuityConflict,match='expired'):
        sync.run('owner',job,get=expired)
    assert db.execute('SELECT COUNT(*) FROM CX_AGENT_SOURCE_REVISIONS').fetchone()[0]==0
    assert db.execute('SELECT STATUS FROM CX_TASK_CONTINUITY_LINKS').fetchone()[0]=='UNOBSERVED'
    assert db.execute('SELECT STATUS FROM CX_AGENT_SYNC_JOBS').fetchone()[0]=='BLOCKED'


def test_host_credential_revocation_prevents_old_source_use_but_allows_disable(store,monkeypatch):
    db,_=store
    monkeypatch.setenv('CX_SOURCE_CREDENTIAL_DOCS_READ','synthetic-secret-not-for-output')
    source=sync.configure('owner',configuration(credential_ref='DOCS_READ'))['source_id']
    job=sync.enqueue('owner',source,{'reason':'Import','idempotency_key':'sync'})['job_id']
    sync.run('owner',job,get=lambda *a,**k:fetched())
    monkeypatch.delenv('CX_SOURCE_CREDENTIAL_DOCS_READ')
    with pytest.raises(PermissionError,match='credential'):
        sync.enqueue('owner',source,{'reason':'Import','idempotency_key':'sync-next'})
    sync.change_state('owner',source,{'expected_version':1,'status':'PAUSED','reason':'Credential disabled','idempotency_key':'pause'})
    assert sync.read_source('owner',source)['status']=='PAUSED'


def test_https_redirect_and_oversize_are_rejected_without_following(monkeypatch):
    monkeypatch.setattr(socket,'getaddrinfo',lambda *a,**k:[(socket.AF_INET,socket.SOCK_STREAM,0,'',('8.8.8.8',443))])
    requests=[]
    class Response:
        status=302
        def getheader(self,key,default=None):
            return default
    class Client:
        def __init__(self,*args):
            pass
        def request(self,*args,**kwargs):
            requests.append(args)
        def getresponse(self):
            return Response()
        def close(self):
            pass
    monkeypatch.setattr(sync,'_PinnedHTTPS',Client)
    with pytest.raises(ValueError,match='redirects'):
        sync.https_get('https://docs.example.org/tree?recursive=1',allowed_hosts={'docs.example.org'})
    assert len(requests)==1 and requests[0][1]=='/tree?recursive=1'


@pytest.mark.parametrize('url',['file:///etc/passwd','ssh://github.com/o/r','https://127.0.0.1/x','https://[::1]/x',
                                'https://169.254.169.254/x','https://u:p@example.org/x','https://example.org:444/x'])
def test_source_url_rejects_unsafe_transports_addresses_and_credentials(url):
    with pytest.raises(ValueError):
        sync.validate_endpoint(url)


@pytest.mark.parametrize('path',['../x','docs/../x','docs/%2e%2e/x','docs\\x','//evil','docs//x','.git/config'])
def test_source_path_rejects_escape_and_helpers(path):
    with pytest.raises(ValueError):
        sync.validate_path(path)


def test_https_revalidates_dns_and_does_not_open_a_private_destination(monkeypatch):
    monkeypatch.setattr(socket,'getaddrinfo',lambda *a,**k:[(socket.AF_INET,socket.SOCK_STREAM,0,'',('192.168.1.10',443))])
    monkeypatch.setattr(sync,'_PinnedHTTPS',lambda *a,**k:pytest.fail('Private address must fail before connect'))
    with pytest.raises(PermissionError,match='Non-public'):
        sync.https_get('https://docs.example.org/x',allowed_hosts={'docs.example.org'})


def test_pinned_git_reads_only_verified_blobs_and_rejects_symlinks(store):
    db,_=store
    text=b'Verified source documentation.'
    sha=hashlib.sha1(b'blob '+str(len(text)).encode()+b'\x00'+text).hexdigest()
    config=configuration()
    config.update(kind='GITHUB',endpoint='https://github.com/example/project',pinned_commit='a'*40,paths=('docs',))
    source=sync.configure('owner',config)['source_id']
    job=sync.enqueue('owner',source,{'reason':'Pinned source import','idempotency_key':'sync'})['job_id']
    urls=[]
    def get(url,**kwargs):
        urls.append(url)
        if '/trees/' in url:
            value={'tree':[{'path':'docs/guide.md','type':'blob','mode':'100644','sha':sha}],'truncated':False}
        else:
            value={'encoding':'base64','content':base64.b64encode(text).decode()}
        return {'status':200,'body':json.dumps(value).encode(),'content_type':'application/json'}
    assert sync.run('owner',job,get=get)['status']=='SUCCEEDED'
    assert all(url.startswith('https://api.github.com/repos/example/project/git/') for url in urls)
    assert 'a'*40 in urls[0] and sha in urls[1]
    source2=sync.configure('owner',{**config,'idempotency_key':'source-2'})['source_id']
    job2=sync.enqueue('owner',source2,{'reason':'Pinned source import','idempotency_key':'sync-2'})['job_id']
    def symlink(url,**kwargs):
        return {'status':200,'body':json.dumps({'tree':[{'path':'docs/link.md','mode':'120000','type':'blob','sha':sha}]}).encode()}
    with pytest.raises(ValueError,match='Symlink'):
        sync.run('owner',job2,get=symlink)


def test_skill_recommendation_ranks_metadata_before_selected_body(monkeypatch):
    records=[{'entity_id':'skill-one','title':'Database backup','skill_name':'backup','skill_version':'1','skill_description':'Database recovery','resource_checksum':'a'*64},
             {'entity_id':'skill-two','title':'Draw picture','skill_name':'drawing','skill_version':'1','skill_description':'Artwork','resource_checksum':'b'*64}]
    class Tx:
        def query(self,sql,params):
            assert 'TEXT_CONTENT' not in sql and 'PARAMETERS' not in sql
            return records
    monkeypatch.setattr(directory.connection,'execute_transaction_callback',lambda fn:fn(Tx()))
    monkeypatch.setattr(directory,'_authority',lambda *a,**k:{'scopes':['ALL']})
    loaded=[]
    def get(entity):
        loaded.append(entity)
        record=next(item for item in records if item['entity_id']==entity)
        return {**record,'status':'ACTIVE','skill_status':'ACTIVE','text_content':'Run an authorized backup','parameters':{},'dependencies':{}}
    monkeypatch.setattr(directory.skill_api,'get_skill',get)
    result=directory.recommend('owner','domain','database backup')
    assert [item['entity_id'] for item in result['items']]==['skill-one'] and loaded==['skill-one']
    assert not result['discovery_grants_execution']
    loaded.clear()
    assert directory.recommend('owner','domain','unrelated astronomy')['items']==[] and loaded==[]
