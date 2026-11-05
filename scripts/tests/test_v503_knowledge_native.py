"""Opt-in persistent-development checks; never select a baseline implicitly.

Run from a generated package with CX_DEVELOPMENT_TARGET and the reviewed
CX_DEVELOPMENT_MANIFEST. Uses native transactions and current service authority;
does not invoke models or claim HTTP acceptance. Independent-login assertions
use real backend credentials only in the explicitly selected isolated target.
"""
from datetime import datetime, timedelta, timezone
from contextlib import contextmanager
import json
import hashlib
import os
from pathlib import Path
import uuid
import time
import re
import shutil

import pytest

from lib import connection, config, product_identity, product_knowledge, knowledge_intake, knowledge_api
from lib import continuity_work as work, continuity_handoff as handoff, continuity_candidates as candidates
from lib import security_domain_api, identity_api, agent_gateway_api, agent_api, edition_features
from lib.continuity_state import ContinuityConflict
from lib import knowledge_grounding,knowledge_signals,embedding_api
from lib import answer_planning,business_channel_runtime
from lib import agent_source_sync,knowledge_curated
from lib.continuity_contracts import SourceRef
from lib import continuity_sources,continuity_assembly,context_selection


def native_entity(value,backend):
    return int(value) if backend=='pg' else str(value)


def test_native_private_knowledge_creation_rolls_back_rejected_actor_and_late_audit(native_target,monkeypatch,record_property):
    target,actor=native_target
    domain='V503_NOTE_'+uuid.uuid4().hex.upper()
    reason='Native private knowledge transaction rollback verification'
    security_domain_api.create_domain(actor,domain,'503 private note atomicity','INTERNAL',reason,actor,reason)
    tables=('ENTITIES','KNOWLEDGE_META','CX_KNOWLEDGE_CONTEXTS','CX_KNOWLEDGE_ACCESS_POLICIES')
    def counts():
        return {table:connection.execute_query_one('SELECT COUNT(*) AS N FROM '+table)['n'] for table in tables}
    with independent_reviewer(actor,domain,reason) as agent:
        before=counts()
        with pytest.raises(PermissionError):
            knowledge_api.create_knowledge(domain,'Must not persist',owned_by_agent='V503_MISSING_'+uuid.uuid4().hex)
        assert counts()==before
        original_audit=identity_api._audit_tx
        def failed_audit(*args,**kwargs):
            original_audit(*args,**kwargs)
            if args[2]=='KNOWLEDGE_POLICY_CHANGE':
                raise RuntimeError('Deliberate private-note audit failure')
        with monkeypatch.context() as change:
            change.setattr(identity_api,'_audit_tx',failed_audit)
            with pytest.raises(RuntimeError,match='Deliberate private-note audit failure'):
                knowledge_api.create_knowledge(domain,'Rollback entity, metadata, context and policy',owned_by_agent=agent)
        assert counts()==before
        assert connection.execute_query_one("SELECT COUNT(*) AS N FROM CX_SECURITY_EVENTS WHERE ACTION_NAME='KNOWLEDGE_POLICY_CHANGE' AND PRINCIPAL_ID=:agent",dict(agent=agent))['n']==0
        note=knowledge_api.create_knowledge(domain,'Exact private note',owned_by_agent=agent,difficulty='BEGINNER')
        try:
            assert knowledge_api.get_knowledge(note,principal_id=agent)['content']=='Exact private note'
            assert knowledge_api.get_access_policy(note)['principal_id']==agent
            assert knowledge_api.get_knowledge_context(note)['agent_id']==agent
            record_property('native_private_knowledge_atomicity',json.dumps(dict(target=target['key'],
                rejected_actor_no_rows=True,late_audit_full_rollback=True,exact_private_readback=True,
                generation_calls=0,embedding_calls=0)))
        finally:
            knowledge_api.delete_knowledge(note)


def test_native_pg_artifact_pointer_join_preserves_exact_ids_and_rejects_invalid_text(native_target,record_property):
    """Execute the real PG adapter expression, including unsafe legacy locators."""
    target,_actor=native_target
    if target['database']!='pg':
        pytest.skip('PG text-pointer to native BIGINT boundary')
    from lib import knowledge_retrieval_adapter
    pointers=['0','1','-1','9223372036854775807','-9223372036854775808',
        '9223372036854775808','-9223372036854775809','00','01','-0','+1','1.0',
        ' 1','1 ','1\n','','1e0','x','9'*128,None,'١']
    entities=[0,1,-1,9223372036854775807,-9223372036854775808]
    params={**{'pointer'+str(i):value for i,value in enumerate(pointers)},
        **{'entity'+str(i):value for i,value in enumerate(entities)}}
    tables=(' FROM (VALUES '+','.join('(CAST(:pointer'+str(i)+' AS VARCHAR(128)))'
        for i in range(len(pointers)))+') p(NATIVE_ENTITY_ID) CROSS JOIN (VALUES '+
        ','.join('(CAST(:entity'+str(i)+' AS BIGINT))' for i in range(len(entities)))+') e(ENTITY_ID) WHERE ')
    def read(tx):
        tx.execute('SET TRANSACTION READ ONLY')
        base='SELECT p.NATIVE_ENTITY_ID,e.ENTITY_ID'+tables
        original=tx.query(base+'p.NATIVE_ENTITY_ID=CAST(e.ENTITY_ID AS VARCHAR(128)) ORDER BY e.ENTITY_ID',params)
        current=tx.query(base+knowledge_retrieval_adapter.artifact_entity_join('p.NATIVE_ENTITY_ID','e.ENTITY_ID')+
            ' ORDER BY e.ENTITY_ID',params)
        assert original==current
        assert len(current)==len(entities)
        assert {row['native_entity_id'] for row in current}==set(map(str,entities))
    connection.execute_transaction_callback(read)
    record_property('native_artifact_pointer_join',json.dumps(dict(target=target['key'],
        pointer_samples=len(pointers),entity_samples=len(entities),exact_text_equivalence=True,
        invalid_and_overflow_rejected=True,readonly=True,generation_calls=0,embedding_calls=0)))


def test_native_task_compatibility_reuses_topology_and_typed_plan_locator(native_target,record_property):
    """Actual adapter operations; no model and no simulated external receipt."""
    from lib import task_plan_api,graph_compat,graph_runtime
    target,actor=native_target
    domain='V503_TASK_'+uuid.uuid4().hex.upper()
    reason='Native Task topology reuse, typed plan locator and exact Graph binding; no generation'
    security_domain_api.create_domain(actor,domain,'Native Task binding check','INTERNAL',reason,actor,reason)
    with independent_reviewer(actor,domain,reason) as agent:
        for action in ('tasks.read','tasks.write','graphs.read','graphs.write'):
            identity_api.assign_permission_override(actor,agent,action,'ALLOW','OWNED',reason)
        plan_id=task_plan_api.create_plan(agent,reason,strategy='V503_NATIVE_GRAPH_BINDING')
        step_id=task_plan_api.add_step(plan_id,'PENDING','Check original Graph version without model use',1)
        plan=task_plan_api.get_plan(plan_id)
        steps=task_plan_api.get_plan_steps(plan_id)
        assert len(steps)==1 and steps[0]['started_at'] is None and steps[0]['completed_at'] is None
        original=graph_compat.get_binding('TASK_PLAN',plan_id)
        versions=len(connection.execute_query('SELECT GRAPH_VERSION_ID FROM GRAPH_VERSIONS WHERE GRAPH_ID=:graph',dict(graph=original['graph_id'])))
        for _ in range(2):
            current=graph_compat.ensure_task_plan_graph(plan,steps)
            assert current['graph_version_id']==original['graph_version_id']
        assert len(connection.execute_query('SELECT GRAPH_VERSION_ID FROM GRAPH_VERSIONS WHERE GRAPH_ID=:graph',dict(graph=original['graph_id'])))==versions
        assert task_plan_api.update_plan(plan_id,status='RUNNING')
        running=graph_compat.get_binding('TASK_PLAN',plan_id)
        assert running['graph_version_id']==original['graph_version_id']
        assert graph_runtime.get_run(running['graph_run_id'])['graph_version_id']==running['graph_version_id']
        assert task_plan_api.update_step(step_id,status='RUNNING')
        started=task_plan_api.get_plan_steps(plan_id)[0]
        assert started['started_at'] and started['completed_at'] is None
        assert task_plan_api.update_step(step_id,status='SUCCESS',tool_output=dict(check='NATIVE_RELATIONAL_BINDING',model_requests=0))
        completed=task_plan_api.get_plan_steps(plan_id)[0]
        assert completed['started_at']==started['started_at'] and completed['completed_at']
        assert task_plan_api.update_plan(plan_id,status='SUCCESS',result_summary=reason)
        assert graph_compat.get_binding('TASK_PLAN',plan_id)['graph_version_id']==original['graph_version_id']
        record_property('native_task_binding',json.dumps(dict(target=target['key'],plan_id=str(plan_id),step_id=str(step_id),
            stable_graph_version=True,native_step_transition=True,generation_calls=0,embedding_calls=0)))


def test_native_private_skill_directory_retains_owner_and_rechecks_exact_content(native_target,record_property):
    from lib import skill_api, agent_directory
    target,actor=native_target
    domain='V503_SKILL_'+uuid.uuid4().hex.upper()
    reason='Owned private Skill metadata discovery and exact loading without execution or generation'
    security_domain_api.create_domain(actor,domain,'Native private Skill directory','INTERNAL',reason,actor,reason)
    with independent_reviewer(actor,domain,reason) as agent:
        identity_api.assign_permission_override(actor,agent,'skills.read','ALLOW','OWNED',reason)
        label='v503-owned-skill-'+uuid.uuid4().hex
        body='Private reference only. Reading this Skill grants no permission to execute or publish.'
        skill=skill_api.register_skill(label,label,text_content=body,owned_by_agent=agent,visibility='PRIVATE')
        try:
            assert skill_api.get_skill(skill)['owned_by_agent']==agent
            discovered=agent_directory.search(agent,domain,'SKILL',label)
            assert len(discovered['items'])==1 and not discovered['body_loaded_for_client']
            assert not discovered['discovery_grants_execution']
            entry=discovered['items'][0]
            assert str(entry['entity_id'])==str(skill) and 'content' not in entry
            loaded=agent_directory.load(agent,domain,'SKILL',entry['entity_id'],entry['version'],entry['content_digest'])
            assert loaded['content']['text_content']==body and not loaded['execution_authorized']
            with pytest.raises(ValueError,match='version or content changed'):
                agent_directory.load(agent,domain,'SKILL',entry['entity_id'],entry['version'],'0'*64)
            assert skill_api.deprecate_skill(skill)
            assert agent_directory.search(agent,domain,'SKILL',label)['items']==[]
            with pytest.raises(PermissionError,match='withdrawn'):
                agent_directory.load(agent,domain,'SKILL',entry['entity_id'],entry['version'],entry['content_digest'])
            record_property('native_private_skill',json.dumps(dict(target=target['key'],
                exact_owner_retained=True,private_discovery=True,exact_loading=True,withdrawal_denied=True,
                generation_calls=0,embedding_calls=0)))
        finally:
            skill_api.deprecate_skill(skill)


@pytest.fixture(scope='module')
def native_target():
    key=os.environ.get('CX_DEVELOPMENT_TARGET')
    if not key:
        pytest.skip('Explicit classified persistent development target required')
    manifest=json.loads(Path(os.environ['CX_DEVELOPMENT_MANIFEST']).read_text())
    target=next(item for item in manifest['targets'] if item['key']==key)
    assert target['classification']=='temporary' and target['purpose']=='persistent-version-development'
    assert target['name'] not in manifest['protected'][target['database']]
    settings=config.load_config().database
    receipt_root=Path(os.environ['CX_CONFIG_PATH']).parent
    if target['database']=='pg':
        assert (settings.host,settings.port,settings.dbname)==(target['host'],target['port'],target['name'])
        actual=connection.execute_query_one('SELECT CURRENT_DATABASE() AS NAME,(SELECT oid FROM pg_database WHERE datname=CURRENT_DATABASE()) AS OID')
        assert actual['name']==target['name']
        receipt_path=receipt_root/'resume-result.json' if (receipt_root/'resume-result.json').exists() else receipt_root/'copy-result.json'
        receipt=json.loads(receipt_path.read_text())
        assert receipt['status']=='COMPLETE' and int(actual['oid'])==receipt['native_identity']['oid']
    elif target['database']=='oracle':
        assert settings.dsn.lower()==f"{target['host']}:{target['port']}/{target['name']}".lower()
        assert settings.user.upper()==target['owner']
        actual=connection.execute_query_one("SELECT SYS_CONTEXT('USERENV','CON_NAME') AS NAME,"
            "SYS_CONTEXT('USERENV','CON_DBID') AS DBID FROM DUAL")
        assert actual['name'].upper()==target['name'].upper()
        complete=receipt_root/'native-copy-result.json'
        if complete.exists():
            receipt=json.loads(complete.read_text())
            assert receipt['target']==target['key'] and receipt['status']=='COMPLETE'
            assert receipt['native_security_metadata_verified'] and receipt['application_catalog_verified']
            assert receipt['application_table_counts_verified'] > 0 and receipt['scheduler_disabled']
            assert not receipt['full_pdb_clone']
            observation=receipt['target_observation']
            # This receipt proves its recorded catalog/security/count scope;
            # it does not assert comparison of every stored row value.
        else:
            receipt=json.loads((receipt_root/'development-admission.json').read_text())
            assert receipt['target']==target['key'] and receipt['status']=='DEVELOPMENT_ONLY'
            assert receipt['native_security_verified'] and not receipt['full_copy_acceptance']
            observation=receipt['observation']
        identity=re.search(r'^IDENTITY\|(\d+)\|([A-F0-9]+)$',observation,re.M)
        assert identity and str(actual['dbid'])==identity.group(1)
    elif target['database']=='yashandb':
        assert settings.dsn.lower()==f"{target['host']}:{target['port']}/{target['name']}".lower()
        assert settings.user.upper()==target['owner']
        receipt=json.loads((receipt_root/'native-copy-result.json').read_text())
        assert receipt['target']==target['key'] and receipt['status']=='VERIFIED_APPLICATION_COPY'
        assert receipt['native_security_verified'] and receipt['exact_row_values_verified']
        assert receipt['exact_stored_definitions_verified'] and not receipt['full_pdb_clone']
        actual=connection.execute_query_one('SELECT CON_ID,OID,RAWTOHEX(CON_UID) AS UID,NAME FROM V$PDBS')
        assert {k:(int(actual[k]) if k in {'con_id','oid'} else actual[k])
                for k in ('con_id','oid','uid','name')}==receipt['native_identity']
        assert actual['name'].upper()==target['name'].upper()
    else:
        pytest.fail('Extend exact native identity checks before selecting another backend')
    product=product_identity.identity()
    assert product['product_key']==target['source_product'] and product['version']==manifest['version']
    rows=connection.execute_query("SELECT DISTINCT i.PRINCIPAL_ID FROM CX_HUMAN_IDENTITIES i "
        "JOIN CX_PRINCIPALS p ON p.PRINCIPAL_ID=i.PRINCIPAL_ID "
        "WHERE i.USERNAME='admin' AND i.IDENTITY_TYPE='LOCAL' AND i.STATUS='ACTIVE' AND p.STATUS='ACTIVE'")
    assert len(rows)==1
    actor=str(rows[0]['principal_id'])
    return target,actor


@contextmanager
def independent_reviewer(actor, domain, reason):
    """Normal owned Agent lifecycle, never elevate a built-in system Agent.

    The API reviewer is an automated test identity, not a Human quality review.
    Native identity teardown remains part of the assertion even on test failure.
    """
    reviewer='V503_REVIEW_'+uuid.uuid4().hex.upper()
    enrolled=None
    try:
        grant=identity_api.create_enrollment_grant(actor,actor,environment='development',
            runtime='native-knowledge-verification',security_domain_id=domain,
            agent_name=reviewer,risk_tier='LOW',ttl_seconds=900)
        enrolled=identity_api.redeem_enrollment(grant['token'],reviewer,
            runtime='native-knowledge-verification',environment='development')
        proof=agent_gateway_api.authenticate_activation_client_secret(reviewer,enrolled['credential'])
        assert proof and enrolled['status']=='PENDING_ACTIVATION'
        baseline=dict(runtime='native-knowledge-verification',purpose=reason,external_runtime_started=False)
        if edition_features.has_feature('compliance'):
            from lib import compliance_api
            compliance_api.activate_from_gateway(reviewer,baseline,credential_type=proof['credential_type'],
                runtime='native-knowledge-verification',environment='development',security_domain_id=domain)
        else:
            identity_api.activate_community_agent(reviewer,domain,baseline)
        assert agent_gateway_api.authenticate_client_secret(reviewer,enrolled['credential'])
        snapshot=agent_api.native_identity_snapshot(reviewer)
        assert snapshot['mapping_state']==snapshot['native_state']=='OBSERVED'
        assert snapshot['login_enabled'] and not snapshot['native_privileged']
        identity_api.transfer_agent_owner(actor,reviewer,actor,reason)
        security_domain_api.set_member(actor,domain,reviewer,'ADMIN',reason)
        for action in ('workspaces.read','workspaces.write','knowledge.read','knowledge.write','actions.propose'):
            identity_api.assign_permission_override(actor,reviewer,action,'ALLOW','OWNED',reason)
            assert identity_api.effective_access(reviewer,action,resource={'security_domain_id':domain})['decision']=='ALLOW'
        yield reviewer
    finally:
        connection.set_agent_context(None)
        if enrolled is not None:
            result=identity_api.offboard_agent(actor,reviewer,environment='DEVELOPMENT',reason=reason)
            native=result['native_identity_revocation']
            assert native['status']=='COMPLETE' and native['audit_status']=='RECORDED'
            assert native['new_connections_blocked'] is True
        security_domain_api.set_domain_status(actor,domain,'REVOKED',reason)


def test_published_learning_is_discoverable_without_bulk_content_and_exactly_readable(native_target,record_property):
    target,actor=native_target
    history=connection.execute_query('SELECT KNOWLEDGE_ID,CONTENT_JSON,CONTENT_DIGEST FROM CX_PLATFORM_KNOWLEDGE '
        'WHERE KNOWLEDGE_KEY=:package_key OR KNOWLEDGE_KEY LIKE :snapshots',
        dict(package_key='product-guide:'+target['source_product'],snapshots='product-guide:'+target['source_product']+':%'))
    text=lambda value:value.read() if hasattr(value,'read') else value
    original={row['knowledge_id']:(text(row['content_json']),row['content_digest']) for row in history}
    result=product_knowledge.publish(actor,target['database'])
    separate=product_knowledge.delivery()['delivery']=='separate'
    assert result['status']=='PUBLISHED' and len(result['knowledge_ids'])==(4 if separate else 13)
    assert re.fullmatch('[a-f0-9]{64}',result['snapshot_revision'])
    for key,values in original.items():
        row=connection.execute_query_one('SELECT CONTENT_JSON,CONTENT_DIGEST FROM CX_PLATFORM_KNOWLEDGE WHERE KNOWLEDGE_ID=:knowledge_id',
            dict(knowledge_id=key))
        assert (text(row['content_json']),row['content_digest'])==values
    directory=product_knowledge.learning_catalog(actor,target['database'],role='AGENT',goal='capabilities')
    if separate:
        assert directory['items']==[] and directory['delivery']=='separate'
        assert product_knowledge.publish(actor,target['database'])['knowledge_ids']==result['knowledge_ids']
        return
    assert len(directory['items'])==1 and 'content' not in directory['items'][0]
    item=directory['items'][0]
    content=product_knowledge.read_learning(actor,target['database'],item['entity_id'],item['content_digest'])
    assert 'context_runtime_enqueue' in content['content'] and not content['automatic_execution']
    with pytest.raises(PermissionError):
        product_knowledge.read_learning(actor,target['database'],item['entity_id'],'0'*64)
    assert product_knowledge.publish(actor,target['database'])['knowledge_ids']==result['knowledge_ids']
    record_property('learning_snapshot',json.dumps(dict(target=target['key'],snapshot_revision=result['snapshot_revision'],
        original_snapshots_preserved=len(original),generation_calls=0,embedding_calls=0)))


def test_native_learning_source_update_failure_rolls_back_snapshot_and_retirement(native_target,tmp_path,monkeypatch):
    from lib import platform_learning
    target,actor=native_target
    installed=product_identity.package_root(product_knowledge.__file__)
    product=product_identity.identity(installed)
    if product_knowledge.delivery(installed)['delivery']=='separate':
        pytest.skip('Optional learning publication uses pinned companions, not local content regeneration')
    selected={'build-manifest.json','scripts/resources/legacy-product-knowledge.json'}
    for unit in platform_learning.sections(product,target['database']):
        selected.update(unit['source_paths'])
    for relative in selected:
        destination=tmp_path/relative
        destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(installed/relative,destination)
    source=tmp_path/'docs/agent-context-assets.md'
    source.write_text(source.read_text()+'\nSynthetic rollback fixture; never publish as product guidance.\n')
    current=product_knowledge.learning_catalog(actor,target['database'])
    before=connection.execute_query_one('SELECT COUNT(*) AS N FROM CX_PLATFORM_KNOWLEDGE')['n']
    audit=product_knowledge.identity_api._audit_tx
    def fail(tx,who,event,*args):
        if event=='PRODUCT_KNOWLEDGE_PUBLISH':
            raise RuntimeError('Synthetic native learning audit failure')
        return audit(tx,who,event,*args)
    with monkeypatch.context() as patch:
        patch.setattr(product_knowledge.identity_api,'_audit_tx',fail)
        with pytest.raises(RuntimeError,match='native learning audit'):
            product_knowledge.publish(actor,target['database'],tmp_path)
    assert connection.execute_query_one('SELECT COUNT(*) AS N FROM CX_PLATFORM_KNOWLEDGE')['n']==before
    assert product_knowledge.learning_catalog(actor,target['database'])==current
    assert product_knowledge.learning_catalog(actor,target['database'],root=tmp_path)['items']==[]


def test_native_candidate_applicability_review_promotion_and_private_policy(native_target):
    _,actor=native_target
    domain='V503_KNOW_'+uuid.uuid4().hex.upper()
    reason='Isolated persistent development knowledge verification'
    security_domain_api.create_domain(actor,domain,'503 knowledge intake','INTERNAL','Native guided intake verification',actor,reason)
    with independent_reviewer(actor,domain,reason) as reviewer:
        verify_candidate(actor,reviewer,domain,reason,native_target[0]['database'])


def test_native_curated_import_review_exact_source_and_revocation(native_target,monkeypatch):
    target,actor=native_target
    domain='V503_CURATED_'+uuid.uuid4().hex.upper()
    reason='Native curator source transaction and publication verification'
    security_domain_api.create_domain(actor,domain,'503 curated intake','INTERNAL',reason,actor,reason)
    with independent_reviewer(actor,domain,reason) as reviewer:
        identity_api.assign_permission_override(actor,reviewer,'agents.read','ALLOW','OWNED',reason)
        text='# Boreal retention\n\nScope: Boreal only. Keep records for 30 days.\n\nException: never delete records under a legal hold.\n'
        body_hash=hashlib.sha256(text.encode()).hexdigest()
        document=knowledge_curated.Document.model_validate(dict(path='/procedures/boreal.md',
            title='Native Boreal retention '+domain,text=text,
            origin=dict(locator='synthetic:procedures/boreal.md',revision='sha256:'+body_hash,
                parent_sha256=body_hash,parent_char_count=len(text),start=0,end=len(text),
                decision_status='CURRENT',context_reviewed=True,
                context_note='Complete synthetic source including scope, unit and legal-hold exception.'),
            intake=dict(purpose='Verify exact governed source publication',source_locator='synthetic:procedures/boreal.md',
                responsible_principal_id=actor,subject='Boreal retention',
                applicable_product=target['source_product'],applicable_version='5.0.3',
                effective_from='2026-11-01T00:00:00Z',classification='INTERNAL',
                audience='PRINCIPAL_PRIVATE',decision_status='CURRENT')))
        endpoint=knowledge_curated.URN_PREFIX+knowledge_curated.manifest_digest([document])
        configured=agent_source_sync.configure(actor,dict(security_domain_id=domain,agent_id=reviewer,
            kind='DOCUMENT',endpoint=endpoint,paths=[document.path],content_types=['text/markdown'],
            reason=reason,idempotency_key=uuid.uuid4().hex))
        source_id=configured['source_id']
        request=dict(expected_version=1,documents=[document.model_dump(mode='json')],
            reason=reason,idempotency_key=uuid.uuid4().hex)
        original_audit=agent_source_sync.identity_api._audit_tx
        def unavailable_audit(tx,who,action,*args):
            if action=='SOURCE_CURATED_IMPORT':
                raise RuntimeError('Synthetic unavailable audit; native rollback required')
            return original_audit(tx,who,action,*args)
        with monkeypatch.context() as patch:
            patch.setattr(agent_source_sync.identity_api,'_audit_tx',unavailable_audit)
            with pytest.raises(RuntimeError,match='native rollback'):
                knowledge_curated.import_documents(actor,source_id,request)
        assert connection.execute_query_one('SELECT COUNT(*) AS N FROM CX_AGENT_SOURCE_REVISIONS WHERE SOURCE_ID=:source',
            {'source':source_id})['n']==0
        assert connection.execute_query_one('SELECT CHECKPOINT_DIGEST FROM CX_AGENT_SOURCES WHERE SOURCE_ID=:source',
            {'source':source_id})['checkpoint_digest'] is None
        assert connection.execute_query_one('SELECT COUNT(*) AS N FROM CX_ARTIFACT_CANDIDATES WHERE SECURITY_DOMAIN_ID=:domain',
            {'domain':domain})['n']==0
        result=knowledge_curated.import_documents(actor,source_id,request)
        assert not result['automatic_publication']
        assert knowledge_curated.import_documents(actor,source_id,request)['imports']==result['imports']
        imported=result['imports'][0]
        reference=SourceRef.model_validate(imported['source'])
        loaded=connection.execute_transaction_callback(lambda tx:agent_source_sync.resolve_source(tx,reviewer,domain,reference))
        assert loaded['text']==text and loaded['provenance']['method']=='CURATOR_SUPPLIED_NOT_REMOTE_FETCHED'
        batch=connection.execute_transaction_callback(
            lambda tx:agent_source_sync.resolve_source_batch(tx,reviewer,domain,[reference,reference]))
        assert batch==[loaded,loaded]
        wrong_digest=reference.model_copy(update={'content_digest':'0'*64})
        assert connection.execute_transaction_callback(
            lambda tx:agent_source_sync.resolve_source_batch(tx,reviewer,domain,[reference,wrong_digest],omit_denied=True))==[loaded,None]
        pending=candidates.read_candidate(reviewer,imported['candidate_id'])
        assert pending['status']=='PENDING' and pending['intake_preview']['publication_eligible']
        assert pending['result_entity_id'] is None
        review=dict(expected_version=1,expected_digest=pending['content_digest'],decision='APPROVED',
            reason=reason,idempotency_key=uuid.uuid4().hex)
        with pytest.raises(PermissionError):
            candidates.review_candidate(actor,imported['candidate_id'],review)
        candidates.review_candidate(reviewer,imported['candidate_id'],review)
        promoted=candidates.promote_candidate(reviewer,imported['candidate_id'],dict(expected_version=2,
            expected_digest=pending['content_digest'],reason=reason,idempotency_key=uuid.uuid4().hex))
        assert promoted['result_entity_id']
        projection=connection.execute_query_one('SELECT NATIVE_ENTITY_ID,CONTENT_DIGEST FROM CX_CONTINUITY_ARTIFACT_REVS '
            'WHERE ARTIFACT_ID=:artifact AND REVISION_ID=:revision',
            {'artifact':promoted['result_entity_id'],'revision':promoted['result_revision_id']})
        artifact=SourceRef(family='KNOWLEDGE',entity_id=promoted['result_entity_id'],
            revision_id=promoted['result_revision_id'],content_digest=projection['content_digest'])
        resolved=connection.execute_transaction_callback(lambda tx:continuity_sources.resolve(tx,actor,domain,artifact))
        assert json.loads(resolved['text'])['body']==text.strip()
        assert knowledge_api.get_knowledge(native_entity(projection['native_entity_id'],target['database']),principal_id=actor)
        loaded_candidates=knowledge_grounding._load_candidates(actor,actor,[str(projection['native_entity_id'])])
        assert len(loaded_candidates)==1 and loaded_candidates[0]['source_context']['intake']['decision_status']=='CURRENT'
        assert loaded_candidates[0]['digest']==knowledge_grounding.citation(actor,actor,str(projection['native_entity_id']))['digest']
        from lib.continuity_promotions import original_source_contexts
        assert original_source_contexts((actor,reviewer),[str(projection['native_entity_id'])])=={
            str(projection['native_entity_id']):loaded_candidates[0]['source_context']}
        inventory=knowledge_api.search_knowledge(keyword=domain,principal_id=actor)
        assert len(inventory)==1 and inventory[0]['source_context']['intake']['decision_status']=='CURRENT'
        inventory_page=knowledge_api.search_knowledge_cursor(actor,keyword=domain)
        assert inventory_page['count']==1 and 'total_items' not in inventory_page
        wid=work.create_work(actor,dict(security_domain_id=domain,owner_principal_id=actor,
            content=dict(objective='Use the exact reviewed Boreal retention source',
                criteria=[dict(criterion_id='scope',description='Preserve scope and legal-hold exception',
                    verification='Verify source and applicability in the prepared input')]),
            reason=reason,idempotency_key=uuid.uuid4().hex))['work_contract_id']
        assembled=continuity_assembly.assemble(actor,dict(request_id=uuid.uuid4().hex,security_domain_id=domain,
            work_contract_id=wid,mandatory_sources=[artifact.model_dump(mode='json')],token_budget=32000,
            purpose=reason,idempotency_key=uuid.uuid4().hex))
        prepared=continuity_assembly.read_assembly(actor,assembled['assembly_id'])
        assert prepared['item_count']==2 and prepared['retrieval_policy'].endswith('SOURCE_CONTEXT_V2')
        assert 'CURATOR_SUPPLIED_NOT_REMOTE_FETCHED' in prepared['text'] and 'legal hold' in prepared['text']
        assert '"decision_status":"CURRENT"' in prepared['text'] and '"applicable_version":"5.0.3"' in prepared['text']
        agent_source_sync.change_state(actor,source_id,dict(expected_version=1,status='REVOKED',
            reason=reason,idempotency_key=uuid.uuid4().hex))
        with pytest.raises(PermissionError):
            connection.execute_transaction_callback(lambda tx:agent_source_sync.resolve_source(tx,reviewer,domain,reference))
        assert connection.execute_transaction_callback(
            lambda tx:agent_source_sync.resolve_source_batch(tx,reviewer,domain,[reference],omit_denied=True))==[None]
        with pytest.raises(PermissionError):
            candidates.read_candidate(reviewer,imported['candidate_id'])
        with pytest.raises(PermissionError):
            knowledge_curated.import_documents(actor,source_id,request)
        with pytest.raises(PermissionError):
            connection.execute_transaction_callback(lambda tx:continuity_sources.resolve(tx,actor,domain,artifact))
        assert knowledge_api.get_knowledge(native_entity(projection['native_entity_id'],target['database']),principal_id=actor) is None
        assert knowledge_grounding._load_candidates(actor,actor,[str(projection['native_entity_id'])])==[]
        assert knowledge_api.search_knowledge(keyword=domain,principal_id=actor)==[]
        inventory_page=knowledge_api.search_knowledge_cursor(actor,keyword=domain)
        assert inventory_page['items']==[] and inventory_page['count']==0 and 'total_items' not in inventory_page
        sends=[]
        with pytest.raises(PermissionError):
            continuity_assembly.consume(actor,assembled['assembly_id'],sends.append)
        assert sends==[]
        assert connection.execute_query_one('SELECT COUNT(*) AS N FROM CX_CONTEXT_INPUT_USES WHERE ASSEMBLY_ID=:assembly',
            {'assembly':assembled['assembly_id']})['n']==0


def test_native_declared_applicability_filters(native_target,monkeypatch):
    """Only the new filter is exercised; prior rollback/replay checks are retained."""
    target,actor=native_target
    domain='V503_SCOPE_'+uuid.uuid4().hex.upper()
    reason='Native declared product version and validity filtering'
    security_domain_api.create_domain(actor,domain,'503 applicability','INTERNAL',reason,actor,reason)
    with independent_reviewer(actor,domain,reason) as reviewer:
        identity_api.assign_permission_override(actor,reviewer,'agents.read','ALLOW','OWNED',reason)
        text='Boreal compares v5.0.2 and v5.0.3. The declared applicability identifies the applicable release.'
        digest=hashlib.sha256(text.encode()).hexdigest()
        document=knowledge_curated.Document.model_validate(dict(path='/scope.md',title='Boreal '+domain,text=text,
            origin=dict(locator='synthetic:scope.md',revision='sha256:'+digest,parent_sha256=digest,
                parent_char_count=len(text),start=0,end=len(text),decision_status='PROPOSED',
                context_reviewed=True,context_note='Complete synthetic source for scope filtering'),
            intake=dict(purpose=reason,source_locator='synthetic:scope.md',responsible_principal_id=actor,
                subject='Boreal',applicable_product=target['source_product'],applicable_version='5.0.3',
                effective_from='2026-11-01T00:00:00Z',effective_until='2026-12-01T00:00:00Z',
                classification='INTERNAL',audience='PRINCIPAL_PRIVATE',decision_status='PROPOSED')))
        source=agent_source_sync.configure(actor,dict(security_domain_id=domain,agent_id=reviewer,kind='DOCUMENT',
            endpoint=knowledge_curated.URN_PREFIX+knowledge_curated.manifest_digest([document]),paths=[document.path],
            content_types=['text/markdown'],reason=reason,idempotency_key=uuid.uuid4().hex))['source_id']
        candidate=knowledge_curated.import_documents(actor,source,dict(expected_version=1,
            documents=[document.model_dump(mode='json')],reason=reason,idempotency_key=uuid.uuid4().hex))['imports'][0]['candidate_id']
        pending=candidates.read_candidate(reviewer,candidate)
        candidates.review_candidate(reviewer,candidate,dict(expected_version=1,expected_digest=pending['content_digest'],
            decision='APPROVED',reason=reason,idempotency_key=uuid.uuid4().hex))
        promoted=candidates.promote_candidate(reviewer,candidate,dict(expected_version=2,expected_digest=pending['content_digest'],
            reason=reason,idempotency_key=uuid.uuid4().hex))
        entity=str(connection.execute_query_one('SELECT NATIVE_ENTITY_ID FROM CX_CONTINUITY_ARTIFACT_REVS WHERE ARTIFACT_ID=:artifact',
            {'artifact':promoted['result_entity_id']})['native_entity_id'])
        # Native keyword/relational/tag/graph authority, with optional model
        # channels explicitly omitted: no Embedding or generation is sent.
        monkeypatch.setattr(embedding_api,'search_authorized_knowledge',lambda *args,**kwargs:[])
        correct=dict(product=target['source_product'],version='5.0.3',as_of='2026-11-01T00:00:00Z',
            decision_statuses=['PROPOSED'])
        for strategy in ('keyword','hybrid'):
            read=lambda scope:knowledge_grounding.search(actor,actor,'Boreal',entity_ids=[entity],
                strategy=strategy,applicability=scope)
            result=read(correct)
            assert [item['entity_id'] for item in result['items']]==[entity]
            knowledge_grounding.validate_citation(actor,actor,result['items'][0])
            for field,value in [('version','5.0.2'),('product','unrelated-product'),
                ('as_of','2026-10-31T23:59:59Z'),('as_of','2026-12-01T00:00:00Z'),('decision_statuses',['CURRENT'])]:
                assert read(dict(correct,**{field:value}))['items']==[]
        agent_source_sync.change_state(actor,source,dict(expected_version=1,status='REVOKED',
            reason=reason,idempotency_key=uuid.uuid4().hex))
        assert read(correct)['items']==[]


def test_native_memory_original_authority(native_target):
    from lib import context_selection
    target,actor=native_target
    domain='V503_MEMORY_'+uuid.uuid4().hex.upper()
    reason='Native Memory original-source revocation and bounded context'
    security_domain_api.create_domain(actor,domain,'503 Memory lineage','INTERNAL',reason,actor,reason)
    with independent_reviewer(actor,domain,reason) as reviewer:
        for action in ('agents.read','memory.write','memory.read'):
            identity_api.assign_permission_override(actor,reviewer,action,'ALLOW','OWNED',reason)
        text='Proposed Boreal retention: keep records for 30 days; preserve legal holds.'
        digest=hashlib.sha256(text.encode()).hexdigest()
        document=knowledge_curated.Document.model_validate(dict(path='/proposal.md',title='Boreal proposal '+domain,text=text,
            origin=dict(locator='synthetic:proposal.md',revision='sha256:'+digest,parent_sha256=digest,
                parent_char_count=len(text),start=0,end=len(text),decision_status='PROPOSED',context_reviewed=True,
                context_note='Complete synthetic proposal with legal-hold exception')))
        source=agent_source_sync.configure(actor,dict(security_domain_id=domain,agent_id=reviewer,kind='DOCUMENT',
            endpoint=knowledge_curated.URN_PREFIX+knowledge_curated.manifest_digest([document]),paths=[document.path],
            content_types=['text/markdown'],reason=reason,idempotency_key=uuid.uuid4().hex))['source_id']
        original=knowledge_curated.import_documents(actor,source,dict(expected_version=1,
            documents=[document.model_dump(mode='json')],reason=reason,idempotency_key=uuid.uuid4().hex))['imports'][0]['source']
        references=[]
        for number in range(2):
            candidate=candidates.create_candidate(actor,dict(security_domain_id=domain,
                content=dict(family='MEMORY',title='Boreal proposal summary '+str(number),
                    body='The retention proposal includes a legal-hold exception.',memory_type='FACT'),
                sources=[original],reason=reason,idempotency_key=uuid.uuid4().hex))['candidate_id']
            pending=candidates.read_candidate(reviewer,candidate)
            candidates.review_candidate(reviewer,candidate,dict(expected_version=1,expected_digest=pending['content_digest'],
                decision='APPROVED',reason=reason,idempotency_key=uuid.uuid4().hex))
            promoted=candidates.promote_candidate(reviewer,candidate,dict(expected_version=2,
                expected_digest=pending['content_digest'],reason=reason,idempotency_key=uuid.uuid4().hex))
            stored=connection.execute_query_one('SELECT CONTENT_DIGEST FROM CX_MEMORY_VERSIONS WHERE VERSION_ID=:revision',
                {'revision':promoted['result_revision_id']})
            references.append(dict(family='MEMORY',entity_id=promoted['result_entity_id'],
                revision_id=promoted['result_revision_id'],content_digest=stored['content_digest']))
        read=lambda:connection.execute_transaction_callback(lambda tx:continuity_sources.resolve_many(tx,actor,domain,references))
        metadata=lambda:connection.execute_transaction_callback(lambda tx:context_selection.metadata_many(tx,actor,domain,references))
        for value in [*read(),*metadata()]:
            assert value['source_context']['provenance'][0]['origin']['decision_status']=='PROPOSED'
        prepared=continuity_assembly.assemble(actor,dict(request_id=uuid.uuid4().hex,security_domain_id=domain,
            sources=references,applicability=dict(decision_statuses=['PROPOSED']),token_budget=64000,
            purpose=reason,idempotency_key=uuid.uuid4().hex))
        context=continuity_assembly.read_assembly(actor,prepared['assembly_id'])
        assert context['item_count']==2 and 'PROPOSED' in context['text']
        agent_source_sync.change_state(actor,source,dict(expected_version=1,status='REVOKED',reason=reason,
            idempotency_key=uuid.uuid4().hex))
        for operation in (read,metadata,lambda:continuity_assembly.read_assembly(actor,prepared['assembly_id'])):
            with pytest.raises(PermissionError):operation()
        sends=[]
        with pytest.raises(PermissionError):continuity_assembly.consume(actor,prepared['assembly_id'],sends.append)
        assert sends==[]


def verify_candidate(actor,reviewer,domain,reason,backend):
    wid=work.create_work(actor,dict(security_domain_id=domain,owner_principal_id=actor,
        content=dict(objective='Verify a sourced knowledge procedure',criteria=[dict(criterion_id='proof',description='Native read is exact',verification='Compare digests')]),
        reason=reason,idempotency_key=uuid.uuid4().hex))['work_contract_id']
    hid=handoff.offer(actor,wid,dict(expected_work_version=1,recipient_principal_id=reviewer,kind='HUMAN_TO_AGENT',
        content=dict(summary='Synthetic native knowledge source',next_actions=[dict(action_id='verify',description='Verify exact knowledge',responsible_principal_id=reviewer,acceptance='Source digest matches')]),
        expires_at=datetime.now(timezone.utc)+timedelta(hours=1),reason=reason,idempotency_key=uuid.uuid4().hex))['handoff_id']
    original=handoff.read_handoff(actor,hid)
    source=dict(family='HANDOFF',entity_id=hid,revision_id='1',content_digest=original['content_digest'])
    value=dict(security_domain_id=domain,content=dict(family='KNOWLEDGE',title='503 native intake '+domain,body='A sourced procedure remains private until separately authorized sharing.'),
        sources=[source],reason=reason,idempotency_key=uuid.uuid4().hex)
    assert not candidates.preview_knowledge(actor,value)['publication_eligible']
    cid=candidates.create_candidate(actor,value)['candidate_id']
    read=candidates.read_candidate(reviewer,cid)
    review=dict(expected_version=1,expected_digest=read['content_digest'],decision='APPROVED',reason=reason,idempotency_key=uuid.uuid4().hex)
    with pytest.raises(ContinuityConflict):
        candidates.review_candidate(reviewer,cid,review)
    value.update(expected_version=1,idempotency_key=uuid.uuid4().hex,intake=dict(purpose='Verify a known procedure',source_locator='handoff:'+hid,
        responsible_principal_id=actor,subject='Native intake verification',applicable_product=product_identity.identity()['product_key'],applicable_version='5.0.3',
        effective_from='2026-11-01T00:00:00Z',classification='INTERNAL',audience='PRINCIPAL_PRIVATE',decision_status='CURRENT'))
    candidates.revise_candidate(actor,cid,value)
    read=candidates.read_candidate(reviewer,cid)
    assert read['intake_preview']['publication_eligible']
    candidates.review_candidate(reviewer,cid,dict(review,expected_version=2,expected_digest=read['content_digest'],idempotency_key=uuid.uuid4().hex))
    result=candidates.promote_candidate(reviewer,cid,dict(expected_version=3,expected_digest=read['content_digest'],reason=reason,idempotency_key=uuid.uuid4().hex))
    row=connection.execute_query_one("SELECT e.VISIBILITY,km.TOPIC FROM ENTITIES e JOIN KNOWLEDGE_META km ON km.ENTITY_ID=e.ENTITY_ID "
        "WHERE CAST(e.ENTITY_ID AS VARCHAR(128))=(SELECT NATIVE_ENTITY_ID FROM CX_CONTINUITY_ARTIFACT_REVS WHERE ARTIFACT_ID=:artifact AND REVISION_ID=:revision)",
        {'artifact':result['result_entity_id'],'revision':result['result_revision_id']})
    assert row['visibility']=='PRIVATE' and row['topic']=='Native intake verification'
    assert candidates.read_candidate(actor,cid,1)['payload'].get('intake') is None
    native=connection.execute_query_one('SELECT NATIVE_ENTITY_ID FROM CX_CONTINUITY_ARTIFACT_REVS '
        'WHERE ARTIFACT_ID=:artifact AND REVISION_ID=:revision',
        {'artifact':result['result_entity_id'],'revision':result['result_revision_id']})['native_entity_id']
    shared=knowledge_api.set_access_policy(native,'PUBLIC_COMPANY',actor,reason=reason)
    assert shared['scope_type']=='PUBLIC_COMPANY'
    with pytest.raises(ContinuityConflict):
        knowledge_api.update_knowledge(native_entity(native,backend),content='Unreviewed in-place replacement')
    # Also verify a reviewed projection owned by the native Agent, so RLS
    # ownership cannot hide a missing write guard behind a zero-row UPDATE.
    agent_value=dict(value,content=dict(value['content'],title='Agent-owned reviewed '+domain),idempotency_key=uuid.uuid4().hex)
    agent_value.pop('expected_version')
    agent_cid=candidates.create_candidate(reviewer,agent_value)['candidate_id']
    detail=candidates.read_candidate(actor,agent_cid)
    candidates.review_candidate(actor,agent_cid,dict(review,expected_version=1,expected_digest=detail['content_digest'],idempotency_key=uuid.uuid4().hex))
    promoted=candidates.promote_candidate(actor,agent_cid,dict(expected_version=2,expected_digest=detail['content_digest'],reason=reason,idempotency_key=uuid.uuid4().hex))
    agent_native=connection.execute_query_one('SELECT NATIVE_ENTITY_ID FROM CX_CONTINUITY_ARTIFACT_REVS '
        'WHERE ARTIFACT_ID=:artifact AND REVISION_ID=:revision',
        {'artifact':promoted['result_entity_id'],'revision':promoted['result_revision_id']})['native_entity_id']
    verify_independent_native_login(reviewer,native_entity(agent_native,backend),backend)
    knowledge_api.set_access_policy(native,'PRINCIPAL_PRIVATE',actor,principal_id=actor,reason=reason)


@contextmanager
def independent_login(agent,backend):
    """No Owner connection, SET ROLE substitution or caller-chosen identity."""
    if backend=='pg':
        import psycopg2
        credentials=agent_api._get_agent_login_credentials(agent)
        conn=psycopg2.connect(**{key:credentials[key] for key in ('host','port','dbname','password')},
            user=credentials['username'],connect_timeout=8)
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT set_config('app.current_agent_id',%s,false)",(agent,))
                cursor.execute('SELECT SESSION_USER,public.current_agent_identity()')
                assert cursor.fetchone()==(credentials['username'],agent)
            conn.commit()
            yield conn
        finally:
            conn.rollback();conn.close()
    else:
        if backend=='yashandb':
            import yaspy as driver
        else:
            import oracledb as driver
        settings=config.load_config().database
        assert re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*',settings.user)
        conn=driver.connect(user=agent_api._database_user_name(agent),
            password=agent_api._get_end_user_password_direct(agent),dsn=settings.dsn)
        try:
            with conn.cursor() as cursor:
                cursor.execute('ALTER SESSION SET CURRENT_SCHEMA='+settings.user)
                cursor.execute("SELECT SYS_CONTEXT('USERENV','SESSION_USER') FROM DUAL" if backend=='yashandb'
                    else 'SELECT ORA_END_USER_CONTEXT.username FROM DUAL')
                assert cursor.fetchone()[0]==agent_api._database_user_name(agent)
            yield conn
        finally:
            conn.rollback();conn.close()


def assert_oracle_denied(conn,sql,params=None,*,backend='oracle'):
    if backend=='yashandb':
        import yaspy as driver
    else:
        import oracledb as driver
    with conn.cursor() as cursor:
        try:
            cursor.execute(sql,params or {})
        except driver.DatabaseError as denied:
            # Native DDS/privilege rejection or our exact new trigger. Syntax,
            # invalid-object and uniqueness errors must fail the test.
            if backend=='yashandb':
                # 02012 is object invisibility, verified separately against
                # Owner existence and grant absence for the intake table.
                assert re.search(r'YAS-(?:02012|01031|02213|05207)\b',str(denied)),str(denied)
            else:
                assert denied.args[0].code in {942,1031,20912,28115,41900}, denied.args[0].code
        else:
            assert sql.startswith('UPDATE ') and cursor.rowcount==0, 'Native bypass unexpectedly succeeded'
        finally:
            conn.rollback()


def verify_independent_native_login(agent,reviewed_entity,backend):
    if backend in {'oracle','yashandb'}:
        note=knowledge_api.create_knowledge('Native boundary private note','Original note',owned_by_agent=agent)
        assert knowledge_api.update_knowledge(note,content='Updated private note')
        with independent_login(agent,backend) as conn:
            attempts=[
                ("UPDATE ENTITIES SET VISIBILITY='PUBLIC' WHERE ENTITY_ID=:id",dict(id=note)),
                ("INSERT INTO ENTITIES(ENTITY_TYPE,TITLE,CONTENT,OWNED_BY_AGENT,VISIBILITY) VALUES('KNOWLEDGE','Bypass','Unreviewed',:agent,'PUBLIC')",dict(agent=agent)),
                ("UPDATE ENTITIES SET CONTENT='Bypass reviewed content' WHERE ENTITY_ID=:id",dict(id=reviewed_entity)),
                ("UPDATE KNOWLEDGE_META SET TOPIC='Bypass reviewed metadata' WHERE ENTITY_ID=:id",dict(id=reviewed_entity)),
                ("INSERT INTO CX_KNOWLEDGE_ACCESS_POLICIES(POLICY_ID,ENTITY_ID,SCOPE_TYPE,CREATED_BY,REASON) VALUES(:policy,:id,'PUBLIC_COMPANY',:agent,'Bypass')",dict(policy='bypass-'+uuid.uuid4().hex,id=note,agent=agent)),
                ('SELECT METADATA_JSON FROM CX_KNOWLEDGE_INTAKE',{}),
            ]
            for sql,params in attempts:
                assert_oracle_denied(conn,sql,params,backend=backend)
        return
    import psycopg2
    # Keep the installed platform's existing RLS contract: this target denies
    # raw private mutations as well. Personal notes remain usable via the
    # authenticated service; do not widen native grants to manufacture a pass.
    note=knowledge_api.create_knowledge('Native boundary private note','Original note',owned_by_agent=agent)
    assert knowledge_api.update_knowledge(note,content='Updated private note')
    credentials=agent_api._get_agent_login_credentials(agent)
    with psycopg2.connect(**{key:credentials[key] for key in ('host','port','dbname','password')},
                          user=credentials['username'],connect_timeout=8) as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT set_config('app.current_agent_id',%s,false)",(agent,))
            cursor.execute('SELECT SESSION_USER,public.current_agent_identity()')
            assert cursor.fetchone()==(credentials['username'],agent)
            conn.commit()
            attempts=[
                ("UPDATE ENTITIES SET VISIBILITY='PUBLIC' WHERE ENTITY_ID=%s",(note,)),
                ("INSERT INTO ENTITIES(ENTITY_TYPE,TITLE,CONTENT,OWNED_BY_AGENT,VISIBILITY) VALUES('KNOWLEDGE','Bypass','Unreviewed',%s,'PUBLIC')",(agent,)),
                ("UPDATE ENTITIES SET CONTENT='Bypass reviewed content' WHERE ENTITY_ID=%s",(reviewed_entity,)),
                ("UPDATE KNOWLEDGE_META SET TOPIC='Bypass reviewed metadata' WHERE ENTITY_ID=%s",(reviewed_entity,)),
                ("INSERT INTO CX_KNOWLEDGE_ACCESS_POLICIES(POLICY_ID,ENTITY_ID,SCOPE_TYPE,CREATED_BY,REASON) VALUES(%s,%s,'PUBLIC_COMPANY',%s,'Bypass')",('bypass-'+uuid.uuid4().hex,str(note),agent)),
                ('SELECT METADATA_JSON FROM CX_KNOWLEDGE_INTAKE',()),
            ]
            for statement,params in attempts:
                try:
                    cursor.execute(statement,params)
                except psycopg2.errors.InsufficientPrivilege:
                    pass
                else:
                    assert statement.startswith('UPDATE ') and cursor.rowcount==0, 'Native bypass unexpectedly succeeded'
                conn.rollback()
            # Removing the optional context hint must not turn this login into
            # a trusted Owner. The new BEFORE trigger rejects publication even
            # before the existing RLS insert check runs.
            cursor.execute("SELECT set_config('app.current_agent_id','',false)");conn.commit()
            with pytest.raises(psycopg2.errors.InsufficientPrivilege,match='governed intake'):
                cursor.execute("INSERT INTO ENTITIES(ENTITY_TYPE,TITLE,CONTENT,OWNED_BY_AGENT,VISIBILITY) "
                    "VALUES('KNOWLEDGE','No context bypass','Unreviewed',%s,'PUBLIC')",(agent,))
            conn.rollback()


def test_native_intake_table_has_no_runtime_read_grant(native_target):
    if native_target[0]['database']=='yashandb':
        with connection.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) FROM USER_TABLES WHERE TABLE_NAME='CX_KNOWLEDGE_INTAKE'")
                assert cursor.fetchone()[0]==1
                for catalog in ('ALL_TAB_PRIVS','ROLE_TAB_PRIVS'):
                    cursor.execute("SELECT COUNT(*) FROM "+catalog+" WHERE OWNER=USER AND TABLE_NAME='CX_KNOWLEDGE_INTAKE'")
                    assert cursor.fetchone()[0]==0
        return
    if native_target[0]['database']=='oracle':
        with connection.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) FROM USER_TAB_PRIVS_MADE WHERE TABLE_NAME='CX_KNOWLEDGE_INTAKE'")
                assert cursor.fetchone()[0]==0
                cursor.execute("SELECT COUNT(*) FROM USER_DATA_GRANTS WHERE OBJECT_OWNER=USER AND OBJECT_NAME='CX_KNOWLEDGE_INTAKE'")
                assert cursor.fetchone()[0]==0
        return
    # A genuine native role permission check; SET ROLE is not an independent
    # Agent login and must never be reported as full Agent RLS acceptance.
    with connection.get_connection() as conn:
        try:
            with conn.cursor() as cursor:
                cursor.execute('SET LOCAL ROLE ai_agent_runtime')
                with pytest.raises(Exception) as denied:
                    cursor.execute('SELECT METADATA_JSON FROM CX_KNOWLEDGE_INTAKE')
                assert getattr(denied.value,'pgcode',None)=='42501'
        finally:
            conn.rollback()


def test_native_legacy_shared_metadata_requires_intake_without_session_hint(native_target):
    from lib import knowledge_native_governance
    target,actor=native_target
    backend=target['database']
    with connection.get_connection() as native:
        with native.cursor() as cursor:
            assert knowledge_native_governance.errors(cursor,backend,legacy_shared=True)==[]
    domain='V503_LEGACY_'+uuid.uuid4().hex.upper()
    reason='Verify additive protection of a legacy shared Knowledge fixture'
    security_domain_api.create_domain(actor,domain,'503 legacy guard','INTERNAL',reason,actor,reason)
    with independent_reviewer(actor,domain,reason) as agent:
        note=knowledge_api.create_knowledge('503 legacy shared fixture','Synthetic fixture; not product facts',owned_by_agent=agent)
        policy='V503_LEGACY_'+uuid.uuid4().hex
        try:
            # Deliberate legacy state in this classified copy, using the trusted
            # Owner fixture setup only. No new product publication bypass.
            connection.execute("INSERT INTO CX_KNOWLEDGE_ACCESS_POLICIES(POLICY_ID,ENTITY_ID,SCOPE_TYPE,CREATED_BY,REASON) "
                "VALUES(:policy,:entity,'PUBLIC_COMPANY',:actor,:reason)",
                dict(policy=policy,entity=str(note),actor=actor,reason=reason))
            assert not connection.execute_query_one('SELECT ARTIFACT_ID FROM CX_CONTINUITY_ARTIFACT_REVS '
                'WHERE NATIVE_ENTITY_ID=:entity',dict(entity=str(note)))
            if backend in {'oracle','yashandb'}:
                with independent_login(agent,backend) as conn:
                    assert_oracle_denied(conn,'INSERT INTO KNOWLEDGE_META(ENTITY_ID,TOPIC) VALUES(:id,:topic)',
                        dict(id=note,topic='Unreviewed replacement'),backend=backend)
                return
            import psycopg2
            credentials=agent_api._get_agent_login_credentials(agent)
            with psycopg2.connect(**{key:credentials[key] for key in ('host','port','dbname','password')},
                                  user=credentials['username'],connect_timeout=8) as conn:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT set_config('app.current_agent_id','',false)")
                    conn.commit()
                    # BEFORE INSERT fires ahead of uniqueness and row checks;
                    # the exact message proves this new guard executed.
                    with pytest.raises(psycopg2.errors.InsufficientPrivilege,match='governed intake'):
                        cursor.execute('INSERT INTO KNOWLEDGE_META(ENTITY_ID,TOPIC) VALUES(%s,%s)',(note,'Unreviewed replacement'))
                    conn.rollback()
        finally:
            connection.execute("UPDATE CX_KNOWLEDGE_ACCESS_POLICIES SET STATUS='RETIRED' WHERE POLICY_ID=:policy",dict(policy=policy))


def signal_fixture_source(actor,reviewer,domain,reason,*,lifetime_seconds=3600):
    wid=work.create_work(actor,dict(security_domain_id=domain,owner_principal_id=actor,
        content=dict(objective='Verify native retrieval signal contributions',criteria=[dict(criterion_id='proof',
            description='Read exact authorized synthetic sources',verification='Native SQL and source digests')]),
        reason=reason,idempotency_key=uuid.uuid4().hex))['work_contract_id']
    hid=handoff.offer(actor,wid,dict(expected_work_version=1,recipient_principal_id=reviewer,kind='HUMAN_TO_AGENT',
        content=dict(summary='Synthetic signal fixture; not product facts or answer labels',next_actions=[dict(action_id='inspect',
            description='Inspect relation, tag and one-hop Knowledge edges',responsible_principal_id=reviewer,acceptance='Current permissions apply')]),
        expires_at=datetime.now(timezone.utc)+timedelta(seconds=lifetime_seconds),reason=reason,idempotency_key=uuid.uuid4().hex))['handoff_id']
    return dict(family='HANDOFF',entity_id=hid,revision_id='1',content_digest=handoff.read_handoff(actor,hid)['content_digest'])


def promote_signal_fixture(proposer,reviewer,domain,source,reason,*,title,body,subject,
                           version='5.0.3',replaces=None):
    request=dict(security_domain_id=domain,content=dict(family='KNOWLEDGE',title=title,body=body),sources=[source],
        intake=dict(purpose='Native retrieval verification fixture',source_locator='handoff:'+source['entity_id'],
            responsible_principal_id=proposer,subject=subject,applicable_product=product_identity.identity()['product_key'],
            applicable_version=version,effective_from='2026-11-01T00:00:00Z',classification='INTERNAL',
            audience='PRINCIPAL_PRIVATE',decision_status='CURRENT'),reason=reason,idempotency_key=uuid.uuid4().hex)
    if replaces is not None:
        request['replaces']=replaces
    cid=candidates.create_candidate(proposer,request)['candidate_id']
    detail=candidates.read_candidate(reviewer,cid)
    exact=dict(expected_digest=detail['content_digest'],reason=reason,idempotency_key=uuid.uuid4().hex)
    candidates.review_candidate(reviewer,cid,dict(exact,expected_version=1,decision='APPROVED'))
    promoted=candidates.promote_candidate(reviewer,cid,dict(exact,expected_version=2,idempotency_key=uuid.uuid4().hex))
    return str(connection.execute_query_one('SELECT NATIVE_ENTITY_ID FROM CX_CONTINUITY_ARTIFACT_REVS '
        'WHERE ARTIFACT_ID=:artifact AND REVISION_ID=:revision',
        {'artifact':promoted['result_entity_id'],'revision':promoted['result_revision_id']})['native_entity_id'])


def test_native_explicit_historical_revision_survives_current_candidate_filter(native_target,monkeypatch,record_property):
    """A new artifact revision must not erase an authorized exact old release."""
    target,actor=native_target
    domain='V503_HISTORY_'+uuid.uuid4().hex.upper()
    reason='Verify exact historical retrieval after a real candidate successor'
    token='history'+uuid.uuid4().hex
    security_domain_api.create_domain(actor,domain,'503 historical retrieval','INTERNAL',reason,actor,reason)
    with independent_reviewer(actor,domain,reason) as reviewer:
        source=signal_fixture_source(actor,reviewer,domain,reason)
        native=[]
        try:
            previous=promote_signal_fixture(actor,reviewer,domain,source,reason,
                title=token+' v5.0.2 procedure',body=token+' v5.0.2 keeps the previous documented procedure.',
                subject=token,version='5.0.2')
            native.append(previous)
            knowledge_api.set_access_policy(previous,'PUBLIC_COMPANY',actor,reason=reason)
            original=knowledge_grounding.citation(actor,reviewer,previous)
            old=connection.execute_query_one('SELECT ARTIFACT_ID,REVISION_ID,CONTENT_DIGEST '
                'FROM CX_CONTINUITY_ARTIFACT_REVS WHERE NATIVE_ENTITY_ID=:entity',dict(entity=previous))
            replacement=dict(family='KNOWLEDGE',entity_id=old['artifact_id'],revision_id=old['revision_id'],
                content_digest=old['content_digest'])
            current=promote_signal_fixture(actor,reviewer,domain,source,reason,
                title=token+' v5.0.3 procedure',body=token+' v5.0.3 uses the separately reviewed current procedure.',
                subject=token,replaces=replacement)
            native.append(current)
            knowledge_api.set_access_policy(current,'PUBLIC_COMPANY',actor,reason=reason)
            search=embedding_api.search_authorized_knowledge
            def without_vector(*args,**kwargs):
                if kwargs.get('channel')=='vector':
                    raise embedding_api.AuthorizedSearchUnavailable('Explicit historical-read vector ablation')
                return search(*args,**kwargs)
            monkeypatch.setattr(embedding_api,'search_authorized_knowledge',without_vector)
            monkeypatch.setattr(embedding_api,'_query_embedding',lambda *_a,**_k:pytest.fail('Historical revision check cannot send Embedding'))
            observations=[]
            for strategy in ('keyword','hybrid'):
                for version,expected in (('5.0.2',previous),('5.0.3',current)):
                    scope=dict(product=target['source_product'],version=version)
                    result=knowledge_grounding.search(actor,reviewer,token,strategy=strategy,applicability=scope)
                    assert {item['entity_id'] for item in result['items']}=={expected}
                    knowledge_grounding.validate_citation(actor,reviewer,result['items'][0])
                    if expected==previous:
                        assert result['items'][0]['content']==original['content']
                        assert result['items'][0]['digest']==original['digest']
                    # Task domain discovery intentionally selects current
                    # roots; it cannot silently restore an old revision.
                    discovery=knowledge_grounding.search(actor,reviewer,token,strategy=strategy,
                        applicability=scope,artifact_domain=domain)
                    assert {item['entity_id'] for item in discovery['items']}==({current} if version=='5.0.3' else set())
                    observations.append(dict(strategy=strategy,version=version,exact_revision=True,
                        current_domain_discovery=version=='5.0.3'))
            knowledge_api.set_access_policy(previous,'PRINCIPAL_PRIVATE',actor,principal_id=actor,reason=reason)
            with pytest.raises(PermissionError):
                knowledge_grounding.validate_citation(actor,reviewer,original)
            assert knowledge_grounding.search(actor,reviewer,token,
                applicability=dict(product=target['source_product'],version='5.0.2'))['items']==[]
            record_property('historical_revision_retrieval',json.dumps(dict(target=target['key'],
                observations=observations,withdrawn_grant_denied=True,generation_calls=0,embedding_calls=0)))
        finally:
            for entity in native:
                knowledge_api.set_access_policy(entity,'PRINCIPAL_PRIVATE',actor,principal_id=actor,reason=reason)


def test_native_semantic_reference_preparation_retains_scope_and_revocation(native_target,monkeypatch):
    from lib import answer_evidence,portal_grounding,native_runtime
    def forbidden(*args,**kwargs):
        raise AssertionError('This native source/preparation check cannot send Provider requests')
    monkeypatch.setattr(embedding_api,'_query_embedding',forbidden)
    monkeypatch.setattr(native_runtime,'_call_llm',forbidden)
    target,actor=native_target
    domain='V503_SEMANTIC_'+uuid.uuid4().hex.upper()
    reason='Isolated native semantic reference and exact-source authorization check'
    security_domain_api.create_domain(actor,domain,'503 semantic references','INTERNAL','Answer preparation verification',actor,reason)
    with independent_reviewer(actor,domain,reason) as reviewer:
        source=signal_fixture_source(actor,reviewer,domain,reason)
        body='容量耗尽后暂停调度。保持等待队列，先由值班人员核实可用容量。'
        native=promote_signal_fixture(actor,reviewer,domain,source,reason,title='调度操作指南',body=body,subject='Scheduling capacity')
        try:
            knowledge_api.set_access_policy(native,'PUBLIC_COMPANY',actor,reason=reason)
            exact=knowledge_grounding.citation(actor,reviewer,native)
            question='v5.0.3 配额不足时，能否删除等待队列以继续执行？'
            result=answer_evidence.assess_for_answer(question,[exact])
            assert result['status']=='PARTIAL_MATCH' and result['items']==[exact]
            assert result['evidence_decision']['semantic_review']['status']=='REQUIRED'
            wrong=answer_evidence.assess_for_answer(question.replace('5.0.3','5.0.30'),[exact])
            assert wrong['items']==[]
            configured=portal_grounding.policy()
            assert '' not in configured['disclosure_profiles']
            prepared=answer_planning.prepare(question,'',configured,result)
            assert prepared['answer_source']=='KNOWLEDGE_EXTRACTS' and prepared['messages']==[]
            assert body in prepared['knowledge_reply']
            assert prepared['citations'][0]['entity_id']==native
            knowledge_api.set_access_policy(native,'PRINCIPAL_PRIVATE',actor,principal_id=actor,reason=reason)
            with pytest.raises(PermissionError):
                knowledge_grounding.validate_citation(actor,reviewer,prepared['citations'][0])
        finally:
            knowledge_api.set_access_policy(native,'PRINCIPAL_PRIVATE',actor,principal_id=actor,reason=reason)


def test_native_relation_tag_fulltext_and_graph_contribute_with_dual_authority(native_target,monkeypatch,record_property):
    target,actor=native_target
    domain='V503_SIGNAL_'+uuid.uuid4().hex.upper()
    reason='Isolated native structured retrieval signal verification'
    token='signal'+uuid.uuid4().hex
    security_domain_api.create_domain(actor,domain,'503 native signals','INTERNAL','Structured retrieval verification',actor,reason)
    with independent_reviewer(actor,domain,reason) as reviewer:
        source=signal_fixture_source(actor,reviewer,domain,reason)
        native={}
        public=set()
        try:
            for kind in ('anchor','title-match','metadata','tag','neighbor','private-human','private-agent'):
                proposer,approver=(reviewer,actor) if kind=='private-agent' else (actor,reviewer)
                native[kind]=promote_signal_fixture(proposer,approver,domain,source,reason,
                    title='Synthetic '+kind+' '+(token if kind=='title-match' else domain),
                    body=('Verified '+token+' procedure.' if kind in {'anchor','private-human','private-agent'} else 'A verified dependent procedure.'),
                    subject=token if kind in {'metadata','private-human','private-agent'} else 'Unrelated synthetic topic')
                if not kind.startswith('private-'):
                    knowledge_api.set_access_policy(native[kind],'PUBLIC_COMPANY',actor,reason=reason)
                    public.add(native[kind])
            assert knowledge_api.add_knowledge_tags(native_entity(native['tag'],target['database']),[token])==1
            for kind in ('neighbor','private-human','private-agent'):
                extra_columns=',TARGET_TYPE' if target['database']=='pg' else ''
                extra_values=",'KNOWLEDGE'" if extra_columns else ''
                id_column='EDGE_ID,' if target['database']!='pg' else ''
                id_value=':edge,' if id_column else ''
                params={'source':native_entity(native['anchor'],target['database']),
                    'target':native_entity(native[kind],target['database'])}
                if id_column:params['edge']='EDGE_'+uuid.uuid4().hex
                connection.execute("INSERT INTO ENTITY_EDGES("+id_column+"SOURCE_ID,SOURCE_TYPE,TARGET_ID"+extra_columns+",EDGE_TYPE,STRENGTH,CONFIDENCE) "
                    "VALUES("+id_value+":source,'KNOWLEDGE',:target"+extra_values+",'RELATED_TO',1,1)",params)
            index_wait_ms=0
            if target['database']=='yashandb':
                # Bounded fixture readiness only; user reads never wait for
                # publication maintenance or rebuild an index.
                started=time.monotonic()
                while True:
                    ready=embedding_api.search_authorized_knowledge(token,channel='fulltext',actor=actor,agent=reviewer)
                    if {item['entity_id'] for item in ready}=={native['anchor'],native['title-match']}:
                        break
                    assert time.monotonic()-started<30,'Native SEARCH publication did not become visible within 30 seconds'
                    time.sleep(1)
                index_wait_ms=round((time.monotonic()-started)*1000,3)
            statements=[]
            cache_statements={}
            original=connection.execute_query
            def observe(sql,params=None):
                executed=sql
                if target['database']=='yashandb' and 'AS CHANNEL_SCORE' in sql:
                    marker='CX503_SIGNAL_'+uuid.uuid4().hex
                    executed=sql.replace('SELECT ','SELECT /* '+marker+' */ ',1)
                    cache_statements[sql]=(marker,executed)
                started=time.monotonic()
                rows=original(executed,params)
                if 'AS CHANNEL_SCORE' in sql:
                    statements.append((sql,dict(params or {}),round((time.monotonic()-started)*1000,3),len(rows)))
                return rows
            def no_embedding(*_args,**_kwargs):
                pytest.fail('This native signal check must not call a model or Embedding provider')
            with monkeypatch.context() as patch:
                patch.setattr(connection,'execute_query',observe)
                patch.setattr(embedding_api,'execute_query',observe)
                patch.setattr(embedding_api,'_query_embedding',no_embedding)
                ids=lambda rows:{row['entity_id'] for row in rows}
                relational=knowledge_signals.candidates(actor,reviewer,[token],channel='relational')
                tagged=knowledge_signals.candidates(actor,reviewer,[token],channel='tag')
                graph=knowledge_signals.candidates(actor,reviewer,[token],channel='graph',anchors=[native['anchor']])
                fulltext=embedding_api.search_authorized_knowledge(token,channel='fulltext',actor=actor,agent=reviewer)
                assert ids(relational)=={native['metadata']}
                assert ids(tagged)=={native['tag']}
                assert ids(graph)=={native['neighbor']}
                assert ids(fulltext)=={native['anchor'],native['title-match']}
                # Deliberate vector ablation, not a Provider failure or model
                # acceptance: all remaining channels and body reads are real.
                search=embedding_api.search_authorized_knowledge
                def without_vector(*args,**kwargs):
                    if kwargs.get('channel')=='vector':
                        raise embedding_api.AuthorizedSearchUnavailable('Explicit vector ablation')
                    return search(*args,**kwargs)
                with patch.context() as ablation:
                    ablation.setattr(embedding_api,'search_authorized_knowledge',without_vector)
                    question='Explain related sources for '+token
                    retrieval=answer_planning.retrieve(actor,reviewer,question)
                    assert retrieval['status']=='MATCHED'
                    # A lexical title hit alone supplies no relationship:
                    # answer evidence retains the actual edge endpoints.
                    assert ids(retrieval['items'])=={native['anchor'],native['neighbor']}
                    plan=answer_planning.prepare(question,'offline-ablation',dict(mode='KNOWLEDGE_ONLY',disclosure_profiles=['offline-ablation']),retrieval)
                    wire=json.loads(plan['messages'][-1]['content'])
                    assert len(wire['authorized_relationships'])==1
                    assert wire['authorized_relationships'][0]['edge_type']=='RELATED_TO'
                    neighbor=next(item for item in plan['citations'] if item['entity_id']==native['neighbor'])
                    business_channel_runtime._check_sources(reviewer,dict(requester_principal_id=actor),[neighbor],{actor})
                assert knowledge_signals.candidates(actor,reviewer,[token],channel='graph',anchors=[native['anchor']],entity_ids=[native['tag']])==[]
                for kind in ('metadata','tag','neighbor'):
                    item=knowledge_grounding.citation(actor,reviewer,native[kind])
                    assert token not in item['title']+item['content']
                    assert knowledge_grounding.citation(actor,reviewer,native[kind],item['digest'])['digest']==item['digest']
                knowledge_api.set_access_policy(native['neighbor'],'PRINCIPAL_PRIVATE',actor,principal_id=actor,reason=reason)
                with pytest.raises(PermissionError):
                    knowledge_grounding.validate_citation(actor,reviewer,neighbor)
                assert knowledge_signals.candidates(actor,reviewer,[token],channel='graph',anchors=[native['anchor']])==[]
                knowledge_api.set_access_policy(native['anchor'],'PRINCIPAL_PRIVATE',actor,principal_id=actor,reason=reason)
                assert knowledge_signals.candidates(actor,reviewer,[token],channel='graph',anchors=[native['anchor']])==[]
                assert ids(embedding_api.search_authorized_knowledge(token,channel='fulltext',actor=actor,agent=reviewer))=={native['title-match']}
                identity_api.assign_permission_override(actor,reviewer,'knowledge.read','DENY','OWNED',reason)
                with pytest.raises(PermissionError):
                    knowledge_signals.candidates(actor,reviewer,[token],channel='relational')
            record_property('native_signal_behavior',json.dumps(dict(target=target['key'],
                status='BEHAVIOR_ASSERTIONS_COMPLETE',generation_calls=0,embedding_calls=0,
                queries=[dict(query_sha256=hashlib.sha256(sql.encode()).hexdigest(),elapsed_ms=elapsed,
                              result_count=count) for sql,params,elapsed,count in statements[:4]])))
            plans=[]
            for sql,params,elapsed,count in statements[:4]:
                if target['database']=='pg':
                    plan=next(iter(original('EXPLAIN (FORMAT JSON) '+sql,params)[0].values()))
                    plan_kind='POSTGRESQL_ESTIMATED'
                elif target['database']=='oracle':
                    statement='V503_'+uuid.uuid4().hex[:24].upper()
                    with connection.get_connection() as conn:
                        try:
                            with conn.cursor() as cursor:
                                cursor.execute("EXPLAIN PLAN SET STATEMENT_ID='"+statement+"' FOR "+sql,params)
                                cursor.execute("SELECT PLAN_TABLE_OUTPUT FROM TABLE(DBMS_XPLAN.DISPLAY('PLAN_TABLE',:statement,'BASIC +PREDICATE'))",dict(statement=statement))
                                plan=[row[0] for row in cursor.fetchall()]
                                assert any('SELECT STATEMENT' in line for line in plan)
                        finally:
                            conn.rollback()
                    plan_kind='ORACLE_ESTIMATED'
                elif target['database']=='yashandb':
                    # EXPLAIN on this native SEARCH query crashed the PDB
                    # (signal 11, cbo_hybridexec.c:127). Read the actual cached
                    # executed cursor instead; never compile a literal replay.
                    marker,executed=cache_statements[sql]
                    cached=original('SELECT SQL_ID,CHILD_NUMBER,PLAN_HASH_VALUE,EXECUTIONS,SQL_FULLTEXT FROM V$SQL '
                        'WHERE SQL_TEXT LIKE :prefix',dict(prefix='SELECT /* '+marker+' */%'))
                    cached=[row for row in cached if row['sql_fulltext']==executed and int(row['executions'])>0]
                    assert cached,'The exact executed native cursor must be present'
                    # Native cache may retain several plans for the same SQL.
                    # Bind every plan identity instead of assuming one child.
                    plan=[];seen=set()
                    for cursor in cached:
                        identity=(cursor['sql_id'],cursor['child_number'],cursor['plan_hash_value'])
                        if identity in seen:continue
                        seen.add(identity)
                        rows=original('SELECT ID,PARENT_ID,OPERATION,OPTIONS,OBJECT_OWNER,OBJECT_NAME,'
                            'ACCESS_PREDICATES,FILTER_PREDICATES FROM V$SQL_PLAN '
                            'WHERE SQL_ID=:id AND CHILD_NUMBER=:child AND PLAN_HASH_VALUE=:plan ORDER BY ID',
                            dict(id=identity[0],child=identity[1],plan=identity[2]))
                        assert rows and any(row['operation']=='SELECT STATEMENT' for row in rows)
                        plan.append(dict(sql_id=identity[0],child_number=identity[1],plan_hash_value=identity[2],
                            executions=cursor['executions'],plan=rows))
                    plan_kind='YASHANDB_EXECUTED_CURSOR_CACHE'
                else:
                    pytest.fail('No admitted native plan observer for this backend')
                # Plan output is retained only for synthetic, owned fixture SQL.
                plans.append(dict(query_sha256=hashlib.sha256(sql.encode()).hexdigest(),elapsed_ms=elapsed,
                    result_count=count,plan_kind=plan_kind,plan=plan))
            record_property('native_signal_evidence',json.dumps(dict(target=target['key'],database=target['name'],
                signals=['relational','tag','graph','fulltext'],generation_calls=0,embedding_calls=0,
                index_readiness_wait_ms=index_wait_ms,plans=plans),default=str))
        finally:
            for key in public:
                knowledge_api.set_access_policy(key,'PRINCIPAL_PRIVATE',actor,principal_id=actor,reason=reason)


def test_native_task_hybrid_discovery_pins_domain_revision_and_rechecks_withdrawal(native_target,monkeypatch,record_property):
    target,actor=native_target
    domain='V503_TASK_'+uuid.uuid4().hex.upper()
    reason='Verify scoped Task context discovery through database hybrid retrieval'
    token='procedure'+uuid.uuid4().hex
    security_domain_api.create_domain(actor,domain,'Task hybrid context','INTERNAL',reason,actor,reason)
    with independent_reviewer(actor,domain,reason) as reviewer:
        original=signal_fixture_source(actor,reviewer,domain,reason,lifetime_seconds=30)
        key=promote_signal_fixture(actor,reviewer,domain,original,reason,
            title='A synthetic reviewed procedure',body='Verified '+token+' procedure; never claim execution from these instructions.',
            subject='Synthetic procedure')
        artifact=connection.execute_query_one('SELECT ARTIFACT_ID,REVISION_ID,CONTENT_DIGEST FROM CX_CONTINUITY_ARTIFACT_REVS WHERE NATIVE_ENTITY_ID=:native',dict(native=key))
        knowledge_api.set_access_policy(key,'PUBLIC_COMPANY',actor,reason=reason)
        try:
            # Only vector availability is deliberately ablated here. Other
            # channels, domain filters, exact sources and transactions are real.
            search=embedding_api.search_authorized_knowledge
            def without_vector(*args,**kwargs):
                if kwargs.get('channel')=='vector':
                    raise embedding_api.AuthorizedSearchUnavailable('Explicit native Task vector ablation')
                return search(*args,**kwargs)
            with monkeypatch.context() as patch:
                patch.setattr(embedding_api,'search_authorized_knowledge',without_vector)
                patch.setattr(embedding_api,'_query_embedding',lambda *_a,**_k:pytest.fail('No provider call in this native Task check'))
                value=dict(request_id=uuid.uuid4().hex,security_domain_id=domain,knowledge_retrieval='hybrid',
                    query_text=token,token_budget=32000,purpose=reason,idempotency_key=uuid.uuid4().hex)
                reference=SourceRef(family='KNOWLEDGE',entity_id=artifact['artifact_id'],
                    revision_id=artifact['revision_id'],content_digest=artifact['content_digest'])
                for principal in (actor,reviewer):
                    assert connection.execute_transaction_callback(lambda tx:
                        context_selection.metadata_many(tx,principal,domain,[reference]))[0] is not None
                retrieved=connection.execute_transaction_callback(lambda tx:knowledge_grounding.search(
                    actor,reviewer,token,strategy='hybrid',artifact_domain=domain,transaction=tx))
                assert [item['entity_id'] for item in retrieved['items']]==[key], retrieved['retrieval']
                built=continuity_assembly.assemble(actor,value,_source_reader=reviewer)
                content=continuity_assembly.read_assembly(actor,built['assembly_id'])
                assert content['retrieval_policy']=='QUERY_HYBRID_BUDGET_SOURCE_CONTEXT_V3'
                assert content['item_count']==1, content['representations']
                assert token in content['text']
                item=content['items'][0]
                assert (item['entity_id'],item['revision_id'],item['content_digest'])==tuple(artifact[key] for key in ('artifact_id','revision_id','content_digest'))
                assert continuity_assembly.assemble(actor,value,_source_reader=reviewer)['replayed']
                # Revoke only the other reader; a new request cannot use the
                # owner's private data as an Agent's execution context.
                knowledge_api.set_access_policy(key,'PRINCIPAL_PRIVATE',actor,principal_id=actor,reason=reason)
                hidden=continuity_assembly.assemble(actor,dict(value,idempotency_key=uuid.uuid4().hex),_source_reader=reviewer)
                assert continuity_assembly.read_assembly(actor,hidden['assembly_id'])['item_count']==0
                # Observe the immutable Handoff's actual configured expiry;
                # never rewrite protected history to simulate withdrawal.
                expiry=connection.execute_query_one('SELECT EXPIRES_AT FROM CX_HANDOFFS WHERE HANDOFF_ID=:id',
                    dict(id=original['entity_id']))['expires_at']
                expiry=expiry.replace(tzinfo=expiry.tzinfo or timezone.utc)
                delay=max(0,(expiry-datetime.now(timezone.utc)).total_seconds())
                assert delay<=30
                if delay:time.sleep(delay+0.05)
                assert handoff.read_handoff(actor,original['entity_id'])['expired']
                with pytest.raises((PermissionError,ContinuityConflict)) as unavailable:
                    continuity_assembly.consume(actor,built['assembly_id'],lambda *_:pytest.fail('Withdrawn source was sent'))
                if isinstance(unavailable.value,ContinuityConflict):
                    assert unavailable.value.code=='EXPIRED'
            record_property('native_task_hybrid',json.dumps(dict(target=target['key'],status='VERIFIED',
                exact_current_revision=True,domain_filter=True,second_reader_revocation=True,
                original_withdrawal_blocks_use=True,generation_calls=0,embedding_calls=0,vector='EXPLICIT_ABLATION')))
        finally:
            knowledge_api.set_access_policy(key,'PRINCIPAL_PRIVATE',actor,principal_id=actor,reason=reason)
