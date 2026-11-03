"""Task discovery retains exact governed sources and normal read authority."""
import pytest
from pydantic import ValidationError
from lib import continuity_assembly as assembly,context_selection,knowledge_grounding,knowledge_api
from lib import continuity_runtime as runtime,agent_source_sync as sync
from lib.continuity_contracts import AssemblyRequest
from .test_knowledge_curated import published_source
from .test_v501_context_assets import store,configuration
from .test_continuity_candidates import candidate_db
from .test_continuity_handoff import fixture
from .test_continuity_work import database
from .test_continuity_candidates import new_candidate,approve


def request(**changes):
    return dict(request_id='hybrid',security_domain_id='domain',query_text='legal hold',
        knowledge_retrieval='hybrid',token_budget=32000,purpose='Find the approved task procedure',
        idempotency_key='hybrid',**changes)


@pytest.mark.parametrize('query',['','   ','x'*2001])
def test_hybrid_context_needs_a_bounded_explicit_query(query):
    with pytest.raises(ValidationError):AssemblyRequest.model_validate(dict(request(),query_text=query))


def recalled(store,monkeypatch):
    db,_=store
    source,reference=published_source(db)
    native=db.execute('SELECT NATIVE_ENTITY_ID FROM CX_CONTINUITY_ARTIFACT_REVS').fetchone()[0]
    calls=[]
    def recall(actor,reader,query,**options):
        calls.append((actor,reader,query,options))
        return dict(items=[dict(entity_id=native)])
    monkeypatch.setattr(knowledge_grounding,'search',recall)
    return db,source,reference,calls


def test_optional_discovery_keeps_body_matches_exact_and_replay_does_not_repeat_search(store,monkeypatch):
    db,source,reference,calls=recalled(store,monkeypatch)
    built=assembly.assemble('owner',request())
    current=assembly.read_assembly('owner',built['assembly_id'])
    assert current['item_count']==1 and 'legal holds' in current['text']
    assert current['retrieval_policy']=='QUERY_HYBRID_BUDGET_SOURCE_CONTEXT_V3'
    assert current['representations'][0]['selection_reason']=='DATABASE_HYBRID'
    assert current['items'][0]['entity_id']==reference['entity_id']
    assert calls[0][3]['artifact_domain']=='domain' and calls[0][3]['strategy']=='hybrid'
    assert calls[0][3]['transaction'] is not None
    assert assembly.assemble('owner',request())['replayed'] and len(calls)==1
    # A source-backed envelope is also the requester-side integrity contract.
    both=runtime._requester_context
    with monkeypatch.context() as patch:
        patch.setattr(assembly,'_read',lambda *_args:current)
        sync.connection.execute_transaction_callback(lambda tx:both(tx,'owner','agent','domain',built['assembly_id']))
    sync.change_state('owner',source,dict(expected_version=1,status='REVOKED',reason='Withdraw source',idempotency_key='withdraw'))
    with pytest.raises(PermissionError):assembly.consume('owner',built['assembly_id'],lambda *_:pytest.fail('Withdrawn source sent'))


def test_discovery_cannot_use_the_target_agents_private_read_as_requester_authority(store,monkeypatch):
    db,source,reference,calls=recalled(store,monkeypatch)
    native=db.execute('SELECT NATIVE_ENTITY_ID FROM CX_CONTINUITY_ARTIFACT_REVS').fetchone()[0]
    # Discovery is deliberately an optimistic fixture. Real current policy
    # metadata must still omit this private source for the second reader.
    built=assembly.assemble('owner',request(),_source_reader='agent')
    assert assembly.read_assembly('owner',built['assembly_id'])['item_count']==0
    assert calls[0][:2]==('owner','agent')
    knowledge_api.set_access_policy(native,'PUBLIC_COMPANY','owner',reason='Explicitly share the synthetic task procedure')
    built=assembly.assemble('owner',dict(request(),idempotency_key='shared'),_source_reader='agent')
    assert assembly.read_assembly('owner',built['assembly_id'])['item_count']==1


def test_discovery_respects_budget_and_deduplicates_explicit_body_match(store,monkeypatch):
    db,source,reference,calls=recalled(store,monkeypatch)
    built=assembly.assemble('owner',dict(request(),sources=[reference]))
    assert assembly.read_assembly('owner',built['assembly_id'])['item_count']==1
    small=assembly.assemble('owner',dict(request(),token_budget=30,allow_partial=True,idempotency_key='small'))
    read=assembly.read_assembly('owner',small['assembly_id'])
    assert read['text']=='' and read['representations'][0]['representation']=='OMITTED'
    # Partial output cannot cut away the original applicability envelope.
    assert db.execute('SELECT COUNT(*) FROM CX_CONTINUITY_ARTIFACTS').fetchone()[0]==1


def test_default_and_zero_entry_requests_do_not_launch_discovery(store,monkeypatch):
    monkeypatch.setattr(knowledge_grounding,'search',lambda *_a,**_k:pytest.fail('No implicit Knowledge provider call'))
    value=request();value.pop('knowledge_retrieval')
    assert assembly.assemble('owner',value)['item_count']==0
    assert assembly.assemble('owner',dict(request(),entry_limit=0,idempotency_key='zero'))['item_count']==0


@pytest.mark.parametrize('revocation',['policy','permission','domain','original'])
def test_shared_knowledge_context_uses_native_policy_without_global_read_scope(store,monkeypatch,revocation):
    from lib import continuity_candidates as candidates,continuity_sources
    from lib.continuity_contracts import SourceRef
    db,original=store
    cid=candidates.create_candidate('owner',new_candidate(original,
        dict(family='KNOWLEDGE',title='Reviewed procedure',body='Follow the authorized procedure.')))['candidate_id']
    promoted=candidates.promote_candidate('agent',cid,approve(cid))
    row=db.execute('SELECT NATIVE_ENTITY_ID,CONTENT_DIGEST FROM CX_CONTINUITY_ARTIFACT_REVS').fetchone()
    native,digest=row
    source=SourceRef(family='KNOWLEDGE',entity_id=promoted['result_entity_id'],
        revision_id=promoted['result_revision_id'],content_digest=digest)
    knowledge_api.set_access_policy(native,'PUBLIC_COMPANY','owner',reason='Share reviewed procedure')
    denied=[False]
    monkeypatch.setattr(knowledge_api.identity_api,'effective_access',lambda actor,action,**_kw:
        dict(decision='DENY' if denied[0] and actor=='agent' and action=='knowledge.read' else 'ALLOW',
            scopes=['OWNED'] if action=='knowledge.read' else ['ALL']))
    monkeypatch.setattr(knowledge_grounding,'search',lambda *_a,**_kw:dict(items=[dict(entity_id=native)]))
    read=lambda:sync.connection.execute_transaction_callback(lambda tx:
        continuity_sources.resolve(tx,'agent','domain',source))
    assert read()['source']==source.model_dump(mode='json')
    built=assembly.assemble('owner',request(),_source_reader='agent')
    assert assembly.read_assembly('owner',built['assembly_id'])['item_count']==1
    if revocation=='policy':
        knowledge_api.set_access_policy(native,'PRINCIPAL_PRIVATE','owner',principal_id='owner',reason='Withdraw sharing')
    elif revocation=='permission':denied[0]=True
    elif revocation=='domain':
        db.execute("UPDATE CX_DOMAIN_MEMBERS SET STATUS='REVOKED' WHERE PRINCIPAL_ID='agent'")
        db.commit()
    else:
        db.execute("UPDATE CX_HANDOFFS SET EXPIRES_AT='2000-01-01' WHERE HANDOFF_ID=?",(original['entity_id'],))
        db.commit()
    with pytest.raises((PermissionError,assembly.ContinuityConflict)):read()
    if revocation=='original':
        with pytest.raises(assembly.ContinuityConflict):
            assembly.assemble('owner',dict(request(),idempotency_key='after-revocation'),_source_reader='agent')
    elif revocation!='domain':
        # This optimistic discovery fixture cannot override any current gate.
        fresh=assembly.assemble('owner',dict(request(),idempotency_key='after-revocation'),_source_reader='agent')
        assert assembly.read_assembly('owner',fresh['assembly_id'])['item_count']==0
