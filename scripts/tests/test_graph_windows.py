"""Graph previews stay bounded and do not disclose adjacent hidden IDs."""
import ast
from pathlib import Path
from types import SimpleNamespace

import pytest


def graph_scope():
    source = Path(__file__).resolve().parents[1] / 'visualization/server.py'
    names = {'_knowledge_to_vis', '_memory_to_vis', '_parse_bounded_limit', '_get_tags_for_entities'}
    nodes = [node for node in ast.parse(source.read_text()).body
             if isinstance(node, ast.FunctionDef) and node.name in names]
    queries = []
    calls = []
    def search(**kwargs):
        calls.append(kwargs)
        return [dict(entity_id='visible', version_id='visible', title='Authorized')]
    def query(sql, params=None):
        queries.append((sql, params))
        if 'entity_tags' in sql or 'CX_MEMORY_RELATIONS' in sql:
            return []
        return [dict(source_id='visible', target_id='hidden', edge_type='RELATED'),
                dict(source_id='hidden', target_id='visible', edge_type='RELATED'),
                dict(source_id='visible', target_id='visible', edge_type='SELF')]
    namespace = dict(connection=SimpleNamespace(execute_query=query),
                     knowledge_api=SimpleNamespace(search_knowledge=search),
                     memory_api=SimpleNamespace(search_memories=search))
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(source), 'exec'), namespace)
    return namespace, calls, queries


@pytest.mark.parametrize('name', ['_knowledge_to_vis', '_memory_to_vis'])
def test_requested_window_reaches_authorized_search_and_is_not_a_total(name):
    scope, calls, _ = graph_scope()
    result = scope[name]('reader', limit=20)
    assert calls == [dict(limit=20, principal_id='reader')]
    assert result['window']['returned'] == 1
    assert result['window']['limit'] == 20
    assert result['window']['complete'] is False


@pytest.mark.parametrize('value', ['garbage', '0', '-1', '1001', []])
def test_invalid_windows_do_not_dispatch_queries(value):
    scope, calls, queries = graph_scope()
    with pytest.raises(ValueError):
        scope['_knowledge_to_vis']('reader', limit=value)
    assert not calls and not queries


def test_hidden_adjacent_knowledge_ids_are_not_exposed_by_edges():
    scope, _, _ = graph_scope()
    result = scope['_knowledge_to_vis']('reader')
    assert result['edges'] == [dict(**{'from': 'visible', 'to': 'visible'}, label='SELF', value=1.0)]
    assert 'hidden' not in str(result)


def test_edge_queries_are_bound_to_the_selected_window():
    scope, _, queries = graph_scope()
    scope['_knowledge_to_vis']('reader', limit=20)
    sql, params = queries[0]
    assert params == {'knowledge0': 'visible'}
    assert 'source_id IN (:knowledge0) AND target_id IN (:knowledge0)' in sql
    assert 'visible' not in sql
    queries.clear()
    scope['_memory_to_vis']('reader', limit=20)
    sql, params = next(row for row in queries if 'CX_MEMORY_RELATIONS' in row[0])
    assert params == {'memory_v0': 'visible'}
    assert 'r.SOURCE_VERSION_ID IN (:memory_v0) OR r.TARGET_VERSION_ID IN (:memory_v0)' in sql
    assert 'FETCH FIRST 1000 ROWS ONLY' in sql


def test_related_memory_endpoints_require_both_current_and_original_source_access(monkeypatch):
    from lib import continuity_promotions, continuity_state
    scope, _, _ = graph_scope()
    checked = []
    class MemoryLifecycleError(Exception):
        pass
    def current_access(reader, row, purpose):
        checked.append(('current', row['version_id'], reader, purpose))
        if row['version_id'] == 'hidden-current':
            raise PermissionError('current authority denied')
    def original_access(tx, reader, family, version, item):
        checked.append(('original', version, reader))
        if version == 'hidden-source':
            raise continuity_state.ContinuityConflict('source_revoked', 'original source was revoked')
    monkeypatch.setattr(continuity_promotions, 'require_memory_original_sources', original_access)
    def query(sql, params=None):
        if 'entity_tags' in sql:
            return []
        if 'CX_MEMORY_RELATIONS' in sql:
            return [dict(source_id='visible', target_id=target, edge_type='DERIVED')
                    for target in ['history', 'hidden-current', 'hidden-source']]
        return [dict(version_id=key, family_id='family-'+key, title=key, is_current=0)
                for key in ['history', 'hidden-current', 'hidden-source']]
    scope['connection'] = SimpleNamespace(execute_query=query,
                                         execute_transaction_callback=lambda callback: callback(object()))
    scope['memory_lifecycle'] = SimpleNamespace(_require_memory_access=current_access,
                                                MemoryLifecycleError=MemoryLifecycleError)
    result = scope['_memory_to_vis']('reader', limit=20)
    assert [row['id'] for row in result['nodes']] == ['visible', 'history']
    assert result['nodes'][1]['history_node'] is True
    assert result['edges'] == [dict(**{'from': 'visible', 'to': 'history'}, label='DERIVED', value=1.0)]
    assert ('original', 'history', 'reader') in checked
    assert ('original', 'hidden-source', 'reader') in checked
    assert not any(item[:2] == ('original', 'hidden-current') for item in checked)
    assert 'hidden-' not in str(result)
