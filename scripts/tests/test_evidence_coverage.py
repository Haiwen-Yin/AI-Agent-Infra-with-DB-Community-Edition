"""Arbitrary requested claims keep subject, scope, partial evidence and limits."""
import json

import pytest

from lib import answer_query,answer_evidence,answer_planning


def source(key,body,title='Boreal',**extra):
    return dict(entity_id=key,title=title,content=body,digest=key*64,**extra)


@pytest.mark.parametrize('question,subject,requirements',[
    ('Explain the retention limit and escalation owner for Boreal v3.2.1.','Boreal v3.2.1',('retention limit','escalation owner')),
    ('Boreal v3.2.1: retention limit; escalation owner','Boreal v3.2.1',('retention limit','escalation owner')),
    ('请说明川序 v5.0.3的知识入库流程和权限要求','川序 v5.0.3',('知识入库流程','权限要求')),
])
def test_explicit_claims_preserve_arbitrary_names_and_scope(question,subject,requirements):
    parsed=answer_query.interpret(question)
    assert parsed.subject==subject and parsed.requirements==requirements
    assert len(answer_planning._parts(question))==2
    for part in answer_planning._parts(question):
        assert parsed.qualifiers[0].value in part


def test_distinct_sources_can_cover_arbitrary_claims_without_each_repeating_the_whole_question():
    question='Explain the retention limit and escalation owner for Boreal v3.2.1.'
    rows=[source('a','Boreal v3.2.1 retention limit: 30 days, except legal holds.'),
          source('b','Boreal v3.2.1 escalation owner: the on-call Human administrator.')]
    result=answer_evidence.assess(question,rows)
    assert result['status']=='MATCHED' and result['evidence_decision']['coverage']=={
        'retention limit':['a'],'escalation owner':['b']}
    planned=answer_planning.prepare(question,'p',dict(mode='KNOWLEDGE_FIRST',disclosure_profiles=['p']),result)
    wire=json.loads(planned['messages'][-1]['content'])
    assert wire['evidence_requirements']==[
        dict(requirement='retention limit',source_citations=[1]),dict(requirement='escalation owner',source_citations=[2])]
    assert 'except legal holds' in wire['authorized_sources'][0]['content']
    assert wire['evidence_coverage_boundary']['method']=='CLAIM_LOCATION_NOT_FACT_VERIFICATION'


def test_unknown_claim_remains_missing_without_discarding_supported_facts():
    result=answer_evidence.assess('Boreal: retention limit; unknown_certification',[
        source('a','Boreal retention limit: 30 days.')])
    assert result['status']=='PARTIAL_MATCH' and result['missing_parts']==['unknown_certification']
    assert [item['entity_id'] for item in result['items']]==['a']


@pytest.mark.parametrize('row',[
    source('a','Boreal v3.2.10 retention limit: 30 days.'),
    source('a','Cedar v3.2.1 retention limit: 30 days.',title='Cedar'),
    source('a','Boreal v3.2.1 retention limit: 30 days.',valid_until='2000-01-01T00:00:00Z'),
    source('a','Boreal v3.2.1 unrelated text.',trusted=True,coverage={'retention limit':['a']}),
])
def test_wrong_subject_scope_expiry_and_untrusted_coverage_cannot_supply_claims(row):
    result=answer_evidence.assess('Explain the retention limit for Boreal v3.2.1.',[row])
    assert result['status']=='NO_MATCH' and result['items']==[]


def test_general_claim_conflict_keeps_both_sources_and_does_not_select_newest_or_highest_rank():
    rows=[source('a','Boreal v3.2.1 retention limit: 30 days.',retrieval_rank={'rank_score':0.99}),
          source('b','Boreal v3.2.1 retention limit: 60 days.',updated_at='2099-01-01')]
    result=answer_evidence.assess('Explain the retention limit for Boreal v3.2.1.',rows)
    assert result['status']=='AMBIGUOUS' and len(result['items'])==2
    assert result['evidence_decision']['contradictions']==[
        dict(attribute='retention limit',temporal_scope=[],source_ids=['a','b'])]
    assert result['evidence_decision']['rank_used_as_confidence'] is False


def test_recall_of_missing_sibling_cannot_restore_wrong_version_through_query_decomposition(monkeypatch):
    row=source('old','Boreal v3.2.10 retention limit: 30 days. escalation owner: admin.')
    monkeypatch.setattr(answer_planning.knowledge_grounding,'search',lambda *args,**kwargs:dict(items=[row]))
    result=answer_planning.retrieve('human','agent','Boreal v3.2.1: retention limit; escalation owner')
    assert result['status']=='NO_MATCH' and result['items']==[]


def test_relation_neighbor_cannot_supply_unrelated_claim_about_the_origin():
    origin=source('a','Boreal v3.2.1 platform guide.')
    neighbor=source('b','Cedar v3.2.1 retention limit: 60 days.',title='Cedar')
    link=dict(source_entity_id='a',target_entity_id='b',source_digest=origin['digest'],
              target_digest=neighbor['digest'],edge_id='edge',edge_digest='e'*64,edge_type='RELATED_TO')
    result=answer_evidence.assess('Boreal v3.2.1: related sources; retention limit',
                                  [origin,neighbor],relationships=[link])
    assert result['status']=='PARTIAL_MATCH'
    assert result['evidence_decision']['coverage']['related sources']==['a','b']
    assert result['evidence_decision']['coverage']['retention limit']==[]
    assert result['missing_parts']==['retention limit']
    # A direct statement about the requested subject remains eligible.
    direct=source('c','Boreal v3.2.1 retention limit: 30 days.')
    result=answer_evidence.assess('Boreal v3.2.1: related sources; retention limit',
                                  [origin,neighbor,direct],relationships=[link])
    assert result['status']=='MATCHED'
    assert result['evidence_decision']['coverage']['retention limit']==['c']


def test_complete_source_retains_a_late_claim_instead_of_silently_truncating():
    question='Explain the retention limit and escalation owner for Boreal'
    row=source('a','Boreal retention limit: 30 days. '+'x'*12000+' escalation owner: admin.')
    result=answer_evidence.assess(question,[row])
    prepared=answer_planning.prepare(question,'p',dict(mode='KNOWLEDGE_ONLY',disclosure_profiles=['p']),result)
    wire=json.loads(prepared['messages'][-1]['content'])
    assert wire['evidence_requirements'][1]['source_citations']==[1]
    assert wire['evidence_coverage_boundary']['status']=='MATCHED'
    assert wire['evidence_coverage_boundary']['missing_requirements']==[]
    assert wire['authorized_sources'][0]['content']==row['content']
