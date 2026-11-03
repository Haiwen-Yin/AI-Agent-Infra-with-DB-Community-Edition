"""Published onboarding discovery uses exact current authorized DB projections."""
import hashlib
import json
from pathlib import Path
import shutil

import pytest

from lib import platform_learning, product_knowledge as knowledge
from .test_product_knowledge import publication, lifecycle


@pytest.fixture
def learning(lifecycle,monkeypatch):
    root,db=lifecycle
    product=dict(product_key='agentx-community',name_zh='OpenTenBase AgentX',name_en='OpenTenBase AgentX',
                 version='5.0.3',edition='Community',databases=['pg'])
    monkeypatch.setattr(knowledge.product_identity,'identity',lambda *_:dict(product))
    from lib import knowledge_api
    monkeypatch.setattr(knowledge_api,'knowledge_access_predicate',lambda *_:"e.VISIBILITY='PUBLIC'")
    if not platform_learning.sections(product, 'pg'):
        pytest.skip('Complete learning payload is delivered separately for this product')
    # Bind the exact reviewed source bytes used by generated packages.
    source=Path(__file__).resolve().parents[1]
    if (source.parent/'build-manifest.json').is_file():
        source=source.parent
    for unit in platform_learning.sections(product,'pg'):
        for relative in unit['source_paths']:
            dest=root/relative;dest.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(source/relative,dest)
    return root,db,product


@pytest.mark.parametrize('database,key,edition',[
    ('oracle','unified-community','Community'),('pg','unified-community','Community'),
    ('yashandb','unified-community','Community'),('pg','agentx-community','Community'),
    ('oracle','oracle-enterprise','Enterprise'),('pg','pg-enterprise','Enterprise'),
    ('yashandb','yashandb-enterprise','Enterprise'),
])
def test_all_seven_targets_publish_applicable_source_bound_learning(learning,database,key,edition):
    root,db,product=learning
    product.update(product_key=key,edition=edition,databases=[database])
    record=knowledge.publish('admin',database,root)
    assert len(record['knowledge_ids'])==13
    directory=knowledge.learning_catalog('admin',database,role='HUMAN',goal='onboarding',root=root)
    assert directory['status']=='AVAILABLE'
    assert len(directory['items'])==2
    assert all('content' not in item for item in directory['items'])
    item=directory['items'][0]
    assert item['product_key']==key and item['version']=='5.0.3'
    loaded=knowledge.read_learning('admin',database,item['entity_id'],item['content_digest'],root=root)
    assert not loaded['automatic_execution']
    assert hashlib.sha256(loaded['content'].encode()).hexdigest()==item['content_digest']
    assert all(hashlib.sha256((root/s['path']).read_bytes()).hexdigest()==s['sha256'] for s in loaded['sources'])
    assert knowledge.publish('admin',database,root)['knowledge_ids']==record['knowledge_ids']
    assert db.execute('SELECT COUNT(*) FROM ENTITIES').fetchone()[0]==13


def test_missing_source_blocks_entire_publication(learning):
    root,db,_=learning
    (root/'docs/knowledge-intake.md').unlink()
    with pytest.raises(ValueError,match='source is unavailable'):
        knowledge.publish('admin','pg',root)
    assert db.execute('SELECT COUNT(*) FROM CX_PLATFORM_KNOWLEDGE').fetchone()[0]==0
    assert db.execute('SELECT COUNT(*) FROM ENTITIES').fetchone()[0]==0


def test_withdrawal_and_projection_changes_invalidate_later_discovery_and_read(learning):
    root,db,_=learning
    knowledge.publish('admin','pg',root)
    item=knowledge.learning_catalog('admin','pg',goal='onboarding',root=root)['items'][0]
    db.execute("UPDATE ENTITIES SET CONTENT='a user edit' WHERE ENTITY_ID=?",(item['entity_id'],));db.commit()
    assert item['entity_id'] not in {i['entity_id'] for i in knowledge.learning_catalog('admin','pg',root=root)['items']}
    with pytest.raises(PermissionError):
        knowledge.read_learning('admin','pg',item['entity_id'],item['content_digest'],root=root)
    db.execute("UPDATE CX_PLATFORM_KNOWLEDGE SET STATUS='REVOKED'");db.commit()
    assert knowledge.learning_catalog('admin','pg',root=root)['items']==[]


def test_permission_and_exact_version_are_rechecked_before_content(learning,monkeypatch):
    root,_,product=learning
    knowledge.publish('admin','pg',root)
    item=knowledge.learning_catalog('admin','pg',root=root)['items'][0]
    with pytest.raises(PermissionError):
        knowledge.read_learning('admin','pg',item['entity_id'],'0'*64,root=root)
    product['version']='5.0.4'
    assert knowledge.learning_catalog('admin','pg',root=root)['items']==[]
    with pytest.raises(PermissionError):
        knowledge.read_learning('admin','pg',item['entity_id'],item['content_digest'],root=root)
    monkeypatch.setattr(knowledge.identity_api,'effective_access',lambda *_:{'decision':'DENY'})
    with pytest.raises(PermissionError):
        knowledge.learning_catalog('admin','pg',root=root)


def test_upgrade_adds_guides_without_changing_prior_snapshot_or_user_edits(learning):
    root,db,product=learning
    product['version']='5.0.2'
    old=knowledge.publish('admin','pg',root)
    previous=db.execute('SELECT CONTENT_JSON,CONTENT_DIGEST FROM CX_PLATFORM_KNOWLEDGE').fetchone()
    changed=old['knowledge_ids'][0]
    db.execute("UPDATE ENTITIES SET CONTENT='retained user edit' WHERE ENTITY_ID=?",(changed,));db.commit()
    product['version']='5.0.3'
    current=knowledge.publish('admin','pg',root)
    assert current['preserved_modified_product']==[changed]
    assert len(current['superseded'])==3
    assert db.execute('SELECT CONTENT_JSON,CONTENT_DIGEST FROM CX_PLATFORM_KNOWLEDGE WHERE VERSION=5000002').fetchone()==previous
    assert db.execute('SELECT COUNT(*) FROM ENTITIES WHERE STATUS=\'ACTIVE\'').fetchone()[0]==14


def test_unpublished_guidance_is_not_a_file_fallback(learning):
    root,_,_=learning
    assert knowledge.learning_catalog('admin','pg',root=root)['items']==[]


def test_installed_root_is_resolved_for_default_public_discovery_and_read(learning,monkeypatch):
    root,_,_=learning
    monkeypatch.setattr(knowledge.product_identity,'package_root',lambda *_:root)
    knowledge.publish('admin','pg')
    item=knowledge.learning_catalog('admin','pg',goal='capabilities')['items'][0]
    assert knowledge.read_learning('admin','pg',item['entity_id'],item['content_digest'])['sources']


def test_same_release_source_update_publishes_a_new_snapshot_and_preserves_user_edits(learning):
    root,db,_=learning
    old=knowledge.publish('admin','pg',root)
    original=[tuple(row) for row in db.execute('SELECT CONTENT_JSON,CONTENT_DIGEST FROM CX_PLATFORM_KNOWLEDGE')]
    item=knowledge.learning_catalog('admin','pg',goal='capabilities',root=root)['items'][0]
    edited=old['knowledge_ids'][0]
    db.execute("UPDATE ENTITIES SET CONTENT='Retain my annotation' WHERE ENTITY_ID=?",(edited,));db.commit()
    source=root/'docs/agent-context-assets.md'
    source.write_text(source.read_text()+'\nSource clarification for this release.\n')
    # An installed file is not publication, and an old digest is not current.
    assert knowledge.learning_catalog('admin','pg',root=root)['items']==[]
    with pytest.raises(PermissionError):
        knowledge.read_learning('admin','pg',item['entity_id'],item['content_digest'],root=root)
    current=knowledge.publish('admin','pg',root)
    assert current['snapshot_revision']!=old['snapshot_revision']
    assert set(current['knowledge_ids']).isdisjoint(old['knowledge_ids'])
    assert set(current['superseded'])==set(old['knowledge_ids'])-{edited}
    assert current['preserved_modified_product']==[edited]
    assert [tuple(row) for row in db.execute('SELECT CONTENT_JSON,CONTENT_DIGEST FROM CX_PLATFORM_KNOWLEDGE')][:1]==original
    loaded=knowledge.learning_catalog('admin','pg',goal='capabilities',root=root)['items'][0]
    exact=knowledge.read_learning('admin','pg',loaded['entity_id'],loaded['content_digest'],root=root)
    assert any(s['path']=='docs/agent-context-assets.md' and s['sha256']==hashlib.sha256(source.read_bytes()).hexdigest()
               for s in exact['sources'])
    assert knowledge.publish('admin','pg',root)['knowledge_ids']==current['knowledge_ids']
    assert db.execute('SELECT COUNT(*) FROM CX_PLATFORM_KNOWLEDGE').fetchone()[0]==2


def test_same_release_republication_failure_rolls_back_history_retirement(learning,monkeypatch):
    root,db,_=learning
    old=knowledge.publish('admin','pg',root)
    source=root/'docs/agent-context-assets.md'
    source.write_text(source.read_text()+'\nUpdated prerequisite.\n')
    audit=knowledge.identity_api._audit_tx
    def fail(tx,actor,event,*args):
        if event=='PRODUCT_KNOWLEDGE_PUBLISH':
            raise RuntimeError('Native projection audit unavailable')
        return audit(tx,actor,event,*args)
    monkeypatch.setattr(knowledge.identity_api,'_audit_tx',fail)
    with pytest.raises(RuntimeError,match='projection audit'):
        knowledge.publish('admin','pg',root)
    assert db.execute('SELECT COUNT(*) FROM CX_PLATFORM_KNOWLEDGE').fetchone()[0]==1
    assert {row[0] for row in db.execute("SELECT ENTITY_ID FROM ENTITIES WHERE STATUS='ACTIVE'")}==set(old['knowledge_ids'])
    assert knowledge.learning_catalog('admin','pg',root=root)['items']==[]


def test_superseded_snapshot_cannot_reactivate_when_source_bytes_are_reverted(learning):
    root,db,_=learning
    source=root/'docs/agent-context-assets.md'
    original=source.read_bytes()
    old=knowledge.publish('admin','pg',root)
    source.write_bytes(original+b'\nNew clarification.\n')
    current=knowledge.publish('admin','pg',root)
    source.write_bytes(original)
    with pytest.raises(ValueError,match='Superseded'):
        knowledge.publish('admin','pg',root)
    assert {row[0] for row in db.execute("SELECT ENTITY_ID FROM ENTITIES WHERE STATUS='ACTIVE'")}==set(current['knowledge_ids'])
    assert old['snapshot_revision']!=current['snapshot_revision']
    assert knowledge.learning_catalog('admin','pg',root=root)['items']==[]


def test_withdrawal_of_same_release_history_does_not_retire_current_snapshot(learning):
    from lib import builtin_knowledge
    root,db,_=learning
    old=knowledge.publish('admin','pg',root)
    original_id=db.execute('SELECT KNOWLEDGE_ID FROM CX_PLATFORM_KNOWLEDGE').fetchone()[0]
    source=root/'docs/agent-context-assets.md'
    source.write_text(source.read_text()+'\nNew clarification.\n')
    current=knowledge.publish('admin','pg',root)
    assert builtin_knowledge.withdraw('admin',original_id,'Withdraw historical guide')['archived_projections']==[]
    assert knowledge.learning_catalog('admin','pg',root=root)['items']
    assert {row[0] for row in db.execute("SELECT ENTITY_ID FROM ENTITIES WHERE STATUS='ACTIVE'")}==set(current['knowledge_ids'])
    assert db.execute('SELECT COUNT(*) FROM CX_PLATFORM_KNOWLEDGE').fetchone()[0]==2


def test_legacy_same_release_snapshot_is_preserved_and_untouched_projections_are_superseded(learning):
    root,db,product=learning
    units=platform_learning.bind_sources(knowledge.sections(product,'pg'),root)
    from lib import builtin_knowledge
    # This is the earlier development shape, before source-addressed snapshots.
    def publish_legacy(tx):
        return builtin_knowledge.publish('admin','product-guide:'+product['product_key'],
            dict(product=product,database='pg',sections=units),audience='PUBLIC',scope_type='PUBLIC',
            version=5000003,reason='Retain earlier development snapshot',dialect='pg',edition='community',_tx=tx)
    knowledge.connection.execute_transaction_callback(publish_legacy)
    original=tuple(db.execute('SELECT CONTENT_JSON,CONTENT_DIGEST FROM CX_PLATFORM_KNOWLEDGE').fetchone())
    for unit in units:
        db.execute("INSERT INTO ENTITIES(ENTITY_ID,ENTITY_TYPE,TITLE,CONTENT,SUMMARY,CATEGORY,VISIBILITY,STATUS) "
                   "VALUES(?,'KNOWLEDGE',?,?,?,'PRODUCT','PUBLIC','ACTIVE')",
                   (knowledge._entity_key(product,'pg',unit['key']),unit['title'],unit['content'],unit['title']))
    db.commit()
    current=knowledge.publish('admin','pg',root)
    assert len(current['superseded'])==13
    assert tuple(db.execute("SELECT CONTENT_JSON,CONTENT_DIGEST FROM CX_PLATFORM_KNOWLEDGE WHERE KNOWLEDGE_KEY=?",
                            ('product-guide:'+product['product_key'],)).fetchone())==original
    assert knowledge.learning_catalog('admin','pg',root=root)['items']


@pytest.mark.parametrize('change',('digest','snapshot_revision','package_key'))
def test_invalid_same_release_history_blocks_update_without_altering_current_data(learning,change):
    root,db,_=learning
    old=knowledge.publish('admin','pg',root)
    if change=='digest':
        db.execute("UPDATE CX_PLATFORM_KNOWLEDGE SET CONTENT_DIGEST='tampered'")
    elif change=='package_key':
        db.execute("UPDATE CX_PLATFORM_KNOWLEDGE SET KNOWLEDGE_KEY=KNOWLEDGE_KEY||'bad'")
    else:
        from lib import builtin_knowledge
        package=json.loads(db.execute('SELECT CONTENT_JSON FROM CX_PLATFORM_KNOWLEDGE').fetchone()[0])
        package['content']['snapshot_revision']='f'*64
        digest=builtin_knowledge._digest(package)
        db.execute('UPDATE CX_PLATFORM_KNOWLEDGE SET CONTENT_JSON=?,CONTENT_DIGEST=?,SIGNATURE=?',
                   (json.dumps(package),digest,'LOCAL-SHA256:'+digest))
    db.commit()
    source=root/'docs/agent-context-assets.md'
    source.write_text(source.read_text()+'\nUpdated prerequisite.\n')
    with pytest.raises(ValueError,match='verification failed|version mismatch'):
        knowledge.publish('admin','pg',root)
    assert db.execute('SELECT COUNT(*) FROM CX_PLATFORM_KNOWLEDGE').fetchone()[0]==1
    assert {row[0] for row in db.execute("SELECT ENTITY_ID FROM ENTITIES WHERE STATUS='ACTIVE'")}==set(old['knowledge_ids'])
