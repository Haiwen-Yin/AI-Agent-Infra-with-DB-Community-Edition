"""Request-local vectors reuse bytes only after fresh effective authority."""
from copy import deepcopy
import json
from unittest.mock import Mock

import pytest

from lib import embedding_api,embedding_governance,answer_planning


@pytest.fixture
def provider(monkeypatch):
    context=dict(agent_id='agent',profile=dict(profile_id='p',version=1,provider_url='https://example.invalid/v1',model_id='e'),
        space=dict(space_id='s'),contract=dict(contract_id='c',dimension=2,distance_metric='COSINE'),mode='PLATFORM_MANAGED')
    binding=Mock(side_effect=lambda *args,**kwargs:deepcopy(context))
    generate=Mock(return_value=[0.5,0.5])
    monkeypatch.setattr(embedding_api,'_governed_context',binding)
    monkeypatch.setattr(embedding_api,'generate_embedding',generate)
    monkeypatch.setattr(embedding_governance,'_profile_api_key',lambda profile:'')
    return context,binding,generate


def test_same_query_and_contract_reuses_one_vector_but_rechecks_binding(provider):
    context,binding,generate=provider
    with embedding_api.query_scope() as state:
        first=embedding_api._query_embedding('Exact query',agent_id='agent')
        second=embedding_api._query_embedding('Exact query',agent_id='agent')
        assert first==second and generate.call_count==1 and binding.call_count==2
        assert state['cache_hits']==1
    usage=embedding_api.query_usage(state)
    assert usage['provider_attempts']==1 and usage['provider_successes']==1
    assert usage['input_characters']==len('Exact query') and not state['cache']
    assert usage['provider_input_tokens'] is None and usage['token_observation']=='UNAVAILABLE'
    assert 'Exact query' not in json.dumps(usage) and 'example.invalid' not in json.dumps(usage)


@pytest.mark.parametrize('field',('profile','space','contract','agent_id'))
def test_changed_binding_cannot_reuse_a_vector(provider,field):
    context,binding,generate=provider
    with embedding_api.query_scope():
        embedding_api._query_embedding('query')
        if field=='profile':context['profile']['version']=2
        elif field=='space':context['space']['space_id']='other'
        elif field=='contract':context['contract']['contract_id']='other'
        else:context['agent_id']='other'
        embedding_api._query_embedding('query')
    assert generate.call_count==2


def test_revocation_after_cache_fill_blocks_reuse(provider):
    context,binding,generate=provider
    with embedding_api.query_scope():
        embedding_api._query_embedding('query')
        binding.side_effect=PermissionError('Contract revoked')
        with pytest.raises(PermissionError):embedding_api._query_embedding('query')
    assert generate.call_count==1


def test_different_text_and_new_request_are_not_the_same_cache_entry(provider):
    context,binding,generate=provider
    with embedding_api.query_scope():
        embedding_api._query_embedding('query')
        embedding_api._query_embedding('query not approved')
    with embedding_api.query_scope():embedding_api._query_embedding('query')
    assert generate.call_count==3 and embedding_api._QUERY_SCOPE.get() is None


@pytest.mark.parametrize('invalid',([0.0,0.0],[float('nan'),1],[True,1],[1],['1',1]))
def test_invalid_vectors_and_failures_never_fill_cache(provider,invalid):
    context,binding,generate=provider
    generate.return_value=invalid
    with embedding_api.query_scope() as state:
        with pytest.raises(ValueError):embedding_api._query_embedding('query')
        assert not state['cache']
        generate.return_value=[0.5,0.5]
        embedding_api._query_embedding('query')
    assert generate.call_count==2 and state['provider_failures']==1


def test_equivalent_decomposed_query_uses_one_embedding_per_request(provider,monkeypatch):
    context,binding,generate=provider
    def search(actor,agent,query,**kwargs):
        embedding_api._query_embedding(query,agent_id=agent)
        return dict(items=[],retrieval_mode='VECTOR')
    monkeypatch.setattr(answer_planning.knowledge_grounding,'search',search)
    result=answer_planning.retrieve('human','agent','Boreal routing and Boreal routing',strategy='vector')
    assert generate.call_count==1
    usage=result['retrieval']['query_embedding']
    assert usage['provider_attempts']==usage['cache_hits']==1
    assert 'query_embedding' not in result['answer_metadata']


def test_explicit_arbitrary_claims_recall_once_and_keep_all_requirements(provider,monkeypatch):
    context,binding,generate=provider
    question='Explain the retention limit and escalation owner for Boreal'
    calls=[]
    def search(actor,agent,query,**kwargs):
        calls.append(query);embedding_api._query_embedding(query,agent_id=agent)
        return dict(items=[],retrieval_mode='VECTOR')
    monkeypatch.setattr(answer_planning.knowledge_grounding,'search',search)
    result=answer_planning.retrieve('human','agent',question,strategy='vector')
    assert calls==[question] and generate.call_count==1
    assert result['missing_parts']==['retention limit','escalation owner']
