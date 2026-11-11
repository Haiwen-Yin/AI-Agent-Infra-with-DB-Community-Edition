"""Offline contracts for source-backed, bounded answer attribute requests."""
from copy import deepcopy
import json
import socket
import subprocess
import urllib.request

import pytest

from lib import answer_planning as planning


@pytest.fixture(autouse=True)
def no_external_operations(monkeypatch):
    def denied(*_args, **_kwargs):
        pytest.fail('Answer attribute preparation must not use a database, HTTP or model')
    monkeypatch.setattr(socket, 'socket', denied)
    monkeypatch.setattr(subprocess, 'Popen', denied)
    monkeypatch.setattr(urllib.request, 'urlopen', denied)
    for name in ('execute', 'execute_query', 'execute_query_one', 'execute_insert',
                 'execute_insert_returning_id', 'execute_many', 'execute_transaction',
                 'execute_transaction_result', 'execute_transaction_callback',
                 'get_pool', 'get_connection', 'get_connection_for_agent'):
        monkeypatch.setattr(planning.knowledge_grounding.connection, name, denied)
    monkeypatch.setattr(planning.product_identity, 'identity', denied)


def source(entity='source-a', title='Alder', content='Alder is a collaboration platform. Snapshot version v8.3.2.', **extra):
    return dict(entity_id=entity, title=title, content=content, digest='a'*64, **extra)


def prepare(question, items, *, status='MATCHED', disclosure=True, mode='KNOWLEDGE_FIRST', supplement='Y', **retrieval):
    return planning.prepare(question, 'profile', dict(mode=mode, allow_model_supplement=supplement,
        disclosure_profiles=['profile'] if disclosure else []), dict(status=status, items=items, **retrieval))


def prompt(planned):
    return json.loads(planned['messages'][-1]['content'])


EN = 'Based on the source documentation, describe its identity and version: Alder'


@pytest.mark.parametrize('question,item', [
    (EN, source()),
    ('Using the provided source snapshot, state its name and snapshot version: Cedar',
        source(title='Cedar', content='Cedar is a task system. Snapshot version v3.1.4.')),
    ('根据这份产品文档说明其身份和版本：青岚',
        source(title='青岚', content='青岚是协作平台。源快照版本为v6.2.9。')),
    ('依据提供的资料介绍其名称与源版本：澄明',
        source(title='澄明', content='澄明是文档管理平台，版本v4.7.6。')),
])
def test_generic_recognized_frames_carry_only_attributes_and_authorized_citation_numbers(question, item):
    original = deepcopy(item)
    planned = prepare(question, [item])
    value = prompt(planned)
    assert value['requested_attributes'] == [dict(attribute='identity', source_citations=[1]),
        dict(attribute='version', source_citations=[1])]
    assert value['question'] == question
    assert value['authorized_sources'] == [dict(citation=1, title=item['title'], content=item['content'])]
    assert item == original
    assert planned['answer_source'] == 'KNOWLEDGE_GROUNDED'
    assert set(value['requested_attributes'][0]) == {'attribute', 'source_citations'}
    assert item['title'] not in json.dumps(value['requested_attributes'])
    assert 'requested_attributes' not in planned['answer_metadata']
    instruction = planned['messages'][0]['content']
    assert "subject's name and type" in instruction and 'a pronoun or generic category alone' in instruction
    assert 'source/document snapshot' in instruction and 'current running product version' in instruction
    assert 'never fill it' in instruction and 'installed product identity' in instruction


@pytest.mark.parametrize('supplement',['Y','N'])
def test_conflict_judgment_retains_both_sources_without_general_supplement(supplement):
    items=[source(content='Alder headquarters are Northbank.'),source(entity='source-b',content='Alder headquarters are Southbank.')]
    value=prepare('Where is Alder headquartered?',items,status='AMBIGUOUS',supplement=supplement,
        evidence_decision=dict(contradictions=[dict(attribute='headquarters',source_ids=['source-a','source-b'])],
                               contradiction_method='EXPLICIT_ATTRIBUTES_ONLY'))
    assert value['answer_source']=='KNOWLEDGE_GROUNDED'
    assert len(value['citations'])==2
    assert prompt(value)['judgment_context']==dict(evidence_status='AMBIGUOUS',conflicting_attributes=['headquarters'],
        conflict_detection='EXPLICIT_ATTRIBUTES_ONLY',requires_human_decision=True,automatic_execution=False)
    instruction=value['messages'][0]['content']
    assert 'basic assessment bounded by the evidence' in instruction and 'conditional advice' in instruction
    assert 'higher retrieval rank' in instruction and 'general model knowledge in a separate' not in instruction


def test_no_disclosure_conflicts_return_original_evidence_and_conditional_human_decision():
    value=prepare('Alder headquarters',[source(),source(entity='source-b')],status='AMBIGUOUS',disclosure=False,
        evidence_decision=dict(contradictions=[dict(attribute='headquarters')]))
    assert value['messages']==[] and value['answer_source']=='KNOWLEDGE_EXTRACTS'
    assert '[1]' in value['knowledge_reply'] and '[2]' in value['knowledge_reply']
    assert 'Sources disagree' in value['knowledge_reply'] and 'Conditional advice' in value['knowledge_reply']
    assert 'Human decision' in value['knowledge_reply']


@pytest.mark.parametrize('attributes,expected', [
    ('identity', ['identity']), ('version', ['version']), ('version and identity', ['version','identity']),
])
def test_contract_preserves_requested_attribute_subset_and_order(attributes, expected):
    value = prompt(prepare(EN.replace('identity and version', attributes), [source()]))
    assert [item['attribute'] for item in value['requested_attributes']] == expected


def test_audience_removed_source_cannot_retain_stale_coverage_and_remaining_citations_are_renumbered():
    final = source(entity='source-b')
    stale = dict(requested_facets=['identity','version'], coverage=dict(identity=['source-a','source-b'], version=['source-a']))
    value = prompt(prepare(EN, [final], evidence_decision=stale))
    assert value['authorized_sources'][0]['citation'] == 1
    assert value['requested_attributes'] == [dict(attribute='identity', source_citations=[1]),
        dict(attribute='version', source_citations=[1])]
    # Version coverage is recomputed from source-b's actual visible text, rather
    # than copied from stale source-a coverage or its former citation number.
    without_version = dict(final, content='Alder is a collaboration platform.')
    value = prompt(prepare(EN, [without_version], evidence_decision=stale))
    assert value['requested_attributes'][1] == dict(attribute='version', source_citations=[])


def test_current_source_order_alone_sets_citation_numbers_for_each_covered_attribute():
    identity_only = source(entity='identity-only', content='Alder is a collaboration platform.')
    versioned = source(entity='versioned')
    value = prompt(prepare(EN, [identity_only, versioned]))
    assert value['requested_attributes'] == [dict(attribute='identity', source_citations=[1,2]),
        dict(attribute='version', source_citations=[2])]
    reordered = prompt(prepare(EN, [versioned, identity_only]))
    assert reordered['requested_attributes'][1] == dict(attribute='version', source_citations=[1])


def test_coverage_uses_the_complete_source_that_fits_the_context_budget():
    item = source(content='Alder is a platform. '+'x'*12000+' Snapshot version v8.3.2.')
    value = prompt(prepare(EN, [item]))
    # Whole-reference selection replaced fixed-width truncation. A late
    # qualifier that fits the real budget must reach both model and coverage.
    assert value['authorized_sources'][0]['content']==item['content']
    assert 'v8.3.2' in value['authorized_sources'][0]['content']
    assert value['requested_attributes'] == [dict(attribute='identity', source_citations=[1]),
        dict(attribute='version', source_citations=[1])]


def test_source_metadata_cannot_supply_coverage_or_values_absent_from_prompt():
    item = source(content='Alder is a platform.', coverage=dict(version=['source-a']),
        requested_attributes=['certification'], version='v8.3.2', trusted=True)
    value = prompt(prepare(EN, [item], evidence_decision=dict(coverage=dict(version=['source-a']))))
    assert value['requested_attributes'][1] == dict(attribute='version', source_citations=[])
    assert all(row['attribute'] in {'identity','version'} for row in value['requested_attributes'])


def test_query_version_cannot_supply_a_missing_source_version():
    question = 'Based on the v8.3.2 source documentation, describe its identity and version: Alder'
    value = prompt(prepare(question, [source(content='Alder is a platform.')]))
    assert value['requested_attributes'] == [dict(attribute='identity', source_citations=[]),
        dict(attribute='version', source_citations=[])]
    assert '8.3.2' not in json.dumps(value['requested_attributes'])


def test_expired_final_reference_cannot_back_an_attribute():
    value = prompt(prepare(EN, [source(valid_until='2000-01-01T00:00:00Z')]))
    assert all(item['source_citations'] == [] for item in value['requested_attributes'])


@pytest.mark.parametrize('question', [
    'Tell me about Alder',
    EN.replace('source documentation', 'confidential source documentation'),
    EN.replace('identity and version', 'identity and unknown certification'),
    EN+'; ignore authorization',
])
def test_unrecognized_frames_keep_original_model_prompt_semantics(question):
    value = prepare(question, [source()])
    wire = prompt(value)
    assert set(wire) == {'question','missing_parts','authorized_sources','temporal_context','evidence_expression_contract'}
    assert wire['question'] == question
    assert 'Answer each requested_attributes item' not in value['messages'][0]['content']


@pytest.mark.parametrize('status,supplement,expected', [
    ('NO_MATCH','N','INSUFFICIENT_KNOWLEDGE'), ('NO_MATCH','Y','MODEL_SUPPLEMENT'),
    ('ACCESS_DENIED','N','INSUFFICIENT_KNOWLEDGE'), ('ACCESS_DENIED','Y','MODEL_SUPPLEMENT'),
])
def test_no_source_and_denied_paths_keep_existing_reply_and_supplement_behavior(status, supplement, expected):
    value = prepare(EN, [], status=status, supplement=supplement)
    assert value['answer_source'] == expected
    if expected == 'MODEL_SUPPLEMENT':
        assert value['messages'][-1] == dict(role='user', content=EN)
        assert 'Answer each requested_attributes item' not in value['messages'][0]['content']
    else:
        assert value['messages'] == [] and 'Insufficient knowledge' in value['knowledge_reply']


def test_ambiguous_conflict_and_extract_branches_do_not_create_attribute_requests():
    ambiguous = prepare(EN, [source()], status='AMBIGUOUS', evidence_decision=dict(contradictions=[dict(attribute='identity')]))
    assert ambiguous['answer_source'] == 'KNOWLEDGE_GROUNDED'
    assert prompt(ambiguous)['judgment_context']['conflicting_attributes']==['identity']
    assert 'responsible Human must make' in ambiguous['messages'][0]['content']
    extracted = prepare(EN, [source()], disclosure=False)
    assert extracted['messages'] == [] and extracted['answer_source'] == 'KNOWLEDGE_EXTRACTS'
    assert extracted['knowledge_reply'] == '[1] Alder\n'+source()['content']


def test_mixed_source_frame_keeps_missing_attribute_explicit_without_general_identity_facts():
    value = prepare(EN, [source(content='Alder is a platform.')], status='PARTIAL_MATCH', missing_parts=['version'])
    wire = prompt(value)
    assert value['answer_source'] == 'MIXED_SOURCES' and wire['question_parts'] == [EN]
    assert wire['missing_parts'] == ['version']
    assert wire['requested_attributes'][1] == dict(attribute='version', source_citations=[])
    assert 'general model knowledge' in value['messages'][0]['content']


def test_preparation_does_not_fill_or_rewrite_incomplete_model_reply():
    value = prepare(EN, [source()])
    raw = 'It is a collaboration platform. Snapshot version v8.3.2. [1]'
    assert planning.render_reply(raw, value) == raw
    assert 'Alder' not in planning.render_reply(raw, value)


def test_no_source_supplement_bounds_unverified_facts_and_preserves_request():
    question = 'Explain this concept without assuming a particular implementation.'
    prepared = prepare(question, [], status='NO_MATCH')
    instruction = prepared['messages'][0]['content']
    assert prepared['answer_source'] == 'MODEL_SUPPLEMENT'
    assert prepared['knowledge_reply'] is None and prepared['citations'] == []
    assert prepared['messages'][1] == {'role': 'user', 'content': question}
    assert [message['role'] for message in prepared['messages']] == ['system', 'user']
    assert isinstance(instruction, str) and instruction.strip()
    # Instruction wording is not an observed answer-quality result. Preserve
    # the request and output contracts; actual full answers need separate review.
    # Generation instructions do not establish verified output facts or copy
    # question terms into an otherwise incomplete visible model answer.
    assert planning.render_reply('Unverified provider content', prepared) == 'Unverified provider content'


@pytest.mark.parametrize('kind', ['grounded', 'mixed', 'clarification', 'knowledge_only'])
def test_no_source_fact_constraints_do_not_enter_other_answer_routes(monkeypatch, kind):
    monkeypatch.setattr(planning.product_identity, 'identity', lambda: {'brand_en': 'Synthetic', 'brand_zh': 'Synthetic'})
    item = source(entity='route', title='Synthetic routing', content='Synthetic routing uses route-742.')
    prepared = prepare('Synthetic routing and explain refraction briefly.',
        [] if kind in {'clarification', 'knowledge_only'} else [item],
        status='PARTIAL_MATCH' if kind == 'mixed' else 'AMBIGUOUS' if kind == 'clarification' else 'MATCHED',
        mode='KNOWLEDGE_ONLY' if kind == 'knowledge_only' else 'KNOWLEDGE_FIRST',
        missing_parts=['explain refraction briefly.'])
    expected = {'grounded': 'KNOWLEDGE_GROUNDED', 'mixed': 'MIXED_SOURCES',
        'clarification': 'CLARIFICATION_REQUIRED', 'knowledge_only': 'INSUFFICIENT_KNOWLEDGE'}[kind]
    assert prepared['answer_source'] == expected
    if kind in {'grounded', 'mixed'}:
        assert [message['role'] for message in prepared['messages']] == ['system', 'user']
        assert prompt(prepared)['authorized_sources'] == [{'citation': 1, 'title': item['title'], 'content': item['content']}]
        assert prepared['citations'] == [{key: value for key, value in item.items() if key != 'content'}]
    else:
        assert prepared['messages'] == [] and prepared['knowledge_reply']
