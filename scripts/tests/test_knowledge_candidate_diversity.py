"""Execute bounded SQL against duplicate, stale, conflicting and hidden facts."""
import copy
import json
from pathlib import Path

import pytest

from lib import knowledge_candidates as candidate, knowledge_grounding as grounding, knowledge_applicability
from lib import knowledge_signals as signals
from .test_knowledge_signals import store, no_external_work, ids

pytestmark = pytest.mark.skipif(not (Path(__file__).resolve().parents[2] / 'adapters').is_dir(),
    reason='Cross-adapter SQLite fixture requires the source checkout; native package checks are separate')


def reviewed(db, add, key, body_digest, *, body='Boreal retention: 30 days; preserve legal holds.',
             product='Boreal', version='3.2.1', status='CURRENT', human=1, agent=1,
             effective_from='2026-01-01T00:00:00Z', effective_until=None):
    add(key, domain='Boreal', human=human, agent=agent)
    db.execute('UPDATE ENTITIES SET TITLE=\'Boreal guide\',CONTENT=:body WHERE ENTITY_ID=:key',dict(body=body,key=key))
    metadata = dict(applicable_product=product, applicable_version=version, decision_status=status,
        effective_from=effective_from, effective_until=effective_until)
    db.execute("INSERT INTO CX_CONTINUITY_ARTIFACTS VALUES(?,'KNOWLEDGE','domain','ACTIVE',?)",(key,'r-'+key))
    db.execute('INSERT INTO CX_CONTINUITY_ARTIFACT_REVS VALUES(?,?,?,?,1,?)',(key,key,'r-'+key,'c-'+key,body_digest))
    db.execute('INSERT INTO CX_KNOWLEDGE_INTAKE VALUES(?,1,?)',('c-'+key,json.dumps(metadata)))
    return dict(intake=metadata)


def test_native_diversity_preserves_conflicts_and_fallbacks_inside_fixed_limit(store):
    db,add=store
    for i in range(100):
        reviewed(db,add,'a-copy-'+str(i).zfill(3),'same-fact')
    reviewed(db,add,'z-owner','owner-fact',body='Boreal escalation owner: Human administrator.')
    reviewed(db,add,'z-conflict','conflicting-fact',body='Boreal retention: 60 days; preserve legal holds.')
    bound=knowledge_applicability.constraints('Boreal v3.2.1',dict(product='Boreal',decision_statuses=['CURRENT']))
    rows=signals.candidates('human','agent',['Boreal'],channel='relational',candidate_scope=bound,limit=4)
    assert set(ids(rows)[:3])=={'a-copy-000','z-owner','z-conflict'}
    assert ids(rows)[3]=='a-copy-001'
    assert len(rows)==4


def test_primary_scope_and_dual_authority_filter_before_limit_with_timezone_bounds(store):
    db,add=store
    for i in range(45):
        reviewed(db,add,'a-wrong-'+str(i),'wrong-'+str(i),product='Boreal Labs')
    for key,kw in [('b-version',dict(version='3.2.10')),('b-proposal',dict(status='HISTORICAL')),
        ('b-future',dict(effective_from='2026-11-02T00:00:01+00:00')),
        ('b-expired',dict(effective_until='2026-11-02T00:00:00+00:00')),
        ('b-human-private',dict(agent=0)),('b-agent-private',dict(human=0))]:
        reviewed(db,add,key,key,**kw)
    reviewed(db,add,'z-good','good',version='v3.2.1',effective_from='2026-11-02T08:00:00+08:00')
    bound=knowledge_applicability.constraints('Boreal v3.2.1',dict(product='Boreal',version='3.2.1',
        decision_statuses=['CURRENT'],as_of='2026-11-02T00:00:00Z'))
    result=signals.candidates('human','agent',['Boreal'],channel='relational',candidate_scope=bound,limit=1)
    assert ids(result)==['z-good']


def test_source_reauthorization_precedes_body_deduplication_and_preserves_exact_citation(store,monkeypatch):
    db,add=store
    contexts={key:reviewed(db,add,key,'same-fact') for key in ['a-revoked','b-current','c-duplicate']}
    contexts['a-revoked']=None
    monkeypatch.setattr(grounding,'_projection_contexts',lambda _a,_b,keys:{key:contexts[key] for key in keys})
    result=grounding.search('human','agent','Boreal v3.2.1',strategy='hybrid',applicability=dict(product='Boreal'))
    assert ids(result['items'])==['b-current']
    assert result['items'][0]['source_context']==contexts['b-current']
    assert result['retrieval']['ranking_generation_calls']==0
    # Exact user-selected identities remain separate, including equal bodies.
    result=grounding.search('human','agent','Boreal v3.2.1',strategy='hybrid',
        applicability=dict(product='Boreal'),entity_ids=['b-current','c-duplicate'])
    assert set(ids(result['items']))=={'b-current','c-duplicate'}


def test_equal_body_never_merges_distinct_original_applicability_or_graph_endpoints():
    first=dict(entity_id='one',title='A fact',content='Unchanged complete body',
        source_context=dict(intake=dict(applicable_version='3.2.1'),derived_sources=[dict(
            source_context=dict(intake=dict(decision_status='HISTORICAL')))]))
    second=copy.deepcopy(first)
    second['entity_id']='two'
    second['source_context']['derived_sources'][0]['source_context']['intake']['decision_status']='CURRENT'
    assert len(candidate.distinct([first,second]))==2
    second=copy.deepcopy(first)
    second['entity_id']='two'
    assert len(candidate.distinct([first,second]))==1
    assert len(candidate.distinct([first,second],preserve_ids={'one','two'}))==2


def test_explicit_historical_version_retains_its_own_declaration(store):
    db,add=store
    reviewed(db,add,'old','old-fact',version='3.2.1')
    add('new',domain='Boreal')
    metadata=dict(applicable_product='Boreal',applicable_version='3.2.2',decision_status='CURRENT')
    db.execute("INSERT INTO CX_CONTINUITY_ARTIFACT_REVS VALUES('old','new','r-new','c-new',1,'new-fact')")
    db.execute("INSERT INTO CX_KNOWLEDGE_INTAKE VALUES('c-new',1,?)",(json.dumps(metadata),))
    db.execute("UPDATE CX_CONTINUITY_ARTIFACTS SET CURRENT_REVISION_ID='r-new' WHERE ARTIFACT_ID='old'")
    bound=knowledge_applicability.constraints('Boreal v3.2.1',dict(product='Boreal',version='3.2.1'))
    assert ids(signals.candidates('human','agent',['Boreal'],channel='relational',candidate_scope=bound,limit=1))==['old']
    # Task's explicit current-domain route continues to exclude old projections.
    assert signals.candidates('human','agent',['Boreal'],channel='relational',candidate_scope=bound,
        artifact_domain='domain',limit=1)==[]
