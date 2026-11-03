"""Quality, source authority and immutable applicability are separate gates."""
import json

import pytest
from pydantic import ValidationError

from lib import continuity_candidates as candidates, knowledge_intake as intake
from lib.continuity_contracts import CandidatePayload, NewCandidate, KnowledgeIntake, content_digest, KnowledgeProposal
from lib.continuity_state import ContinuityConflict, ContinuityError
from .test_continuity_work import database
from .test_continuity_handoff import fixture
from .test_continuity_candidates import candidate_db, PROPOSALS, new_candidate, approve


def test_legacy_payload_bytes_and_request_digest_unchanged():
    source=dict(family='SOURCE',entity_id='s',revision_id='r',content_digest='a'*64)
    old=dict(content=PROPOSALS[1],sources=[source],replaces=None)
    value=CandidatePayload.model_validate(old)
    assert value.model_dump(mode='json')==old
    assert 'intake' not in NewCandidate.model_validate(dict(old,security_domain_id='d',reason='test',idempotency_key='k')).model_dump(mode='json')
    assert content_digest(value)==content_digest(CandidatePayload.model_validate(dict(old,intake=None)))


def test_effective_time_cannot_be_naive_or_inferred():
    with pytest.raises(ValidationError):
        KnowledgeIntake(effective_from='2026-11-01T00:00:00')
    with pytest.raises(ValidationError):
        KnowledgeIntake(effective_until='2026-11-01T00:00:00Z')
    value=KnowledgeIntake()
    assert value.effective_from is None


def test_preview_retains_table_headers_units_negation_exceptions_and_code():
    body='Use milliseconds; do not interpret as seconds.\n\n| mode | limit (ms) |\n|---|---|\n| slow | 180000 |\n\nExcept when a human stops work.\n\n```sql\nSELECT 1;\n\nSELECT 2;\n```\n'
    spans=intake.chunks(body,target=65)
    assert ''.join(item['text'] for item in spans)==body
    assert any('| mode | limit (ms) |\n|---|---|\n| slow | 180000 |' in item['text'] for item in spans)
    assert any('SELECT 1;\n\nSELECT 2;' in item['text'] for item in spans)
    assert all(body[item['start']:item['end']]==item['text'] for item in spans)


def test_incomplete_candidate_persists_but_cannot_be_approved(candidate_db):
    db,source=candidate_db
    value=new_candidate(source,PROPOSALS[1]);value.pop('intake')
    preview=candidates.preview_knowledge('owner',value)
    assert not preview['publication_eligible']
    assert preview['chunks'][0]['text']==PROPOSALS[1]['body']
    assert db.execute('SELECT COUNT(*) FROM CX_ARTIFACT_CANDIDATES').fetchone()[0]==0
    cid=candidates.create_candidate('owner',value)['candidate_id']
    detail=candidates.read_candidate('owner',cid)
    assert detail['intake_preview']==preview
    with pytest.raises(ContinuityConflict,match='Complete knowledge'):
        approve(cid)
    assert db.execute('SELECT STATUS FROM CX_ARTIFACT_CANDIDATES').fetchone()[0]=='PENDING'
    assert db.execute('SELECT COUNT(*) FROM ENTITIES').fetchone()[0]==0


def test_revised_metadata_is_bound_to_exact_review_and_history(candidate_db):
    db,source=candidate_db
    value=new_candidate(source,PROPOSALS[1])
    cid=candidates.create_candidate('owner',value)['candidate_id']
    old=candidates.read_candidate('owner',cid)
    changed=dict(value,expected_version=1,idempotency_key='revise',intake=dict(value['intake'],applicable_version='5.0.4'))
    candidates.revise_candidate('owner',cid,changed)
    current=candidates.read_candidate('owner',cid)
    assert old['content_digest']!=current['content_digest']
    assert candidates.read_candidate('owner',cid,1)['payload']['intake']['applicable_version']=='5.0.3'
    assert current['payload']['intake']['applicable_version']=='5.0.4'
    result=candidates.promote_candidate('agent',cid,approve(cid))
    assert result['result_entity_id']
    assert db.execute('SELECT VISIBILITY FROM ENTITIES').fetchone()[0]=='PRIVATE'
    assert db.execute('SELECT COUNT(*) FROM CX_KNOWLEDGE_INTAKE').fetchone()[0]==2
    assert tuple(db.execute('SELECT DOMAIN,TOPIC FROM KNOWLEDGE_META').fetchone())==('unified-community','Synthetic procedure')


@pytest.mark.parametrize('change,error',[
    ({'classification':'PUBLIC'},ContinuityConflict),
    ({'responsible_principal_id':'outsider'},PermissionError),
])
def test_declared_classification_and_responsible_member_checked(candidate_db,change,error):
    db,source=candidate_db
    value=new_candidate(source,PROPOSALS[1]);value['intake'].update(change)
    cid=candidates.create_candidate('owner',value)['candidate_id']
    with pytest.raises(error):
        approve(cid)
    assert db.execute('SELECT COUNT(*) FROM CX_CANDIDATE_REVIEWS').fetchone()[0]==0


def test_responsibility_revocation_after_approval_blocks_promotion(candidate_db):
    db,source=candidate_db
    cid=candidates.create_candidate('owner',new_candidate(source,PROPOSALS[1]))['candidate_id']
    promotion=approve(cid)
    db.execute("UPDATE CX_DOMAIN_MEMBERS SET STATUS='REVOKED' WHERE PRINCIPAL_ID='owner'");db.commit()
    with pytest.raises(PermissionError):
        candidates.promote_candidate('agent',cid,promotion)
    assert db.execute('SELECT COUNT(*) FROM ENTITIES').fetchone()[0]==0


def test_preview_rechecks_exact_source_and_does_not_write(candidate_db):
    db,source=candidate_db
    value=new_candidate(dict(source,content_digest='f'*64),PROPOSALS[1])
    with pytest.raises(ContinuityConflict):
        candidates.preview_knowledge('owner',value)
    assert db.execute('SELECT COUNT(*) FROM CX_CANDIDATE_REVISIONS').fetchone()[0]==0


def test_tampered_metadata_is_never_returned_as_verified(candidate_db):
    db,source=candidate_db
    cid=candidates.create_candidate('owner',new_candidate(source,PROPOSALS[1]))['candidate_id']
    db.execute("UPDATE CX_KNOWLEDGE_INTAKE SET METADATA_JSON='{}'");db.commit()
    with pytest.raises(ContinuityError,match='integrity'):
        candidates.read_candidate('owner',cid)


@pytest.mark.parametrize('options',[
    {'visibility':'SHARED'}, {'visibility':'PUBLIC'}, {'sharing_scope':'ORGANIZATION_SUBTREE'},
])
def test_direct_api_cannot_publish_shared_uploads(monkeypatch,options):
    from lib import knowledge_api
    def no_write(*args,**kwargs): pytest.fail('Shared direct creation must fail before any mutation')
    monkeypatch.setattr(knowledge_api,'execute_insert_returning_id',no_write)
    monkeypatch.setattr(knowledge_api,'get_agent_knowledge_context',no_write)
    with pytest.raises(ContinuityConflict,match='Shared knowledge requires'):
        knowledge_api.create_knowledge('Upload','Unreviewed text',owned_by_agent='agent',**options)


def test_duplicate_and_possible_conflict_comparison_never_discloses_private_neighbors(candidate_db):
    db,source=candidate_db
    for identifier,body,visibility in [('same','Verified synthetic knowledge.','PUBLIC'),
                                       ('different','A conflicting statement.','PUBLIC'),('secret','Hidden text.','PRIVATE')]:
        db.execute("INSERT INTO ENTITIES(ENTITY_ID,ENTITY_TYPE,TITLE,CONTENT,STATUS,VISIBILITY) VALUES(?,'KNOWLEDGE','Knowledge',?,'ACTIVE',?)",
                   (identifier,body,visibility))
    db.commit()
    result=candidates.preview_knowledge('owner',new_candidate(source,PROPOSALS[1]))
    assert result['comparisons']==[{'entity_id':'different','code':'POSSIBLE_CONFLICT'}, {'entity_id':'same','code':'POSSIBLE_DUPLICATE'}]
    assert not result['exhaustive'] and not result['automatic_publication']
    assert 'secret' not in json.dumps(result) and 'Hidden text' not in json.dumps(result)
    assert db.execute('SELECT COUNT(*) FROM CX_ARTIFACT_CANDIDATES').fetchone()[0]==0


def historical_approved(candidate_db):
    """An actual pre-intake revision/review, not approval via a bypass flag."""
    db,source=candidate_db
    original=new_candidate(source,PROPOSALS[1]);original.pop('intake')
    cid=candidates.create_candidate('owner',original)['candidate_id']
    old=candidates.read_candidate('owner',cid)
    db.execute("INSERT INTO CX_CANDIDATE_REVIEWS(REVIEW_ID,CANDIDATE_ID,REVISION_NO,REVIEWER_ID,DECISION,CONTENT_DIGEST,REASON) "
               "VALUES('historical',?,1,'agent','APPROVED',?,'Historical independent review')",(cid,old['content_digest']))
    db.execute("UPDATE CX_ARTIFACT_CANDIDATES SET STATUS='APPROVED',VERSION=2,REVIEWED_BY='agent' WHERE CANDIDATE_ID=?",(cid,))
    db.commit()
    return cid,old,dict(new_candidate(source,PROPOSALS[1]),expected_version=2,idempotency_key='supplement')


def test_legacy_approval_requires_new_revision_and_new_independent_review(candidate_db):
    db,_=candidate_db
    cid,old,supplement=historical_approved(candidate_db)
    assert candidates.read_candidate('owner',cid)['legacy_remediation_allowed']
    assert not candidates.read_candidate('agent',cid)['legacy_remediation_allowed']
    promotion=dict(expected_version=2,expected_digest=old['content_digest'],reason='Promote legacy',idempotency_key='old-promote')
    with pytest.raises(ContinuityConflict):
        candidates.promote_candidate('agent',cid,promotion)
    revised=candidates.revise_candidate('owner',cid,supplement)
    assert revised['version']==3 and candidates.revise_candidate('owner',cid,supplement)['replayed']
    current=candidates.read_candidate('owner',cid)
    assert current['status']=='PENDING' and current['revision_no']==2 and not current['legacy_remediation_allowed']
    assert db.execute('SELECT REVIEWED_BY FROM CX_ARTIFACT_CANDIDATES').fetchone()[0] is None
    assert candidates.read_candidate('owner',cid,1)['content_digest']==old['content_digest']
    assert db.execute("SELECT CONTENT_DIGEST FROM CX_CANDIDATE_REVIEWS WHERE REVISION_NO=1").fetchone()[0]==old['content_digest']
    with pytest.raises(ContinuityConflict):
        candidates.promote_candidate('agent',cid,dict(promotion,expected_version=3,expected_digest=current['content_digest'],idempotency_key='premature'))
    result=candidates.promote_candidate('agent',cid,approve(cid))
    assert result['result_entity_id']
    assert db.execute('SELECT COUNT(*) FROM CX_CANDIDATE_REVIEWS').fetchone()[0]==2
    assert not candidates.read_candidate('owner',cid)['legacy_remediation_allowed']


@pytest.mark.parametrize('change',[
    {'intake':None}, {'content':dict(PROPOSALS[1],body='Changed after historical approval')},
])
def test_legacy_remediation_only_supplements_metadata(candidate_db,change):
    db,_=candidate_db
    cid,_,supplement=historical_approved(candidate_db)
    with pytest.raises(ContinuityConflict,match='Supplement intake'):
        candidates.revise_candidate('owner',cid,dict(supplement,**change))
    assert db.execute('SELECT COUNT(*) FROM CX_CANDIDATE_REVISIONS').fetchone()[0]==1


def test_legacy_remediation_rechecks_source_on_first_send_and_replay(candidate_db):
    db,_=candidate_db
    cid,_,supplement=historical_approved(candidate_db)
    candidates.revise_candidate('owner',cid,supplement)
    db.execute("UPDATE CX_HANDOFFS SET EXPIRES_AT='2000-01-01 00:00:00'");db.commit()
    with pytest.raises(ContinuityConflict):
        candidates.revise_candidate('owner',cid,supplement)


def test_legacy_remediation_preserves_expected_version_and_proposer(candidate_db):
    db,_=candidate_db
    cid,_,supplement=historical_approved(candidate_db)
    with pytest.raises(PermissionError):
        candidates.revise_candidate('agent',cid,supplement)
    with pytest.raises(ContinuityConflict):
        candidates.revise_candidate('owner',cid,dict(supplement,expected_version=1))
    db.execute("UPDATE CX_DOMAIN_MEMBERS SET STATUS='REVOKED' WHERE PRINCIPAL_ID='owner'");db.commit()
    with pytest.raises(PermissionError):
        candidates.revise_candidate('owner',cid,supplement)


def test_shared_policy_requires_exact_current_review_and_rolls_back_on_audit_failure(candidate_db,monkeypatch):
    from lib import knowledge_api
    db,source=candidate_db
    cid=candidates.create_candidate('owner',new_candidate(source,PROPOSALS[1]))['candidate_id']
    candidates.promote_candidate('agent',cid,approve(cid))
    entity=db.execute('SELECT NATIVE_ENTITY_ID FROM CX_CONTINUITY_ARTIFACT_REVS').fetchone()[0]
    # A normal explicit sharing operation after the separate candidate review.
    shared=knowledge_api.set_access_policy(entity,'PUBLIC_COMPANY','owner',reason='Publish reviewed procedure')
    assert shared['scope_type']=='PUBLIC_COMPANY'
    before=[tuple(row) for row in db.execute('SELECT * FROM CX_KNOWLEDGE_ACCESS_POLICIES')]
    def fail(*args): raise RuntimeError('Audit unavailable')
    with monkeypatch.context() as patch:
        patch.setattr(knowledge_api.identity_api,'_audit_tx',fail)
        with pytest.raises(RuntimeError,match='Audit unavailable'):
            knowledge_api.set_access_policy(entity,'PUBLIC_COMPANY','owner',reason='Repeat explicit sharing')
    assert [tuple(row) for row in db.execute('SELECT * FROM CX_KNOWLEDGE_ACCESS_POLICIES')]==before
    db.execute("UPDATE ENTITIES SET CONTENT='Tampered native body' WHERE ENTITY_ID=?",(entity,));db.commit()
    with pytest.raises(ContinuityConflict,match='approved revision'):
        knowledge_api.set_access_policy(entity,'PUBLIC_COMPANY','owner',reason='Must not publish tampered content')


def test_private_upload_cannot_be_shared_by_policy_or_visibility_update(candidate_db):
    from lib import knowledge_api
    db,_=candidate_db
    db.execute("INSERT INTO ENTITIES(ENTITY_ID,ENTITY_TYPE,TITLE,CONTENT,STATUS,OWNED_BY_AGENT,VISIBILITY) "
               "VALUES('upload','KNOWLEDGE','Upload','Unreviewed','ACTIVE','owner','PRIVATE')");db.commit()
    with pytest.raises(ContinuityConflict):
        knowledge_api.set_access_policy('upload','PUBLIC_COMPANY','owner',reason='Bypass attempt')
    with pytest.raises(ContinuityConflict):
        knowledge_api.update_knowledge('upload',visibility='PUBLIC')
    assert knowledge_api.update_knowledge('upload',content='Edited private note')
    assert db.execute('SELECT COUNT(*) FROM CX_KNOWLEDGE_ACCESS_POLICIES').fetchone()[0]==0


def test_reviewed_native_body_cannot_be_mutated_in_place(candidate_db):
    from lib import knowledge_api
    db,source=candidate_db
    cid=candidates.create_candidate('owner',new_candidate(source,PROPOSALS[1]))['candidate_id']
    candidates.promote_candidate('agent',cid,approve(cid))
    entity=db.execute('SELECT NATIVE_ENTITY_ID FROM CX_CONTINUITY_ARTIFACT_REVS').fetchone()[0]
    with pytest.raises(ContinuityConflict):
        knowledge_api.update_knowledge(entity,content='Unreviewed replacement')
    with pytest.raises(ContinuityConflict):
        knowledge_api.delete_knowledge(entity)
    assert db.execute('SELECT CONTENT FROM ENTITIES').fetchone()[0]==PROPOSALS[1]['body']


@pytest.mark.parametrize('status,start,end',[
    ('ACTIVE','2000-01-01',None),('RETIRED','2000-01-01',None),
    ('ACTIVE','2999-01-01',None),('ACTIVE','2000-01-01','2001-01-01'),
])
def test_organization_sharing_requires_current_target_in_writer_scope(candidate_db,monkeypatch,status,start,end):
    from lib import knowledge_api,organization_api
    db,source=candidate_db
    cid=candidates.create_candidate('owner',new_candidate(source,PROPOSALS[1]))['candidate_id']
    candidates.promote_candidate('agent',cid,approve(cid))
    entity=db.execute('SELECT NATIVE_ENTITY_ID FROM CX_CONTINUITY_ARTIFACT_REVS').fetchone()[0]
    db.execute('INSERT INTO CX_ORGANIZATIONS VALUES(?,?,?,?)',('org',status,start,end));db.commit()
    if status=='ACTIVE' and start=='2000-01-01' and end is None:
        with monkeypatch.context() as patch:
            patch.setattr(organization_api,'_scope_clause',lambda *args:('1=0',{}))
            with pytest.raises(PermissionError,match='organization is unavailable'):
                knowledge_api.set_access_policy(entity,'ORGANIZATION_SUBTREE','owner',organization_id='org')
        assert knowledge_api.set_access_policy(entity,'ORGANIZATION_SUBTREE','owner',organization_id='org')['organization_id']=='org'
    else:
        with pytest.raises(PermissionError,match='organization is unavailable'):
            knowledge_api.set_access_policy(entity,'ORGANIZATION_SUBTREE','owner',organization_id='org')
        assert db.execute("SELECT SCOPE_TYPE FROM CX_KNOWLEDGE_ACCESS_POLICIES WHERE STATUS='ACTIVE'").fetchone()[0]=='PRINCIPAL_PRIVATE'
