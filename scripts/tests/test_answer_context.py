"""Whole-source budgets retain late exceptions and atomic evidence groups."""
import json
from datetime import datetime, timezone

import pytest

from lib import answer_evidence, answer_planning,answer_context
from lib.continuity_state import ContinuityConflict


def item(key, content):
    return dict(entity_id=key, title='Boreal', content=content, digest=key*64)


def prepare(rows, *, model=True, budget=None, relationships=()):
    question='Boreal: retention limit; escalation owner'
    result=answer_evidence.assess(question, rows, relationships=relationships)
    result['relationships']=list(relationships)
    return answer_planning.prepare(question, 'p',
        dict(mode='KNOWLEDGE_ONLY', disclosure_profiles=['p'] if model else []),
        result, context_budget=budget)


@pytest.mark.parametrize('model', [True, False])
def test_late_exception_table_code_and_negation_survive_whole_reference(model):
    body=('Boreal retention limit: 30 days.\n\n'+'Long explanatory material. '*420+
          '\n| Condition | Limit |\n| legal hold | never delete |\n\n'
          '```sql\nSELECT 1;\n```\nDo not delete legal holds.\n'
          'Boreal escalation owner: the on-call Human.')
    planned=prepare([item('a',body)], model=model)
    if model:
        assert json.loads(planned['messages'][-1]['content'])['authorized_sources'][0]['content']==body
    else:
        assert body in planned['knowledge_reply']
    assert planned['context_selection']['representations'][0]['representation']=='COMPLETE'


def test_temporal_anchor_does_not_relabel_source_or_fill_unknown_event_time(monkeypatch):
    instant=datetime(2026,11,2,7,30,tzinfo=timezone.utc)
    class Clock:
        @staticmethod
        def now(zone):
            assert zone==timezone.utc
            return instant
    monkeypatch.setattr(answer_planning,'datetime',Clock)
    source=item('a','Boreal retention limit: 30 days; escalation owner: on-call Human. Event time is unknown.')
    source['source_context']=dict(intake=dict(decision_status='PROPOSED',
        effective_from='2026-11-02T05:09:05Z'),provenance=[])
    original=json.loads(json.dumps(source))
    planned=prepare([source])
    prompt=json.loads(planned['messages'][-1]['content'])
    anchor=datetime.fromisoformat(prompt['temporal_context']['assessment_time_utc'])
    submitted=prompt['authorized_sources'][0]
    assert anchor>datetime.fromisoformat(submitted['source_context']['intake']['effective_from'])
    assert submitted['source_context']==original['source_context']
    assert submitted['content']==original['content'] and source==original
    assert prompt['temporal_context']['meaning']=='CURRENT_OBSERVATION_NOT_EVENT_TIME_OR_POLICY_ADOPTION'


@pytest.mark.parametrize('model', [True, False])
def test_oversized_reference_is_omitted_with_boundary_and_later_small_source_survives(model):
    rows=[item('a','Boreal retention limit: 30 days. '+'条款 '*17000+'Do not delete legal holds.'),
          item('b','Boreal escalation owner: on-call Human.')]
    planned=prepare(rows, model=model)
    assert [row['entity_id'] for row in planned['citations']]==['b']
    assert planned['retrieval_status']=='PARTIAL_MATCH'
    assert planned['answer_metadata']['missing_parts_count']==1
    visible=str(planned['messages']) if model else planned['knowledge_reply']
    assert 'omitted' in visible and '30 days' not in visible
    assert planned['context_selection']['omitted_count']==1
    assert planned['context_selection']['budget']['conservative_total_units']<=32768


def test_conflict_group_is_not_reduced_to_a_false_single_conclusion():
    rows=[item('a','Boreal retention limit: 30 days.'),
          item('b','Boreal retention limit: 60 days. '+'x'*33000),
          item('c','Boreal escalation owner: on-call Human.')]
    planned=prepare(rows)
    assert [row['entity_id'] for row in planned['citations']]==['c']
    wire=json.loads(planned['messages'][-1]['content'])
    assert wire['evidence_requirements'][0]['source_citations']==[]
    assert planned['context_selection']['omitted_count']==2


def test_relationship_endpoints_cannot_be_orphaned_by_budget_selection():
    origin=item('a','Boreal retention limit: 30 days. '+'x'*33000)
    target=item('b','Boreal escalation owner: on-call Human.')
    link=dict(source_entity_id='a',target_entity_id='b',source_digest=origin['digest'],
        target_digest=target['digest'],edge_id='edge',edge_digest='e'*64,edge_type='RELATED_TO')
    planned=prepare([origin,target], relationships=[link])
    assert planned['citations']==[] and planned['messages']==[]
    assert planned['context_selection']['omitted_count']==2


def test_question_and_instruction_overhead_are_bounded_before_any_dispatch():
    with pytest.raises(ContinuityConflict, match='budget'):
        prepare([item('a','Boreal retention limit: 30 days.')],budget={'token_budget':100})


def test_receipt_is_explicit_about_local_count_and_not_provider_usage():
    planned=prepare([item('a','Boreal retention limit: 30 days. escalation owner: on-call Human.')])
    receipt=planned['context_selection']
    assert receipt['stage']=='PREPARED_ANSWER_MESSAGES'
    assert receipt['scope']=='NOT_FINAL_PROVIDER_PAYLOAD_OR_REPORTED_USAGE'
    assert receipt['count_method']=='UTF8_UPPER_BOUND'
    assert receipt['ranking_generation_calls']==0


def test_budget_gaps_combine_with_prior_query_gaps_in_metadata_and_supplement_scope():
    question='Boreal: retention limit; escalation owner; audit contact'
    rows=[item('a','Boreal retention limit: 30 days. '+'x'*33000),
          item('b','Boreal escalation owner: on-call Human.')]
    result=answer_evidence.assess(question,rows)
    result['_query_missing_parts']=['audit contact']
    planned=answer_planning.prepare(question,'p',dict(mode='KNOWLEDGE_FIRST',
        allow_model_supplement='Y',disclosure_profiles=['p']),result)
    assert planned['answer_metadata']['missing_parts_count']==2
    assert planned['answer_source']=='MIXED_SOURCES'
    assert planned['answer_source_scope']['uncovered_question_parts']==[1,3]


def test_final_budget_scopes_reset_and_cannot_conflict_with_actual_output_limit():
    planned=prepare([item('a','Boreal retention limit: 30 days.')])
    payload=dict(model='demo',messages=planned['messages'],stream=False)
    with answer_context.dispatch_budget(planned['context_selection']):
        bounded,receipt=answer_context.final_payload(payload)
        assert bounded['max_tokens']==4096
        assert receipt['stage']=='FINAL_PROVIDER_JSON'
        assert receipt['output_reserve']==4096
        with answer_context.dispatch_budget(None):
            assert answer_context.final_payload(payload)==(payload,None)
        with pytest.raises(ContinuityConflict) as denied:
            answer_context.final_payload(dict(payload,max_tokens=8192))
        assert denied.value.model_not_dispatched
    assert answer_context.final_payload(payload)==(payload,None)


def test_final_payload_measures_all_actual_transport_fields_before_sending():
    planned=prepare([item('a','Boreal retention limit: 30 days.')])
    with answer_context.dispatch_budget(planned['context_selection']):
        with pytest.raises(ContinuityConflict) as denied:
            answer_context.final_payload(dict(model='demo',messages=planned['messages'],
                stream=True,stream_options={'include_usage':True},tools=[{'description':'x'*40000}]))
        assert denied.value.model_not_dispatched
        assert denied.value.code=='PROVIDER_INPUT_EXCEEDS_TOKEN_BUDGET'


@pytest.mark.parametrize('model',[True,False])
def test_noncurrent_original_applicability_is_kept_with_its_whole_reference(model):
    source=item('a','Boreal retention limit: 30 days; escalation owner: on-call Human.')
    source['source_context']=dict(candidate_digest='f'*64,
        intake=dict(decision_status='HISTORICAL',applicable_version='3.2.1',applicable_product='Boreal',
            effective_from='2020-01-01T00:00:00Z',effective_until='2021-01-01T00:00:00Z'),
        provenance=[dict(origin=dict(locator='docs/old.md',context_note='Historical procedure; retain its exception.'))])
    planned=prepare([source],model=model)
    if model:
        submitted=json.loads(planned['messages'][-1]['content'])['authorized_sources'][0]
        assert submitted['source_context']==source['source_context']
        assert 'none establishes current policy' in planned['messages'][0]['content']
    else:
        assert 'HISTORICAL' in planned['knowledge_reply'] and '3.2.1' in planned['knowledge_reply']
    assert planned['context_selection']['ranking_generation_calls']==0
