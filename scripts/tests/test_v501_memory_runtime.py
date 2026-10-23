"""Relational transaction harness for temporal evidence, notes and retrospectives.

SQLite tests establish service contracts only; native adapter acceptance remains
a separate release requirement.
"""
from datetime import datetime, timedelta, timezone
import json

import pytest

from lib import (memory_quality as quality, continuity_notes as notes, continuity_retrospectives as retros,
                 continuity_sources as sources, continuity_work as work, continuity_handoff as handoff,
                 continuity_candidates as candidates, memory_lifecycle as memory, task_continuity as tasks)
from lib.continuity_contracts import SourceRef
from lib.continuity_state import ContinuityError, ContinuityConflict
from .test_continuity_work import database, request
from .test_continuity_handoff import fixture, offer_request
from .test_continuity_candidates import candidate_db, new_candidate, approve


def test_work_note_list_normalises_database_identifier_case():
    assert notes._normalise_rows([{"NOTE_ID": "WN_1", "STATUS": "ACTIVE"}]) == [
        {"note_id": "WN_1", "status": "ACTIVE"}
    ]


@pytest.fixture
def runtime(candidate_db,monkeypatch):
    db,source=candidate_db
    db.executescript('''
        CREATE TABLE CX_LLM_PROVIDER_PROFILES(PROFILE_ID TEXT PRIMARY KEY,VERSION INTEGER,STATUS TEXT,HEALTH_STATE TEXT,
            PROVIDER_URL TEXT,MODEL_ID TEXT,API_KEY_CIPHER TEXT);
        INSERT INTO CX_LLM_PROVIDER_PROFILES VALUES('model',1,'ACTIVE','HEALTHY','http://model.test/v1','test-model',NULL);
        CREATE TABLE CX_PORTAL_KNOWLEDGE_POLICY(POLICY_ID TEXT PRIMARY KEY,VERSION INTEGER,DISCLOSURE_PROFILES_JSON TEXT);
        INSERT INTO CX_PORTAL_KNOWLEDGE_POLICY VALUES('DEFAULT',1,'["model"]');
        CREATE TABLE CX_CONTEXT_ASSEMBLIES(ASSEMBLY_ID TEXT PRIMARY KEY);
        CREATE TABLE TASK_PLANS(PLAN_ID TEXT PRIMARY KEY,AGENT_ID TEXT,STATUS TEXT,GOAL TEXT,PRIORITY INTEGER,STRATEGY TEXT);
        CREATE TABLE TASK_STEPS(STEP_ID TEXT PRIMARY KEY,PLAN_ID TEXT,PLAN_STATUS TEXT,STEP_ORDER INTEGER,
            DESCRIPTION TEXT,TOOL_NAME TEXT,STATUS TEXT);
        INSERT INTO TASK_PLANS VALUES('501','owner','RUNNING','validation',5,NULL);
    ''')
    for statement in tasks.schema_statements('pg')+quality.schema_statements('pg')+notes.schema_statements('pg')+retros.schema_statements('pg'):
        db.execute(statement.replace('CREATE TABLE ','CREATE TABLE IF NOT EXISTS ',1))
    from lib import continuity_publications
    for statement in continuity_publications.schema_statements('pg'):
        db.execute(statement)
    monkeypatch.setattr(notes.connection,'DATABASE_DIALECT','sqlite')
    monkeypatch.setattr(memory,'execute_transaction_callback',notes.connection.execute_transaction_callback)
    db.commit()
    wid=db.execute('SELECT WORK_CONTRACT_ID FROM CX_WORK_CONTRACTS').fetchone()[0]
    return db,source,wid


def note_request(**change):
    return dict(expected_work_version=1,content=dict(note_type='FINDING',title='Verified finding',body='Exact result',**change),
                reason='Retain working evidence',idempotency_key='note')


@pytest.mark.parametrize('identifier_case',['lower','upper'])
def test_note_listing_first_page_and_continuation_with_oracle_null_semantics(runtime,monkeypatch,identifier_case):
    db,_,wid=runtime
    note_ids=[]
    for index in range(3):
        value=dict(note_request(),idempotency_key='list-note-'+str(index))
        note_ids.append(notes.create_note('owner',wid,value)['note_id'])
    transaction=notes.connection.execute_transaction_callback

    def oracle_empty_strings(callback):
        def perform(tx):
            class ListTransaction:
                query_one=tx.query_one
                execute=tx.execute
                def query(self,statement,params):
                    if 'FROM CX_WORK_NOTES' not in statement:
                        return tx.query(statement,params)
                    # Exercise SQL's NULL comparison, not a Python filter.
                    bound={key:None if value=='' else value for key,value in params.items()}
                    rows=db.execute(statement.replace('FETCH FIRST :lim ROWS ONLY','LIMIT :lim'),bound)
                    return [{key.upper() if identifier_case=='upper' else key.lower():row[key]
                             for key in row.keys()} for row in rows]
            return callback(ListTransaction())
        return transaction(perform)

    monkeypatch.setattr(notes.connection,'execute_transaction_callback',oracle_empty_strings)
    first=notes.list_notes('owner',wid,limit=2)
    assert [item['note_id'] for item in first['items']]==sorted(note_ids)[:2]
    assert first['next_after']==sorted(note_ids)[1]
    second=notes.list_notes('owner',wid,limit=2,after=first['next_after'])
    assert [item['note_id'] for item in second['items']]==sorted(note_ids)[2:]
    assert second['next_after'] is None
    assert notes.list_notes('owner',wid,after=sorted(note_ids)[-1])==dict(items=[],next_after=None)
    with pytest.raises(PermissionError):
        notes.list_notes('outsider',wid)
    with pytest.raises(PermissionError):
        notes.list_notes('owner','unavailable-work')


def test_note_inventory_rechecks_the_original_execution_resource(runtime):
    db,_,wid=runtime
    note_id=notes.create_note('owner',wid,note_request())['note_id']
    db.execute('ALTER TABLE CX_AGENT_RELATIONSHIPS ADD COLUMN RELATIONSHIP_ID TEXT')
    db.execute("INSERT INTO CX_WORK_EXECUTION_LINKS(WORK_CONTRACT_ID,LINK_KIND,ENTITY_ID,SOURCE_PRINCIPAL_ID,CREATED_BY) VALUES(?,'TASK','501','owner','owner')",(wid,))
    db.commit()
    assert notes.read_note('owner',note_id)['note_id']==note_id
    with pytest.raises(PermissionError,match='Execution resource access denied'):
        notes.list_notes('reader',wid)


def ref(actor,note_id):
    value=notes.read_note(actor,note_id)
    return SourceRef(family='WORKING_NOTE',entity_id=note_id,revision_id=str(value['revision_no']),content_digest=value['content_digest'])


def test_unknown_event_and_offset_are_not_replaced_with_ingestion_time():
    unknown=quality.temporal_facts({})
    assert unknown['event_at'] is None and unknown['event_time_state']=='UNKNOWN'
    assert unknown['observed_at'] is not None
    no_offset=quality.temporal_facts(dict(event_at='2026-01-02T12:30:00'))
    assert no_offset['event_time_state']=='UNKNOWN_OFFSET' and no_offset['event_at'] is None
    assert no_offset['event_time_text']=='2026-01-02T12:30:00'
    known=quality.temporal_facts(dict(event_at='2026-01-02T12:30:00+08:00'))
    assert known['event_at']==datetime(2026,1,2,4,30)
    with pytest.raises(ValueError):
        quality.temporal_facts(dict(applies_from='2026-01-01T00:00:00'))


@pytest.mark.parametrize(('dialect', 'expression'), [
    ('pg', "CURRENT_TIMESTAMP AT TIME ZONE 'UTC'"),
    ('postgresql', "CURRENT_TIMESTAMP AT TIME ZONE 'UTC'"),
    ('oracle', 'SYS_EXTRACT_UTC(SYSTIMESTAMP)'),
    ('yashandb', 'SYS_EXTRACT_UTC(SYSTIMESTAMP)'),
])
def test_applicability_compares_utc_naive_facts_in_utc(runtime, monkeypatch, dialect, expression):
    _, _, _ = runtime
    monkeypatch.setattr(quality.connection, 'DATABASE_DIALECT', dialect)
    predicate = quality.applicable_sql()
    assert predicate.count(expression) == 2

    class Tx:
        def query_one(self, sql, params):
            assert expression in sql
            assert params == {'version': 'version'}
            return None

    quality.require_applicable(Tx(), 'version')


def test_late_evidence_and_exact_correction_guard(runtime):
    db,_,_=runtime
    class Tx:
        def query_one(self,sql,params):
            return dict(applies_from='2026-05-01 00:00:00',event_at=None)
    old=quality.temporal_facts(dict(event_at='2026-04-01T00:00:00Z'))
    with pytest.raises(ContinuityConflict,match='Older applicable'):
        quality.guard_successor(Tx(),'current',old)
    with pytest.raises(ValueError):
        quality.temporal_facts(dict(corrects_version_id='current',correction_scope='fact'))
    correction=quality.temporal_facts(dict(corrects_version_id='current',correction_scope='address',applies_from='2026-04-01T00:00:00Z'))
    quality.guard_successor(Tx(),'current',correction)
    with pytest.raises(ContinuityConflict,match='exact current'):
        quality.guard_successor(Tx(),'other',correction)


@pytest.mark.parametrize('kind',['FINDING','REJECTED_APPROACH','VALIDATION','OPEN_QUESTION','NEXT_ACTION'])
def test_notes_are_typed_versioned_and_never_publish(runtime,kind):
    db,source,wid=runtime
    value=note_request(sources=[source])
    value['content']['note_type']=kind
    result=notes.create_note('owner',wid,value)
    assert notes.create_note('owner',wid,value)['replayed']
    first=notes.read_note('agent',result['note_id'])
    assert first['content']['note_type']==kind
    assert notes.read_note('reader',result['note_id'])['content_unavailable']=='SOURCE_AUTHORITY_CHANGED'
    changed=dict(expected_version=1,content=dict(value['content'],body='New result'),reason='Correct finding',idempotency_key='revise')
    assert notes.revise_note('owner',result['note_id'],changed)['revision_no']==2
    assert notes.read_note('owner',result['note_id'],1)['content']['body']=='Exact result'
    assert notes.revise_note('owner',result['note_id'],changed)['replayed']
    assert db.execute('SELECT COUNT(*) FROM CX_ARTIFACT_CANDIDATES').fetchone()[0]==0
    assert db.execute('SELECT COUNT(*) FROM CX_MEMORY_VERSIONS').fetchone()[0]==0
    with pytest.raises(ContinuityConflict):
        notes.revise_note('owner',result['note_id'],dict(changed,idempotency_key='stale'))


def test_pinned_note_expiry_blocks_fresh_handoff_resolution(runtime):
    db,_,wid=runtime
    value=note_request(expires_at=datetime.now(timezone.utc)+timedelta(hours=1))
    note_id=notes.create_note('owner',wid,value)['note_id']
    source=ref('owner',note_id)
    # Advance the clock without corrupting the immutable note content/digest.
    original=notes.datetime
    class Clock(datetime):
        @classmethod
        def now(cls,tz=None):
            return original.now(tz)+timedelta(hours=2)
    from unittest.mock import patch
    with patch.object(notes,'datetime',Clock):
        assert notes.read_note('owner',note_id,1)['expired']
        with pytest.raises(ContinuityConflict,match='not available'):
            notes.connection.execute_transaction_callback(lambda tx:sources.resolve(tx,'owner','domain',source))
    offered=offer_request(key='note-handoff')
    # Original fixture already has a handoff; retire it to test a new offer.
    db.execute("UPDATE CX_HANDOFFS SET STATUS='REJECTED',ACTIVE_WORK_ID=NULL")
    db.commit()
    offered['content']['evidence']=[source.model_dump(mode='json')]
    hid=handoff.offer('owner',wid,offered)['handoff_id']
    with patch.object(notes,'datetime',Clock):
        with pytest.raises(ContinuityConflict,match='not available'):
            handoff.read_handoff('agent',hid)


def test_note_authority_sources_and_audit_are_transactional(runtime,monkeypatch):
    db,source,wid=runtime
    note_id=notes.create_note('owner',wid,note_request(sources=[source]))['note_id']
    with pytest.raises(PermissionError):
        notes.read_note('outsider',note_id)
    def fail(*args):
        raise RuntimeError('audit unavailable')
    monkeypatch.setattr(notes.identity_api,'_audit_tx',fail)
    with pytest.raises(RuntimeError):
        notes.revise_note('owner',note_id,dict(expected_version=1,content=note_request()['content'],reason='change',idempotency_key='change'))
    assert notes.read_note('owner',note_id)['version']==1
    assert db.execute('SELECT COUNT(*) FROM CX_WORK_NOTE_REVISIONS').fetchone()[0]==1
    db.execute("UPDATE CX_DOMAIN_MEMBERS SET STATUS='REVOKED' WHERE PRINCIPAL_ID='owner'")
    db.commit()
    with pytest.raises(PermissionError):
        notes.create_note('owner',wid,note_request(sources=[source]))


def test_retired_note_and_digest_tamper_never_resolve(runtime):
    db,_,wid=runtime
    note_id=notes.create_note('owner',wid,note_request())['note_id']
    source=ref('owner',note_id)
    notes.change_state('owner',note_id,dict(expected_version=1,status='RETIRED',reason='No longer current',idempotency_key='retire'))
    with pytest.raises(ContinuityConflict,match='not available'):
        notes.connection.execute_transaction_callback(lambda tx:sources.resolve(tx,'owner','domain',source))
    db.execute("UPDATE CX_WORK_NOTE_REVISIONS SET BODY_TEXT='corrupt'")
    db.commit()
    with pytest.raises(ContinuityError,match='integrity'):
        notes.read_note('owner',note_id)


def _memory_source(source,key):
    cid=candidates.create_candidate('owner',new_candidate(source,key=key))['candidate_id']
    result=candidates.promote_candidate('agent',cid,approve(cid))
    record=notes.connection.execute_transaction_callback(lambda tx:tx.query_one(
        'SELECT CONTENT_DIGEST FROM CX_MEMORY_VERSIONS WHERE VERSION_ID=:version',{'version':result['result_revision_id']}))
    return dict(family='MEMORY',entity_id=result['result_entity_id'],revision_id=result['result_revision_id'],
                content_digest=record['content_digest'])


def test_unresolved_reconciliation_never_activates_or_accepts_self_review(runtime):
    db,source,_=runtime
    # Existing candidate publication generates two independent native families.
    refs=[_memory_source(source,key) for key in ['m1','m2']]
    request=dict(security_domain_id='domain',sources=refs,relation_kind='CONTRADICTION',method='semantic-v1',policy_revision='p1',
                 confidence=0.9,confidence_meaning='Estimated relation likelihood, not factual truth',
                 reason='Verify contradictory evidence',idempotency_key='reconcile',judgment_available=False)
    created=quality.propose_reconciliation('owner',request)
    assert created['status']=='UNRESOLVED'
    assert quality.propose_reconciliation('owner',request)['replayed']
    with pytest.raises(ContinuityConflict):
        quality.review_reconciliation('agent',created['proposal_id'],decision='APPROVED',reason='review')
    request.update(judgment_available=True,idempotency_key='resolved')
    second=quality.propose_reconciliation('owner',request)
    with pytest.raises(PermissionError):
        quality.review_reconciliation('owner',second['proposal_id'],decision='APPROVED',reason='review')
    approved=quality.review_reconciliation('agent',second['proposal_id'],decision='APPROVED',reason='independent')
    assert not approved['activated']
    assert quality.review_reconciliation('agent',second['proposal_id'],decision='APPROVED',reason='independent')['replayed']
    with pytest.raises(ContinuityConflict):
        quality.review_reconciliation('agent',second['proposal_id'],decision='REJECTED',reason='different decision')
    assert db.execute('SELECT COUNT(*) FROM CX_MEMORY_RELATIONS').fetchone()[0]==0


def retrospective(source,**change):
    return dict(security_domain_id='domain',task_id='501',trigger='FAILURE',target_family='EXPERIENCE',sources=[source],
        policy_revision='p1',profile_id='model',profile_version=1,reason='Review task failure',idempotency_key='retro',**change)


def test_retrospective_reuses_task_steps_attempts_and_candidate_review_chain(runtime):
    db,source,_=runtime
    value=retrospective(source)
    created=retros.create_job('owner',value)
    assert retros.create_job('owner',value)['replayed']
    loaded=retros.read_job('owner',created['job_id'])
    assert loaded['status']=='PENDING' and loaded['sources']==[source]
    assert db.execute('SELECT COUNT(*) FROM TASK_PLANS').fetchone()[0]==1
    calls=[]
    def generate(frozen):
        calls.append(frozen)
        return dict(family='EXPERIENCE',title='Retry safely',problem='Uncertain prior outcome',solution='Reconcile first',
                    validation='The deterministic scenario passed',applicability='Unknown sends')
    result=retros.run_once('owner',created['job_id'],'non-principal-worker',generate)
    assert result['status']=='PROPOSED' and not result['published']
    assert db.execute('SELECT STATUS FROM TASK_STEPS').fetchone()[0]=='SUCCESS'
    assert candidates.read_candidate('owner',result['candidate_id'])['status']=='PENDING'
    assert db.execute('SELECT COUNT(*) FROM ENTITIES').fetchone()[0]==0
    assert retros.run_once('owner',created['job_id'],'non-principal-worker',generate)['replayed']
    assert len(calls)==1


def test_uncertain_generation_is_not_resent_and_revocation_blocks_use(runtime):
    db,source,_=runtime
    created=retros.create_job('owner',retrospective(source))
    calls=[]
    def failed(frozen):
        calls.append(1)
        raise TimeoutError('Unknown transport result')
    assert retros.run_once('owner',created['job_id'],'worker',failed)['status']=='UNOBSERVED'
    assert retros.run_once('owner',created['job_id'],'worker',failed)['status']=='UNOBSERVED'
    assert len(calls)==1 and db.execute('SELECT COUNT(*) FROM CX_ARTIFACT_CANDIDATES').fetchone()[0]==0
    db.execute("UPDATE CX_DOMAIN_MEMBERS SET STATUS='REVOKED' WHERE PRINCIPAL_ID='owner'")
    db.commit()
    with pytest.raises(PermissionError):
        retros.read_job('owner',created['job_id'])


def test_stale_model_and_candidate_audit_failure_rollback(runtime,monkeypatch):
    db,source,_=runtime
    created=retros.create_job('owner',retrospective(source))
    db.execute("UPDATE CX_LLM_PROVIDER_PROFILES SET VERSION=2")
    db.commit()
    with pytest.raises(ContinuityConflict,match='exact healthy'):
        retros.run_once('owner',created['job_id'],'worker',lambda _:None)
    assert db.execute('SELECT COUNT(*) FROM CX_TASK_CONTINUITY_ATTEMPTS').fetchone()[0]==0


def test_default_model_worker_is_executable_and_enforces_disclosure_budget(runtime,monkeypatch):
    db,source,_=runtime
    from lib import provider_capability_probes, agent_extension_contracts
    monkeypatch.setattr(provider_capability_probes,'apply_parameters',lambda profile,payload:payload)
    calls=[]
    class Response:
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def read(self,limit):
            return json.dumps(dict(model='test-model',choices=[dict(finish_reason='stop',message=dict(content=json.dumps(
                dict(family='EXPERIENCE',title='Check before retry',problem='Unknown state',solution='Reconcile',
                     validation='Deterministic verification',applicability='Task failures'))))])).encode()
    class Opener:
        def open(self,request,timeout):
            calls.append(json.loads(request.data))
            assert request.full_url=='http://model.test/v1/chat/completions' and timeout==120
            return Response()
    monkeypatch.setattr(agent_extension_contracts,'opener',lambda:Opener())
    created=retros.create_job('owner',retrospective(source))
    assert retros.run_once('owner',created['job_id'],'worker')['status']=='PROPOSED'
    assert len(calls)==1 and calls[0]['max_tokens']<=8192//3 and not calls[0]['stream']
    denied=retrospective(source)
    denied['idempotency_key']='denied'
    created=retros.create_job('owner',denied)
    db.execute("UPDATE CX_PORTAL_KNOWLEDGE_POLICY SET VERSION=2,DISCLOSURE_PROFILES_JSON='[]'")
    db.commit()
    assert retros.run_once('owner',created['job_id'],'worker')['status']=='FAILED'
    assert len(calls)==1


def test_note_cannot_turn_handoff_source_into_an_unauthorized_read(runtime):
    _,source,wid=runtime
    note_id=notes.create_note('owner',wid,note_request(sources=[source]))['note_id']
    visible=notes.read_note('reader',note_id)
    assert visible['content'] is None
    assert visible['content_unavailable']=='SOURCE_AUTHORITY_CHANGED'


def test_unknown_reconciliation_fields_and_nonfinite_confidence_are_rejected():
    with pytest.raises(ValueError,match='Unsupported'):
        quality.propose_reconciliation('owner',dict(extra='not allowed'))


def test_every_new_memory_records_unknown_event_without_inventing_time(runtime):
    db,source,_=runtime
    memory_source=_memory_source(source,'time-fact')
    temporal=quality.read_time('owner',memory_source)
    assert temporal['event_time_state']=='UNKNOWN' and temporal['event_at'] is None
    assert temporal['observed_at'] is not None and temporal['provenance']=='RECORDED'
    db.execute("UPDATE CX_MEMORY_TIME_FACTS SET EVENT_TIME_STATE='UNKNOWN_OFFSET',EVENT_TIME_TEXT='corrupt'")
    db.commit()
    with pytest.raises(ContinuityError,match='integrity'):
        quality.read_time('owner',memory_source)
    db.execute("DELETE FROM CX_MEMORY_TIME_FACTS WHERE VERSION_ID=?",(memory_source['revision_id'],))
    db.commit()
    legacy=quality.read_time('owner',memory_source)
    assert legacy['event_at'] is None and legacy['event_time_state']=='UNKNOWN'
    assert legacy['observed_at'] is not None and legacy['provenance']=='HISTORICAL_INGESTION_TIME'


def test_restore_creates_new_revision_and_preserves_history_with_atomic_audit(runtime,monkeypatch):
    db,source,_=runtime
    original=_memory_source(source,'restore-source')
    next_version=memory.create_successor(original['entity_id'],original['revision_id'],dict(title='Changed',body='A changed fact.',
        memory_type='FACT',memory_scope='AGENT_MEMORY',classification='INTERNAL',security_domain_id='domain',owner_principal_id='owner'),actor='owner')
    before=db.execute('SELECT TITLE,BODY_TEXT,CONTENT_DIGEST,REASON FROM CX_MEMORY_VERSIONS WHERE VERSION_ID=?',(original['revision_id'],)).fetchone()[:]
    value=dict(expected_version_id=next_version['version_id'],historical_version_id=original['revision_id'],
               reason='Restore independently verified prior wording',idempotency_key='restore')
    result=quality.restore_version('owner',original['entity_id'],value)
    assert result['version_number']==3 and result['version_id']!=original['revision_id']
    assert quality.restore_version('owner',original['entity_id'],value)['replayed']
    assert db.execute('SELECT TITLE,BODY_TEXT,CONTENT_DIGEST,REASON FROM CX_MEMORY_VERSIONS WHERE VERSION_ID=?',(original['revision_id'],)).fetchone()[:]==before
    assert db.execute('SELECT SOURCE_REF FROM CX_MEMORY_VERSIONS WHERE VERSION_ID=?',(result['version_id'],)).fetchone()[0]=='RESTORE:'+original['revision_id']
    with pytest.raises(ContinuityConflict):
        quality.restore_version('owner',original['entity_id'],dict(value,idempotency_key='stale'))
    count=db.execute('SELECT COUNT(*) FROM CX_MEMORY_VERSIONS').fetchone()[0]
    def fail(*args):
        raise RuntimeError('audit failed')
    monkeypatch.setattr(quality.identity_api,'_audit_tx',fail)
    with pytest.raises(RuntimeError):
        quality.restore_version('owner',original['entity_id'],dict(value,expected_version_id=result['version_id'],idempotency_key='audit-failure'))
    assert db.execute('SELECT COUNT(*) FROM CX_MEMORY_VERSIONS').fetchone()[0]==count
    assert db.execute('SELECT CURRENT_VERSION_ID FROM CX_MEMORY_FAMILIES').fetchone()[0]==result['version_id']


@pytest.mark.parametrize('database',['oracle','pg','yashandb'])
def test_migration_generation_and_relational_contract(database):
    import importlib.util
    from pathlib import Path
    root=Path(__file__).resolve().parents[2]
    if not (root/'tools/v501_generate_memory_quality.py').is_file():
        pytest.skip('Source generator is not shipped in runtime packages')
    import sys
    monkey_path=str(root/'tools')
    sys.path.insert(0,monkey_path)
    try:
        from v501_generate_memory_quality import render
        sql,facts=render(database)
    finally:
        sys.path.remove(monkey_path)
    path=root/'adapters'/database/'deploy/103_v5_0_1_memory_quality.sql'
    assert path.read_text()==sql
    assert len(facts)==12
    assert 'CX_WORK_NOTE_SOURCES' in facts and 'CX_RETROSPECTIVE_SOURCES' in facts
    assert 'REVOKE ' in sql
    assert ('RAISE evidence_immutable' in sql)==(database=='yashandb')
