"""Bound graph projection reads to the exact preauthorized window."""
import pytest

from lib import knowledge_api


def test_graph_details_batches_edges_without_disclosing_outside_endpoints(monkeypatch):
    queries = []
    def query(sql, params):
        queries.append((sql, params))
        if 'FROM ENTITY_EDGES' in sql:
            return [dict(edge_id='inside', source_id='a', target_id='b'),
                    dict(edge_id='outside', source_id='a', target_id='hidden')]
        return [dict(entity_id='a', organization_chain_json='[{"organization_id":"org"}]',
                     responsible_groups_json='[]', execution_groups_json='[]'),
                dict(entity_id='hidden', organization_chain_json='[]')]
    monkeypatch.setattr(knowledge_api, 'execute_query', query)
    result = knowledge_api.knowledge_graph_details(['a', 'b', 'a'])
    assert len(queries) == 2
    assert queries[0][1] == queries[1][1] == dict(graph_entity_0='a', graph_entity_1='b')
    assert 'SOURCE_ID IN (' in queries[0][0] and 'AND TARGET_ID IN (' in queries[0][0]
    assert [edge['edge_id'] for edge in result['edges']] == ['inside']
    assert set(result['contexts']) == {'a'}
    assert result['contexts']['a']['organization_chain'] == [dict(organization_id='org')]


def test_graph_details_empty_window_never_reads_database(monkeypatch):
    monkeypatch.setattr(knowledge_api, 'execute_query', lambda *_: pytest.fail('Empty window queried'))
    assert knowledge_api.knowledge_graph_details([]) == dict(edges=[], contexts={})
    with pytest.raises(ValueError, match='200'):
        knowledge_api.knowledge_graph_details(range(201))
