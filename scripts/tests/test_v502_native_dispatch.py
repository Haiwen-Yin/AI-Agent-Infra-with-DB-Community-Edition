"""Native Worker/Channel integration with real leases and capacity ledgers.

These are SQLite relational and synthetic transport observations. They do not
establish native-database, real-provider or OS-sandbox release acceptance.
"""
import io
import json
import pytest

from lib import business_channel_runtime as business, connection, continuity_runtime, continuity_assembly
from lib import edition_features, identity_api, model_credentials, model_dispatch
from lib import native_agent_api, native_runtime
from lib.agent_extension_schema import TABLES
from .test_v502_ingress_credentials import add_machine_credential, ingress, mutate_after_admission, occupy_other_origin, read_admissions
from .test_v502_model_capacity import ledger


@pytest.mark.parametrize('screening', ['BOUNDED_RULES_NOT_SEMANTIC_VERIFICATION','VERIFIED',None])
def test_public_answer_metadata_cannot_assert_calibration_or_semantic_verification(screening):
    value=native_runtime._safe_answer_metadata(dict(probability_calibration='VERIFIED',
        answer_correctness_probability=.99,rank_meaning='PROBABILITY',publication_screening=screening))
    assert value['probability_calibration']=='UNAVAILABLE'
    assert 'answer_correctness_probability' not in value
    assert value['rank_meaning']=='RECIPROCAL_RANK_NOT_PROBABILITY'
    assert value['publication_screening']==('BOUNDED_RULES_NOT_SEMANTIC_VERIFICATION'
        if screening=='BOUNDED_RULES_NOT_SEMANTIC_VERIFICATION' else 'UNASSESSED')


@pytest.fixture
def worker(ingress, monkeypatch):
    state = ingress
    db = state.db
    db.executescript("""
        ALTER TABLE CX_SECURITY_DOMAINS ADD COLUMN DOMAIN_NAME TEXT;
        ALTER TABLE CX_SECURITY_DOMAINS ADD COLUMN CLASSIFICATION TEXT;
        ALTER TABLE CX_SECURITY_DOMAINS ADD COLUMN PURPOSE TEXT;
        CREATE TABLE TASK_PLANS(PLAN_ID TEXT PRIMARY KEY,AGENT_ID TEXT,GOAL TEXT,STATUS TEXT,PRIORITY INTEGER,STRATEGY TEXT);
        ALTER TABLE AGENT_REGISTRY ADD COLUMN AGENT_NAME TEXT;
        ALTER TABLE AGENT_REGISTRY ADD COLUMN AGENT_ROLE TEXT;
        ALTER TABLE CX_LLM_PROVIDER_PROFILES ADD COLUMN UPDATED_AT TIMESTAMP;
        ALTER TABLE CX_NATIVE_AGENTS ADD COLUMN DEPLOYMENT_TARGET_ID TEXT DEFAULT 'target';
        ALTER TABLE CX_NATIVE_AGENTS ADD COLUMN ACTIVATION_STATE TEXT DEFAULT 'ACTIVE';
        ALTER TABLE CX_NATIVE_AGENTS ADD COLUMN SOURCE TEXT DEFAULT 'PLATFORM_CREATED';
        ALTER TABLE CX_NATIVE_AGENTS ADD COLUMN AGENT_KIND TEXT DEFAULT 'BUSINESS';
        ALTER TABLE CX_NATIVE_AGENTS ADD COLUMN IS_PROTECTED TEXT DEFAULT 'N';
        ALTER TABLE CX_NATIVE_AGENTS ADD COLUMN TEMPLATE_ID TEXT DEFAULT 'template';
        CREATE TABLE CX_DEPLOYMENT_TARGETS(TARGET_ID TEXT PRIMARY KEY,TARGET_TYPE TEXT,STATUS TEXT,CONFIG_JSON TEXT);
        INSERT INTO CX_DEPLOYMENT_TARGETS VALUES('target','LOCAL_MANAGED','ACTIVE','{}');
        CREATE TABLE CX_RUNTIME_EXECUTIONS(EXECUTION_ID TEXT PRIMARY KEY,AGENT_ID TEXT,TARGET_ID TEXT,
            ISOLATION_LEVEL TEXT,STATUS TEXT,INPUT_JSON TEXT,CONTEXT_DIGEST TEXT,WORKER_ID TEXT,NODE_ID TEXT,
            FENCING_TOKEN INTEGER DEFAULT 0,LEASE_EXPIRES_AT TIMESTAMP,OUTPUT_JSON TEXT,FAILURE_REASON TEXT,
            COMPLETED_AT TIMESTAMP,UPDATED_AT TIMESTAMP,CREATED_AT TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            STARTED_AT TIMESTAMP,ISOLATION_EVIDENCE_JSON TEXT,ISOLATION_EVIDENCE_REF TEXT,ISOLATION_ADMITTED_AT TIMESTAMP);
        CREATE TABLE CX_CHANNELS(CHANNEL_ID TEXT PRIMARY KEY,SECURITY_DOMAIN_ID TEXT,CLASSIFICATION TEXT,
            STATUS TEXT,UPDATED_AT TIMESTAMP);
        INSERT INTO CX_CHANNELS VALUES('channel','domain','INTERNAL','ACTIVE',NULL);
        CREATE TABLE CX_CHANNEL_MEMBERS(MEMBER_ID TEXT PRIMARY KEY,CHANNEL_ID TEXT,PRINCIPAL_ID TEXT,
            MEMBER_ROLE TEXT,STATUS TEXT,VALID_UNTIL TIMESTAMP);
        INSERT INTO CX_CHANNEL_MEMBERS VALUES('cm1','channel','origin-a','MEMBER','ACTIVE',NULL),
            ('cm2','channel','agent','MEMBER','ACTIVE',NULL);
        CREATE TABLE CX_CHANNEL_THREADS(THREAD_ID TEXT PRIMARY KEY,CHANNEL_ID TEXT,THREAD_TYPE TEXT,STATUS TEXT);
        CREATE TABLE CX_CHANNEL_THREAD_MEMBERS(THREAD_MEMBER_ID TEXT,THREAD_ID TEXT,PRINCIPAL_ID TEXT,STATUS TEXT,VALID_UNTIL TIMESTAMP);
        CREATE TABLE CX_CHANNEL_MESSAGES(MESSAGE_ID TEXT PRIMARY KEY,CHANNEL_ID TEXT,PRINCIPAL_ID TEXT,
            BODY_TEXT TEXT,THREAD_TYPE TEXT,THREAD_ID TEXT,REFERENCE_JSON TEXT,REDACTED_AT TIMESTAMP,
            MESSAGE_TYPE TEXT,BODY_CLASSIFICATION TEXT);
        INSERT INTO CX_CHANNEL_MESSAGES VALUES('message','channel','origin-a','Explain quantum tunneling.',
            'CHANNEL',NULL,'{"mentions":["agent"]}',NULL,'TEXT','INTERNAL');
        CREATE TABLE CX_AGENT_TEMPLATES(TEMPLATE_ID TEXT PRIMARY KEY,STATUS TEXT,CONTENT_JSON TEXT);
        INSERT INTO CX_AGENT_TEMPLATES VALUES('template','PUBLISHED','{"isolation_level":"DOMAIN_ISOLATED"}');
        CREATE TABLE CX_ADMIN_AGENT_MEMBERS(MEMBER_ID TEXT,GROUP_ID TEXT,AGENT_ID TEXT,STATUS TEXT,VOTING_ENABLED TEXT);
    """)
    from lib import task_continuity, processing_recovery_schema
    for statement in task_continuity.schema_statements('pg') + processing_recovery_schema.schema_statements('pg'):
        db.execute(statement)
    for statement in continuity_assembly.schema_statements('pg') + continuity_runtime.schema_statements('pg') + continuity_runtime.credential_schema_statements('pg'):
        db.execute(statement)
    from lib.agent_integration_bindings import TABLES as BINDINGS
    db.execute('CREATE TABLE CX_RUNTIME_DERIVATIONS(' + BINDINGS['CX_RUNTIME_DERIVATIONS']['definition'] + ')')
    db.execute('CREATE TABLE CX_FRAMEWORK_EXECUTIONS(' + TABLES['CX_FRAMEWORK_EXECUTIONS']['definition'] + ')')
    for table in ('CX_FRAMEWORK_BINDINGS', 'CX_FRAMEWORK_REQUESTS'):
        db.execute('CREATE TABLE ' + table + '(' + BINDINGS[table]['definition'] + ')')
    db.execute('CREATE TABLE CX_EXECUTION_OBSERVATIONS(' + TABLES['CX_EXECUTION_OBSERVATIONS']['definition'] + ')')
    db.commit()
    monkeypatch.setattr(edition_features, 'MODEL_RUNTIME_CONTEXT_ENABLED', True, raising=False)
    monkeypatch.setattr(connection, 'DATABASE_DIALECT', 'sqlite')
    def sqlite_timestamp(column):
        assert connection.DATABASE_DIALECT == 'sqlite'
        return column
    monkeypatch.setattr(connection, 'session_timestamp_utc_expression', sqlite_timestamp)
    monkeypatch.setattr(native_agent_api, '_lease_deadline_sql', lambda: "datetime('now','+5 minutes')")
    def execute(sql, params):
        try:
            result = db.execute(sql.replace(' FOR UPDATE', ''), params).rowcount
            db.commit()
            return result
        except BaseException:
            db.rollback()
            raise
    monkeypatch.setattr(connection, 'execute', execute)
    monkeypatch.setattr(identity_api, '_audit', lambda actor, action, family, resource, outcome, reason:
        connection.execute_transaction_callback(lambda tx: identity_api._audit_tx(tx, actor, action, family, resource, outcome, reason)))
    state.sends.clear()
    class Response:
        def __init__(self, stream):
            self.stream = stream
            self.content = 'Quantum tunneling crosses a potential barrier.'
            self.body = io.BytesIO(json.dumps({'model': 'model', 'choices': [{'message': {'content': self.content},
                'finish_reason': 'stop'}], 'usage': {'total_tokens': 12}}).encode())
        def __enter__(self):
            return self
        def __exit__(self, *args):
            self.body.close()
            return False
        def observe(self):
            if state.after_response[0] is not None:
                callback, state.after_response[0] = state.after_response[0], None
                callback()
        def read(self, size):
            self.observe()
            return self.body.read(size)
        def __iter__(self):
            self.observe()
            for event in ({'model': 'model', 'choices': [{'delta': {'content': self.content}}]},
                          {'model': 'model', 'choices': [{'delta': {}, 'finish_reason': 'stop'}]},
                          {'model': 'model', 'choices': [], 'usage': {'total_tokens': 12}}):
                yield ('data: ' + json.dumps(event) + '\n\n').encode()
            yield b'data: [DONE]\n\n'
    def send(request, **kwargs):
        payload = json.loads(request.data)
        state.sends.append(payload)
        return Response(payload.get('stream'))
    monkeypatch.setattr(model_dispatch, 'open_controlled', send)
    return state


def enqueue_native(state):
    with model_credentials.server_session(state.session):
        return native_runtime.enqueue('origin-a', 'agent', [{'role': 'user', 'content': 'Explain quantum tunneling.'}],
                                      'Authorized synthetic native invocation')['execution_id']


def enqueue_channel(state):
    with model_credentials.server_session(state.session):
        return business.enqueue('origin-a', 'channel', 'message', 'agent', 'CHANNEL', '', 'en')['execution_id']


def execution(state, execution_id):
    return state.db.execute('SELECT * FROM CX_RUNTIME_EXECUTIONS WHERE EXECUTION_ID=?', (execution_id,)).fetchone()


def channel_reply(state):
    return state.db.execute("SELECT BODY_TEXT,MESSAGE_TYPE FROM CX_CHANNEL_MESSAGES WHERE MESSAGE_TYPE<>'TEXT'").fetchone()


def test_native_enqueues_original_session_and_completes_actual_capacity_and_execution(worker):
    execution_id = enqueue_native(worker)
    receipt = worker.db.execute('SELECT * FROM CX_RUNTIME_MODEL_CREDENTIALS').fetchone()
    assert receipt['actor_id'] == 'origin-a' and receipt['credential_digest'] == worker.digest
    assert receipt['credential_kind'] == 'WEB' and receipt['required_scope'] is None
    assert receipt['profile_id'] == 'profile' and receipt['profile_version'] == 1
    assert native_runtime.execute_one('worker', 'node')['status'] == 'COMPLETED'
    assert execution(worker, execution_id)['status'] == 'COMPLETED' and len(worker.sends) == 1
    admission = read_admissions(worker)[0]
    assert admission['source_kind'] == 'NATIVE' and admission['source_id'] == execution_id
    assert admission['credential_digest'] == worker.digest and admission['status'] == 'COMPLETED'
    assert worker.db.execute('SELECT FINISH_CODE FROM CX_EXECUTION_OBSERVATIONS').fetchone()['finish_code'] == 'COMPLETED'
    assert native_runtime.execute_one('worker', 'node')['status'] == 'IDLE'


def native_block(state, execution_id):
    from lib import processing_recovery as recovery
    raw = state.db.execute('SELECT * FROM CX_PROCESSING_BLOCKS WHERE TARGET_ID=? ORDER BY CREATED_AT DESC', (execution_id,)).fetchone()
    block = {key.lower(): value for key, value in dict(raw).items()}
    return block, recovery.ExactTarget.model_validate({key: block.get(key) for key in recovery.ExactTarget.model_fields})


def native_values(state, sql):
    return tuple(state.db.execute(sql).fetchone().values())


def native_retry(state, execution_id):
    from lib import processing_recovery as recovery
    block, target = native_block(state, execution_id)
    return recovery.admit_retry('origin-a', dict(block_id=block['block_id'], expected_version=block['version'], target=target.model_dump(),
        reason_code=block['reason_code'], add_requests=2, add_steps=2, add_tokens=100, decision_digest='e' * 64, idempotency_key='native-retry'))


def native_unknown(state, monkeypatch):
    execution_id = enqueue_native(state)
    def lost(*args, **kwargs):
        raise TimeoutError('Synthetic response was not observed')
    with monkeypatch.context() as changed:
        changed.setattr(model_dispatch, 'open_controlled', lost)
        assert native_runtime.execute_one('worker', 'node')['status'] == 'UNOBSERVED'
    return execution_id


@pytest.mark.parametrize('channel', [False, True])
def test_real_native_task_budget_and_exact_provider_mapping(worker, channel):
    from lib import processing_native
    execution_id = enqueue_channel(worker) if channel else enqueue_native(worker)
    root = worker.db.execute('SELECT * FROM CX_TASK_CONTINUITY_LINKS WHERE LINK_ID=?', (execution_id,)).fetchone()
    assert root['actor_id'] == 'origin-a' and root['canonical_task_id']
    assert root['security_domain_id'] == ('domain' if channel else processing_native.INTERNAL_ANCHOR)
    assert native_runtime.execute_one('worker', 'node')['status'] == 'COMPLETED'
    attempt = worker.db.execute('SELECT * FROM CX_TASK_CONTINUITY_ATTEMPTS').fetchone()
    mapped = worker.db.execute('SELECT * FROM CX_PROCESSING_NATIVE_ATTEMPTS').fetchone()
    provider = worker.db.execute('SELECT * FROM CX_PROCESSING_NATIVE_CALLS').fetchone()
    assert attempt['status'] == 'SUCCEEDED' and mapped['task_attempt_id'] == attempt['attempt_id']
    assert provider['task_attempt_id'] == attempt['attempt_id'] and provider['source_attempt_id'] != attempt['attempt_id']
    assert native_values(worker, 'SELECT REQUESTS_USED,STEPS_USED,TOKENS_USED FROM CX_PROCESSING_BUDGETS') == (1, 1, 12)


def test_explicit_native_retry_uses_original_task_input_credential_and_budget(worker, monkeypatch):
    from lib import processing_recovery as recovery
    execution_id = enqueue_native(worker)
    original = execution(worker, execution_id)['input_json']
    def not_sent(*args, **kwargs):
        raise model_dispatch.ModelNotDispatched('DENIED_BEFORE_SEND', 'Synthetic exact no-send')
    with monkeypatch.context() as changed:
        changed.setattr(native_runtime, '_call_llm', not_sent)
        assert native_runtime.execute_one('worker', 'node')['status'] == 'FAILED'
    receipt = native_retry(worker, execution_id)
    queued = recovery.dispatch_retry('origin-a', receipt['recovery_id'])
    assert queued['status'] == 'QUEUED' and not queued['dispatched'] and not worker.sends
    assert recovery.dispatch_retry('origin-a', receipt['recovery_id'])['replayed']
    assert execution(worker, execution_id)['input_json'] == original
    assert native_runtime.execute_one('worker-2', 'node')['status'] == 'COMPLETED'
    assert len(worker.sends) == 1 and native_values(worker, 'SELECT COUNT(*) FROM TASK_PLANS') == (1,)
    assert native_values(worker, 'SELECT COUNT(DISTINCT BUDGET_ID) FROM CX_PROCESSING_CHAINS') == (1,)
    assert native_values(worker, 'SELECT REQUESTS_USED,STEPS_USED,TOKENS_USED FROM CX_PROCESSING_BUDGETS') == (2, 2, 12)
    assert recovery.dispatch_retry('origin-a', receipt['recovery_id'])['replayed']
    assert native_runtime.execute_one('worker', 'node')['status'] == 'IDLE'


def test_unknown_native_read_retains_unknown_and_operator_resolution_is_atomic(worker, monkeypatch):
    from lib import processing_recovery as recovery
    execution_id = native_unknown(worker, monkeypatch)
    block, target = native_block(worker, execution_id)
    value = dict(expected_version=block['version'], target=target.model_dump(), mode='READ_ORIGINAL',
        reason='Read the exact original lifecycle', idempotency_key='native-read')
    assert recovery.reconcile_decision('origin-a', block['block_id'], value)['status'] == 'UNOBSERVED'
    assert read_admissions(worker)[0]['status'] == 'UNKNOWN'
    assert execution(worker, execution_id)['status'] == 'UNOBSERVED'
    value.update(mode='OPERATOR_RESOLUTION', outcome='FAILED', idempotency_key='native-resolved', reason='Explicit synthetic operator termination confirmation')
    original = identity_api._audit_tx
    def audit(tx, actor, action, *args):
        if action == 'PROCESSING_RECONCILED':
            raise RuntimeError('Required reconciliation audit unavailable')
        return original(tx, actor, action, *args)
    with monkeypatch.context() as changed:
        changed.setattr(identity_api, '_audit_tx', audit)
        with pytest.raises(RuntimeError, match='audit'):
            recovery.reconcile_decision('admin', block['block_id'], value)
    assert read_admissions(worker)[0]['status'] == 'UNKNOWN'
    assert execution(worker, execution_id)['status'] == 'UNOBSERVED'
    assert native_values(worker, 'SELECT STATUS FROM CX_TASK_CONTINUITY_ATTEMPTS') == ('UNOBSERVED',)
    assert recovery.reconcile_decision('admin', block['block_id'], value)['status'] == 'FAILED'
    assert read_admissions(worker)[0]['status'] == 'COMPLETED'
    assert execution(worker, execution_id)['status'] == 'FAILED'
    receipt = native_retry(worker, execution_id)
    recovery.dispatch_retry('origin-a', receipt['recovery_id'])
    assert native_runtime.execute_one('worker-2', 'node')['status'] == 'COMPLETED'


def test_expired_native_lease_fences_real_task_and_rolls_back_failed_claim_audit(worker, monkeypatch):
    from lib import task_continuity
    execution_id = enqueue_native(worker)
    original = task_continuity._transition
    def audit(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError('Required claim transition unavailable')
    with monkeypatch.context() as changed:
        changed.setattr(task_continuity, '_transition', audit)
        with pytest.raises(RuntimeError, match='transition'):
            native_agent_api.claim_runtime('worker', 'node', 1)
        assert execution(worker, execution_id)['status'] == 'PENDING'
        assert native_values(worker, 'SELECT COUNT(*) FROM CX_PROCESSING_NATIVE_ATTEMPTS') == (0,)
    native_agent_api.claim_runtime('worker', 'node', 1)
    worker.db.execute("UPDATE CX_RUNTIME_EXECUTIONS SET LEASE_EXPIRES_AT=datetime('now','-1 second')")
    worker.db.commit()
    assert native_agent_api.reconcile_expired_runtime() == 1
    assert execution(worker, execution_id)['status'] == 'UNOBSERVED'
    assert native_values(worker, 'SELECT STATUS FROM CX_TASK_CONTINUITY_ATTEMPTS') == ('UNOBSERVED',)
    assert native_agent_api.claim_runtime('replacement', 'node', 1) == []
    assert not worker.sends


def test_native_unicode_input_digest_and_inert_registry_projection(worker, monkeypatch):
    from lib import processing_native, agent_registration
    worker.db.execute("DELETE FROM AGENT_REGISTRY WHERE AGENT_ID='agent'")
    worker.db.commit()
    with model_credentials.server_session(worker.session):
        receipt = native_runtime.enqueue('origin-a', 'agent', [{'role': 'user', 'content': '你好，解释量子隧穿。'}], '中文输入')
    projection = worker.db.execute('SELECT AGENT_ID,AGENT_NAME,STATUS,AGENT_ROLE FROM AGENT_REGISTRY').fetchone()
    assert projection['status'] == 'DORMANT' and processing_native.is_projection('agent')
    assert native_values(worker, 'SELECT COUNT(*) FROM CX_PROCESSING_NATIVE_AGENTS') == (1,)
    for action in (lambda: agent_registration.register_agent('agent', owner_ref='origin-a'),
                   lambda: agent_registration.adopt_legacy_agent('agent'), lambda: agent_registration.set_status('agent', 'ACTIVE')):
        with pytest.raises(PermissionError, match='accounting projection'):
            action()
    assert agent_registration.authenticate_agent('agent', 'invented') is None
    assert native_runtime.execute_one('worker', 'node')['status'] == 'COMPLETED'
    assert execution(worker, receipt['execution_id'])['status'] == 'COMPLETED'
    assert worker.db.execute('SELECT AGENT_ID,AGENT_NAME,STATUS,AGENT_ROLE FROM AGENT_REGISTRY').fetchone() == projection


@pytest.mark.parametrize('kind', ['CALL', 'STREAM'])
@pytest.mark.parametrize('code', ['KNOWN_NO_SEND', 'UNKNOWN_SEND'])
def test_provider_open_preserves_known_no_send_and_unknown_identity(worker, monkeypatch, kind, code):
    from contextlib import contextmanager
    from lib.continuity_state import ContinuityConflict
    error = model_dispatch.ModelNotDispatched('EXACT_NO_SEND', 'Synthetic no send') if code == 'KNOWN_NO_SEND' else ContinuityConflict('UNKNOWN_SEND', 'Exact original unknown send')
    class Ticket:
        def timeout_seconds(self, value, **_options):
            return value
        def open(self, *args, **kwargs):
            raise error
    @contextmanager
    def dispatch(*args, **kwargs):
        yield Ticket()
    monkeypatch.setattr(model_dispatch, 'dispatch', dispatch)
    profile = dict(profile_id='profile', model_id='model', provider_url='http://synthetic/v1', provider_kind='OPENAI_COMPATIBLE')
    with pytest.raises(type(error)) as caught:
        if kind == 'STREAM':
            native_runtime._stream_llm(profile, [{'role': 'user', 'content': 'test'}], lambda _: None)
        else:
            native_runtime._call_llm(profile, [{'role': 'user', 'content': 'test'}])
    assert caught.value is error


@pytest.mark.parametrize('sql', [
    "UPDATE CX_WEB_SESSIONS SET REVOKED_AT=CURRENT_TIMESTAMP",
    "UPDATE CX_NATIVE_AGENTS SET STATUS='INACTIVE'",
    "UPDATE CX_NATIVE_AGENTS SET LLM_PROFILE_ID='new-profile'",
    "UPDATE CX_LLM_PROVIDER_PROFILES SET API_KEY_CIPHER='changed' WHERE PROFILE_ID='profile'",
    "UPDATE CX_RUNTIME_EXECUTIONS SET INPUT_JSON='{}'",
    "UPDATE CX_RUNTIME_EXECUTIONS SET FENCING_TOKEN=FENCING_TOKEN+1",
    "UPDATE CX_RUNTIME_EXECUTIONS SET TARGET_ID='another-target'",
    "UPDATE CX_DEPLOYMENT_TARGETS SET CONFIG_JSON='{\"changed\":true}'",
    "INSERT INTO TEST_PERMISSIONS VALUES('origin-a','agents.operate','DENY')",
])
def test_native_rechecks_original_authority_and_real_fence_after_capacity_admission(worker, monkeypatch, sql):
    execution_id = enqueue_native(worker)
    mutate_after_admission(monkeypatch, worker, sql)
    outcome = native_runtime.execute_one('worker', 'node')
    assert outcome['status'] == 'FAILED' and not worker.sends
    assert execution(worker, execution_id)['output_json'] is None
    assert read_admissions(worker)[0]['status'] == 'REJECTED'
    assert worker.db.execute('SELECT HEALTH_STATE FROM CX_LLM_PROVIDER_PROFILES WHERE PROFILE_ID=\'profile\'').fetchone()['health_state'] == 'HEALTHY'


def test_native_profile_choice_is_frozen_before_worker_claim(worker):
    execution_id = enqueue_native(worker)
    worker.db.execute("UPDATE CX_NATIVE_AGENTS SET LLM_PROFILE_ID='new-profile'")
    worker.db.commit()
    assert native_runtime.execute_one('worker', 'node')['status'] == 'FAILED'
    assert not worker.sends and read_admissions(worker) == []
    assert execution(worker, execution_id)['output_json'] is None


def test_native_queue_does_not_wait_or_degrade_health_and_cancels_known_no_send(worker):
    execution_id = enqueue_native(worker)
    occupy_other_origin(worker)
    result = native_runtime.execute_one('worker', 'node')
    assert result['status'] == 'FAILED' and result['failure_code'] == 'MODEL_CAPACITY_QUEUED'
    assert execution(worker, execution_id)['status'] == 'FAILED' and not worker.sends
    queued = next(item for item in read_admissions(worker) if item['source_id'] == execution_id)
    assert queued['status'] == 'CANCELLED'
    assert worker.db.execute("SELECT HEALTH_STATE FROM CX_LLM_PROVIDER_PROFILES WHERE PROFILE_ID='profile'").fetchone()['health_state'] == 'HEALTHY'
    assert native_runtime.execute_one('worker', 'node')['status'] == 'IDLE'


def test_native_unknown_send_retains_capacity_and_is_never_retried(worker, monkeypatch):
    execution_id = enqueue_native(worker)
    def send(*args, **kwargs):
        worker.sends.append(True)
        raise TimeoutError('Synthetic original transport uncertainty')
    monkeypatch.setattr(model_dispatch, 'open_controlled', send)
    result = native_runtime.execute_one('worker', 'node')
    assert result['status'] == 'UNOBSERVED' and len(worker.sends) == 1
    assert execution(worker, execution_id)['status'] == 'UNOBSERVED'
    assert read_admissions(worker)[0]['status'] == 'UNKNOWN'
    assert native_runtime.execute_one('worker', 'node')['status'] == 'IDLE' and len(worker.sends) == 1


def test_native_missing_receipt_cannot_borrow_ambient_context(worker):
    with model_credentials.server_session(None):
        execution_id = native_runtime.enqueue('origin-a', 'agent', [{'role': 'user', 'content': 'Explain tunneling.'}], 'Legacy no-credential fixture')['execution_id']
    with model_dispatch.authenticated_context('origin-a', 'NATIVE', 'another-source', 'another-attempt',
            credential_digest=worker.digest, reauthorize=lambda tx, record: None, worker_key='another-worker'):
        result = native_runtime.execute_one('worker', 'node')
    assert result['status'] == 'FAILED' and not worker.sends and read_admissions(worker) == []
    assert execution(worker, execution_id)['status'] == 'FAILED'


def test_native_completed_transport_cannot_persist_after_original_session_revocation(worker):
    execution_id = enqueue_native(worker)
    def revoke():
        worker.db.execute('UPDATE CX_WEB_SESSIONS SET REVOKED_AT=CURRENT_TIMESTAMP')
        worker.db.commit()
    worker.after_response[0] = revoke
    assert native_runtime.execute_one('worker', 'node')['status'] == 'FAILED'
    assert len(worker.sends) == 1 and read_admissions(worker)[0]['status'] == 'COMPLETED'
    assert execution(worker, execution_id)['output_json'] is None


@pytest.mark.parametrize('withdraw_scope', [False, True])
def test_native_machine_execution_uses_the_original_operation_scope(worker, monkeypatch, withdraw_scope):
    from lib import continuity_bindings
    transport = add_machine_credential(worker)
    worker.db.execute("UPDATE CX_AGENT_ACCESS_TOKENS SET SCOPE_JSON='[\"agents.operate\"]'")
    worker.db.commit()
    with continuity_bindings.authenticated_transport(transport):
        receipt = native_runtime.enqueue('origin-a', 'agent', [{'role': 'user', 'content': 'Explain tunneling.'}],
                                         'Original machine request')
    stored = worker.db.execute('SELECT * FROM CX_RUNTIME_MODEL_CREDENTIALS').fetchone()
    assert stored['required_scope'] == 'agents.operate' and stored['credential_kind'] == 'AGENT'
    assert stored['credential_digest'] == transport['token_digest'] and stored['auth_method'] is None
    if withdraw_scope:
        mutate_after_admission(monkeypatch, worker, "UPDATE CX_AGENT_ACCESS_TOKENS SET SCOPE_JSON='[]'")
    result = native_runtime.execute_one('worker', 'node')
    assert result['status'] == ('FAILED' if withdraw_scope else 'COMPLETED')
    assert len(worker.sends) == int(not withdraw_scope)
    assert execution(worker, receipt['execution_id'])['status'] == result['status']


def test_business_channel_uses_original_source_stream_and_atomic_publication(worker):
    execution_id = enqueue_channel(worker)
    receipt = worker.db.execute('SELECT * FROM CX_RUNTIME_MODEL_CREDENTIALS').fetchone()
    assert receipt['source_digest'] and receipt['credential_digest'] == worker.digest
    assert native_runtime.execute_one('worker', 'node')['status'] == 'COMPLETED'
    assert execution(worker, execution_id)['status'] == 'COMPLETED'
    assert 'Quantum tunneling' in channel_reply(worker)['body_text']
    admission = read_admissions(worker)[0]
    assert admission['source_kind'] == 'CHANNEL' and admission['source_id'] == execution_id
    assert admission['status'] == 'COMPLETED' and len(worker.sends) == 1
    assert worker.sends[0]['stream'] is True


@pytest.mark.parametrize('unsafe', [False, True])
def test_grounded_expression_contract_buffers_partials_and_keeps_usage(worker, monkeypatch, unsafe):
    monkeypatch.setattr(business.answer_planning, 'retrieve', lambda *args, **kwargs:
        {'status': 'MATCHED', 'items': [{'entity_id': 'source', 'digest': 'source-digest',
            'title': 'Synthetic reference', 'content': 'The observed loss is unknown.'}], 'missing_parts': []})
    execution_id = enqueue_channel(worker)
    stored = json.loads(execution(worker, execution_id)['input_json'])
    assert stored['answer_expression_contract']['references'][0]['entity_id'] == 'source'
    published = []
    original = identity_api.update_channel_agent_response
    def publish(*args, **kwargs):
        published.append(dict(content=args[2], completed=kwargs.get('completed')))
        return original(*args, **kwargs)
    monkeypatch.setattr(identity_api, 'update_channel_agent_response', publish)
    if unsafe:
        def send(request, **kwargs):
            worker.sends.append(json.loads(request.data))
            parts = ['I am ', '95%', ' confident that the answer is correct.']
            events = [{'model': 'model', 'choices': [{'delta': {'content': part}}]} for part in parts]
            events.extend([{'model': 'model', 'choices': [{'delta': {}, 'finish_reason': 'stop'}]},
                           {'model': 'model', 'choices': [], 'usage': {'total_tokens': 12}}])
            class Response:
                def __enter__(self):
                    return self
                def __exit__(self, *args):
                    return False
                def __iter__(self):
                    for event in events:
                        yield ('data: '+json.dumps(event)+'\n\n').encode()
                    yield b'data: [DONE]\n\n'
            return Response()
        monkeypatch.setattr(model_dispatch, 'open_controlled', send)
    result = native_runtime.execute_one('worker', 'node')
    assert result['status'] == 'COMPLETED', execution(worker, execution_id)['failure_reason']
    assert len(published) == 1 and published[0]['completed'] is True
    assert len(worker.sends) == 1 and worker.sends[0]['stream'] is True
    assert read_admissions(worker)[0]['status'] == 'COMPLETED'
    assert '95%' not in channel_reply(worker)['body_text']
    if unsafe:
        assert 'was withheld' in channel_reply(worker)['body_text']
    else:
        assert 'Quantum tunneling' in channel_reply(worker)['body_text']


@pytest.mark.parametrize('sql', [
    "UPDATE CX_WEB_SESSIONS SET REVOKED_AT=CURRENT_TIMESTAMP",
    "UPDATE CX_CHANNEL_MESSAGES SET BODY_TEXT='changed source' WHERE MESSAGE_ID='message'",
    "UPDATE CX_CHANNEL_MESSAGES SET REFERENCE_JSON='{}' WHERE MESSAGE_ID='message'",
    "UPDATE CX_CHANNEL_MESSAGES SET REDACTED_AT=CURRENT_TIMESTAMP WHERE MESSAGE_ID='message'",
    "UPDATE CX_CHANNEL_MEMBERS SET STATUS='REVOKED' WHERE PRINCIPAL_ID='origin-a'",
    "UPDATE CX_PORTAL_KNOWLEDGE_POLICY SET ALLOW_MODEL_SUPPLEMENT='N'",
    "UPDATE CX_NATIVE_AGENTS SET ACTIVATION_STATE='INACTIVE'",
])
def test_business_channel_rechecks_original_credential_source_and_admission_before_send(worker, monkeypatch, sql):
    execution_id = enqueue_channel(worker)
    mutate_after_admission(monkeypatch, worker, sql)
    outcome = native_runtime.execute_one('worker', 'node')
    assert outcome['status'] == 'FAILED' and not worker.sends
    assert read_admissions(worker)[0]['status'] == 'REJECTED'
    assert execution(worker, execution_id)['output_json'] is None
    reply = channel_reply(worker)
    assert reply is None or 'Quantum tunneling' not in reply['body_text']


@pytest.mark.parametrize('sql', [
    "UPDATE CX_WEB_SESSIONS SET REVOKED_AT=CURRENT_TIMESTAMP",
    "UPDATE CX_CHANNEL_MESSAGES SET BODY_TEXT='changed source' WHERE MESSAGE_ID='message'",
    "UPDATE CX_CHANNEL_MEMBERS SET STATUS='REVOKED' WHERE PRINCIPAL_ID='origin-a'",
])
def test_business_channel_completed_response_cannot_publish_after_original_authority_changes(worker, sql):
    execution_id = enqueue_channel(worker)
    def withdraw():
        worker.db.execute(sql)
        worker.db.commit()
    worker.after_response[0] = withdraw
    outcome = native_runtime.execute_one('worker', 'node')
    assert outcome['status'] == 'FAILED' and len(worker.sends) == 1
    assert read_admissions(worker)[0]['status'] == 'COMPLETED'
    assert execution(worker, execution_id)['output_json'] is None
    reply = channel_reply(worker)
    assert reply is None or 'Quantum tunneling' not in reply['body_text']


def test_channel_publication_guard_denial_rolls_back_body_in_same_transaction(worker):
    execution_id = enqueue_channel(worker)
    assert native_agent_api.claim_runtime('worker', 'node', limit=1)
    identity_api.begin_channel_agent_response('agent', 'channel', execution_id=execution_id)
    def deny(tx):
        tx.execute("UPDATE CX_CHANNEL_MESSAGES SET BODY_TEXT='must rollback' WHERE MESSAGE_TYPE='AGENT_RESPONSE_STREAMING'", {})
        raise PermissionError('Original credential withdrawn at publication')
    with pytest.raises(PermissionError):
        identity_api.update_channel_agent_response('agent', 'channel', 'must never publish', execution_id=execution_id,
            completed=True, before_publish=deny, lock_principals=('origin-a', 'agent'))
    assert channel_reply(worker) == {'body_text': '[streaming]', 'message_type': 'AGENT_RESPONSE_STREAMING'}


@pytest.mark.parametrize('change', ['none', 'source', 'audience'])
def test_grounded_channel_binds_original_source_and_complete_disclosure_audience(worker, monkeypatch, change):
    monkeypatch.setattr(business.answer_planning, 'retrieve', lambda *args, **kwargs:
        {'status': 'MATCHED', 'items': [{'entity_id': 'source', 'digest': 'source-digest',
            'title': 'Synthetic reference', 'content': 'Quantum tunneling explanation.'}], 'missing_parts': []})
    worker.db.execute("INSERT INTO CX_CHANNEL_MEMBERS VALUES('cm3','channel','origin-b','MEMBER','ACTIVE',NULL)")
    worker.db.commit()
    execution_id = enqueue_channel(worker)
    if change == 'source':
        mutate_after_admission(monkeypatch, worker, "UPDATE TEST_SOURCES SET STATUS='REVOKED'")
    elif change == 'audience':
        mutate_after_admission(monkeypatch, worker, "UPDATE CX_CHANNEL_MEMBERS SET STATUS='REVOKED' WHERE PRINCIPAL_ID='origin-b'")
    result = native_runtime.execute_one('worker', 'node')
    assert result['status'] == ('COMPLETED' if change == 'none' else 'FAILED')
    assert len(worker.sends) == int(change == 'none')
    assert read_admissions(worker)[0]['status'] == ('COMPLETED' if change == 'none' else 'REJECTED')
    if change != 'none':
        assert execution(worker, execution_id)['output_json'] is None


def test_channel_unknown_stream_is_not_automatically_retried_as_non_streaming(worker, monkeypatch):
    execution_id = enqueue_channel(worker)
    class Incomplete:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def __iter__(self):
            yield b'data: {"model":"model","choices":[{"delta":{"content":"Unfinished"}}]}\n\n'
            raise RuntimeError('LLM provider returned no content')
    def send(request, **kwargs):
        worker.sends.append(json.loads(request.data))
        return Incomplete()
    monkeypatch.setattr(model_dispatch, 'open_controlled', send)
    result = native_runtime.execute_one('worker', 'node')
    assert result['status'] == 'UNOBSERVED' and len(worker.sends) == 1
    assert worker.sends[0]['stream'] is True
    assert read_admissions(worker)[0]['status'] == 'UNKNOWN'
    assert execution(worker, execution_id)['output_json'] is None
    assert 'Unfinished' not in channel_reply(worker)['body_text']


@pytest.fixture
def management(worker, monkeypatch):
    from lib import admin_management, management_knowledge
    db = worker.db
    db.execute('UPDATE CX_CHANNELS SET CHANNEL_ID=?', (admin_management.ADMIN_CHANNEL_ID,))
    db.execute('UPDATE CX_CHANNEL_MEMBERS SET CHANNEL_ID=?', (admin_management.ADMIN_CHANNEL_ID,))
    db.execute('UPDATE CX_CHANNEL_MEMBERS SET PRINCIPAL_ID=? WHERE PRINCIPAL_ID=\'agent\'', (native_agent_api.PLATFORM_ADMIN_AGENT_ID,))
    db.execute('UPDATE CX_CHANNEL_MESSAGES SET CHANNEL_ID=?,REFERENCE_JSON=?',
               (admin_management.ADMIN_CHANNEL_ID, json.dumps({'mentions': [native_agent_api.PLATFORM_ADMIN_AGENT_ID]})))
    db.execute("INSERT INTO CX_PRINCIPALS(PRINCIPAL_ID,STATUS,PRINCIPAL_TYPE) VALUES(?,'ACTIVE','AGENT')", (native_agent_api.PLATFORM_ADMIN_AGENT_ID,))
    db.execute("INSERT INTO CX_NATIVE_AGENTS(AGENT_ID,LLM_PROFILE_ID,STATUS) VALUES(?,'profile','ACTIVE')", (native_agent_api.PLATFORM_ADMIN_AGENT_ID,))
    db.execute("INSERT INTO CX_ADMIN_AGENT_MEMBERS VALUES('admin-member',?,?,'ACTIVE','Y')",
               (admin_management.ADMIN_GROUP_ID, native_agent_api.PLATFORM_ADMIN_AGENT_ID))
    db.commit()
    monkeypatch.setattr(management_knowledge, 'retrieve', lambda *args: {'items': []})
    return worker


@pytest.mark.parametrize('revoke_membership', [False, True])
def test_management_channel_uses_original_human_session_and_current_group_admission(management, monkeypatch, revoke_membership):
    from lib import admin_management
    state = management
    with model_credentials.server_session(state.session):
        receipt = native_agent_api.create_channel_execution('origin-a', admin_management.ADMIN_CHANNEL_ID, 'message',
            'Explain quantum tunneling.', native_agent_api.PLATFORM_ADMIN_AGENT_ID, response_language='en')
    if revoke_membership:
        mutate_after_admission(monkeypatch, state, "UPDATE CX_ADMIN_AGENT_MEMBERS SET STATUS='REVOKED'")
    result = native_runtime.execute_one('worker', 'node')
    assert result['status'] == ('FAILED' if revoke_membership else 'COMPLETED')
    assert len(state.sends) == int(not revoke_membership)
    assert read_admissions(state)[0]['status'] == ('REJECTED' if revoke_membership else 'COMPLETED')
    assert execution(state, receipt['execution_id'])['output_json'] is None if revoke_membership else channel_reply(state)['message_type'] == 'AGENT_RESPONSE'


@pytest.fixture
def context_worker(worker, monkeypatch):
    from lib import continuity_work, continuity_policy, continuity_execution_links
    db = worker.db
    db.execute("INSERT INTO CX_DOMAIN_MEMBERS VALUES('domain','agent','ACTIVE','MEMBER',NULL)")
    db.execute("UPDATE CX_SECURITY_DOMAINS SET CLASSIFICATION='INTERNAL' WHERE CLASSIFICATION IS NULL")
    for statement in continuity_work.schema_statements('pg') + continuity_policy.schema_statements('pg') + continuity_execution_links.schema_statements('pg'):
        db.execute(statement)
    db.commit()
    monkeypatch.setattr(connection, 'scalar_select_suffix', lambda: '')
    created = continuity_work.create_work('origin-a', dict(security_domain_id='domain', owner_principal_id='origin-a',
        reason='Exact original Work source', idempotency_key='work', content=dict(objective='Verify the original Work context',
        criteria=[dict(criterion_id='one', description='Exact context', verification='Synthetic ledger assertions')], constraints=[])))
    with model_credentials.server_session(worker.session):
        receipt = continuity_runtime.enqueue('origin-a', dict(agent_id='agent',
            messages=[dict(role='user', content='Explain this Work reference.')],
            context=dict(request_id='context', security_domain_id='domain', work_contract_id=created['work_contract_id'],
                         purpose='Synthetic original context', idempotency_key='context'),
            reason='Explicit original context execution', idempotency_key='context-execution'))
    return worker, receipt


@pytest.mark.parametrize('withdraw_requester', [False, True])
def test_context_native_worker_rechecks_real_assembly_and_original_requester(context_worker, monkeypatch, withdraw_requester):
    state, receipt = context_worker
    if withdraw_requester:
        mutate_after_admission(monkeypatch, state,
                               "UPDATE CX_DOMAIN_MEMBERS SET STATUS='REVOKED' WHERE PRINCIPAL_ID='origin-a'")
    result = native_runtime.execute_one('worker', 'node')
    assert result['status'] == ('FAILED' if withdraw_requester else 'COMPLETED')
    assert len(state.sends) == int(not withdraw_requester)
    assert read_admissions(state)[0]['status'] == ('REJECTED' if withdraw_requester else 'COMPLETED')
    if not withdraw_requester:
        assert 'Verify the original Work context' in state.sends[0]['messages'][-1]['content']
        assert state.db.execute('SELECT STATUS FROM CX_CONTEXT_INPUT_USES').fetchone()['status'] == 'SENT'
        assert state.db.execute('SELECT FENCING_TOKEN FROM CX_RUNTIME_CONTEXT_ATTEMPTS').fetchone()['fencing_token'] == 1
    assert native_runtime.execute_one('worker', 'node')['status'] == 'IDLE'


def test_explicit_context_retry_reuses_frozen_context_without_rewriting_first_use(context_worker, monkeypatch):
    from lib import processing_recovery as recovery
    state, receipt = context_worker
    def not_sent(*args, **kwargs):
        raise model_dispatch.ModelNotDispatched('DENIED_BEFORE_SEND', 'Synthetic exact no-send')
    with monkeypatch.context() as changed:
        changed.setattr(native_runtime, '_call_llm', not_sent)
        assert native_runtime.execute_one('worker', 'node')['status'] == 'FAILED'
    original = state.db.execute('SELECT * FROM CX_CONTEXT_INPUT_USES').fetchone()
    original_context = state.db.execute('SELECT * FROM CX_RUNTIME_CONTEXT_ATTEMPTS').fetchone()
    accepted = native_retry(state, receipt['execution_id'])
    recovery.dispatch_retry('origin-a', accepted['recovery_id'])
    assert native_runtime.execute_one('retry-worker', 'node')['status'] == 'COMPLETED'
    assert len(state.sends) == 1 and 'Reference context' in state.sends[0]['messages'][-1]['content']
    assert state.db.execute('SELECT * FROM CX_CONTEXT_INPUT_USES').fetchone() == original
    assert state.db.execute('SELECT * FROM CX_RUNTIME_CONTEXT_ATTEMPTS').fetchone() == original_context
    assert native_values(state, 'SELECT REQUESTS_USED,STEPS_USED,TOKENS_USED FROM CX_PROCESSING_BUDGETS') == (2, 2, 12)


@pytest.mark.parametrize('changed', ['credential', 'profile', 'agent', 'target', 'channel-source', 'channel-member'])
@pytest.mark.parametrize('boundary', ['ADMISSION', 'DISPATCH'])
def test_native_recovery_rechecks_original_current_authority_at_each_boundary(worker, monkeypatch, changed, boundary):
    from lib import processing_recovery as recovery
    execution_id = enqueue_channel(worker) if changed.startswith('channel') else enqueue_native(worker)
    def not_sent(*args, **kwargs):
        raise model_dispatch.ModelNotDispatched('DENIED_BEFORE_SEND', 'Synthetic exact no-send')
    with monkeypatch.context() as altered:
        altered.setattr(native_runtime, '_stream_llm', not_sent)
        altered.setattr(native_runtime, '_call_llm', not_sent)
        assert native_runtime.execute_one('worker', 'node')['status'] == 'FAILED'
    accepted = native_retry(worker, execution_id) if boundary == 'DISPATCH' else None
    statement = {
        'credential': 'UPDATE CX_WEB_SESSIONS SET REVOKED_AT=CURRENT_TIMESTAMP',
        'profile': 'UPDATE CX_LLM_PROVIDER_PROFILES SET VERSION=VERSION+1',
        'agent': "UPDATE CX_NATIVE_AGENTS SET STATUS='INACTIVE'",
        'target': "UPDATE CX_DEPLOYMENT_TARGETS SET STATUS='INACTIVE'",
        'channel-source': "UPDATE CX_CHANNEL_MESSAGES SET REDACTED_AT=CURRENT_TIMESTAMP WHERE MESSAGE_ID='message'",
        'channel-member': "UPDATE CX_CHANNEL_MEMBERS SET STATUS='REVOKED' WHERE PRINCIPAL_ID='origin-a'",
    }[changed]
    worker.db.execute(statement)
    worker.db.commit()
    with pytest.raises(PermissionError):
        if boundary == 'ADMISSION':
            native_retry(worker, execution_id)
        else:
            recovery.dispatch_retry('origin-a', accepted['recovery_id'])
    assert not worker.sends and execution(worker, execution_id)['status'] == 'FAILED'


@pytest.mark.parametrize('channel', [False, True])
def test_native_result_reader_keeps_all_business_data_reads_in_supplied_transaction(worker, monkeypatch, channel):
    from .test_v502_model_capacity import Transaction
    execution_id = enqueue_channel(worker) if channel else enqueue_native(worker)
    monkeypatch.setattr(connection, 'execute_query_one', lambda *_a, **_kw: pytest.fail('Global business data read escaped transaction'))
    assert native_runtime.get_execution('origin-a', execution_id, transaction=Transaction(worker.db))['execution_id'] == execution_id


def test_internal_native_anchor_cannot_be_discovered_populated_or_repurposed(worker, monkeypatch):
    from lib import processing_native, security_domain_api as domains
    execution_id = enqueue_native(worker)
    anchor = processing_native.INTERNAL_ANCHOR
    worker.db.executescript('ALTER TABLE CX_SECURITY_DOMAINS ADD COLUMN CREATED_AT TIMESTAMP; '
        'CREATE TABLE CX_DOMAIN_GOVERNANCE(SECURITY_DOMAIN_ID TEXT,OWNER_PRINCIPAL_ID TEXT,REASON TEXT,UPDATED_AT TIMESTAMP);')
    worker.db.commit()
    monkeypatch.setattr(domains, '_limit_clause', lambda: 'LIMIT :limit')
    assert anchor not in {item['security_domain_id'] for item in domains.list_domains('origin-a', include_inactive=True)}
    assert domains._domain_row(anchor) is None and not domains._actor_can_use_domain('origin-a', anchor)
    with pytest.raises(domains.SecurityDomainError):
        domains.create_domain('origin-a', anchor, 'Changed', 'INTERNAL', 'Changed', 'origin-a', 'Attempt repurpose')
    with pytest.raises(domains.SecurityDomainError):
        domains.set_member('origin-a', anchor, 'origin-a', 'OWNER', 'Attempt membership')
    with pytest.raises(identity_api.IdentityError, match='accounting anchors'):
        identity_api.create_channel('origin-a', 'Forbidden Channel', anchor)
    worker.db.execute("INSERT INTO CX_DOMAIN_MEMBERS VALUES(?,'origin-a','ACTIVE','OWNER',NULL)", (anchor,))
    worker.db.commit()
    with pytest.raises(Exception, match='cannot contain members'):
        native_agent_api.claim_runtime('worker', 'node', 1)
    assert execution(worker, execution_id)['status'] == 'PENDING' and not worker.sends


def test_native_accounting_projection_cannot_reenroll_or_activate_as_external_identity(worker, monkeypatch):
    worker.db.execute("DELETE FROM AGENT_REGISTRY WHERE AGENT_ID='agent'")
    worker.db.commit()
    enqueue_native(worker)
    with pytest.raises(PermissionError, match='accounting projection'):
        identity_api.redeem_enrollment('x' * 64, agent_id='agent')
    monkeypatch.setattr(identity_api, '_compliance_enabled', lambda: False)
    with pytest.raises(PermissionError, match='accounting projection'):
        identity_api.activate_community_agent('agent', 'domain', {'runtime': 'external'})
    worker.db.execute("UPDATE AGENT_REGISTRY SET STATUS='ACTIVE'")
    worker.db.commit()
    with pytest.raises(Exception, match='accounting projection changed'):
        native_agent_api.claim_runtime('worker', 'node', 1)
    assert not worker.sends


@pytest.fixture
def framework_worker(worker, monkeypatch):
    from lib import framework_execution, effective_capabilities, isolated_framework_runtime, runtime_isolation
    from lib.agent_integration_bindings import TABLES as BINDINGS
    db = worker.db
    config = dict(framework_rootfs='/synthetic/frozen-rootfs', uid=10001, gid=10001)
    db.execute("UPDATE CX_DEPLOYMENT_TARGETS SET TARGET_TYPE='LOCAL_LINUX_SANDBOX',CONFIG_JSON=?", (json.dumps(config),))
    db.commit()
    monkeypatch.setattr(effective_capabilities, 'require', lambda *args, **kwargs: None)
    monkeypatch.setattr(effective_capabilities, 'authorize', lambda *args, **kwargs: None)
    rootfs_digest = 'sha256:' + 'a' * 64
    monkeypatch.setattr(framework_execution, 'verify_rootfs', lambda *args, **kwargs: rootfs_digest)
    class SyntheticFramework:
        # This is a broker lifecycle fixture, not evidence of an actual OS sandbox.
        def __init__(self, execution, config):
            self.used = False
        def evidence(self):
            return dict(enforcement_mode='VERIFIED', runtime_identity='synthetic-peer',
                boundaries=list(runtime_isolation.BOUNDARIES), max_isolation_level='DEDICATED_CONTAINER', rootfs_digest=rootfs_digest)
        def start(self):
            return self.evidence()
        def model(self, profile, messages, call, authorize):
            assert not self.used
            self.used = True
            authorize()
            result = call(profile, messages)
            authorize()
            self.observation = dict(framework='langgraph', framework_version=isolated_framework_runtime.FRAMEWORK_VERSION,
                                    steps=['prepare', 'model', 'finalize'])
            return result
        def close(self):
            pass
    monkeypatch.setattr(isolated_framework_runtime, 'FrameworkWorker', SyntheticFramework)
    with model_credentials.server_session(worker.session):
        receipt = framework_execution.enqueue('origin-a', 'domain', 'agent',
            [{'role': 'user', 'content': 'Explain quantum tunneling.'}], 'framework', 'Original approved framework input')
    return worker, receipt


@pytest.mark.parametrize('withdraw_session', [False, True])
def test_fixed_framework_native_broker_rechecks_original_credential_and_bound_runtime(framework_worker, monkeypatch, withdraw_session):
    state, receipt = framework_worker
    if withdraw_session:
        mutate_after_admission(monkeypatch, state, 'UPDATE CX_WEB_SESSIONS SET REVOKED_AT=CURRENT_TIMESTAMP')
    result = native_runtime.execute_one('worker', 'node')
    assert result['status'] == ('FAILED' if withdraw_session else 'COMPLETED')
    assert len(state.sends) == int(not withdraw_session)
    assert read_admissions(state)[0]['status'] == ('REJECTED' if withdraw_session else 'COMPLETED')
    observed = state.db.execute('SELECT OBSERVATION_JSON FROM CX_FRAMEWORK_EXECUTIONS').fetchone()['observation_json']
    assert (observed is None) is withdraw_session
    assert execution(state, receipt['execution_id'])['output_json'] is None if withdraw_session else json.loads(observed)['isolation_verified'] is True
