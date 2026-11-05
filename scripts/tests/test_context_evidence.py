"""Current read authority applies to omitted-source metadata as well as bodies."""
import pytest

from lib import agent_source_sync as sync, continuity_assembly as assembly
from .test_v501_context_assets import store, imported, context
from .test_continuity_candidates import candidate_db
from .test_continuity_handoff import fixture
from .test_continuity_work import database


def test_omitted_source_identity_is_hidden_after_revocation(store):
    source, job, reference, result = imported(store)
    prepared = assembly.assemble('owner', context(query_text='quantum gravity', sources=[reference]))
    first = assembly.read_assembly('owner', prepared['assembly_id'])
    assert first['item_count'] == 0 and len(first['representations']) == 1
    assert first['representations'][0]['delivery_status'] == 'OMITTED'
    sync.change_state('owner', source, dict(expected_version=1, status='REVOKED',
        reason='Source authority withdrawn', idempotency_key='revoke'))
    second = assembly.read_assembly('owner', prepared['assembly_id'])
    assert second['text'] == '' and second['representations'] == []
    assert second['unavailable_representation_count'] == 1
    assert source not in str(second)


def test_assembly_replay_revalidates_and_rerenders_without_retrieval_or_embedding(store, monkeypatch):
    from lib import context_selection, embedding_api
    source, job, reference, result = imported(store)
    calls = dict(selection=0, body=0, embedding=0)
    select = context_selection.select_sources
    resolve = assembly.resolve_many
    def selected(*args, **kwargs):
        calls['selection'] += 1
        return select(*args, **kwargs)
    def resolved(*args, **kwargs):
        calls['body'] += 1
        return resolve(*args, **kwargs)
    def unexpected_embedding(*args, **kwargs):
        calls['embedding'] += 1
        pytest.fail('Explicit-source preparation must not request an embedding')
    monkeypatch.setattr(context_selection, 'select_sources', selected)
    monkeypatch.setattr(assembly, 'resolve_many', resolved)
    monkeypatch.setattr(embedding_api, '_query_embedding', unexpected_embedding)
    monkeypatch.setattr(embedding_api, 'generate_embedding', unexpected_embedding)
    request = context(query_text='database maintenance', mandatory_sources=[reference])
    prepared = assembly.assemble('owner', request)
    assert prepared['item_count'] == 1
    first = dict(calls)
    replay = assembly.assemble('owner', request)
    assert replay['replayed'] and replay['assembly_id'] == prepared['assembly_id']
    assert first == dict(selection=1, body=1, embedding=0)
    assert calls == dict(selection=1, body=2, embedding=0)
    # No TTL-only reuse: unchanged request/assembly identity cannot bypass revocation.
    sync.change_state('owner', source, dict(expected_version=1, status='REVOKED',
        reason='Source authority withdrawn', idempotency_key='revoke'))
    with pytest.raises(PermissionError):
        assembly.assemble('owner', request)
