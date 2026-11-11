"""Curated uploads retain provenance and the ordinary candidate authority."""
import hashlib
import json

import pytest

from lib import knowledge_curated as curated,agent_source_sync as sync,continuity_candidates as candidates
from lib.continuity_contracts import SourceRef
from lib.continuity_state import ContinuityConflict,ContinuityError
from .test_v501_context_assets import store,configuration
from .test_continuity_candidates import candidate_db
from .test_continuity_handoff import fixture
from .test_continuity_work import database
from .test_continuity_candidates import approve


def document(text='Scope: Boreal only. Never delete legal holds.\n'):
    return dict(path='/docs/procedure.md',title='Boreal procedure',text=text,
        origin=dict(locator='docs/procedure.md',revision='worktree:sha256:'+hashlib.sha256(text.encode()).hexdigest(),
            parent_sha256=hashlib.sha256(text.encode()).hexdigest(),parent_char_count=len(text),start=0,end=len(text),
            decision_status='CURRENT',context_reviewed=True,context_note='Complete original source, including its exception.'))


def prepare_source(documents):
    typed=[curated.Document.model_validate(item) for item in documents]
    value=configuration()
    value.update(endpoint=curated.URN_PREFIX+curated.manifest_digest(typed),paths=tuple(item.path for item in typed),
        content_types=('text/markdown',))
    return sync.configure('owner',value)['source_id']


def request(documents):
    return dict(expected_version=1,documents=documents,reason='Reviewed local document snapshots',idempotency_key='curated-upload')


def test_exact_upload_is_pending_replayable_and_revocation_rechecks_original_source(store):
    db,_=store
    doc=document();source=prepare_source([doc]);value=request([doc])
    result=curated.import_documents('owner',source,value)
    assert not result['automatic_publication']
    assert result['provenance']=='CURATOR_SUPPLIED_NOT_REMOTE_FETCHED'
    assert db.execute('SELECT STATUS FROM CX_ARTIFACT_CANDIDATES').fetchone()[0]=='PENDING'
    assert db.execute('SELECT COUNT(*) FROM ENTITIES').fetchone()[0]==0
    reference=SourceRef.model_validate(result['imports'][0]['source'])
    loaded=sync.connection.execute_transaction_callback(lambda tx:sync.resolve_source(tx,'owner','domain',reference))
    assert loaded['text']==doc['text'] and loaded['provenance']['locator']=='docs/procedure.md'
    assert loaded['provenance']['method']=='CURATOR_SUPPLIED_NOT_REMOTE_FETCHED'
    candidate=candidates.read_candidate('owner',result['imports'][0]['candidate_id'])
    assert candidate['payload']['sources']==[reference.model_dump(mode='json')]
    assert not candidate['intake_preview']['publication_eligible']
    replay=curated.import_documents('owner',source,value)
    assert replay['replayed'] and replay['imports']==result['imports']
    assert db.execute('SELECT COUNT(*) FROM CX_AGENT_SOURCE_REVISIONS').fetchone()[0]==1
    assert db.execute('SELECT COUNT(*) FROM CX_ARTIFACT_CANDIDATES').fetchone()[0]==1
    sync.change_state('owner',source,dict(expected_version=1,status='REVOKED',reason='Revoke source',idempotency_key='revoke'))
    with pytest.raises(PermissionError):
        sync.connection.execute_transaction_callback(lambda tx:sync.resolve_source(tx,'owner','domain',reference))
    with pytest.raises(PermissionError):curated.import_documents('owner',source,value)


def test_manifest_change_and_unrelated_reader_cannot_commit_even_one_source(store):
    db,_=store
    original=document();source=prepare_source([original])
    with pytest.raises(ContinuityConflict,match='manifest'):
        curated.import_documents('owner',source,request([document('A changed original document.')]))
    with pytest.raises(PermissionError):curated.import_documents('outsider',source,request([original]))
    assert db.execute('SELECT COUNT(*) FROM CX_AGENT_SOURCE_REVISIONS').fetchone()[0]==0
    assert db.execute('SELECT CHECKPOINT_DIGEST FROM CX_AGENT_SOURCES').fetchone()[0] is None


def test_audit_failure_rolls_back_all_sources_candidates_intake_and_checkpoint(store,monkeypatch):
    db,_=store
    docs=[document(),dict(document('A second complete source.'),path='/docs/second.md')]
    source=prepare_source(docs)
    audit=sync.identity_api._audit_tx
    def fail(tx,actor,action,*args):
        if action=='SOURCE_CURATED_IMPORT':raise RuntimeError('Synthetic unavailable audit')
        return audit(tx,actor,action,*args)
    monkeypatch.setattr(sync.identity_api,'_audit_tx',fail)
    with pytest.raises(RuntimeError,match='audit'):
        curated.import_documents('owner',source,request(docs))
    for table in ('CX_AGENT_SOURCE_REVISIONS','CX_ARTIFACT_CANDIDATES','CX_KNOWLEDGE_INTAKE'):
        assert db.execute('SELECT COUNT(*) FROM '+table).fetchone()[0]==0
    assert db.execute('SELECT CHECKPOINT_DIGEST FROM CX_AGENT_SOURCES').fetchone()[0] is None


def test_curated_uri_cannot_be_fetched_or_use_a_network_credential(store):
    doc=document();source=prepare_source([doc])
    with pytest.raises(ContinuityConflict,match='curated-import'):
        sync.enqueue('owner',source,dict(reason='No remote fetch',idempotency_key='sync'))
    configured=sync.read_source('owner',source)
    with pytest.raises(ContinuityConflict):
        sync._fetch(configured,lambda *args,**kwargs:pytest.fail('A URN must never reach network or filesystem I/O'))
    value=configuration();value.update(endpoint=configured['endpoint'],credential_ref='DOCS_READ')
    with pytest.raises(ValueError):sync.SourceConfiguration.model_validate(value)


@pytest.mark.parametrize('field,value',[('context_reviewed',False),('end',5),('parent_sha256','0'*64)])
def test_unreviewed_units_bad_offsets_and_false_parent_digests_are_rejected(field,value):
    doc=document();doc['origin'][field]=value
    with pytest.raises(ValueError):curated.Document.model_validate(doc)


def test_body_digest_alone_does_not_hide_tampered_curator_provenance(store):
    db,_=store
    doc=document();source=prepare_source([doc])
    reference=SourceRef.model_validate(curated.import_documents('owner',source,request([doc]))['imports'][0]['source'])
    cipher=json.loads(db.execute('SELECT CONTENT_CIPHER FROM CX_AGENT_SOURCE_REVISIONS').fetchone()[0])
    cipher['curated']['origin']['locator']='docs/false-source.md'
    db.execute('UPDATE CX_AGENT_SOURCE_REVISIONS SET CONTENT_CIPHER=?',(json.dumps(cipher),));db.commit()
    with pytest.raises(ContinuityError,match='provenance'):
        sync.connection.execute_transaction_callback(lambda tx:sync.resolve_source(tx,'owner','domain',reference))


def test_published_derived_knowledge_retains_current_original_source_authority(store):
    from lib import continuity_sources,continuity_promotions
    db,_=store
    doc=document()
    doc['intake']=dict(purpose='Retain the exact reviewed procedure',source_locator='docs/procedure.md',
        responsible_principal_id='owner',subject='Boreal retention',applicable_product='unified-community',
        applicable_version='5.0.3',effective_from='2026-11-01T00:00:00Z',classification='INTERNAL',
        audience='PRINCIPAL_PRIVATE',decision_status='CURRENT')
    source=prepare_source([doc])
    imported=curated.import_documents('owner',source,request([doc]))['imports'][0]
    cid=imported['candidate_id']
    result=candidates.promote_candidate('agent',cid,approve(cid))
    native,content_hash=db.execute('SELECT NATIVE_ENTITY_ID,CONTENT_DIGEST FROM CX_CONTINUITY_ARTIFACT_REVS').fetchone()
    ref=SourceRef(family='KNOWLEDGE',entity_id=result['result_entity_id'],
        revision_id=result['result_revision_id'],content_digest=content_hash)
    read=lambda:sync.connection.execute_transaction_callback(lambda tx:continuity_sources.resolve(tx,'owner','domain',ref))
    assert json.loads(read()['text'])['body']==doc['text'].strip()
    sync.change_state('owner',source,dict(expected_version=1,status='REVOKED',reason='Withdraw procedure',idempotency_key='withdraw'))
    with pytest.raises(PermissionError):read()
    with pytest.raises(PermissionError):
        sync.connection.execute_transaction_callback(lambda tx:continuity_promotions.require_original_sources(tx,'owner',native))
    # Withdrawal is a read boundary; immutable published history remains.
    assert db.execute('SELECT COUNT(*) FROM ENTITIES').fetchone()[0]==1
    assert db.execute('SELECT STATUS FROM CX_ARTIFACT_CANDIDATES').fetchone()[0]=='APPROVED'


def published_source(db):
    doc=document()
    doc['origin']['decision_status']='PROPOSED'
    doc['intake']=dict(purpose='Preserve a proposal without turning it into policy',source_locator='docs/procedure.md',
        responsible_principal_id='owner',subject='Boreal retention',applicable_product='unified-community',
        applicable_version='5.0.3',effective_from='2026-11-01T00:00:00Z',classification='INTERNAL',
        audience='PRINCIPAL_PRIVATE',decision_status='PROPOSED')
    source=prepare_source([doc])
    cid=curated.import_documents('owner',source,request([doc]))['imports'][0]['candidate_id']
    result=candidates.promote_candidate('agent',cid,approve(cid))
    digest=db.execute('SELECT CONTENT_DIGEST FROM CX_CONTINUITY_ARTIFACT_REVS').fetchone()[0]
    ref=dict(family='KNOWLEDGE',entity_id=result['result_entity_id'],revision_id=result['result_revision_id'],content_digest=digest)
    return source,ref


def test_batched_source_reads_equal_serial_and_recheck_revocation_on_next_use(store):
    db,_=store
    docs=[document(),dict(document('A second complete procedure.'),path='/docs/second.md')]
    source=prepare_source(docs)
    refs=[SourceRef.model_validate(item['source']) for item in
        curated.import_documents('owner',source,request(docs))['imports']]
    def compare(tx):
        serial=[sync.resolve_source(tx,'owner','domain',ref) for ref in refs]
        assert sync.resolve_source_batch(tx,'owner','domain',refs)==serial
    sync.connection.execute_transaction_callback(compare)
    sync.change_state('owner',source,dict(expected_version=1,status='REVOKED',reason='Revoke batch source',idempotency_key='batch-revoke'))
    assert sync.connection.execute_transaction_callback(
        lambda tx:sync.resolve_source_batch(tx,'owner','domain',refs,omit_denied=True))==[None,None]


def test_shared_agent_authority_is_rechecked_in_both_phases_without_cross_call_cache(store, monkeypatch):
    from lib import agent_assets
    db,_ = store
    docs = [document(), dict(document('Another complete source unit.'),path='/docs/another.md')]
    source = prepare_source(docs)
    refs = [SourceRef.model_validate(item['source']) for item in
            curated.import_documents('owner',source,request(docs))['imports']]
    calls = []
    original = agent_assets._agent
    def tracked(*args, **kwargs):
        calls.append(args[1:])
        return original(*args, **kwargs)
    monkeypatch.setattr(agent_assets,'_agent',tracked)
    def read(tx):
        result = sync.resolve_source_batch(tx,'owner','domain',[*refs,refs[0]])
        assert result[0] == result[2] and result[0] is not result[2]
        return result
    assert len(sync.connection.execute_transaction_callback(read)) == 3
    assert len(calls) == 2, 'Same Agent/domain must be freshly authorized before and after bodies'
    sync.connection.execute_transaction_callback(read)
    assert len(calls) == 4, 'No authority cache survives a batch call'


@pytest.mark.parametrize('fault',['digest','retired','pair'])
def test_batch_rejects_unavailable_revision_metadata_before_loading_any_cipher(store,fault):
    db,_=store
    doc=document();source=prepare_source([doc])
    ref=SourceRef.model_validate(curated.import_documents('owner',source,request([doc]))['imports'][0]['source'])
    if fault=='digest':ref=ref.model_copy(update={'content_digest':'0'*64})
    elif fault=='retired':
        db.execute("UPDATE CX_AGENT_SOURCE_REVISIONS SET LIFECYCLE_STATE='RETIRED'");db.commit()
    else:ref=ref.model_copy(update={'revision_id':'SR_not_an_owned_revision'})
    def read(tx):
        class MetadataOnly:
            def query(self,statement,params):
                assert 'CONTENT_CIPHER' not in statement.upper(),'Denied source body reached the native reader'
                return tx.query(statement,params)
            def query_one(self,statement,params):return tx.query_one(statement,params)
        return sync.resolve_source_batch(MetadataOnly(),'owner','domain',[ref],omit_denied=True)
    assert sync.connection.execute_transaction_callback(read)==[None]


@pytest.mark.parametrize('change',['revoke','revision','provenance'])
def test_batch_never_returns_bodies_after_authority_or_integrity_changes(store,monkeypatch,change):
    db,_=store
    doc=document();source=prepare_source([doc])
    ref=SourceRef.model_validate(curated.import_documents('owner',source,request([doc]))['imports'][0]['source'])
    if change=='provenance':
        cipher=json.loads(db.execute('SELECT CONTENT_CIPHER FROM CX_AGENT_SOURCE_REVISIONS').fetchone()[0])
        cipher['curated']['origin']['locator']='docs/false-batch-source.md'
        db.execute('UPDATE CX_AGENT_SOURCE_REVISIONS SET CONTENT_CIPHER=?',(json.dumps(cipher),));db.commit()
        with pytest.raises(ContinuityError,match='provenance'):
            sync.connection.execute_transaction_callback(lambda tx:sync.resolve_source_batch(tx,'owner','domain',[ref]))
        return
    original=sync._resolved_source
    def changed(*args):
        result=original(*args)
        if change=='revoke':db.execute("UPDATE CX_AGENT_SOURCES SET STATUS='REVOKED'")
        else:db.execute("UPDATE CX_AGENT_SOURCE_REVISIONS SET LIFECYCLE_STATE='RETIRED'")
        return result
    monkeypatch.setattr(sync,'_resolved_source',changed)
    if change=='revoke':
        assert sync.connection.execute_transaction_callback(
            lambda tx:sync.resolve_source_batch(tx,'owner','domain',[ref],omit_denied=True))==[None]
    else:
        with pytest.raises(ContinuityConflict,match='changed'):
            sync.connection.execute_transaction_callback(lambda tx:sync.resolve_source_batch(tx,'owner','domain',[ref]))


def test_bulk_projection_context_equals_exact_serial_reads_and_denies_either_reader(store,monkeypatch):
    from lib import continuity_promotions as promotions
    db,_=store
    published_source(db)
    native=db.execute('SELECT NATIVE_ENTITY_ID FROM CX_CONTINUITY_ARTIFACT_REVS').fetchone()[0]
    serial=sync.connection.execute_transaction_callback(lambda tx:promotions.require_original_sources(tx,'owner',native))
    bulk=lambda actors:sync.connection.execute_transaction_callback(
        lambda tx:promotions.original_source_contexts(actors,[native],transaction=tx))
    assert bulk(('owner','agent'))=={native:serial}
    authority=sync._authority
    def deny_agent(tx,actor,source,**kwargs):
        if actor=='agent':raise PermissionError('Synthetic original source grant revoked')
        return authority(tx,actor,source,**kwargs)
    monkeypatch.setattr(sync,'_authority',deny_agent)
    assert bulk(('owner','agent'))=={native:None}
    # The first reader's successful original must not authorize the other.
    assert bulk(('agent','owner'))=={native:None}
    assert bulk(('owner',))=={native:serial}


def test_bulk_projection_rejects_retirement_during_source_body_loading(store,monkeypatch):
    from lib import continuity_promotions as promotions
    db,_=store
    published_source(db)
    native=db.execute('SELECT NATIVE_ENTITY_ID FROM CX_CONTINUITY_ARTIFACT_REVS').fetchone()[0]
    original=sync._resolved_source
    def retire(*args):
        result=original(*args)
        db.execute("UPDATE CX_CONTINUITY_ARTIFACTS SET STATUS='RETIRED'")
        return result
    monkeypatch.setattr(sync,'_resolved_source',retire)
    with pytest.raises(ContinuityConflict,match='changed'):
        sync.connection.execute_transaction_callback(
            lambda tx:promotions.original_source_contexts(('owner',),[native],transaction=tx))


@pytest.mark.parametrize('bulk',[False,True])
def test_memory_summary_retains_original_proposal_and_revocation_even_when_locator_changes(store,bulk):
    from lib import continuity_sources,continuity_assembly as assembly,knowledge_api,context_selection
    from .test_continuity_candidates import new_candidate
    db,_=store
    source,knowledge=published_source(db)
    # Give the independent reviewer explicit access to the synthetic private
    # Knowledge before using it as an original, as in the real review contract.
    native=db.execute('SELECT NATIVE_ENTITY_ID FROM CX_CONTINUITY_ARTIFACT_REVS').fetchone()[0]
    knowledge_api.set_access_policy(native,'PUBLIC_COMPANY','owner',reason='Explicit synthetic Memory review access')
    references=[]
    for number in range(2 if bulk else 1):
        content=dict(family='MEMORY',title='Boreal summary '+str(number),body='A sourced summary of the retention proposal.',memory_type='FACT')
        cid=candidates.create_candidate('owner',new_candidate(knowledge,content,key='memory-'+str(number)))['candidate_id']
        result=candidates.promote_candidate('agent',cid,approve(cid))
        version=db.execute('SELECT CONTENT_DIGEST FROM CX_MEMORY_VERSIONS WHERE VERSION_ID=?',(result['result_revision_id'],)).fetchone()
        references.append(dict(family='MEMORY',entity_id=result['result_entity_id'],revision_id=result['result_revision_id'],content_digest=version[0]))
    # Attaching an external Artifact can change the locator. It cannot erase
    # the authoritative candidate-result binding or grant original-source access.
    db.execute("UPDATE CX_MEMORY_VERSIONS SET SOURCE_REF='artifact:replacement-locator'");db.commit()
    values=sync.connection.execute_transaction_callback(lambda tx:continuity_sources.resolve_many(tx,'owner','domain',references))
    for value in values:
        ancestor=value['source_context']['derived_sources'][0]['source_context']
        assert ancestor['intake']['decision_status']=='PROPOSED'
        assert ancestor['provenance'][0]['origin']['decision_status']=='PROPOSED'
        assert 'source_context' not in json.loads(value['text'])
    for ref in references:
        metadata=sync.connection.execute_transaction_callback(lambda tx:context_selection.metadata(tx,'owner','domain',ref))
        assert metadata['source_context']['derived_sources'][0]['source_context']['intake']['decision_status']=='PROPOSED'
    result=assembly.assemble('owner',dict(request_id='memory-context',security_domain_id='domain',
        purpose='Use a sourced summary',sources=references,token_budget=64000,idempotency_key='memory-context',
        applicability=dict(product='unified-community',version='5.0.3',decision_statuses=['PROPOSED'])))
    context=assembly.read_assembly('owner',result['assembly_id'])
    assert context['item_count']==len(references) and 'PROPOSED' in context['text']
    sync.change_state('owner',source,dict(expected_version=1,status='REVOKED',reason='Withdraw original proposal',idempotency_key='withdraw'))
    with pytest.raises(PermissionError):
        sync.connection.execute_transaction_callback(lambda tx:continuity_sources.resolve_many(tx,'owner','domain',references))
    for ref in references:
        with pytest.raises(PermissionError):
            sync.connection.execute_transaction_callback(lambda tx:context_selection.metadata(tx,'owner','domain',ref))
    with pytest.raises(PermissionError):assembly.read_assembly('owner',result['assembly_id'])
    sends=[]
    with pytest.raises(PermissionError):assembly.consume('owner',result['assembly_id'],sends.append)
    assert sends==[] and db.execute('SELECT COUNT(*) FROM CX_MEMORY_VERSIONS').fetchone()[0]==len(references)


@pytest.mark.parametrize('mandatory',[False,True])
def test_task_assembly_applies_scope_and_keeps_required_source_failure_atomic(store,mandatory):
    from lib import continuity_assembly as assembly
    db,_=store
    _,reference=published_source(db)
    value=dict(request_id='scoped-context',security_domain_id='domain',purpose='Use an applicable source',
        token_budget=32000,idempotency_key='scoped-context',
        applicability=dict(product='unified-community',version='5.0.2'))
    value['mandatory_sources' if mandatory else 'sources']=[reference]
    if mandatory:
        with pytest.raises(ContinuityConflict) as error:assembly.assemble('owner',value)
        assert error.value.code=='SOURCE_NOT_APPLICABLE'
        assert db.execute('SELECT COUNT(*) FROM CX_CONTEXT_ASSEMBLIES').fetchone()[0]==0
    else:
        created=assembly.assemble('owner',value)
        context=assembly.read_assembly('owner',created['assembly_id'])
        assert context['item_count']==0 and context['text']==''
        assert context['representations'][0]['selection_reason']=='SOURCE_NOT_APPLICABLE'
    value.update(idempotency_key='correct-scope',applicability=dict(product='unified-community',version='5.0.3',
        as_of='2026-11-01T00:00:00Z',decision_statuses=['PROPOSED']))
    created=assembly.assemble('owner',value)
    context=assembly.read_assembly('owner',created['assembly_id'])
    assert context['item_count']==1 and 'PROPOSED' in context['text']
    # The structured scope is part of request identity; changing it cannot
    # replay a preparation authorized under different applicability.
    with pytest.raises(ContinuityConflict):
        assembly.assemble('owner',dict(value,applicability=dict(version='5.0.2')))


def test_manual_memory_successors_keep_reviewed_origins_and_cannot_erase_withdrawal(store,monkeypatch):
    from lib import continuity_sources,context_selection,knowledge_api,memory_lifecycle as memory
    from .test_continuity_candidates import new_candidate
    db,_=store
    monkeypatch.setattr(memory,'execute_transaction_callback',sync.connection.execute_transaction_callback)
    source,knowledge=published_source(db)
    native=db.execute('SELECT NATIVE_ENTITY_ID FROM CX_CONTINUITY_ARTIFACT_REVS').fetchone()[0]
    knowledge_api.set_access_policy(native,'PUBLIC_COMPANY','owner',reason='Explicit synthetic review access')
    cid=candidates.create_candidate('owner',new_candidate(knowledge,
        dict(family='MEMORY',title='Reviewed summary',body='Retention remains a proposal.',memory_type='FACT')))['candidate_id']
    promoted=candidates.promote_candidate('agent',cid,approve(cid))
    family,original=promoted['result_entity_id'],promoted['result_revision_id']
    revision=original
    for number in range(3):
        successor=memory.create_successor(family,revision,dict(title='Edited summary '+str(number),
            body='An edited summary is still based on the proposal.',memory_type='FACT',security_domain_id='domain',
            owner_principal_id='owner',source_ref='unrelated:manual-note',reason='Review wording'),actor='owner')
        revision=successor['version_id']
    digest=db.execute('SELECT CONTENT_DIGEST FROM CX_MEMORY_VERSIONS WHERE VERSION_ID=?',(revision,)).fetchone()[0]
    reference=dict(family='MEMORY',entity_id=family,revision_id=revision,content_digest=digest)
    read=lambda:sync.connection.execute_transaction_callback(lambda tx:continuity_sources.resolve(tx,'owner','domain',reference))
    metadata=lambda:sync.connection.execute_transaction_callback(lambda tx:context_selection.metadata(tx,'owner','domain',reference))
    for value in (read(),metadata()):
        context=value['source_context']
        assert context['candidate_id']==cid
        assert context['inherited_memory_origin']['revision_id']==original
        assert context['derived_sources'][0]['source_context']['intake']['decision_status']=='PROPOSED'
    sync.change_state('owner',source,dict(expected_version=1,status='REVOKED',reason='Withdraw original',idempotency_key='withdraw'))
    for operation in (read,metadata):
        with pytest.raises(PermissionError):operation()
    assert db.execute('SELECT COUNT(*) FROM CX_MEMORY_VERSIONS').fetchone()[0]==4


@pytest.mark.parametrize('planned',[False,True])
def test_new_task_context_binds_applicability_and_revocation_before_dispatch(store,planned):
    from lib import continuity_assembly as assembly
    db,_=store
    source,ref=published_source(db)
    value=dict(request_id='context',security_domain_id='domain',purpose='Use reviewed retention sources',
        sources=[ref],token_budget=16000,idempotency_key='context')
    if planned:value['mandatory_sources']=[ref]
    result=assembly.assemble('owner',value)
    context=assembly.read_assembly('owner',result['assembly_id'])
    envelope=json.loads(context['text'])
    assert envelope['source']==ref
    assert envelope['source_context']['intake']['decision_status']=='PROPOSED'
    assert envelope['source_context']['intake']['applicable_version']=='5.0.3'
    assert envelope['source_context']['provenance'][0]['origin']['decision_status']=='PROPOSED'
    assert json.loads(envelope['content'])['body']==document()['text'].strip()
    assert context['content_digest']==hashlib.sha256(context['text'].encode()).hexdigest()
    sync.change_state('owner',source,dict(expected_version=1,status='REVOKED',reason='Withdraw source',idempotency_key='withdraw'))
    sends=[]
    with pytest.raises(PermissionError):assembly.consume('owner',result['assembly_id'],sends.append)
    assert sends==[]
    assert db.execute('SELECT COUNT(*) FROM CX_CONTEXT_INPUT_USES').fetchone()[0]==0


def test_applicability_cannot_be_cut_off_to_fit_a_task_context(store):
    from lib import continuity_assembly as assembly
    db,_=store
    _,ref=published_source(db)
    result=assembly.assemble('owner',dict(request_id='context',security_domain_id='domain',
        purpose='Budgeted procedure lookup',sources=[ref],query_text='Boreal procedure',token_budget=100,
        allow_partial=True,idempotency_key='small'))
    context=assembly.read_assembly('owner',result['assembly_id'])
    assert context['text']=='' and context['item_count']==0
    assert context['representations'][0]['representation']=='OMITTED'
    assert context['representations'][0]['delivery_status']=='OMITTED'


@pytest.mark.parametrize('planned',[False,True])
def test_historical_task_context_keeps_exact_bytes_but_rechecks_sources(store,monkeypatch,planned):
    from lib import continuity_assembly as assembly
    db,_=store
    source,ref=published_source(db)
    value=dict(request_id='old-context',security_domain_id='domain',purpose='Historical prepared input',
        sources=[ref],token_budget=16000,idempotency_key='old-context')
    if planned:value['mandatory_sources']=[ref]
    # Reconstruct the historical renderer, not the source body or its digest.
    with monkeypatch.context() as patch:
        patch.setattr(assembly,'_source_text',lambda resolved,**kwargs:resolved['text'])
        result=assembly.assemble('owner',value)
    policy='QUERY_METADATA_BUDGET_V1' if planned else 'EXPLICIT_ORDER_UTF8_UPPER_BOUND'
    db.execute('UPDATE CX_CONTEXT_ASSEMBLIES SET RETRIEVAL_POLICY=? WHERE ASSEMBLY_ID=?',(policy,result['assembly_id']))
    db.commit()
    context=assembly.read_assembly('owner',result['assembly_id'])
    assert json.loads(context['text'])==dict(family='KNOWLEDGE',title='Boreal procedure',body=document()['text'].strip())
    assert context['content_digest']==result['content_digest']
    assert assembly.assemble('owner',value)['replayed']
    received=[]
    assembly.consume('owner',result['assembly_id'],received.append)
    assert received==[context['text']]
    sync.change_state('owner',source,dict(expected_version=1,status='REVOKED',reason='Withdraw source',idempotency_key='withdraw'))
    with pytest.raises(PermissionError):assembly.read_assembly('owner',result['assembly_id'])


def test_derived_summary_retains_original_proposal_status_and_transitive_revocation(store):
    from lib import continuity_sources,knowledge_api
    from .test_continuity_candidates import new_candidate
    db,_=store
    source,ref=published_source(db)
    # A reviewer has no implicit read of the owner's private Knowledge. Make
    # this synthetic reviewed projection explicitly shared before review.
    native=db.execute('SELECT NATIVE_ENTITY_ID FROM CX_CONTINUITY_ARTIFACT_REVS').fetchone()[0]
    knowledge_api.set_access_policy(native,'PUBLIC_COMPANY','owner',reason='Explicit synthetic summary review access')
    value=new_candidate(ref,dict(family='KNOWLEDGE',title='Boreal summary',
        body='Boreal records: 30-day retention; preserve records under legal hold.'),key='summary')
    cid=candidates.create_candidate('owner',value)['candidate_id']
    result=candidates.promote_candidate('agent',cid,approve(cid))
    digest=db.execute('SELECT CONTENT_DIGEST FROM CX_CONTINUITY_ARTIFACT_REVS WHERE REVISION_ID=?',
        (result['result_revision_id'],)).fetchone()[0]
    summary=SourceRef(family='KNOWLEDGE',entity_id=result['result_entity_id'],
        revision_id=result['result_revision_id'],content_digest=digest)
    read=lambda:sync.connection.execute_transaction_callback(lambda tx:continuity_sources.resolve(tx,'owner','domain',summary))
    context=read()['source_context']
    assert context['intake']['decision_status']=='CURRENT'
    original=context['derived_sources'][0]
    assert original['source']==ref and original['source_context']['intake']['decision_status']=='PROPOSED'
    sync.change_state('owner',source,dict(expected_version=1,status='REVOKED',reason='Withdraw original proposal',idempotency_key='withdraw'))
    with pytest.raises(PermissionError):read()


def test_duplicate_preview_cannot_disclose_a_revoked_derived_source(store):
    from .test_continuity_candidates import new_candidate
    db,handoff_source=store
    source,_=published_source(db)
    value=new_candidate(handoff_source,dict(family='KNOWLEDGE',title='Boreal procedure',body='Another procedure.'))
    assert len(candidates.preview_knowledge('owner',value)['comparisons'])==1
    sync.change_state('owner',source,dict(expected_version=1,status='REVOKED',reason='Withdraw original proposal',idempotency_key='withdraw'))
    assert candidates.preview_knowledge('owner',value)['comparisons']==[]
