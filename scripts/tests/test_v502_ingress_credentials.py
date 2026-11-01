"""Real capacity transitions and original credentials for supported ingresses.

SQLite relational fixtures and an independent synthetic transport are not
native-database or real-provider acceptance evidence.
"""
import base64
import hashlib
import io
import json
from datetime import timedelta
from types import SimpleNamespace

import pytest

from lib import answer_quality as quality, config, connection, continuity_bindings
from lib import identity_api, managed_inputs, model_credentials, model_dispatch
from lib import model_endpoint_capacity as capacity
from lib import native_runtime, portal_grounding, task_continuity
from lib.agent_extension_schema import TABLES
from .test_v502_model_capacity import Transaction, admission, claim, ledger


@pytest.fixture
def ingress(ledger, monkeypatch):
    db, group_id, clock, _ = ledger
    db.executescript("""
        ALTER TABLE CX_PRINCIPALS ADD COLUMN MFA_REQUIRED TEXT DEFAULT 'N';
        ALTER TABLE CX_PRINCIPALS ADD COLUMN PERMISSION_VERSION INTEGER DEFAULT 1;
        ALTER TABLE CX_PRINCIPALS ADD COLUMN PRINCIPAL_TYPE TEXT DEFAULT 'HUMAN';
        INSERT INTO CX_PRINCIPALS(PRINCIPAL_ID,STATUS,PRINCIPAL_TYPE) VALUES('agent','ACTIVE','AGENT');
        ALTER TABLE CX_LLM_PROVIDER_PROFILES ADD COLUMN API_KEY_CIPHER TEXT;
        ALTER TABLE CX_LLM_PROVIDER_PROFILES ADD COLUMN HEALTH_STATE TEXT DEFAULT 'HEALTHY';
        CREATE TABLE CX_WEB_SESSIONS(SESSION_DIGEST TEXT PRIMARY KEY,PRINCIPAL_ID TEXT,AUTH_METHOD TEXT,
            MFA_LEVEL TEXT,NODE_ID TEXT,PERMISSION_VERSION INTEGER,CREATED_AT TIMESTAMP,EXPIRES_AT TIMESTAMP,REVOKED_AT TIMESTAMP);
        CREATE TABLE CX_WEB_SESSION_POLICIES(POLICY_KEY TEXT PRIMARY KEY,ABSOLUTE_TIMEOUT_SECONDS INTEGER);
        INSERT INTO CX_WEB_SESSION_POLICIES VALUES('PORTAL',3600),('DASHBOARD',3600);
        CREATE TABLE CX_PORTAL_KNOWLEDGE_POLICY(POLICY_ID TEXT PRIMARY KEY,MODE TEXT,ALLOW_MODEL_SUPPLEMENT TEXT,
            DISCLOSURE_PROFILES_JSON TEXT,VERSION INTEGER);
        INSERT INTO CX_PORTAL_KNOWLEDGE_POLICY VALUES('DEFAULT','KNOWLEDGE_FIRST','Y','["profile"]',1);
        CREATE TABLE CX_PORTAL_LLM_ALLOWLIST(POLICY_ID TEXT,PROFILE_ID TEXT,STATUS TEXT);
        INSERT INTO CX_PORTAL_LLM_ALLOWLIST VALUES('DEFAULT','profile','ACTIVE');
        CREATE TABLE CX_PORTAL_PAGE_LEASES(LEASE_ID TEXT,SESSION_DIGEST TEXT,STATUS TEXT,LEASE_EXPIRES_AT TIMESTAMP);
        CREATE TABLE CX_SECURITY_DOMAINS(SECURITY_DOMAIN_ID TEXT PRIMARY KEY,STATUS TEXT);
        INSERT INTO CX_SECURITY_DOMAINS VALUES('domain','ACTIVE');
        CREATE TABLE CX_DOMAIN_MEMBERS(SECURITY_DOMAIN_ID TEXT,PRINCIPAL_ID TEXT,STATUS TEXT,MEMBERSHIP_TIER TEXT,VALID_UNTIL TIMESTAMP);
        INSERT INTO CX_DOMAIN_MEMBERS VALUES('domain','origin-a','ACTIVE','OWNER',NULL);
        CREATE TABLE AGENT_REGISTRY(AGENT_ID TEXT PRIMARY KEY,STATUS TEXT);
        INSERT INTO AGENT_REGISTRY VALUES('agent','ACTIVE');
        CREATE TABLE CX_NATIVE_AGENTS(AGENT_ID TEXT PRIMARY KEY,LLM_PROFILE_ID TEXT,STATUS TEXT);
        INSERT INTO CX_NATIVE_AGENTS VALUES('agent','profile','ACTIVE');
        CREATE TABLE TEST_SOURCES(ENTITY_ID TEXT PRIMARY KEY,CONTENT_DIGEST TEXT,STATUS TEXT);
        INSERT INTO TEST_SOURCES VALUES('source','source-digest','ACTIVE');
        CREATE TABLE TEST_PERMISSIONS(ACTOR_ID TEXT,ACTION_NAME TEXT,DECISION TEXT);
        CREATE TABLE CX_AGENT_INSTANCES(INSTANCE_ID TEXT PRIMARY KEY,AGENT_ID TEXT,SECURITY_DOMAIN_ID TEXT,
            STATUS TEXT,FENCING_TOKEN INTEGER,LEASE_EXPIRES_AT TIMESTAMP);
        CREATE TABLE CX_AGENT_ACCESS_TOKENS(TOKEN_DIGEST TEXT PRIMARY KEY,AGENT_ID TEXT,INSTANCE_ID TEXT,
            SCOPE_JSON TEXT,LEASE_DIGEST TEXT,FENCING_TOKEN INTEGER,EXPIRES_AT TIMESTAMP,REVOKED_AT TIMESTAMP);
        CREATE TABLE CX_RUNTIME_ISOLATION_CONTRACTS(AGENT_ID TEXT,INSTANCE_ID TEXT,STATUS TEXT);
    """)
    for name in ('CX_PROVIDER_CAP_PROBES', 'CX_PROVIDER_PARAM_CONTRACTS', 'CX_MANAGED_INPUT_ASSETS', 'CX_MANAGED_ASSET_USES'):
        db.execute('CREATE TABLE ' + name + '(' + TABLES[name]['definition'] + ')')
    now = identity_api._now()
    session_digest = hashlib.sha256(b'synthetic-original-session').hexdigest()
    db.execute('INSERT INTO CX_WEB_SESSIONS VALUES(?,?,?,?,?,?,?,?,NULL)',
               (session_digest, 'origin-a', 'LOCAL:PORTAL', 'NONE', 'test-node', 1,
                now.isoformat(sep=' '), (now + timedelta(minutes=30)).isoformat(sep=' ')))
    session = dict(session_digest=session_digest, principal_id='origin-a', agent_id='agent',
                   permission_version=1, auth_method='LOCAL:PORTAL')
    db.commit()
    reader = Transaction(db)
    monkeypatch.setattr(connection, 'execute_query_one', reader.query_one)
    monkeypatch.setattr(connection, 'execute_query', reader.query)
    # This fixture retains original credential SQL and normal domain checks.
    # Entry and action policies use a small mutable relational policy fixture.
    def effective_access(actor, action, **kwargs):
        record = reader.query_one('SELECT DECISION FROM TEST_PERMISSIONS WHERE ACTOR_ID=:actor AND ACTION_NAME=:action_name',
                                  {'actor': actor, 'action_name': action})
        return {'decision': record['decision'] if record else 'ALLOW'}
    monkeypatch.setattr(identity_api, 'effective_access', effective_access)
    monkeypatch.setattr(identity_api, 'entry_allowed', lambda actor, entry: effective_access(actor, entry)['decision'] == 'ALLOW')
    monkeypatch.setattr(identity_api, '_agent_visible_to', lambda actor, agent, **_options: True)
    monkeypatch.setattr(config, 'get_config', lambda: SimpleNamespace(llm=config.LLMConfig(request_timeout_seconds=180)))
    monkeypatch.setattr(portal_grounding.answer_planning, 'retrieve',
                        lambda *args, **kwargs: {'status': 'NO_MATCH', 'items': [], 'missing_parts': []})
    def require_reader(actor, agent):
        actor_record = reader.query_one('SELECT STATUS FROM CX_PRINCIPALS WHERE PRINCIPAL_ID=:actor', {'actor': actor})
        agent_record = reader.query_one('SELECT STATUS FROM AGENT_REGISTRY WHERE AGENT_ID=:agent_id', {'agent_id': agent})
        if not actor_record or actor_record['status'] != 'ACTIVE' or not agent_record or agent_record['status'] != 'ACTIVE':
            raise PermissionError('Original reader or Agent changed')
    def citation(actor, agent, source_id, expected_digest, **_options):
        require_reader(actor, agent)
        record = reader.query_one('SELECT * FROM TEST_SOURCES WHERE ENTITY_ID=:source_id', {'source_id': source_id})
        if not record or record['status'] != 'ACTIVE' or record['content_digest'] != expected_digest:
            raise PermissionError('Original source changed')
        return record
    from lib import agent_registration, agent_gateway_api
    monkeypatch.setattr(portal_grounding.knowledge_grounding, 'require_reader', require_reader)
    monkeypatch.setattr(portal_grounding.knowledge_grounding, 'citation', citation)
    monkeypatch.setattr(agent_registration, 'get_registration',
        lambda agent: reader.query_one('SELECT * FROM AGENT_REGISTRY WHERE AGENT_ID=:agent_id', {'agent_id': agent}))
    monkeypatch.setattr(agent_gateway_api, '_compliance_allows', lambda *args: True)
    # Synthetic encrypted values keep the fixture outside all local key stores.
    encode = lambda value: 'fixture:' + json.dumps(value)
    decode = lambda value: json.loads(value.removeprefix('fixture:'))
    monkeypatch.setattr(managed_inputs, 'encrypt_section', encode)
    monkeypatch.setattr(managed_inputs, 'decrypt_section', decode)
    monkeypatch.setattr(quality, 'encrypt_section', encode)
    monkeypatch.setattr(quality, 'decrypt_section', decode)
    sends, after_response = [], [None]
    class Response:
        def __init__(self, content):
            self.body = io.BytesIO(content)
        def __enter__(self):
            return self
        def __exit__(self, *args):
            self.body.close()
            return False
        def read(self, size=-1):
            if after_response[0] is not None:
                callback, after_response[0] = after_response[0], None
                callback()
            return self.body.read(size)
    def send(request, **kwargs):
        sends.append(json.loads(request.data))
        return Response(json.dumps({'model': 'model', 'choices': [{'message': {'content': 'Quantum tunneling crosses a potential barrier.'},
                                  'finish_reason': 'stop'}], 'usage': {'total_tokens': 12}}).encode())
    monkeypatch.setattr(model_dispatch, 'open_controlled', send)
    monkeypatch.setattr(native_runtime.urllib.request, 'urlopen',
                        lambda *args, **kwargs: pytest.fail('Selected resource bypassed controlled transport'))
    return SimpleNamespace(db=db, group_id=group_id, clock=clock, session=session, digest=session_digest,
                           sends=sends, after_response=after_response, encode=encode)


def mutate_after_admission(monkeypatch, state, sql):
    original = capacity.admit
    def admit(*args, **kwargs):
        record = original(*args, **kwargs)
        state.db.execute(sql)
        state.db.commit()
        return record
    monkeypatch.setattr(capacity, 'admit', admit)


def read_admissions(state):
    return list(state.db.execute('SELECT * FROM CX_MODEL_ADMISSIONS ORDER BY CREATED_AT_MS,ADMISSION_ID'))


def occupy_other_origin(state):
    record = capacity.admit('origin-b', state.group_id, admission('other-request', 'b'))
    return capacity.begin_dispatch('origin-b', record['admission_id'], claim(record), reauthorize=lambda tx, item: None)


def portal_answer(state, **changes):
    return portal_grounding.answer(dict(state.session, **changes), 'What is quantum tunneling?',
                                   native_runtime._llm_profile('profile'), supplement=True)


def add_asset(state, *, image=False):
    content = b'synthetic input'
    state.db.execute("INSERT INTO CX_MANAGED_INPUT_ASSETS(ASSET_ID,OWNER_ID,SECURITY_DOMAIN_ID,FILE_NAME,MEDIA_TYPE,BYTE_COUNT,CONTENT_DIGEST,CONTENT_CIPHER,EXTRACTED_CIPHER,STATUS) VALUES('asset','origin-a','domain','input.txt',:media,:count,:digest,:cipher,:extracted,'ACTIVE')",
        {'media': 'image/png' if image else 'text/plain', 'count': len(content), 'digest': hashlib.sha256(content).hexdigest(),
         'cipher': state.encode({'content': base64.b64encode(content).decode()}), 'extracted': state.encode({'text': 'Synthetic document.'})})
    if image:
        state.db.execute("INSERT INTO CX_PROVIDER_CAP_PROBES(PROBE_ID,PROFILE_ID,PROFILE_VERSION,MODEL_ID,API_DIALECT,CAPABILITY_KEY,STATUS,PARAMETER_DIGEST,SCHEMA_DIGEST,EXPIRES_AT,ACTOR_ID) VALUES('image-probe','profile',1,'model','OPENAI','IMAGE_INPUT','VERIFIED',:digest,:digest,:expires,'origin-a')",
                         {'digest': 'a' * 64, 'expires': (identity_api._now() + timedelta(hours=1)).isoformat(sep=' ')})
    state.db.commit()


def managed_query(state):
    with model_credentials.server_session(state.session):
        return managed_inputs.query('origin-a', 'asset', 'profile', 'Explain the supplied input.')


def add_machine_credential(state):
    token_digest = hashlib.sha256(b'synthetic-machine-token').hexdigest()
    expiry = (identity_api._now() + timedelta(minutes=30)).isoformat(sep=' ')
    state.db.execute("INSERT INTO CX_AGENT_INSTANCES VALUES('instance','origin-a','domain','ACTIVE',7,?)", (expiry,))
    state.db.execute("INSERT INTO CX_AGENT_ACCESS_TOKENS VALUES(?,'origin-a','instance','[\"model_gateway.forward\"]','lease',7,?,NULL)", (token_digest, expiry))
    state.db.commit()
    return dict(instance_id='instance', fencing_token=7, token_digest=token_digest)


@pytest.mark.parametrize('sql', [
    "UPDATE CX_WEB_SESSIONS SET REVOKED_AT=CURRENT_TIMESTAMP",
    "UPDATE CX_WEB_SESSIONS SET EXPIRES_AT='2000-01-01 00:00:00'",
    "UPDATE CX_WEB_SESSIONS SET CREATED_AT='2000-01-01 00:00:00'",
    "UPDATE CX_WEB_SESSIONS SET MFA_LEVEL='SETUP'",
    "UPDATE CX_PRINCIPALS SET MFA_REQUIRED='Y' WHERE PRINCIPAL_ID='origin-a'",
    "UPDATE CX_PRINCIPALS SET PERMISSION_VERSION=2 WHERE PRINCIPAL_ID='origin-a'",
    "UPDATE CX_WEB_SESSIONS SET AUTH_METHOD='LOCAL:DASHBOARD'",
    "UPDATE CX_WEB_SESSIONS SET NODE_ID='another-node'",
    "INSERT INTO TEST_PERMISSIONS VALUES('origin-a','PORTAL','DENY')",
])
def test_original_session_binding_rechecks_all_authoritative_facts(ingress, sql):
    binding = model_credentials.capture('origin-a', session=ingress.session)
    assert binding.credential_digest == ingress.digest
    ingress.db.execute(sql)
    ingress.db.commit()
    with pytest.raises(PermissionError):
        connection.execute_transaction_callback(lambda tx: model_credentials.recheck(tx, binding))


def test_web_capture_requires_server_identity_and_preserves_legacy_no_credential(ingress):
    with pytest.raises(PermissionError):
        model_credentials.capture('origin-b', session=ingress.session)
    with model_credentials.server_session(ingress.session):
        assert model_credentials.capture('origin-a').credential_digest == ingress.digest
    assert model_credentials.capture('origin-a') is None


@pytest.mark.parametrize('sql', [
    "UPDATE CX_AGENT_ACCESS_TOKENS SET REVOKED_AT=CURRENT_TIMESTAMP",
    "UPDATE CX_AGENT_ACCESS_TOKENS SET EXPIRES_AT='2000-01-01 00:00:00'",
    "UPDATE CX_AGENT_ACCESS_TOKENS SET SCOPE_JSON='[]'",
    "UPDATE CX_AGENT_INSTANCES SET FENCING_TOKEN=8",
    "UPDATE CX_AGENT_INSTANCES SET STATUS='REVOKED'",
    "INSERT INTO CX_RUNTIME_ISOLATION_CONTRACTS VALUES('origin-a','instance','REVOKED')",
])
def test_original_machine_token_scope_instance_and_fence_are_rechecked(ingress, sql):
    transport = add_machine_credential(ingress)
    with continuity_bindings.authenticated_transport(transport):
        binding = model_credentials.capture('origin-a', required_scope='model_gateway.forward')
        assert binding.credential_digest == transport['token_digest']
        with model_credentials.server_session(ingress.session), pytest.raises(PermissionError, match='Mixed'):
            model_credentials.capture('origin-a')
    ingress.db.execute(sql)
    ingress.db.commit()
    with pytest.raises(PermissionError):
        connection.execute_transaction_callback(lambda tx: model_credentials.recheck(tx, binding))


def test_selected_portal_completes_with_original_session_ledger_receipt(ingress):
    result = portal_answer(ingress)
    assert 'Quantum tunneling' in result['reply'] and len(ingress.sends) == 1
    admission = read_admissions(ingress)[0]
    assert admission['source_kind'] == 'PORTAL' and admission['credential_digest'] == ingress.digest
    assert admission['status'] == 'COMPLETED'
    assert admission['source_id'] == admission['source_attempt_id']
    assert ingress.db.execute('SELECT STATUS FROM CX_MODEL_CAP_ATTEMPTS').fetchone()['status'] == 'COMPLETED'


@pytest.mark.parametrize('sql', [
    "UPDATE CX_WEB_SESSIONS SET REVOKED_AT=CURRENT_TIMESTAMP",
    "UPDATE CX_PORTAL_KNOWLEDGE_POLICY SET VERSION=2",
    "UPDATE CX_PORTAL_KNOWLEDGE_POLICY SET DISCLOSURE_PROFILES_JSON='[]'",
    "UPDATE CX_PORTAL_LLM_ALLOWLIST SET STATUS='REVOKED'",
    "UPDATE AGENT_REGISTRY SET STATUS='REVOKED'",
    "UPDATE CX_LLM_PROVIDER_PROFILES SET API_KEY_CIPHER='changed' WHERE PROFILE_ID='profile'",
])
def test_portal_rechecks_original_credential_profile_policy_and_agent_before_send(ingress, monkeypatch, sql):
    mutate_after_admission(monkeypatch, ingress, sql)
    with pytest.raises(Exception) as failure:
        portal_answer(ingress)
    assert getattr(failure.value, 'model_not_dispatched', False)
    assert not ingress.sends
    assert read_admissions(ingress)[0]['status'] == 'REJECTED'
    assert ingress.db.execute('SELECT COUNT(*) AS n FROM CX_MODEL_CAP_ATTEMPTS').fetchone()['n'] == 0


def test_portal_original_source_and_page_lease_are_rechecked(ingress, monkeypatch):
    monkeypatch.setattr(portal_grounding.answer_planning, 'retrieve', lambda *args, **kwargs:
                        {'status': 'MATCHED', 'items': [{'entity_id': 'source', 'digest': 'source-digest',
                         'title': 'Synthetic source', 'content': 'Quantum tunneling explanation.'}], 'missing_parts': []})
    ingress.db.execute("INSERT INTO CX_PORTAL_PAGE_LEASES VALUES('page',?,'ACTIVE',?)",
                       (ingress.digest, (identity_api._now() + timedelta(minutes=5)).isoformat(sep=' ')))
    ingress.db.commit()
    mutate_after_admission(monkeypatch, ingress, "UPDATE TEST_SOURCES SET STATUS='REVOKED'")
    with pytest.raises(Exception) as failure:
        portal_answer(ingress, portal_page_lease_id='page')
    assert getattr(failure.value, 'model_not_dispatched', False) and not ingress.sends
    assert read_admissions(ingress)[0]['status'] == 'REJECTED'


def test_portal_page_lease_expiry_blocks_dispatch(ingress, monkeypatch):
    ingress.db.execute("INSERT INTO CX_PORTAL_PAGE_LEASES VALUES('page',?,'ACTIVE',?)",
                       (ingress.digest, (identity_api._now() + timedelta(minutes=5)).isoformat(sep=' ')))
    ingress.db.commit()
    mutate_after_admission(monkeypatch, ingress, "UPDATE CX_PORTAL_PAGE_LEASES SET STATUS='RELEASED'")
    with pytest.raises(Exception) as failure:
        portal_answer(ingress, portal_page_lease_id='page')
    assert getattr(failure.value, 'model_not_dispatched', False) and not ingress.sends
    assert read_admissions(ingress)[0]['status'] == 'REJECTED'


def test_missing_original_session_cannot_send_selected_portal_resource(ingress):
    with pytest.raises(PermissionError, match='authenticated supported dispatch'):
        portal_answer(ingress, session_digest='')
    assert not ingress.sends and read_admissions(ingress) == []


def test_completed_portal_transport_does_not_publish_after_original_session_revocation(ingress):
    def revoke():
        ingress.db.execute('UPDATE CX_WEB_SESSIONS SET REVOKED_AT=CURRENT_TIMESTAMP')
        ingress.db.commit()
    ingress.after_response[0] = revoke
    with pytest.raises(PermissionError):
        portal_answer(ingress)
    assert len(ingress.sends) == 1
    assert read_admissions(ingress)[0]['status'] == 'COMPLETED'


def test_selected_managed_input_keeps_real_use_and_capacity_receipts(ingress):
    add_asset(ingress)
    result = managed_query(ingress)
    assert result['status'] == 'SUCCEEDED' and len(ingress.sends) == 1
    use = ingress.db.execute('SELECT * FROM CX_MANAGED_ASSET_USES').fetchone()
    admission = read_admissions(ingress)[0]
    assert use['status'] == 'SUCCEEDED' and admission['status'] == 'COMPLETED'
    assert admission['source_kind'] == 'EXTERNAL' and admission['source_id'] == use['use_id']
    assert admission['credential_digest'] == ingress.digest


def test_selected_machine_managed_input_preserves_original_scope_and_credential_hash(ingress):
    add_asset(ingress)
    transport = add_machine_credential(ingress)
    with continuity_bindings.authenticated_transport(transport):
        result = managed_inputs.query('origin-a', 'asset', 'profile', 'Explain this input.')
    assert result['status'] == 'SUCCEEDED' and len(ingress.sends) == 1
    assert read_admissions(ingress)[0]['credential_digest'] == transport['token_digest']


def test_machine_managed_dispatch_rechecks_the_original_scope_after_admission(ingress, monkeypatch):
    add_asset(ingress)
    transport = add_machine_credential(ingress)
    mutate_after_admission(monkeypatch, ingress, "UPDATE CX_AGENT_ACCESS_TOKENS SET SCOPE_JSON='[]'")
    with continuity_bindings.authenticated_transport(transport):
        result = managed_inputs.query('origin-a', 'asset', 'profile', 'Explain this input.')
    assert result['status'] == 'FAILED' and result['result'] is None and not ingress.sends
    assert read_admissions(ingress)[0]['status'] == 'REJECTED'


def test_missing_credential_cannot_send_selected_managed_resource(ingress):
    add_asset(ingress)
    result = managed_inputs.query('origin-a', 'asset', 'profile', 'Explain this input.')
    assert result['status'] == 'FAILED' and result['result'] is None
    assert not ingress.sends and read_admissions(ingress) == []


@pytest.mark.parametrize('sql', [
    "UPDATE CX_WEB_SESSIONS SET REVOKED_AT=CURRENT_TIMESTAMP",
    "UPDATE CX_MANAGED_INPUT_ASSETS SET STATUS='REVOKED'",
    "UPDATE CX_MANAGED_INPUT_ASSETS SET VERSION=2",
    "UPDATE CX_MANAGED_INPUT_ASSETS SET EXTRACTED_CIPHER='changed'",
    "UPDATE CX_MANAGED_ASSET_USES SET INPUT_DIGEST='changed'",
    "INSERT INTO TEST_PERMISSIONS VALUES('origin-a','model_gateway.forward','DENY')",
])
def test_managed_input_stale_credential_asset_use_and_permission_are_known_not_sent(ingress, monkeypatch, sql):
    add_asset(ingress)
    mutate_after_admission(monkeypatch, ingress, sql)
    result = managed_query(ingress)
    assert result['status'] == 'FAILED' and result['result'] is None and not ingress.sends
    assert read_admissions(ingress)[0]['status'] == 'REJECTED'
    assert ingress.db.execute('SELECT STATUS FROM CX_MANAGED_ASSET_USES').fetchone()['status'] == 'FAILED'


def test_managed_image_requires_original_current_verified_probe_after_queue(ingress, monkeypatch):
    add_asset(ingress, image=True)
    mutate_after_admission(monkeypatch, ingress, "UPDATE CX_PROVIDER_CAP_PROBES SET STATUS='STALE'")
    result = managed_query(ingress)
    assert result['status'] == 'FAILED' and not ingress.sends
    assert read_admissions(ingress)[0]['status'] == 'REJECTED'


def test_completed_managed_transport_with_revoked_original_session_hides_output(ingress):
    add_asset(ingress)
    def revoke():
        ingress.db.execute('UPDATE CX_WEB_SESSIONS SET REVOKED_AT=CURRENT_TIMESTAMP')
        ingress.db.commit()
    ingress.after_response[0] = revoke
    result = managed_query(ingress)
    assert result['status'] == 'UNOBSERVED' and result['result'] is None and len(ingress.sends) == 1
    assert read_admissions(ingress)[0]['status'] == 'COMPLETED'


@pytest.fixture
def evaluation(ingress, monkeypatch):
    from lib import edition_features, processing_recovery_schema
    db = ingress.db
    db.executescript("""
        CREATE TABLE TASK_PLANS(PLAN_ID TEXT PRIMARY KEY,AGENT_ID TEXT,GOAL TEXT,STATUS TEXT,PRIORITY INTEGER,STRATEGY TEXT);
        CREATE TABLE CX_CONTEXT_ASSEMBLIES(ASSEMBLY_ID TEXT PRIMARY KEY);
        CREATE TABLE CX_ANSWER_EVAL_CASES(CASE_ID TEXT,VERSION INTEGER,QUERY_TEXT TEXT,EXPECTED_MODE TEXT,
            EXPECTED_ENTITIES_JSON TEXT,STATUS TEXT,CASE_DIGEST TEXT,PRIMARY KEY(CASE_ID,VERSION));
        INSERT INTO CX_ANSWER_EVAL_CASES VALUES('case',1,'What is quantum tunneling?','NO_MATCH','[]','ACTIVE','case-digest');
    """)
    for statement in task_continuity.schema_statements('pg') + quality.schema_statements('pg') + processing_recovery_schema.schema_statements('pg'):
        db.execute(statement)
    db.commit()
    monkeypatch.setattr(connection, 'DATABASE_DIALECT', 'oracle')
    monkeypatch.setattr(edition_features, 'MODEL_RUNTIME_CONTEXT_ENABLED', True, raising=False)
    monkeypatch.setattr(quality.answer_evaluation, '_require_owner', lambda actor: None)
    quality.register_rubric('origin-a', 'case', 1, {'required_phrases': ['tunneling'],
                            'allowed_answer_sources': ['MODEL_SUPPLEMENT']}, 'Frozen rubric fixture')
    run = quality.enqueue('origin-a', dict(case_id='case', case_version=1, rubric_revision=1,
        security_domain_id='domain', agent_id='agent', entry_kind='PORTAL', idempotency_key='evaluation',
        reason='Frozen isolated evaluation'))
    return ingress, run['run_id']


def execute_evaluation(state, run_id):
    with model_credentials.server_session(state.session):
        return quality.execute('origin-a', run_id, worker_id='actual-quality-worker')


def test_selected_evaluation_uses_original_session_worker_and_frozen_input(evaluation):
    state, run_id = evaluation
    assert execute_evaluation(state, run_id)['status'] == 'SUCCEEDED'
    admission = read_admissions(state)[0]
    attempt = state.db.execute('SELECT * FROM CX_TASK_CONTINUITY_ATTEMPTS').fetchone()
    frozen = state.db.execute('SELECT * FROM CX_ANSWER_QUALITY_INPUTS').fetchone()
    assert admission['source_kind'] == 'EVALUATION' and admission['source_id'] == run_id
    assert admission['source_attempt_id'] == attempt['attempt_id'] == frozen['attempt_id']
    assert admission['credential_digest'] == state.digest and admission['status'] == 'COMPLETED'
    assert attempt['status'] == 'SUCCEEDED' and len(state.sends) == 1


def test_missing_credential_cannot_send_selected_evaluation_resource(evaluation):
    state, run_id = evaluation
    with pytest.raises(PermissionError, match='authenticated supported dispatch'):
        quality.execute('origin-a', run_id)
    assert not state.sends and read_admissions(state) == []
    assert state.db.execute('SELECT STATUS FROM CX_TASK_CONTINUITY_ATTEMPTS').fetchone()['status'] == 'FAILED'
    assert state.db.execute('SELECT STATUS FROM CX_TASK_CONTINUITY_LEASES').fetchone()['status'] == 'RELEASED'


def test_completed_evaluation_revocation_hides_output_and_preserves_completed_transport(evaluation):
    state, run_id = evaluation
    def revoke():
        state.db.execute('UPDATE CX_WEB_SESSIONS SET REVOKED_AT=CURRENT_TIMESTAMP')
        state.db.commit()
    state.after_response[0] = revoke
    with pytest.raises(PermissionError):
        execute_evaluation(state, run_id)
    assert len(state.sends) == 1 and read_admissions(state)[0]['status'] == 'COMPLETED'
    assert state.db.execute('SELECT COUNT(*) AS n FROM CX_ANSWER_QUALITY_OUTPUTS').fetchone()['n'] == 0
    assert state.db.execute('SELECT STATUS FROM CX_TASK_CONTINUITY_ATTEMPTS').fetchone()['status'] == 'UNOBSERVED'


@pytest.mark.parametrize('sql', [
    "UPDATE CX_WEB_SESSIONS SET REVOKED_AT=CURRENT_TIMESTAMP",
    "UPDATE CX_NATIVE_AGENTS SET STATUS='INACTIVE'",
    "UPDATE CX_TASK_CONTINUITY_LEASES SET LEASE_OWNER='different-worker'",
    "UPDATE CX_ANSWER_QUALITY_INPUTS SET INPUT_DIGEST='changed'",
    "UPDATE CX_ANSWER_EVAL_CASES SET STATUS='RETIRED'",
    "UPDATE CX_PORTAL_KNOWLEDGE_POLICY SET VERSION=2",
])
def test_evaluation_dispatch_rechecks_actual_worker_frozen_input_source_and_identity(evaluation, monkeypatch, sql):
    state, run_id = evaluation
    mutate_after_admission(monkeypatch, state, sql)
    with pytest.raises(Exception) as failure:
        execute_evaluation(state, run_id)
    assert getattr(failure.value, 'model_not_dispatched', False) and not state.sends
    assert read_admissions(state)[0]['status'] == 'REJECTED'
    assert state.db.execute('SELECT COUNT(*) AS n FROM CX_ANSWER_QUALITY_OUTPUTS').fetchone()['n'] == 0
    if 'different-worker' in sql:
        assert state.db.execute('SELECT LEASE_OWNER,STATUS FROM CX_TASK_CONTINUITY_LEASES').fetchone() == {
            'lease_owner': 'different-worker', 'status': 'ACTIVE'}


def test_evaluation_queued_behind_other_origin_cancels_and_finishes_business_lease(evaluation):
    state, run_id = evaluation
    occupied = occupy_other_origin(state)
    with pytest.raises(model_dispatch.CapacityQueued):
        execute_evaluation(state, run_id)
    records = read_admissions(state)
    queued = next(item for item in records if item['source_kind'] == 'EVALUATION')
    assert queued['status'] == 'CANCELLED'
    assert capacity.read_admission('origin-a', queued['admission_id'])['attempt_id'] is None
    assert capacity.read_admission('origin-b', occupied['admission_id'])['status'] == 'DISPATCHING'
    attempt = state.db.execute('SELECT * FROM CX_TASK_CONTINUITY_ATTEMPTS').fetchone()
    assert attempt['status'] == 'FAILED' and attempt['error_code'] == 'MODEL_CAPACITY_QUEUED'
    assert state.db.execute('SELECT STATUS FROM CX_TASK_CONTINUITY_LEASES').fetchone()['status'] == 'RELEASED'
    assert state.db.execute('SELECT STATUS FROM CX_ANSWER_QUALITY_RUNS').fetchone()['status'] == 'FAILED'
    assert not state.sends and execute_evaluation(state, run_id)['replayed']


def test_evaluation_queue_cleanup_failure_still_releases_known_no_send_business_attempt(evaluation, monkeypatch):
    state, run_id = evaluation
    occupy_other_origin(state)
    def unavailable(*args, **kwargs):
        raise RuntimeError('Synthetic queue cleanup failure')
    monkeypatch.setattr(capacity, 'cancel_admission', unavailable)
    with pytest.raises(RuntimeError, match='queue cleanup failure'):
        execute_evaluation(state, run_id)
    assert not state.sends
    assert state.db.execute('SELECT STATUS FROM CX_TASK_CONTINUITY_ATTEMPTS').fetchone()['status'] == 'FAILED'
    assert state.db.execute('SELECT STATUS FROM CX_TASK_CONTINUITY_LEASES').fetchone()['status'] == 'RELEASED'
    assert next(item for item in read_admissions(state) if item['source_kind'] == 'EVALUATION')['status'] == 'QUEUED'
