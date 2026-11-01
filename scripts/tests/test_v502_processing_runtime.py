"""Native retry uses original jobs, immutable inputs, credentials and budgets."""
from datetime import datetime, timedelta

import pytest

from lib import answer_quality as quality, connection, edition_features, identity_api
from lib import model_credentials, model_dispatch, model_endpoint_schema
from lib import processing_recovery as recovery, processing_recovery_schema
from lib import processing_runtime as adapter, task_continuity as tasks
from lib.continuity_state import ContinuityConflict, ContinuityError
from .test_answer_quality import database as quality_database, enqueue
from .test_v502_governed_model_turns import (governed, runtime, candidate_db, fixture, database,
    retrospective, new_turn, model, turns, bindings, TRANSPORT, TOKEN, evidence, retros, PROPOSALS)
from .test_v501_context_assets import store, configuration, fetched
from lib import agent_source_sync as sync
from lib.model_results import ModelResultError


SESSION = "7" * 64


@pytest.fixture(autouse=True)
def text_native_reference_fixture(monkeypatch):
    # Every runner here uses SQLite TEXT keys with Oracle semantics. A PG
    # package also supplies its BIGINT locator normalizer; changing the
    # dialect alone cannot turn that concrete function into an Oracle one.
    # Model only the fixture's native key type; real authority, memberships,
    # original credentials, input digests and recovery fences remain checked.
    monkeypatch.setattr(connection, "normalize_execution_reference", lambda _kind, value: value, raising=False)


@pytest.fixture
def native(quality_database, monkeypatch):
    db = quality_database
    monkeypatch.setattr(edition_features, "MODEL_RUNTIME_CONTEXT_ENABLED", True)
    db.executescript("""
        ALTER TABLE CX_PRINCIPALS ADD COLUMN MFA_REQUIRED TEXT DEFAULT 'N';
        ALTER TABLE CX_PRINCIPALS ADD COLUMN PERMISSION_VERSION INTEGER DEFAULT 1;
        CREATE TABLE CX_WEB_SESSIONS(SESSION_DIGEST TEXT PRIMARY KEY,PRINCIPAL_ID TEXT,AUTH_METHOD TEXT,
            MFA_LEVEL TEXT,NODE_ID TEXT,PERMISSION_VERSION INTEGER,CREATED_AT TIMESTAMP,EXPIRES_AT TIMESTAMP,REVOKED_AT TIMESTAMP);
        CREATE TABLE CX_WEB_SESSION_POLICIES(POLICY_KEY TEXT PRIMARY KEY,ABSOLUTE_TIMEOUT_SECONDS INTEGER);
        INSERT INTO CX_WEB_SESSION_POLICIES VALUES('DASHBOARD',3600);
        CREATE TABLE CX_AGENT_RELATIONSHIPS(RELATIONSHIP_ID TEXT,AGENT_ID TEXT,PRINCIPAL_ID TEXT,
            RELATIONSHIP_ROLE TEXT,STATUS TEXT,ENDED_AT TIMESTAMP);
        INSERT INTO CX_DOMAIN_MEMBERS VALUES('domain','agent','ACTIVE','MEMBER',NULL);
        INSERT INTO CX_AGENT_RELATIONSHIPS VALUES('ownership','agent','owner','PRIMARY_OWNER','ACTIVE',NULL);
    """)
    for sql in model_endpoint_schema.schema_statements("pg") + processing_recovery_schema.schema_statements("pg"):
        db.execute(sql)
    now = datetime.now()
    db.execute("INSERT INTO CX_WEB_SESSIONS VALUES(?,'owner','LOCAL:DASHBOARD','NONE','node',1,?,?,NULL)",
               (SESSION, now, now + timedelta(minutes=30)))
    db.commit()
    monkeypatch.setattr(identity_api, "entry_allowed", lambda *_: True)
    return db


def execute_original(run_id):
    with model_credentials.server_session({"session_digest": SESSION, "principal_id": "owner"}):
        return quality.execute("owner", run_id)


def fail_before_send(native, monkeypatch):
    run_id = enqueue()
    def unsent(*_args, **_kwargs):
        raise model_dispatch.ModelNotDispatched("MODEL_DISPATCH_DENIED", "Known no-send test")
    monkeypatch.setattr(quality.native_runtime, "_call_llm", unsent)
    with pytest.raises(model_dispatch.ModelNotDispatched):
        execute_original(run_id)
    return run_id


def admit(native, run_id, *, actor="owner", key="retry-1"):
    block = dict(native.execute("SELECT * FROM CX_PROCESSING_BLOCKS WHERE TARGET_ID=? ORDER BY CREATED_AT DESC", (run_id,)).fetchone())
    target = recovery.ExactTarget.model_validate({name: block.get(name.upper()) for name in recovery.ExactTarget.model_fields})
    value = {"block_id": block["BLOCK_ID"], "expected_version": block["VERSION"], "target": target.model_dump(),
        "reason_code": block["REASON_CODE"], "add_requests": 1, "add_steps": 2, "add_tokens": 100,
        "decision_digest": "d" * 64, "idempotency_key": key}
    return recovery.admit_retry(actor, value), value


def queued(native, monkeypatch):
    run_id = fail_before_send(native, monkeypatch)
    receipt, value = admit(native, run_id)
    result = connection.execute_transaction_callback(lambda tx: adapter.dispatch_recovery(tx, "owner", receipt["recovery_id"]))
    assert result["status"] == "QUEUED" and not result["dispatched"]
    return run_id, receipt, value


def successful_provider(monkeypatch):
    def complete(*_args, **_kwargs):
        return {"content": "Quantum tunneling crosses a potential barrier.", "model": "model", "usage": {"total_tokens": 9}}
    monkeypatch.setattr(quality.native_runtime, "_call_llm", complete)


def test_original_known_failure_freezes_current_credential_and_input(native, monkeypatch):
    run_id = fail_before_send(native, monkeypatch)
    assert native.execute("SELECT CREDENTIAL_DIGEST FROM CX_ANSWER_QUALITY_CREDENTIALS WHERE RUN_ID=?", (run_id,)).fetchone()[0] == SESSION
    assert native.execute("SELECT COUNT(*) FROM CX_ANSWER_QUALITY_INPUTS WHERE RUN_ID=?", (run_id,)).fetchone()[0] == 1
    assert native.execute("SELECT STATUS FROM CX_ANSWER_QUALITY_RUNS WHERE RUN_ID=?", (run_id,)).fetchone()[0] == "FAILED"
    assert native.execute("SELECT REQUESTS_USED,STEPS_USED FROM CX_PROCESSING_BUDGETS").fetchone()[:] == (1, 1)


def test_retry_reuses_exact_original_input_without_retrieval_or_replacement_credential(native, monkeypatch):
    run_id, receipt, value = queued(native, monkeypatch)
    original_input = native.execute("SELECT ATTEMPT_ID,INPUT_CIPHER,INPUT_DIGEST FROM CX_ANSWER_QUALITY_INPUTS WHERE RUN_ID=?", (run_id,)).fetchone()[:]
    successful_provider(monkeypatch)
    monkeypatch.setattr(model_credentials, "capture", lambda *_a, **_kw: pytest.fail("Retry captured replacement credential"))
    monkeypatch.setattr(quality.answer_planning, "retrieve", lambda *_a, **_kw: pytest.fail("Retry performed a new retrieval"))
    result = adapter.run_recovery("owner", receipt["recovery_id"])
    assert result["status"] == "SUCCEEDED"
    assert native.execute("SELECT ATTEMPT_ID,INPUT_CIPHER,INPUT_DIGEST FROM CX_ANSWER_QUALITY_INPUTS WHERE RUN_ID=?", (run_id,)).fetchone()[:] == original_input
    retry_input = native.execute("SELECT ATTEMPT_ID,INPUT_CIPHER,INPUT_DIGEST FROM CX_ANSWER_QUALITY_RETRY_INPUTS WHERE RUN_ID=?", (run_id,)).fetchone()[:]
    assert retry_input[0] != original_input[0] and retry_input[1:] == original_input[1:]
    assert native.execute("SELECT COUNT(*) FROM TASK_PLANS").fetchone()[0] == 1
    assert native.execute("SELECT COUNT(DISTINCT BUDGET_ID) FROM CX_PROCESSING_CHAINS").fetchone()[0] == 1
    assert native.execute("SELECT REQUESTS_USED,STEPS_USED FROM CX_PROCESSING_BUDGETS").fetchone()[:] == (2, 2)
    assert recovery.admit_retry("owner", value)["replayed"]
    monkeypatch.setattr(quality.native_runtime, "_call_llm", lambda *_a, **_kw: pytest.fail("Completed retry resent"))
    assert adapter.run_recovery("owner", receipt["recovery_id"])["status"] == "SUCCEEDED"


@pytest.mark.parametrize("when", ("ADMISSION", "DISPATCH", "WORKER"))
@pytest.mark.parametrize("changed", ("credential", "profile", "case", "membership"))
def test_current_original_authority_is_checked_at_each_recovery_boundary(native, monkeypatch, when, changed):
    run_id = fail_before_send(native, monkeypatch)
    receipt = admit(native, run_id)[0] if when != "ADMISSION" else None
    if when == "WORKER":
        connection.execute_transaction_callback(lambda tx: adapter.dispatch_recovery(tx, "owner", receipt["recovery_id"]))
    statements = {
        "credential": "UPDATE CX_WEB_SESSIONS SET REVOKED_AT=CURRENT_TIMESTAMP",
        "profile": "UPDATE CX_LLM_PROVIDER_PROFILES SET VERSION=VERSION+1",
        "case": "UPDATE CX_ANSWER_EVAL_CASES SET STATUS='RETIRED'",
        "membership": "UPDATE CX_DOMAIN_MEMBERS SET STATUS='REVOKED' WHERE PRINCIPAL_ID='owner'",
    }
    native.execute(statements[changed])
    native.commit()
    with pytest.raises(PermissionError):
        if when == "ADMISSION":
            admit(native, run_id)
        elif when == "DISPATCH":
            connection.execute_transaction_callback(lambda tx: adapter.dispatch_recovery(tx, "owner", receipt["recovery_id"]))
        else:
            adapter.run_recovery("owner", receipt["recovery_id"])
    assert native.execute("SELECT COUNT(*) FROM CX_TASK_CONTINUITY_ATTEMPTS").fetchone()[0] == 1


def test_recovery_queue_and_required_audit_commit_atomically(native, monkeypatch):
    run_id = fail_before_send(native, monkeypatch)
    receipt, _ = admit(native, run_id)
    before = native.execute("SELECT CONTINUITY_ID,STATUS FROM CX_ANSWER_QUALITY_RUNS WHERE RUN_ID=?", (run_id,)).fetchone()[:]
    original = identity_api._audit_tx
    def reject(tx, actor, action, *args):
        if action == "NATIVE_PROCESSING_RECOVERY_QUEUED":
            raise RuntimeError("audit unavailable")
        return original(tx, actor, action, *args)
    monkeypatch.setattr(identity_api, "_audit_tx", reject)
    with pytest.raises(RuntimeError, match="audit"):
        connection.execute_transaction_callback(lambda tx: adapter.dispatch_recovery(tx, "owner", receipt["recovery_id"]))
    assert native.execute("SELECT CONTINUITY_ID,STATUS FROM CX_ANSWER_QUALITY_RUNS WHERE RUN_ID=?", (run_id,)).fetchone()[:] == before
    assert native.execute("SELECT STATUS FROM CX_PROCESSING_RECOVERY_STATES").fetchone()[0] == "ACCEPTED"


def test_missing_original_credential_denies_admission_before_receipt(native, monkeypatch):
    run_id = fail_before_send(native, monkeypatch)
    native.execute("DELETE FROM CX_ANSWER_QUALITY_CREDENTIALS")
    native.commit()
    with pytest.raises(ContinuityError, match="original evaluation credential"):
        admit(native, run_id)
    assert native.execute("SELECT COUNT(*) FROM CX_PROCESSING_RECOVERIES").fetchone()[0] == 0


def test_unknown_original_request_cannot_be_admitted_or_requeued(native, monkeypatch):
    run_id = enqueue()
    def unknown(*_args, **_kwargs):
        raise TimeoutError("Provider outcome unknown")
    monkeypatch.setattr(quality.native_runtime, "_call_llm", unknown)
    with pytest.raises(TimeoutError):
        execute_original(run_id)
    with pytest.raises(ContinuityConflict, match="reconciled"):
        admit(native, run_id)
    assert native.execute("SELECT STATUS FROM CX_TASK_CONTINUITY_LINKS").fetchone()[0] == "UNOBSERVED"


def test_same_queue_receipt_is_idempotent_and_never_resets_native_attempt(native, monkeypatch):
    run_id, receipt, _ = queued(native, monkeypatch)
    repeated = connection.execute_transaction_callback(lambda tx: adapter.dispatch_recovery(tx, "owner", receipt["recovery_id"]))
    assert repeated["replayed"] and repeated["status"] == "QUEUED"
    assert native.execute("SELECT COUNT(*) FROM CX_TASK_CONTINUITY_ATTEMPTS").fetchone()[0] == 1


def test_saved_input_tampering_fails_before_new_attempt(native, monkeypatch):
    run_id, receipt, _ = queued(native, monkeypatch)
    native.execute("UPDATE CX_ANSWER_QUALITY_INPUTS SET INPUT_DIGEST=?", ("0" * 64,))
    native.commit()
    with pytest.raises(PermissionError, match="integrity"):
        adapter.run_recovery("owner", receipt["recovery_id"])
    assert native.execute("SELECT COUNT(*) FROM CX_TASK_CONTINUITY_ATTEMPTS").fetchone()[0] == 1


@pytest.fixture
def native_turn(governed):
    db, source = governed
    db.execute("ALTER TABLE CX_AGENT_RELATIONSHIPS ADD COLUMN RELATIONSHIP_ID TEXT")
    db.execute("INSERT INTO CX_AGENT_RELATIONSHIPS(AGENT_ID,PRINCIPAL_ID,RELATIONSHIP_ROLE,STATUS,RELATIONSHIP_ID) VALUES('owner','reader','PRIMARY_OWNER','ACTIVE','owner-reader')")
    db.execute("UPDATE CX_DOMAIN_MEMBERS SET MEMBERSHIP_TIER='ADMIN' WHERE PRINCIPAL_ID='reader'")
    db.commit()
    from .test_v501_memory_runtime import notes, note_request, ref
    work_id = db.execute('SELECT WORK_CONTRACT_ID FROM CX_WORK_CONTRACTS').fetchone()[0]
    note_id = notes.create_note('owner', work_id, note_request())['note_id']
    return db, ref('owner', note_id).model_dump(mode='json')


def stopped_turn(native_turn, monkeypatch):
    turn_id, registered, _ = new_turn(native_turn)
    def completed_but_rejected(*_args, **_kwargs):
        raise ModelResultError('OUTPUT_TRUNCATED', request_complete=True)
    monkeypatch.setattr(quality.native_runtime, '_call_llm', completed_but_rejected)
    with bindings.authenticated_transport(TRANSPORT):
        assert turns.run_once('owner', turn_id, 'worker')['status'] == 'FAILED'
    return turn_id, registered


def test_human_recovers_original_agent_model_stage_without_replacing_credential_or_task(native_turn, monkeypatch):
    db, _ = native_turn
    turn_id, registered = stopped_turn(native_turn, monkeypatch)
    original = db.execute("SELECT ATTEMPT_ID,INPUT_DIGEST,REQUEST_DIGEST FROM CX_MODEL_TOOL_STAGES WHERE TURN_ID=? AND PHASE='PROPOSAL'", (turn_id,)).fetchone()[:]
    receipt, _ = admit(db, turn_id + ':PROPOSAL', actor='reader')
    assert connection.execute_transaction_callback(lambda tx: adapter.dispatch_recovery(tx, 'reader', receipt['recovery_id']))['status'] == 'QUEUED'
    calls = []
    def proposed(profile, messages, **kwargs):
        calls.append((profile, messages))
        context = model_dispatch._context.get()
        assert context.actor == 'owner' and context.credential_digest == TOKEN
        return dict(content='', tool_calls=[{'id':'recovered-call','type':'function','function':{
            'name':turns._tool_name(registered),'arguments':quality.json.dumps({registered['resource_parameter']:registered['source_entity_id']})}}], request_id='native-recovered')
    monkeypatch.setattr(quality.native_runtime, '_call_llm', proposed)
    assert adapter.run_recovery('reader', receipt['recovery_id'])['status'] == 'WAITING_APPROVAL'
    current = db.execute("SELECT ATTEMPT_ID,INPUT_DIGEST,REQUEST_DIGEST FROM CX_MODEL_TOOL_STAGES WHERE TURN_ID=? AND PHASE='PROPOSAL'", (turn_id,)).fetchone()[:]
    assert current[0] != original[0] and current[1:] == original[1:]
    assert db.execute('SELECT COUNT(*) FROM TASK_PLANS').fetchone()[0] == 1
    assert db.execute('SELECT COUNT(*) FROM CX_TASK_CONTINUITY_ATTEMPTS').fetchone()[0] == 2
    assert db.execute('SELECT COUNT(*) FROM CX_MCP_TOOL_REQUESTS').fetchone()[0] == 1
    assert len(calls) == 1
    assert adapter.run_recovery('reader', receipt['recovery_id'])['status'] == 'WAITING_APPROVAL'
    assert len(calls) == 1


@pytest.mark.parametrize('changed', ('credential', 'probe', 'deadline', 'approval'))
def test_model_stage_recovery_denies_current_credential_probe_deadline_or_registration_approval_changes(native_turn, monkeypatch, changed):
    db, _ = native_turn
    turn_id, _ = stopped_turn(native_turn, monkeypatch)
    statements = {
        'credential': 'UPDATE CX_AGENT_ACCESS_TOKENS SET REVOKED_AT=CURRENT_TIMESTAMP',
        'probe': "UPDATE CX_PROVIDER_CAP_PROBES SET STATUS='STALE'",
        'deadline': "UPDATE CX_MODEL_TOOL_TURNS SET DEADLINE_AT='2000-01-01 00:00:00'",
        'approval': "UPDATE CX_ACTION_CARDS SET STATUS='REJECTED'",
    }
    db.execute(statements[changed])
    db.commit()
    with pytest.raises((PermissionError, ContinuityConflict)):
        admit(db, turn_id + ':PROPOSAL', actor='reader')
    assert db.execute('SELECT COUNT(*) FROM CX_PROCESSING_RECOVERIES').fetchone()[0] == 0


def test_retrospective_recovery_reuses_candidate_pipeline_and_exact_original_sources(native_turn, monkeypatch):
    db, source = native_turn
    proposal = PROPOSALS[0]
    schema = retros._schema(proposal['family'])
    evidence(db, 'retry-structured', schema, capability='STRUCTURED_OUTPUT')
    value = retrospective(source)
    value.update(target_family=proposal['family'], output_mode='NATIVE_STRICT', output_probe_id='retry-structured', token_budget=32768)
    with bindings.authenticated_transport(TRANSPORT):
        job = retros.create_job('owner', value)['job_id']
    def stopped(*_args, **_kwargs):
        raise ModelResultError('OUTPUT_TRUNCATED', request_complete=True)
    monkeypatch.setattr(quality.native_runtime, '_call_llm', stopped)
    assert retros.run_once('owner', job, 'worker')['status'] == 'FAILED'
    receipt, _ = admit(db, job, actor='reader')
    connection.execute_transaction_callback(lambda tx: adapter.dispatch_recovery(tx, 'reader', receipt['recovery_id']))
    calls = []
    def generated(*_args, **_kwargs):
        calls.append(True)
        assert model_dispatch._context.get().credential_digest == TOKEN
        return dict(content=quality.json.dumps(proposal), structured=proposal, finish_reason='stop', request_complete=True, usage={})
    monkeypatch.setattr(quality.native_runtime, '_call_llm', generated)
    observed = adapter.run_recovery('reader', receipt['recovery_id'])
    assert observed['status'] == 'PROPOSED' and not observed['published']
    assert db.execute('SELECT STATUS FROM CX_ARTIFACT_CANDIDATES').fetchone()[0] == 'PENDING'
    assert db.execute('SELECT COUNT(*) FROM ENTITIES').fetchone()[0] == 0
    assert db.execute('SELECT COUNT(*) FROM TASK_PLANS').fetchone()[0] == 1
    assert len(calls) == 1
    assert adapter.run_recovery('reader', receipt['recovery_id'])['status'] == 'PROPOSED'
    assert len(calls) == 1


@pytest.fixture
def native_sync(store, monkeypatch):
    db, source = store
    monkeypatch.setattr(edition_features, 'MODEL_RUNTIME_CONTEXT_ENABLED', True)
    db.execute("ALTER TABLE CX_AGENT_RELATIONSHIPS ADD COLUMN RELATIONSHIP_ID TEXT")
    db.execute("INSERT INTO CX_AGENT_RELATIONSHIPS(AGENT_ID,PRINCIPAL_ID,RELATIONSHIP_ROLE,STATUS,RELATIONSHIP_ID) VALUES('agent','owner','PRIMARY_OWNER','ACTIVE','owner-agent')")
    for sql in model_endpoint_schema.schema_statements('pg') + processing_recovery_schema.schema_statements('pg'):
        db.execute(sql)
    db.commit()
    return db, source


def test_source_known_read_retries_consume_same_durable_budget_and_native_limit(native_sync):
    db, _ = native_sync
    source = sync.configure('owner', configuration(max_attempts=2))['source_id']
    job = sync.enqueue('owner', source, {'reason':'Import original source','idempotency_key':'retry-source'})['job_id']
    with pytest.raises(TimeoutError):
        sync.run('owner', job, get=lambda *_a, **_kw: (_ for _ in ()).throw(TimeoutError('read timeout')))
    assert db.execute('SELECT REQUESTS_USED,STEPS_USED FROM CX_PROCESSING_BUDGETS').fetchone()[:] == (0, 1)
    assert sync.run('owner', job, get=lambda *_a, **_kw: fetched())['status'] == 'SUCCEEDED'
    assert db.execute('SELECT REQUESTS_USED,STEPS_USED FROM CX_PROCESSING_BUDGETS').fetchone()[:] == (0, 2)
    assert db.execute('SELECT ATTEMPT_COUNT FROM CX_AGENT_SYNC_JOBS').fetchone()[0] == 2


def test_source_explicit_recovery_reuses_original_job_and_keeps_native_attempt_count(native_sync, monkeypatch):
    db, _ = native_sync
    source = sync.configure('owner', configuration(max_attempts=2))['source_id']
    job = sync.enqueue('owner', source, {'reason':'Import original source','idempotency_key':'retry-source'})['job_id']
    with pytest.raises(ValueError):
        sync.run('owner', job, get=lambda *_a, **_kw: (_ for _ in ()).throw(ValueError('known stopped local fetch rejection')))
    receipt, _ = admit(db, job)
    connection.execute_transaction_callback(lambda tx: adapter.dispatch_recovery(tx, 'owner', receipt['recovery_id']))
    monkeypatch.setattr(sync, 'https_get', lambda *_a, **_kw: fetched())
    assert adapter.run_recovery('owner', receipt['recovery_id'])['status'] == 'SUCCEEDED'
    assert db.execute('SELECT ATTEMPT_COUNT FROM CX_AGENT_SYNC_JOBS').fetchone()[0] == 2
    assert db.execute('SELECT COUNT(*) FROM TASK_PLANS').fetchone()[0] == 1
    assert db.execute('SELECT COUNT(DISTINCT BUDGET_ID) FROM CX_PROCESSING_CHAINS').fetchone()[0] == 1
    assert adapter.run_recovery('owner', receipt['recovery_id'])['status'] == 'SUCCEEDED'
    assert db.execute('SELECT ATTEMPT_COUNT FROM CX_AGENT_SYNC_JOBS').fetchone()[0] == 2


def test_source_native_exhaustion_cannot_be_reset_with_processing_budget(native_sync):
    db, _ = native_sync
    source = sync.configure('owner', configuration(max_attempts=1))['source_id']
    job = sync.enqueue('owner', source, {'reason':'Import original source','idempotency_key':'retry-source'})['job_id']
    with pytest.raises(ValueError):
        sync.run('owner', job, get=lambda *_a, **_kw: (_ for _ in ()).throw(ValueError('known local rejection')))
    with pytest.raises(ContinuityConflict, match='retry budget'):
        admit(db, job)


def test_source_credential_rotation_cannot_substitute_original_recovery_identity(native_sync, monkeypatch):
    db, _ = native_sync
    monkeypatch.setenv('CX_SOURCE_CREDENTIAL_DOCS', 'synthetic-original-token')
    source = sync.configure('owner', configuration(max_attempts=2, credential_ref='DOCS'))['source_id']
    job = sync.enqueue('owner', source, {'reason':'Import original source','idempotency_key':'retry-source'})['job_id']
    with pytest.raises(ValueError):
        sync.run('owner', job, get=lambda *_a, **_kw: (_ for _ in ()).throw(ValueError('known local rejection')))
    monkeypatch.setenv('CX_SOURCE_CREDENTIAL_DOCS', 'synthetic-replacement-token')
    with pytest.raises(PermissionError, match='credential changed'):
        admit(db, job)
    assert db.execute('SELECT COUNT(*) FROM CX_PROCESSING_RECOVERIES').fetchone()[0] == 0
    assert 'synthetic-' not in str(db.execute('SELECT * FROM CX_AGENT_SYNC_CREDENTIALS').fetchone()[:])
