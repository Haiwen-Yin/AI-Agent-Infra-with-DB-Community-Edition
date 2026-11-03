"""Optional content delivery preserves entrypoints and audited publication."""
import copy
import hashlib
import json
from pathlib import Path

import pytest

from lib import builtin_knowledge, product_identity, product_knowledge as knowledge
from .test_product_knowledge import publication, lifecycle


@pytest.fixture
def external(lifecycle, monkeypatch):
    root, db = lifecycle
    product = dict(product_key='agentx-community', name_zh='OpenTenBase AgentX', name_en='OpenTenBase AgentX',
                   version='5.0.3', edition='Community', databases=['pg'])
    monkeypatch.setattr(product_identity, 'identity', lambda *_: dict(product))
    from lib import knowledge_api
    monkeypatch.setattr(knowledge_api, 'knowledge_access_predicate', lambda *_: "e.VISIBILITY='PUBLIC'")
    unit = dict(key='learn-start', title='Optional guide', content='Reviewed optional learning content',
                roles=['HUMAN', 'ADMIN', 'AGENT'], goals=['onboarding'], sources=[], source_paths=[],
                version='5.0.3', product_key=product['product_key'], edition='Community', database='pg')
    content = knowledge._snapshot(product, 'pg', [unit])
    bundle = dict(format='platform-learning/1', snapshots={'pg': content})
    (root / 'build-manifest.json').write_text(json.dumps({'platform_learning': {
        'delivery': 'separate', 'snapshots': {'pg': {'revision': content['snapshot_revision'],
                                                  'sha256': builtin_knowledge._digest(content)}}}}))
    return root, db, product, bundle


def test_fresh_community_installs_only_short_facts_and_keeps_learning_entry(external):
    root, db, _, _ = external
    result = knowledge.install_default('admin', 'pg', root, initialize=True)
    assert len(result['knowledge_ids']) == 4
    directory = knowledge.learning_catalog('admin', 'pg', root=root)
    assert directory['items'] == [] and directory['delivery'] == 'separate' and directory['can_import']
    assert db.execute('SELECT COUNT(*) FROM ENTITIES').fetchone()[0] == 4


def test_explicit_import_is_discoverable_idempotent_and_exactly_readable(external):
    root, db, _, bundle = external
    knowledge.install_default('admin', 'pg', root, initialize=True)
    imported = knowledge.import_learning('admin', 'pg', bundle, root=root)
    assert len(imported['superseded']) == 4
    assert knowledge.import_learning('admin', 'pg', bundle, root=root)['knowledge_ids'] == imported['knowledge_ids']
    directory = knowledge.learning_catalog('admin', 'pg', role='AGENT', root=root)
    assert directory['status'] == 'AVAILABLE' and len(directory['items']) == 1
    item = directory['items'][0]
    assert 'content' not in item
    loaded = knowledge.read_learning('admin', 'pg', item['entity_id'], item['content_digest'], root=root)
    assert hashlib.sha256(loaded['content'].encode()).hexdigest() == item['content_digest']
    assert db.execute('SELECT COUNT(*) FROM ENTITIES').fetchone()[0] == 5


def test_upgrade_preserves_imported_content_history_and_user_changes(external):
    root, db, _, bundle = external
    result = knowledge.import_learning('admin', 'pg', bundle, root=root)
    db.execute("UPDATE ENTITIES SET CONTENT='User addition' WHERE ENTITY_ID=?", (result['knowledge_ids'][0],))
    db.commit()
    before = '\n'.join(db.iterdump())
    assert knowledge.install_default('admin', 'pg', root)['status'] == 'PRESERVED_EXISTING'
    assert '\n'.join(db.iterdump()) == before


@pytest.mark.parametrize('mutation', ['content', 'product', 'version', 'database', 'format', 'snapshots'])
def test_wrong_or_tampered_companion_cannot_publish_any_data(external, mutation):
    root, db, _, original = external
    bundle = copy.deepcopy(original)
    content = bundle['snapshots']['pg']
    if mutation == 'content':
        content['sections'][0]['content'] = 'Tampered'
    elif mutation in {'product', 'version'}:
        content['product']['product_key' if mutation == 'product' else 'version'] = 'wrong'
    elif mutation == 'database':
        content['database'] = 'oracle'
    elif mutation == 'format':
        bundle['format'] = 'unknown'
    else:
        bundle['snapshots'] = []
    with pytest.raises(ValueError):
        knowledge.import_learning('admin', 'pg', bundle, root=root)
    assert db.execute('SELECT COUNT(*) FROM CX_PLATFORM_KNOWLEDGE').fetchone()[0] == 0
    assert db.execute('SELECT COUNT(*) FROM ENTITIES').fetchone()[0] == 0


def test_import_denied_before_publication_and_ui_import_hint_respects_authority(external, monkeypatch):
    root, db, _, bundle = external
    monkeypatch.setattr(knowledge.identity_api, 'effective_access',
                        lambda _, action: {'decision': 'DENY' if action == 'platform.manage' else 'ALLOW'})
    assert not knowledge.learning_catalog('reader', 'pg', root=root)['can_import']
    with pytest.raises(PermissionError):
        knowledge.import_learning('reader', 'pg', bundle, root=root)
    assert db.execute('SELECT COUNT(*) FROM CX_PLATFORM_KNOWLEDGE').fetchone()[0] == 0


def test_import_audit_failure_rolls_back_package_chunks_and_entities(external, monkeypatch):
    root, db, _, bundle = external
    def fail(*_):
        raise RuntimeError('Injected audit failure')
    monkeypatch.setattr(knowledge.identity_api, '_audit_tx', fail)
    with pytest.raises(RuntimeError, match='audit failure'):
        knowledge.import_learning('admin', 'pg', bundle, root=root)
    for table in ('ENTITIES', 'CX_PLATFORM_KNOWLEDGE', 'CX_PLATFORM_KNOWLEDGE_CHUNKS'):
        assert db.execute('SELECT COUNT(*) FROM ' + table).fetchone()[0] == 0


def test_withdrawal_disables_optional_learning_and_republication(external):
    root, db, _, bundle = external
    knowledge.import_learning('admin', 'pg', bundle, root=root)
    row = db.execute('SELECT KNOWLEDGE_ID FROM CX_PLATFORM_KNOWLEDGE').fetchone()
    builtin_knowledge.withdraw('admin', row[0], 'Retire optional guide')
    assert knowledge.learning_catalog('admin', 'pg', root=root)['items'] == []
    with pytest.raises(builtin_knowledge.KnowledgeLifecycleError):
        knowledge.import_learning('admin', 'pg', bundle, root=root)


def test_separate_runtime_package_has_no_complete_payload():
    root = product_identity.package_root(__file__)
    if knowledge.delivery(root)['delivery'] != 'separate':
        pytest.skip('Requires a generated Community or AgentX package')
    from lib import platform_learning
    assert not (root / 'scripts/lib/platform_learning_content.py').exists()
    assert platform_learning.sections(product_identity.identity(root), 'pg') == ()
    assert not list(root.glob('**/*platform-learning-v*.json'))

