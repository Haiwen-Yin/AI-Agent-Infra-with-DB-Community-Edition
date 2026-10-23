"""Memory asset metadata reuses current source authority, never asset grants.

SQLite is an offline relational harness, not three-vendor acceptance evidence.
"""
import re
import sqlite3

import pytest

from lib import agent_assets as assets, context_selection as selection
from lib import continuity_assembly as assembly, continuity_sources as sources
from lib import memory_lifecycle as memory, memory_quality
from lib.continuity_contracts import SourceRef
from lib.continuity_state import ContinuityConflict
from .test_continuity_sources import memory_source
from .test_continuity_work import database


@pytest.fixture
def memory_assets(memory_source, monkeypatch):
    db, source, _ = memory_source
    db.execute("ALTER TABLE CX_PRINCIPALS ADD COLUMN PRINCIPAL_TYPE TEXT DEFAULT 'HUMAN'")
    db.execute('ALTER TABLE CX_PRINCIPALS ADD COLUMN PERMISSION_VERSION INTEGER DEFAULT 1')
    db.execute("INSERT INTO CX_PRINCIPALS(PRINCIPAL_ID,STATUS,PRINCIPAL_TYPE) VALUES('agent','ACTIVE','AGENT')")
    db.execute("INSERT INTO CX_DOMAIN_MEMBERS VALUES('domain','agent','ACTIVE','MEMBER',NULL)")
    for statement in assembly.schema_statements('pg') + selection.schema_statements('pg') + assets.schema_statements('pg'):
        db.execute(statement)
    db.commit()
    # These are role-decision inputs. The real work, domain-membership, memory
    # lifecycle, applicability, binding and assembly readers remain in use.
    grants = {'owner': {'decision': 'ALLOW', 'scopes': ['SELF']},
              'agent': {'decision': 'ALLOW', 'scopes': ['ASSIGNED']},
              'reader': {'decision': 'ALLOW', 'scopes': ['SELF']}}
    decisions = []
    resource_denials = set()

    def access(actor, action, resource=None):
        decisions.append((actor, action, resource))
        if action == 'memory.read':
            if resource is not None and actor in resource_denials:
                return {'decision': 'DENY', 'scopes': ['ALL']}
            return grants.get(actor, {'decision': 'DENY', 'scopes': []})
        return {'decision': 'ALLOW', 'scopes': ['ALL']}

    monkeypatch.setattr(memory.identity_api, 'effective_access', access)
    monkeypatch.setattr(assets.identity_api, '_agent_visible_to', lambda actor, agent: actor in {'owner', 'agent'})
    monkeypatch.setattr(assets.identity_api, '_limit_clause', lambda key: ' LIMIT :' + key)

    def metadata(actor='agent', reference=None, domain='domain'):
        return assets.connection.execute_transaction_callback(
            lambda tx: selection.metadata(tx, actor, domain, reference or source))

    def bind():
        return assets.bind('owner', dict(security_domain_id='domain', agent_id='agent', source=source,
            purpose='Use this assigned memory for current work', reason='Explicit binding', idempotency_key='bind'))['binding_id']

    def build(binding, key='assembly'):
        return assets.assemble('owner', [binding], dict(request_id='request-' + key, security_domain_id='domain',
            purpose='Current task context', query_text='Fact', idempotency_key=key))['assembly_id']

    return dict(db=db, source=source, metadata=metadata, bind=bind, build=build,
                grants=grants, decisions=decisions, resource_denials=resource_denials)


def deny_body_reads(db):
    """SQLite itself rejects even a discarded or wildcard-selected body field."""
    def authorize(action, table, column, database, trigger):
        if action == sqlite3.SQLITE_READ and table.upper() == 'CX_MEMORY_VERSIONS' and column.upper() == 'BODY_TEXT':
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK
    db.set_authorizer(authorize)


def test_human_owned_assigned_memory_bind_inventory_and_planned_assembly(memory_assets):
    state = memory_assets
    db, source = state['db'], state['source']
    assert db.execute("SELECT PRINCIPAL_TYPE FROM CX_PRINCIPALS WHERE PRINCIPAL_ID='owner'").fetchone()[0] == 'HUMAN'
    assert db.execute("SELECT OWNER_PRINCIPAL_ID FROM CX_MEMORY_VERSIONS WHERE VERSION_ID='v1'").fetchone()[0] == 'owner'
    binding = state['bind']()
    deny_body_reads(db)
    try:
        for actor in ('owner', 'agent'):
            result = state['metadata'](actor)
            assert result == {'name': 'Fact', 'description': '', 'source': SourceRef.model_validate(source)}
        result = assets.list_bindings('owner', 'domain', 'agent')
        assert result['next_cursor'] is None
        assert len(result['items']) == 1
        item = result['items'][0]
        assert item['binding_id'] == binding and item['source'] == source and item['name'] == 'Fact'
        assert item['binding_grants_authority'] is False
        assert not {'text', 'body', 'body_text'} & item.keys()
    finally:
        db.set_authorizer(None)
    built = state['build'](binding)
    current = assembly.read_assembly('owner', built)
    assert current['item_count'] == 1 and 'Synthetic body' in current['text']
    assert assets.load('owner', binding)['source'] == source
    assert ('agent', 'memory.read', {'security_domain_id': 'domain'}) in state['decisions']
    assert ('agent', 'memory.read', None) in state['decisions']


def test_metadata_passes_safe_fields_and_runtime_purpose_to_real_authority(memory_assets, monkeypatch):
    state = memory_assets
    original = memory._require_memory_access
    seen = []

    def authorize(actor, version, *, purpose):
        seen.append((actor, dict(version), purpose))
        return original(actor, version, purpose=purpose)

    monkeypatch.setattr(memory, '_require_memory_access', authorize)
    deny_body_reads(state['db'])
    try:
        assert state['metadata']()['name'] == 'Fact'
    finally:
        state['db'].set_authorizer(None)
    assert len(seen) == 1 and seen[0][0] == 'agent' and seen[0][2] == 'RUNTIME_CONTEXT'
    assert seen[0][1]['owner_principal_id'] == 'owner'
    assert seen[0][1]['memory_scope'] == 'AGENT_MEMORY'
    assert set(seen[0][1]) == {'title', 'content_digest', 'lifecycle_state', 'valid_until',
                             'owner_principal_id', 'security_domain_id', 'memory_scope', 'classification'}


@pytest.mark.parametrize('grant', [None, {'decision': 'DENY', 'scopes': ['ASSIGNED']},
    {'decision': 'ALLOW', 'scopes': ['SELF']}, {'decision': 'ALLOW', 'scopes': []},
    {'decision': 'ALLOW', 'scopes': ['NOT_A_SCOPE']}])
def test_no_grant_or_self_only_nonowner_cannot_read_bind_or_keep_assets(memory_assets, grant):
    state = memory_assets
    binding = state['bind']()
    built = state['build'](binding)
    if grant is None:
        del state['grants']['agent']
    else:
        state['grants']['agent'] = grant
    with pytest.raises(PermissionError):
        state['metadata']()
    assert assets.list_bindings('owner', 'domain', 'agent')['items'] == []
    with pytest.raises(PermissionError):
        assets.load('owner', binding)
    with pytest.raises(PermissionError):
        state['build'](binding, 'revoked')
    with pytest.raises(PermissionError):
        assembly.consume('owner', built, lambda text: pytest.fail('Revoked authority must not send'))
    assert state['db'].execute('SELECT COUNT(*) FROM CX_CONTEXT_INPUT_USES').fetchone()[0] == 0
    with pytest.raises(PermissionError):
        state['bind']()


def test_ordinary_nonowner_cannot_read_memory_metadata(memory_assets):
    with pytest.raises(PermissionError, match='Source access denied'):
        memory_assets['metadata']('reader')


@pytest.mark.parametrize('grant', [None, {'decision': 'DENY', 'scopes': ['ALL']}])
def test_operator_memory_grant_revocation_blocks_existing_assets(memory_assets, grant):
    state = memory_assets
    binding = state['bind']()
    built = state['build'](binding)
    if grant is None:
        del state['grants']['owner']
    else:
        state['grants']['owner'] = grant
    with pytest.raises(PermissionError):
        state['metadata']('owner')
    assert assets.list_bindings('owner', 'domain', 'agent')['items'] == []
    with pytest.raises(PermissionError):
        assets.load('owner', binding)
    with pytest.raises(PermissionError):
        assembly.consume('owner', built, lambda text: pytest.fail('Operator grant revocation must block send'))
    assert state['db'].execute('SELECT COUNT(*) FROM CX_CONTEXT_INPUT_USES').fetchone()[0] == 0


def test_resource_scoped_deny_is_not_overridden_by_global_all(memory_assets, monkeypatch):
    state = memory_assets
    state['grants']['agent'] = {'decision': 'ALLOW', 'scopes': ['ALL']}
    state['resource_denials'].add('agent')
    monkeypatch.setattr(memory, '_require_memory_access', lambda *a, **k: pytest.fail('Resource deny must stop before source scope'))
    with pytest.raises(PermissionError, match='Source access denied'):
        state['metadata']()


@pytest.mark.parametrize('actor', ['owner', 'agent'])
@pytest.mark.parametrize('change', ['revoked', 'expired', 'removed', 'inactive_principal'])
def test_current_domain_membership_and_principal_are_required(memory_assets, actor, change):
    state = memory_assets
    binding = state['bind']()
    built = state['build'](binding)
    db = state['db']
    if change == 'revoked':
        db.execute("UPDATE CX_DOMAIN_MEMBERS SET STATUS='REVOKED' WHERE PRINCIPAL_ID=?", (actor,))
    elif change == 'expired':
        db.execute("UPDATE CX_DOMAIN_MEMBERS SET VALID_UNTIL='2000-01-01' WHERE PRINCIPAL_ID=?", (actor,))
    elif change == 'removed':
        db.execute('DELETE FROM CX_DOMAIN_MEMBERS WHERE PRINCIPAL_ID=?', (actor,))
    else:
        db.execute("UPDATE CX_PRINCIPALS SET STATUS='REVOKED' WHERE PRINCIPAL_ID=?", (actor,))
    db.commit()
    with pytest.raises(PermissionError):
        state['metadata'](actor)
    with pytest.raises(PermissionError):
        assets.load('owner', binding, metadata_only=True)
    with pytest.raises(PermissionError):
        assembly.consume('owner', built, lambda text: pytest.fail('Membership revocation must block send'))
    assert db.execute('SELECT COUNT(*) FROM CX_CONTEXT_INPUT_USES').fetchone()[0] == 0


def test_assigned_is_not_a_domain_membership_grant_even_after_workspace_precheck(memory_assets, monkeypatch):
    state = memory_assets
    state['db'].execute("UPDATE CX_DOMAIN_MEMBERS SET STATUS='REVOKED' WHERE PRINCIPAL_ID='agent'")
    state['db'].commit()
    # Exercise the independent memory authority check rather than relying only
    # on the earlier workspace authorization to reject this missing membership.
    monkeypatch.setattr(selection.work, '_authorize', lambda *a, **k: None)
    with pytest.raises(PermissionError, match='Source access denied'):
        state['metadata']()


@pytest.mark.parametrize('change', ['domain_inactive', 'source_cross_domain'])
def test_domain_boundary_cannot_be_bypassed_by_assignment(memory_assets, change):
    state = memory_assets
    if change == 'domain_inactive':
        state['db'].execute("UPDATE CX_SECURITY_DOMAINS SET STATUS='REVOKED'")
    else:
        state['db'].execute("UPDATE CX_MEMORY_VERSIONS SET SECURITY_DOMAIN_ID='another-domain'")
    state['db'].commit()
    with pytest.raises(PermissionError):
        state['metadata']()
    with pytest.raises(PermissionError):
        state['bind']()


def test_exact_record_domain_is_rechecked_after_locator(memory_assets, monkeypatch):
    state = memory_assets
    state['db'].execute("UPDATE CX_MEMORY_VERSIONS SET SECURITY_DOMAIN_ID='another-domain'")
    state['db'].commit()
    monkeypatch.setattr(sources, 'locate', lambda *a: dict(security_domain_id='domain', owner_principal_id='owner'))
    monkeypatch.setattr(memory, '_require_memory_access', lambda *a, **k: pytest.fail('Cross-domain record must fail closed'))
    with pytest.raises(PermissionError, match='Source access denied'):
        state['metadata']()


@pytest.mark.parametrize('scope', sorted(memory.MEMORY_SCOPES))
def test_memory_scope_and_purpose_are_left_to_original_authority(memory_assets, monkeypatch, scope):
    state = memory_assets
    state['db'].execute('UPDATE CX_MEMORY_VERSIONS SET MEMORY_SCOPE=?', (scope,))
    state['db'].commit()
    original = memory._require_memory_access

    def authorize(actor, version, *, purpose):
        assert version['memory_scope'] == scope and purpose == 'RUNTIME_CONTEXT'
        original(actor, version, purpose=purpose)
        raise memory.MemoryLifecycleError('PURPOSE_DENIED', 'Protected authority detail')

    monkeypatch.setattr(memory, '_require_memory_access', authorize)
    with pytest.raises(PermissionError, match='^Source access denied$') as caught:
        state['metadata']()
    assert isinstance(caught.value.__cause__, memory.MemoryLifecycleError)


@pytest.mark.parametrize('state_name', ['CANDIDATE', 'SUPERSEDED', 'EXPIRED', 'ARCHIVED', 'QUARANTINED', 'UNAVAILABLE'])
@pytest.mark.parametrize('changed', ['exact_version', 'current_family'])
def test_blocked_or_forgotten_versions_hide_existing_bindings(memory_assets, state_name, changed):
    state = memory_assets
    binding = state['bind']()
    built = state['build'](binding)
    db = state['db']
    if changed == 'current_family':
        db.execute("INSERT INTO CX_MEMORY_VERSIONS(VERSION_ID,FAMILY_ID,LIFECYCLE_STATE) VALUES('v2','f1',?)", (state_name,))
        db.execute("UPDATE CX_MEMORY_FAMILIES SET CURRENT_VERSION_ID='v2'")
    else:
        db.execute('UPDATE CX_MEMORY_VERSIONS SET LIFECYCLE_STATE=?', (state_name,))
    db.commit()
    with pytest.raises(PermissionError):
        state['metadata']()
    assert assets.list_bindings('owner', 'domain', 'agent')['items'] == []
    with pytest.raises(PermissionError):
        assets.load('owner', binding)
    with pytest.raises(PermissionError):
        assembly.consume('owner', built, lambda text: pytest.fail('Blocked or forgotten memory must not send'))
    assert db.execute('SELECT COUNT(*) FROM CX_CONTEXT_INPUT_USES').fetchone()[0] == 0


@pytest.mark.parametrize('change', ['expired_version', 'future_applicability', 'expired_applicability'])
def test_temporal_ineligibility_is_rechecked_and_hidden_in_inventory(memory_assets, change):
    state = memory_assets
    binding = state['bind']()
    built = state['build'](binding)
    db = state['db']
    if change == 'expired_version':
        db.execute("UPDATE CX_MEMORY_VERSIONS SET VALID_UNTIL='2000-01-01'")
    else:
        start, until = ('2999-01-01', None) if change == 'future_applicability' else (None, '2000-01-01')
        db.execute("INSERT INTO CX_MEMORY_TIME_FACTS VALUES('v1',?,?)", (start, until))
    db.commit()
    with pytest.raises(PermissionError, match='^Source access denied$'):
        state['metadata']()
    assert assets.list_bindings('owner', 'domain', 'agent')['items'] == []
    with pytest.raises((PermissionError, ContinuityConflict)):
        assets.load('owner', binding)
    with pytest.raises((PermissionError, ContinuityConflict)):
        assembly.consume('owner', built, lambda text: pytest.fail('Future/expired memory must not send'))
    assert db.execute('SELECT COUNT(*) FROM CX_CONTEXT_INPUT_USES').fetchone()[0] == 0


@pytest.mark.parametrize('state_name', memory.ORDINARY_VISIBLE_STATES)
def test_existing_ordinary_visible_states_are_not_reclassified(memory_assets, state_name):
    state = memory_assets
    state['db'].execute('UPDATE CX_MEMORY_VERSIONS SET LIFECYCLE_STATE=?', (state_name,))
    state['db'].commit()
    assert state['metadata']()['name'] == 'Fact'
    assert state['bind']()


@pytest.mark.parametrize('change', ['entity_id', 'revision_id', 'content_digest'])
def test_metadata_requires_exact_family_revision_and_digest(memory_assets, change):
    state = memory_assets
    value = dict(state['source'], **{change: '0' * 64 if change == 'content_digest' else 'missing'})
    expected = ContinuityConflict if change == 'content_digest' else PermissionError
    with pytest.raises(expected):
        state['metadata'](reference=value)


def test_metadata_does_not_swallow_unrelated_applicability_conflicts(memory_assets, monkeypatch):
    def fail(tx, revision):
        raise ContinuityConflict('INTEGRITY_ERROR', 'Temporal record is inconsistent')
    monkeypatch.setattr(memory_quality, 'require_applicable', fail)
    with pytest.raises(ContinuityConflict) as caught:
        memory_assets['metadata']()
    assert caught.value.code == 'INTEGRITY_ERROR'


@pytest.mark.parametrize('dialect', ['pg', 'oracle', 'yashandb'])
def test_metadata_uses_portable_exact_binds_and_no_body_for_each_dialect(memory_assets, monkeypatch, dialect):
    state = memory_assets
    monkeypatch.setattr(memory_quality.connection, 'DATABASE_DIALECT', dialect)
    original = assets.connection.execute_transaction_callback
    statements = []

    def run(callback):
        def perform(tx):
            class Observed:
                def query_one(self, sql, params):
                    statements.append(sql)
                    assert set(re.findall(r'(?<!:):([A-Za-z][A-Za-z0-9_]*)', sql)) == set(params)
                    assert not re.search(r'\b(BODY_TEXT|NVL|ROWNUM|SYS_GUID|DUAL)\b|SELECT\s+(?:v\.)?\*', sql, re.I)
                    assert not {'audit', 'by', 'user', 'grant', 'level', 'mode', 'uid', 'resource', 'size'} & set(params)
                    return tx.query_one(sql, params)
            return callback(Observed())
        return original(perform)

    monkeypatch.setattr(assets.connection, 'execute_transaction_callback', run)
    deny_body_reads(state['db'])
    try:
        assert state['metadata']()['name'] == 'Fact'
    finally:
        state['db'].set_authorizer(None)
    assert any('JOIN CX_MEMORY_FAMILIES' in sql and 'CURRENT_VERSION_ID' in sql for sql in statements)
    assert any('CX_MEMORY_TIME_FACTS' in sql for sql in statements)


@pytest.mark.parametrize('family', ['KNOWLEDGE', 'EXPERIENCE', 'SKILL'])
@pytest.mark.parametrize('actor,scopes,allowed', [('owner', ['SELF'], True), ('agent', ['ASSIGNED'], False),
                                               ('agent', ['SELF'], False), ('agent', ['ALL'], True)])
def test_nonmemory_owner_all_boundary_is_unchanged(monkeypatch, family, actor, scopes, allowed):
    monkeypatch.setattr(sources, 'locate', lambda *a: dict(security_domain_id='domain', owner_principal_id='owner'))
    monkeypatch.setattr(selection.work, '_authorize', lambda *a, **k: None)
    monkeypatch.setattr(selection.identity_api, 'effective_access', lambda *a, **k: dict(decision='ALLOW', scopes=scopes))
    value = dict(family=family, entity_id='artifact', revision_id='revision', content_digest='a' * 64)
    class Transaction:
        def query_one(self, sql, params):
            if sql.startswith('SELECT e.ENTITY_ID '):
                return {'entity_id': 'entity'}
            return {'title': 'Artifact', 'content_digest': 'a' * 64}
    if allowed:
        assert selection.metadata(Transaction(), actor, 'domain', value)['name'] == 'Artifact'
    else:
        with pytest.raises(PermissionError, match='Source access denied'):
            selection.metadata(Transaction(), actor, 'domain', value)
