"""Expression safeguards cannot promote retrieval or source flags to certainty."""
import json

import pytest

from lib import answer_expression as expression, answer_planning as planning


def prepare(items, **retrieval):
    return planning.prepare('Describe the incident evidence and its confidence.', 'p',
                            dict(mode='KNOWLEDGE_ONLY', disclosure_profiles=['p']),
                            dict(status='MATCHED', items=items, **retrieval))


def test_final_reference_identity_unknown_and_proposed_scope_survive():
    row = dict(entity_id='authorized', revision_id='revision-7', digest='a'*64,
               title='Incident report', content='Local draft. Root cause unknown; action proposed.',
               score=.999, confidence=1, probability_calibration='VERIFIED',
               source_context=dict(intake=dict(decision_status='PROPOSED', effective_from=None)))
    plan = prepare([row])
    value = json.loads(plan['messages'][-1]['content'])['evidence_expression_contract']
    assert value['references'] == [dict(citation=1, entity_id='authorized', digest='a'*64,
                                       revision_id='revision-7', origin='AUTHORIZED_REFERENCE_NOT_FACT_CERTIFICATION',
                                       declared_decision_status='PROPOSED', effective_from=None, effective_until=None,
                                       applicability_at_assessment='UNKNOWN',
                                       time_meaning='DECLARED_APPLICABILITY_NOT_EVENT_OR_COLLECTION_TIME')]
    assert value['probability_calibration'] == 'UNAVAILABLE'
    assert value['answer_correctness_probability'] is None
    assert not value['rank_is_confidence']
    assert 'Never turn a null into zero' in plan['messages'][0]['content']
    assert 'authorized' not in str(plan['answer_metadata'])


@pytest.mark.parametrize('start,end,expected', [
    ('2026-11-10T15:20:07Z', None, 'WITHIN_DECLARED_INTERVAL'),
    ('2026-11-10T23:20:07+08:00', None, 'WITHIN_DECLARED_INTERVAL'),
    ('2026-11-10T16:00:01Z', None, 'NOT_YET_EFFECTIVE'),
    ('2026-11-10T16:00:00Z', None, 'WITHIN_DECLARED_INTERVAL'),
    ('2026-11-10T15:00:00Z', '2026-11-10T16:00:00Z', 'EXPIRED'),
    (None, None, 'UNKNOWN'),
    ('2026-11-10T15:00:00', None, 'UNKNOWN'),
    ('invalid', None, 'UNKNOWN'),
    ('2026-11-10T17:00:00Z', '2026-11-10T16:00:00Z', 'UNKNOWN'),
])
def test_same_day_timezone_and_interval_edges_do_not_turn_current_evidence_into_future(start,end,expected):
    intake=dict(effective_from=start,effective_until=end)
    assert expression.applicability(intake,'2026-11-10T16:00:00+00:00')==expected
    assert expression.applicability(intake,None)=='UNKNOWN'


@pytest.mark.parametrize('reply', [
    'I am 95% confident that this answer is correct.',
    'My confidence is 99 percent.',
    '本回答置信度为95%。', '我的结论可信度：98％。',
    'Confidence: 99%', '**置信度**：90%',
])
def test_unsupported_self_probability_is_withheld_not_silently_rewritten(reply):
    plan = prepare([dict(entity_id='a', digest='a'*64, content='Loss is unknown.')])
    result = planning.render_reply(reply, plan)
    assert 'was withheld' in result
    assert reply not in result
    assert plan['answer_expression_contract']['publication_screening'] == 'BOUNDED_RULES_NOT_SEMANTIC_VERIFICATION'


@pytest.mark.parametrize('reply', [
    'The source reports a 95% confidence interval [1].',
    '来源记载的置信区间为95% [1]，损失未知，建议尚未批准。',
    'Source confidence is 90% [1]; this is not a probability that the answer is correct.',
    'I cannot give a calibrated probability for this answer.',
    '10% of requests failed in the source window [1].', '',
])
def test_source_quantities_and_unknowns_are_preserved_without_claiming_verification(reply):
    plan = prepare([dict(entity_id='a', digest='a'*64, content=reply)])
    assert planning.render_reply(reply, plan) == reply
    assert plan['answer_metadata']['probability_calibration'] == 'UNAVAILABLE'


def test_original_extracts_and_historical_noncontract_answers_are_not_screened():
    raw = 'My confidence is 99%.'
    assert expression.screen(raw, {}) == raw
    assert expression.screen(raw, dict(answer_expression_contract=dict(revision=expression.REVISION),
                                       knowledge_reply=raw)) == raw


@pytest.mark.parametrize('body,reply', [
    ('变更待审批，没有执行或验收记录。', '扩容尚未完成，因为变更待审批 [1]。'),
    ('No execution or verification receipt exists.', 'The proposed action has not succeeded [1].'),
])
def test_missing_receipts_cannot_publish_a_categorical_negative_action_outcome(body, reply):
    plan=prepare([dict(entity_id='a',digest='a'*64,content=body)])
    result=planning.render_reply(reply,plan)
    assert reply not in result and 'was withheld' in result
    assert '> '+body in result
    assert 'cannot establish success, failure or non-execution' in result


@pytest.mark.parametrize('body,reply', [
    ('没有执行或验收记录。', '没有完成证据，实际结果待核实 [1]。'),
    ('No execution or verification receipt exists.', 'The outcome remains unverified [1].'),
    ('执行已失败，返回错误代码 E42。', '执行未成功，返回 E42 [1]。'),
    ('No execution or verification receipt exists.', 'Code example: `has not succeeded`.'),
    ('No execution or verification receipt exists.', 'The input sample is 3/10 [1].'),
])
def test_outcome_guard_keeps_unknowns_recorded_failures_code_and_other_quantities(body,reply):
    plan=prepare([dict(entity_id='a',digest='a'*64,content=body)])
    assert planning.render_reply(reply,plan)==reply


def test_no_match_generation_receives_record_semantics_without_hidden_record_state():
    plan = planning.prepare('Explain the lifecycle of a stored information record.', 'p',
                            dict(mode='KNOWLEDGE_FIRST', allow_model_supplement=True,
                                 disclosure_profiles=['p']),
                            dict(status='NO_MATCH', items=[]))
    assert plan['answer_source'] == 'MODEL_SUPPLEMENT'
    assert plan['citations'] == []
    instruction = plan['messages'][0]['content']
    assert 'not proof that a record never existed' in instruction
    assert 'across sessions' in instruction
    assert 'not human recollections or work permits' in instruction
    assert 'without claiming to have observed' in instruction
    assert 'establishing falsehood, physical deletion' in instruction
    assert 'Unknown event time cannot be inferred' in instruction
    assert 'itself archive or delete' in instruction
    assert 'does not establish that a previous state is still valid' in instruction
    assert 'proves greater accuracy or supersession' in instruction
    assert 'Check one relevant ordinary counterexample' not in instruction
    assert plan['messages'][1]['content'] == 'Explain the lifecycle of a stored information record.'


def test_no_match_without_supplement_remains_a_deterministic_insufficiency():
    plan = planning.prepare('Explain the lifecycle of a stored information record.', 'p',
                            dict(mode='KNOWLEDGE_ONLY', allow_model_supplement=False),
                            dict(status='NO_MATCH', items=[]))
    assert plan['answer_source'] == 'INSUFFICIENT_KNOWLEDGE'
    assert plan['messages'] == []
    assert 'Insufficient knowledge accessible' in plan['knowledge_reply']


def test_budget_binds_only_retained_references_and_keeps_omission_unknown():
    rows = [dict(entity_id='large', digest='a'*64, content='Boreal retention limit: 30 days. '+'unrelated '*50000),
            dict(entity_id='small', digest='b'*64, content='Boreal escalation owner: on-call Human.')]
    plan = planning.prepare('Boreal: retention limit; escalation owner', 'p',
                           dict(mode='KNOWLEDGE_ONLY', disclosure_profiles=['p']),
                           dict(status='MATCHED', items=rows))
    contract = plan['answer_expression_contract']
    assert [item['entity_id'] for item in contract['references']] == ['small']
    assert contract['omitted_reference_count'] == 1
    assert contract['coverage_meaning'] == 'LOCATION_OR_UNASSESSED_NOT_FACT_VERIFICATION'


@pytest.mark.parametrize('marker', ['[3]', '[0]', '[1, 3]', '[1-3]', '[2-1]', '[3](#ref-3)'])
def test_nonexistent_reference_withholds_generation_and_preserves_exact_window(marker):
    plan = prepare([dict(entity_id='a', digest='a'*64, content='North is one source claim.'),
                    dict(entity_id='b', digest='b'*64, content='South is the conflicting claim.')])
    raw = 'The contradiction has been resolved ' + marker + '.'
    output = planning.render_reply(raw, plan)
    assert 'generated answer was withheld' in output
    assert raw not in output
    assert '[1]\n> North is one source claim.' in output
    assert '[2]\n> South is the conflicting claim.' in output
    assert marker not in output
    assert expression.invalid_references(raw, plan['answer_expression_contract']) == [marker.split('(')[0]]


@pytest.mark.parametrize('raw', ['Claims disagree [1], [2].', 'Claims disagree [1,2].',
                               'Claims disagree [1–2].', 'Use array `[3]`.',
                               'Example:\n```python\nvalues = [3]\n```', 'Year [2026].', r'Escaped \[3\].'])
def test_reference_guard_keeps_valid_markers_and_literal_code(raw):
    plan = prepare([dict(entity_id='a', digest='a'*64, content='North.'),
                    dict(entity_id='b', digest='b'*64, content='South.')])
    assert planning.render_reply(raw, plan) == raw


def test_no_source_reference_failure_never_invents_an_extract_or_retries():
    plan = planning.prepare('Explain a generic topic.', 'p',
                            dict(mode='KNOWLEDGE_FIRST', allow_model_supplement=True),
                            dict(status='NO_MATCH', items=[]))
    output = planning.render_reply('The answer is certain [1].', plan)
    assert 'generated answer was withheld' in output
    assert '> ' not in output
    assert plan['citations'] == []


def test_partial_semantic_review_does_not_demand_invented_advice_or_timing_proxies():
    row = dict(entity_id='a', digest='a'*64, content='Event time unknown. Observed at 08:58, ingested at 09:00.')
    plan = planning.prepare('When did the alert happen?', 'p',
                            dict(mode='KNOWLEDGE_ONLY', disclosure_profiles=['p']),
                            dict(items=[row], status='PARTIAL_MATCH', missing_parts=['SEMANTIC_EVIDENCE_REVIEW'],
                                 evidence_decision=dict(semantic_review=dict(status='REQUIRED', candidates=[]))))
    instruction = plan['messages'][0]['content']
    assert 'four concise sentences' in instruction
    assert 'Do not add an advice section' in instruction
    assert 'invent a substitute, a time range or a likely cause' in instruction
    assert 'Give an evidence-backed judgment in this order' not in instruction
