"""Queue-to-publication and later-reader knowledge disclosure regressions."""
import json

import pytest

from .test_business_channel_runtime import store, enqueue
from lib import business_channel_runtime as business, identity_api

_effective_access = identity_api.effective_access
_require = identity_api._require


@pytest.fixture
def sources(store, monkeypatch):
    item = {'entity_id': 'K1', 'title': 'Product', 'content': 'private source', 'digest': 'd1'}
    monkeypatch.setattr(business.answer_planning, 'retrieve', lambda *a, **kw: {
        'status': 'MATCHED', 'items': [item], 'missing_parts': [],
        'answer_metadata': {'evidence_status': 'MATCHED', 'policy_revision': 'answer-evidence-v1'}})
    monkeypatch.setattr(business.knowledge_grounding, 'citation', lambda *a: item)
    return store


def payload(db):
    return json.loads(db.execute('SELECT INPUT_JSON FROM CX_RUNTIME_EXECUTIONS').fetchone()[0])


def test_unapproved_profile_gets_extracts_without_source_in_model_messages(sources):
    sources.execute("UPDATE CX_PORTAL_KNOWLEDGE_POLICY SET DISCLOSURE_PROFILES_JSON='[]'")
    enqueue()
    value = payload(sources)
    assert 'private source' in value['knowledge_reply']
    assert 'private source' not in json.dumps(value['messages'])


@pytest.mark.parametrize('change', [
    "UPDATE CX_PORTAL_KNOWLEDGE_POLICY SET VERSION=2",
    "UPDATE CX_NATIVE_AGENTS SET LLM_PROFILE_ID='other'",
    "UPDATE CX_PORTAL_KNOWLEDGE_POLICY SET DISCLOSURE_PROFILES_JSON='[]'",
])
def test_revocation_between_enqueue_and_send_denies(sources, change):
    result = enqueue()
    sources.execute("UPDATE CX_RUNTIME_EXECUTIONS SET STATUS='CLAIMED'")
    sources.execute(change)
    with pytest.raises(PermissionError):
        business.validate_response('agent', 'channel', result['execution_id'])


def test_changed_knowledge_blocks_result_and_later_read(sources, monkeypatch):
    result = enqueue()
    sources.execute("UPDATE CX_RUNTIME_EXECUTIONS SET STATUS='CLAIMED'")
    def changed(*args):
        raise business.knowledge_grounding.GroundingError('changed')
    monkeypatch.setattr(business.knowledge_grounding, 'citation', changed)
    with pytest.raises(business.knowledge_grounding.GroundingError):
        business.validate_response('agent', 'channel', result['execution_id'])
    with pytest.raises(business.knowledge_grounding.GroundingError):
        business.require_result_reader('human', 'agent', result['execution_id'])


def add_reader(db):
    db.execute("INSERT INTO CX_PRINCIPALS VALUES ('reader','HUMAN','ACTIVE')")
    db.execute("INSERT INTO CX_CHANNEL_MEMBERS VALUES ('cm3','channel','reader','MEMBER','ACTIVE',NULL)")
    db.execute("INSERT INTO CX_DOMAIN_MEMBERS VALUES ('dm3','domain','reader','ACTIVE',NULL)")


def deny_reader(monkeypatch):
    def citation(actor, *args):
        if actor == 'reader':
            raise PermissionError('not authorized for source')
        return {}
    monkeypatch.setattr(business.knowledge_grounding, 'citation', citation)


def test_audience_intersection_excludes_private_source(sources, monkeypatch):
    add_reader(sources)
    deny_reader(monkeypatch)
    enqueue()
    assert not payload(sources).get('knowledge_citations')
    assert 'private source' not in json.dumps(payload(sources))


def test_new_member_cannot_receive_or_read_previous_grounded_reply(sources, monkeypatch):
    result = enqueue()
    sources.execute("UPDATE CX_RUNTIME_EXECUTIONS SET STATUS='CLAIMED'")
    add_reader(sources)
    deny_reader(monkeypatch)
    with pytest.raises(PermissionError):
        business.validate_response('agent', 'channel', result['execution_id'])
    with pytest.raises(PermissionError):
        business.require_result_reader('reader', 'agent', result['execution_id'])


def test_knowledge_only_does_not_fall_back_to_model(store):
    store.execute("UPDATE CX_PORTAL_KNOWLEDGE_POLICY SET MODE='KNOWLEDGE_ONLY',ALLOW_MODEL_SUPPLEMENT='N'")
    enqueue()
    assert 'Insufficient knowledge' in payload(store)['knowledge_reply']


def test_no_match_uses_model_without_disclosure_approval(store):
    store.execute("UPDATE CX_PORTAL_KNOWLEDGE_POLICY SET DISCLOSURE_PROFILES_JSON='[]'")
    result = enqueue()
    value = payload(store)
    assert not value.get('knowledge_reply')
    assert not value.get('knowledge_citations')
    assert 'general model knowledge' in value['messages'][0]['content']
    store.execute("UPDATE CX_RUNTIME_EXECUTIONS SET STATUS='CLAIMED'")
    business.validate_response('agent', 'channel', result['execution_id'])


def test_revoked_model_supplement_policy_blocks_queued_general_answer(store):
    result = enqueue()
    store.execute("UPDATE CX_RUNTIME_EXECUTIONS SET STATUS='CLAIMED'")
    store.execute("UPDATE CX_PORTAL_KNOWLEDGE_POLICY SET ALLOW_MODEL_SUPPLEMENT='N'")
    with pytest.raises(PermissionError):
        business.validate_response('agent', 'channel', result['execution_id'])


def test_filtered_private_sources_use_general_model_only(sources, monkeypatch):
    add_reader(sources)
    deny_reader(monkeypatch)
    enqueue()
    value = payload(sources)
    assert not value.get('knowledge_reply')
    assert not value.get('knowledge_citations')
    assert 'private source' not in json.dumps(value['messages'])
    assert 'general model knowledge' in value['messages'][0]['content']


def test_legacy_queued_knowledge_is_not_sent(sources):
    result = enqueue()
    value = payload(sources)
    value.pop('knowledge_contract')
    sources.execute("UPDATE CX_RUNTIME_EXECUTIONS SET INPUT_JSON=?,STATUS='CLAIMED'", (json.dumps(value),))
    with pytest.raises(PermissionError):
        business.validate_response('agent', 'channel', result['execution_id'])


@pytest.mark.parametrize('status,visible', [('CLAIMED', True), ('COMPLETED', True), ('FAILED', False)])
def test_model_source_annotation_comes_from_persisted_execution(store, status, visible):
    result = enqueue()
    store.execute('UPDATE CX_RUNTIME_EXECUTIONS SET STATUS=?', (status,))
    message = {'principal_id': 'agent', 'channel_id': 'channel', 'message_type': 'AGENT_RESPONSE',
               'body_text': 'General answer', 'reference_json': json.dumps({'execution_id': result['execution_id']})}
    business.filter_messages('human', [message])
    assert (message.get('answer_source') == 'MODEL_SUPPLEMENT') is visible
    assert message['body_text'] == 'General answer'


def test_grounded_reply_cannot_forge_model_source_annotation(sources):
    result = enqueue()
    sources.execute("UPDATE CX_RUNTIME_EXECUTIONS SET STATUS='COMPLETED'")
    message = {'principal_id': 'agent', 'channel_id': 'channel', 'message_type': 'AGENT_RESPONSE',
               'body_text': 'Grounded', 'answer_source': 'MODEL_SUPPLEMENT',
               'reference_json': json.dumps({'execution_id': result['execution_id'], 'answer_source': 'MODEL_SUPPLEMENT'})}
    business.filter_messages('human', [message])
    assert 'answer_source' not in message


def test_previous_verified_execution_restores_general_source(store):
    result = enqueue()
    value = payload(store)
    value.pop('answer_source')
    store.execute("UPDATE CX_RUNTIME_EXECUTIONS SET STATUS='COMPLETED',INPUT_JSON=?", (json.dumps(value),))
    assert business.require_result_reader('human', 'agent', result['execution_id']) == 'MODEL_SUPPLEMENT'


def test_message_page_reuses_permissions_but_next_read_observes_revocation(store, monkeypatch):
    result = enqueue()
    store.execute("UPDATE CX_RUNTIME_EXECUTIONS SET STATUS='COMPLETED'")
    store.executescript('''
      ALTER TABLE CX_PRINCIPALS ADD COLUMN PERMISSION_VERSION INTEGER DEFAULT 1;
      CREATE TABLE CX_USER_ROLES(PRINCIPAL_ID TEXT,ROLE_CODE TEXT,STATUS TEXT,VALID_UNTIL TEXT);
      CREATE TABLE CX_ROLE_TEMPLATES(ROLE_CODE TEXT,PERMISSIONS_JSON TEXT,DATA_SCOPES_JSON TEXT);
      CREATE TABLE CX_USER_PERMISSION_OVERRIDES(PRINCIPAL_ID TEXT,RESOURCE_ACTION TEXT,EFFECT TEXT,
        DATA_SCOPE TEXT,SECURITY_DOMAIN_ID TEXT,REASON TEXT,GRANTED_BY TEXT,VALID_UNTIL TEXT,CREATED_AT TEXT);
      CREATE TABLE CX_DELEGATIONS(DELEGATION_ID TEXT,GRANTOR_PRINCIPAL_ID TEXT,GRANTEE_PRINCIPAL_ID TEXT,
        PERMISSIONS_JSON TEXT,DATA_SCOPE TEXT,STATUS TEXT,VALID_UNTIL TEXT,CREATED_AT TEXT);
      INSERT INTO CX_USER_ROLES VALUES('human','END_USER','ACTIVE',NULL);
      INSERT INTO CX_ROLE_TEMPLATES VALUES('END_USER','["channels.read"]','["OWN"]');
    ''')
    monkeypatch.setattr(identity_api, 'effective_access', _effective_access)
    monkeypatch.setattr(identity_api, '_require', _require)
    sql = []
    store.set_trace_callback(sql.append)
    def page():
        return [{'principal_id': 'agent', 'channel_id': 'channel', 'message_type': 'AGENT_RESPONSE',
                 'body_text': 'General answer', 'reference_json': json.dumps({'execution_id': result['execution_id']})}
                for _ in range(50)]
    visible = business.filter_messages('human', page())
    assert all(item['body_text'] == 'General answer' for item in visible)
    # channels.read and domains.manage each resolve their role only once.
    assert sum('FROM CX_USER_ROLES' in statement for statement in sql) == 2
    # Actual reply provenance and domain membership remain checked per item.
    assert sum('FROM CX_RUNTIME_EXECUTIONS' in statement for statement in sql) == 50
    assert sum('FROM CX_DOMAIN_MEMBERS' in statement for statement in sql) == 50
    store.execute("INSERT INTO CX_USER_PERMISSION_OVERRIDES VALUES('human','channels.read','DENY','NONE',NULL,'revoked','admin',NULL,CURRENT_TIMESTAMP)")
    sql.clear()
    denied = business.filter_messages('human', page())
    assert all(item['body_text'] != 'General answer' and item['reference_json'] == '{}' for item in denied)
    assert sum('FROM CX_USER_ROLES' in statement for statement in sql) == 1


def test_message_page_does_not_cache_knowledge_authorization(sources, monkeypatch):
    result = enqueue()
    sources.execute("UPDATE CX_RUNTIME_EXECUTIONS SET STATUS='COMPLETED'")
    calls = []
    def citation(*args):
        calls.append(args)
        if len(calls) > 2:
            raise business.knowledge_grounding.GroundingError('source revoked')
        return {}
    monkeypatch.setattr(business.knowledge_grounding, 'citation', citation)
    messages = [{'principal_id': 'agent', 'channel_id': 'channel', 'message_type': 'AGENT_RESPONSE',
                 'body_text': 'Grounded answer', 'reference_json': json.dumps({'execution_id': result['execution_id']})}
                for _ in range(2)]
    business.filter_messages('human', messages)
    assert messages[0]['body_text'] == 'Grounded answer'
    assert messages[1]['body_text'] != 'Grounded answer'
