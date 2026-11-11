"""Natural questions retain uncertain authorized references without claiming truth."""
import json

import pytest

from lib import answer_evidence as evidence, answer_planning as planning


QUESTION = '配额不足时，能否删除等待队列以继续执行？'


@pytest.mark.parametrize('question', [
    'INC-2027-0402 每月费用是多少？',
    'INC-2027-0402 当前审批超时是多久？',
    'INC-2027-0402 故障从 10:01 还是 10:04 开始？',
    'INC-2027-0402 Does this value mean a calibrated probability?',
    'INC-2027-0402 Has the recovery already succeeded?',
])
def test_natural_question_after_record_locator_retains_unassessed_source(question):
    row = reference(body='INC-2027-0402\n仅有历史观察，未验证当前结论。')
    result = evidence.assess_for_answer(question, [row])
    assert result['items'] == [row] and result['status'] == 'PARTIAL_MATCH'
    assert result['evidence_decision']['semantic_review']['status'] == 'REQUIRED'


def test_decomposition_carries_the_explicit_record_constraint_to_each_part():
    question = 'INC-2027-0402 当前值是多少？同时说明此前的值。'
    assert planning._parts(question) == ['INC-2027-0402 当前值是多少？', 'inc-2027-0402 说明此前的值。']


def test_literal_record_clause_survives_an_unrelated_second_question(monkeypatch):
    row = reference(body='INC-2027-0402 routing uses the authorized route label jade-501.')
    other = reference('b', 'Quantum tunneling permits barrier penetration.')
    monkeypatch.setattr(planning.knowledge_grounding, 'search', lambda *_a, **_k: {'items': [row, other]})
    question = 'INC-2027-0402 routing and explain quantum tunneling briefly.'
    result = planning.retrieve('reader', 'agent', question)
    assert result['items'] == [row] and result['status'] == 'PARTIAL_MATCH'
    assert result['missing_parts'] == ['inc-2027-0402 explain quantum tunneling briefly.']
    plan = planning.prepare(question, 'profile', dict(mode='KNOWLEDGE_FIRST',
        allow_model_supplement='Y', disclosure_profiles=['profile']), result)
    assert plan['answer_source'] == 'MIXED_SOURCES'
    assert plan['answer_source_scope'] == {'uncovered_question_parts': [2]}
    assert [item['entity_id'] for item in plan['citations']] == ['a']


@pytest.mark.parametrize('body,extra', [
    ('INC-2027-0403 routing uses jade-501.', {}),
    ('INC-2027-0402 an unrelated topic.', {}),
    ('INC-2027-0402 routing uses jade-501.', {'valid_until': '2000-01-01T00:00:00Z'}),
    ('INC-2027-0402 v3.2.0 routing uses jade-501.', {}),
])
def test_partial_record_recovery_keeps_locator_claim_validity_and_version(monkeypatch, body, extra):
    row = reference(body=body, **extra)
    monkeypatch.setattr(planning.knowledge_grounding, 'search', lambda *_a, **_k: {'items': [row]})
    question = 'INC-2027-0402 routing and explain quantum tunneling briefly.'
    if 'v3.2.0' in body:
        question = question.replace(' routing', ' v3.2.1 routing')
    result = planning.retrieve('reader', 'agent', question)
    assert result['items'] == [] and result['status'] == 'NO_MATCH'


def reference(key='a', body='容量耗尽后暂停调度。保持等待队列，先由值班人员核实可用容量。', **extra):
    return dict(entity_id=key, title='调度操作指南', content=body, digest=key*64, **extra)


def test_paraphrased_reference_is_unassessed_and_never_turns_rank_into_support():
    row = reference(retrieval_rank={'rank_score': 0.99}, trusted=True, coverage={'all': True})
    strict = evidence.assess(QUESTION, [row])
    assert strict['status'] == 'NO_MATCH'
    result = evidence.assess_for_answer(QUESTION, [row])
    assert result['status'] == 'PARTIAL_MATCH' and result['items'] == [row]
    decision = result['evidence_decision']
    assert decision['coverage'] == strict['evidence_decision']['coverage']
    assert decision['semantic_review']['candidates'][0]['coverage'] == 'UNASSESSED_NOT_SUPPORTED'
    assert decision['rank_used_as_confidence'] is False
    assert 'SEMANTIC_EVIDENCE_REVIEW' in result['missing_parts']


def test_natural_review_keeps_an_explicit_record_locator_as_a_hard_constraint(monkeypatch):
    good = reference('a', 'INC-2027-0402\n事件时间未知，首次观察在 08:58。')
    unrelated = reference('b', '事故响应需要检查当前任务。')
    question = 'INC-2027-0402 告警发生在什么时候？'
    result = evidence.assess_for_answer(question, [unrelated, good])
    assert result['items'] == [good]
    assert {'entity_id': 'b', 'reason': 'EXPLICIT_LOCATOR_UNSUPPORTED'} in result['evidence_decision']['rejected_sources']
    monkeypatch.setattr(planning.knowledge_grounding, 'search', lambda *_a, **_k: {'items': [unrelated]})
    denied = planning.retrieve('reader', 'agent', question+' 同时说明如何处置。')
    assert denied['status'] == 'NO_MATCH' and denied['items'] == []


@pytest.mark.parametrize('question', [
    '甲骨文公司总部在哪里？',
    'How much revenue does Oracle Corporation earn?',
    'Boreal v3.2.1: retention limit; escalation owner',
    'Using the documentation, describe its identity and version: Boreal',
    'Using classified documentation, explain its identity and version: Boreal',
])
def test_structured_fact_and_failed_document_frames_keep_strict_contract(question):
    rows = [reference()]
    assert evidence.assess_for_answer(question, rows) == evidence.assess(question, rows)


@pytest.mark.parametrize('row', [
    reference(valid_until='2000-01-01T00:00:00Z'),
    reference(body='Release v3.2.10. Pause scheduling.'),
    reference(body='Version v3.2.1. Pause scheduling.', source_context={'intake': {'applicable_version': '3.2.10'}}),
])
def test_semantic_review_cannot_restore_expired_or_wrong_version_sources(row):
    result = evidence.assess_for_answer('How can I safely pause scheduling in v3.2.1?', [row])
    assert result['status'] == 'NO_MATCH' and result['items'] == []


def test_explicit_reviewed_version_can_apply_without_inventing_a_literal_in_body():
    row = reference(source_context={'intake': {'applicable_version': '3.2.1'}})
    result = evidence.assess_for_answer('How can I safely pause scheduling in v3.2.1?', [row])
    assert result['status'] == 'PARTIAL_MATCH' and result['items'] == [row]
    assert result['evidence_decision']['semantic_review']['status'] == 'REQUIRED'
    assert 'v3.2.1' not in row['content']


def test_unknown_date_is_not_supplied_by_a_version_declaration():
    row = reference(source_context={'intake': {'applicable_version': '3.2.1'}})
    result = evidence.assess_for_answer('How can I pause scheduling in v3.2.1 on 2027-04-12?', [row])
    assert result['items'] == []


def test_retrieval_preparation_retains_whole_body_and_disables_general_gap_filling(monkeypatch):
    row = reference()
    monkeypatch.setattr(planning.knowledge_grounding, 'search', lambda *_a, **_k: {'items': [row]})
    result = planning.retrieve('reader', 'agent', QUESTION)
    plan = planning.prepare(QUESTION, 'profile', dict(mode='KNOWLEDGE_FIRST',
        allow_model_supplement='Y', disclosure_profiles=['profile']), result)
    assert plan['answer_source'] == 'KNOWLEDGE_GROUNDED'
    wire = json.loads(plan['messages'][-1]['content'])
    assert wire['question'] == QUESTION
    assert wire['authorized_sources'][0]['content'] == row['content']
    assert wire['semantic_evidence_review']['coverage'] == 'UNASSESSED_NOT_SUPPORTED'
    assert wire['semantic_evidence_review']['unassessed_source_citations'] == [1]
    assert 'do not fill enterprise gaps from general knowledge' in plan['messages'][0]['content']
    assert 'question_parts' not in wire
    assert 'semantic_evidence_review' not in plan['answer_metadata']


def test_bounded_selection_does_not_restore_omitted_reference_or_stale_review_list():
    rows = [reference(body='大文档 '*20000), reference('b')]
    result = evidence.assess_for_answer(QUESTION, rows)
    plan = planning.prepare(QUESTION, 'profile', dict(mode='KNOWLEDGE_ONLY', disclosure_profiles=['profile']), result)
    assert [item['entity_id'] for item in plan['citations']] == ['b']
    wire = json.loads(plan['messages'][-1]['content'])
    assert wire['semantic_evidence_review']['unassessed_source_citations'] == [1]
    assert wire['authorized_sources'][0]['content'] == rows[1]['content']
    assert plan['context_selection']['omitted_count'] == 1


def test_no_candidates_still_returns_no_match_without_synthetic_reference():
    result = evidence.assess_for_answer(QUESTION, [])
    assert result['status'] == 'NO_MATCH' and result['items'] == []
    assert 'semantic_review' not in result['evidence_decision']


def test_partial_literal_match_does_not_publish_unassessed_clauses_as_model_supplements():
    question='同一产品版本的内置手册来源修正后，怎样更新并保留历史和用户补充？'
    row=reference(body='同一产品版本的来源文档修正后，生成新快照，原快照及其摘要保持不变。用户补充保留原样。')
    strict=evidence.assess(question,[row])
    assert strict['items']==[row] and strict['status']=='PARTIAL_MATCH'
    assert strict['missing_parts'] and any(strict['evidence_decision']['coverage'].values())
    result=evidence.assess_for_answer(question,[row])
    assert result['evidence_decision']['coverage']==strict['evidence_decision']['coverage']
    assert result['evidence_decision']['semantic_review']['candidates'][0]['entity_id']==row['entity_id']
    for disclosed in (True,False):
        plan=planning.prepare(question,'profile',dict(mode='KNOWLEDGE_FIRST',allow_model_supplement='Y',
            disclosure_profiles=['profile'] if disclosed else []),result)
        assert plan['answer_source']!='MIXED_SOURCES' and not plan['answer_source_scope']
        if disclosed:
            wire=json.loads(plan['messages'][-1]['content'])
            assert wire['semantic_evidence_review']['unassessed_source_citations']==[1]
            assert wire['evidence_coverage_boundary']['semantic_coverage']=='UNASSESSED_NOT_SUPPORTED'
            assert wire['authorized_sources'][0]['content']==row['content']
        else:
            assert 'Support for each part' in plan['knowledge_reply']
        assert planning.render_reply('source-based answer',plan)=='source-based answer'
