"""Applicability is a filter over authorized evidence, not text popularity."""
import copy
import json

import pytest
from pathlib import Path

from lib import knowledge_applicability as applicability, knowledge_grounding as grounding, embedding_api
from .test_knowledge_signals import store, no_external_work

# The cross-adapter SQLite fixture dynamically imports source adapters. A
# generated single-backend package intentionally does not ship the repository
# adapter tree; its native checks cover that package separately.
pytestmark = pytest.mark.skipif(
    not (Path(__file__).resolve().parents[2] / "adapters").is_dir(),
    reason="Cross-adapter applicability checks run from the source checkout",
)


def item(version='5.0.3', product='unified-community', status='CURRENT'):
    return dict(entity_id='source', title='Boreal release', content='Boreal v5.0.2 and v5.0.3 are compared here.',
        source_context=dict(intake=dict(applicable_product=product, applicable_version=version,
            effective_from='2026-11-01T08:00:00+08:00', effective_until='2026-12-01T00:00:00Z',
            decision_status=status), provenance=[dict(origin=dict(decision_status=status))]))


@pytest.mark.parametrize('scope', [dict(product='agentx-community'), dict(version='5.0.2'),
    dict(as_of='2026-10-31T23:59:59Z'), dict(as_of='2026-12-01T00:00:00Z'),
    dict(decision_statuses=['PROPOSED'])])
def test_explicit_contradictory_declarations_cannot_be_overridden_by_body_mentions(scope):
    assert not applicability.matches(item(), applicability.constraints('Boreal', scope))


@pytest.mark.parametrize('scope', [dict(product='unified-community'), dict(version='v5.0.3'),
    dict(as_of='2026-11-01T00:00:00Z'), dict(as_of='2026-11-30T23:59:59Z'),
    dict(decision_statuses=['CURRENT'])])
def test_exact_product_version_time_interval_and_decision_filters(scope):
    assert applicability.matches(item(), applicability.constraints('Boreal', scope))


def test_question_version_and_explicit_scope_intersect_before_recall():
    with pytest.raises(ValueError, match='disagree'):
        applicability.constraints('Boreal v5.0.2', dict(version='5.0.3'))
    assert applicability.matches(item(), applicability.constraints('Compare Boreal v5.0.2 and v5.0.3'))
    assert not applicability.matches(item(version='5.0.2'), applicability.constraints('Boreal v5.0.3'))


def test_event_date_is_not_inferred_to_be_an_effective_time_request():
    assert applicability.matches(item(), applicability.constraints('What event occurred for Boreal on 2026-10-31?'))


@pytest.mark.parametrize('scope', [dict(product='unified-community'), dict(version='5.0.3'),
    dict(as_of='2026-11-01T00:00:00Z'), dict(decision_statuses=['CURRENT'])])
def test_legacy_unknown_declarations_do_not_become_universal_applicability(scope):
    legacy=dict(title='Boreal v5.0.3', content='A legacy note')
    assert not applicability.matches(legacy, applicability.constraints('Boreal', scope))
    assert applicability.matches(legacy, applicability.constraints('Boreal v5.0.3'))
    assert applicability.matches(legacy, applicability.constraints('Boreal'))


def test_current_summary_cannot_erase_original_proposal_and_version():
    summary=item()
    original=item(version='5.0.2', status='PROPOSED')
    summary['source_context']['derived_sources']=[dict(source_context=original['source_context'])]
    assert not applicability.matches(summary, applicability.constraints('Boreal v5.0.3'))
    assert not applicability.matches(summary, applicability.constraints('Boreal', dict(decision_statuses=['CURRENT'])))
    assert applicability.matches(summary, applicability.constraints('Boreal'))
    # The original curator declaration is also binding if a reviewer relabels
    # only the projection's intake, without changing the immutable original.
    summary=item()
    summary['source_context']['provenance'][0]['origin']['decision_status']='PROPOSED'
    assert not applicability.matches(summary, applicability.constraints('Boreal', dict(decision_statuses=['CURRENT'])))


def test_memory_without_known_original_applicability_cannot_satisfy_structured_filters():
    memory=dict(title='Summary',content='A claim',source_context=dict(candidate_id='candidate',sources=[],provenance=[]))
    assert not applicability.matches(memory,applicability.constraints('Summary',dict(decision_statuses=['CURRENT'])))
    assert not applicability.matches(memory,applicability.constraints('Summary',dict(version='5.0.3')))


@pytest.mark.parametrize('scope', [[], '', dict(extra='arbitrary'), dict(as_of='2026-11-01'),
    dict(as_of=1234567), dict(as_of=True), dict(decision_statuses=['ACTIVE'])])
def test_invalid_filters_fail_closed(scope):
    with pytest.raises(ValueError):applicability.constraints('Boreal', scope)


@pytest.mark.parametrize('strategy', ['keyword', 'fulltext', 'vector', 'hybrid'])
def test_each_retrieval_route_applies_scope_before_selection_and_citation(store,monkeypatch,strategy):
    db,add=store
    for key in ['correct', 'wrong-version', 'wrong-product', 'future']:
        add(key,domain='Boreal')
    db.execute("UPDATE ENTITIES SET TITLE='Boreal v5.0.2 v5.0.3',CONTENT='Boreal v5.0.2 v5.0.3'")
    contexts={key:item()['source_context'] for key in ['correct','wrong-version','wrong-product','future']}
    contexts['wrong-version']=item(version='5.0.2')['source_context']
    contexts['wrong-product']=item(product='agentx-community')['source_context']
    contexts['future']['intake']['effective_from']='2026-11-02T00:00:00Z'
    for key,context in contexts.items():
        db.execute("INSERT INTO CX_CONTINUITY_ARTIFACTS VALUES(?,'KNOWLEDGE','domain','ACTIVE',?)",(key,'r-'+key))
        db.execute('INSERT INTO CX_CONTINUITY_ARTIFACT_REVS VALUES(?,?,?,?,1,?)',(key,key,'r-'+key,'c-'+key,'digest-'+key))
        db.execute('INSERT INTO CX_KNOWLEDGE_INTAKE VALUES(?,1,?)',('c-'+key,json.dumps(context['intake'])))
    monkeypatch.setattr(grounding,'_projection_contexts',lambda _a,_b,keys:{key:contexts[key] for key in keys})
    monkeypatch.setattr(grounding,'citation',lambda actor,agent,key,*a,**kw:grounding._load_candidates(actor,agent,[key])[0])
    monkeypatch.setattr(embedding_api,'search_authorized_knowledge',lambda *a,**kw:[{'entity_id':key} for key in contexts])
    scope=dict(product='unified-community',version='5.0.3',as_of='2026-11-01T00:00:00Z')
    result=grounding.search('human','agent','Boreal v5.0.3',strategy=strategy,applicability=scope)
    assert [source['entity_id'] for source in result['items']]==['correct']
    source=result['items'][0]
    assert source['applicability_constraints']['versions']==['5.0.3']
    assert result['retrieval']['ranking_generation_calls']==0
    grounding.validate_citation('human','agent',source)
    # Recheck the actual current declaration, not the previously selected copy.
    contexts['correct']=copy.deepcopy(contexts['wrong-version'])
    with pytest.raises(grounding.GroundingError,match='applicability'):
        grounding.validate_citation('human','agent',source)
