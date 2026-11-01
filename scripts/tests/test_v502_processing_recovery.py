"""Processing recovery contract checks with a project-local SQLite harness.

This is transaction/restart evidence, not native adapter or release acceptance.
There are no model, provider, service or live database calls.
"""
from datetime import datetime, timedelta, timezone
import re
import sqlite3

import pytest

from lib import processing_recovery as recovery, processing_recovery_schema, task_continuity
from lib.continuity_state import ContinuityConflict, ContinuityError

DEFAULT_AUTHORITY = recovery._default_authority

@pytest.fixture
def ledger(tmp_path, monkeypatch):
    from lib import connection, edition_features, identity_api
    monkeypatch.setattr(connection, "DATABASE_DIALECT", "oracle")
    monkeypatch.setattr(edition_features, "MODEL_RUNTIME_CONTEXT_ENABLED", True, raising=False)

    class Ledger:
        path = tmp_path / "processing.sqlite"
        events = []
        grants = {key: True for key in ("actor", "agent", "domain", "credential", "source", "capability", "approval", "revision")}

        def open(self):
            self.db = sqlite3.connect(self.path, check_same_thread=False)
            self.db.row_factory = sqlite3.Row
            self.db.execute("PRAGMA foreign_keys=ON")

        def restart(self):
            self.db.close()
            self.open()

        def execute(self, statement, params):
            # Native Oracle/YashanDB reject extra binds: enforce that here.
            assert set(re.findall(r":([a-zA-Z_][a-zA-Z_0-9]*)", statement)) == set(params)
            return self.db.execute(statement.replace(" FOR UPDATE", ""), params).rowcount

        def query(self, statement, params):
            assert set(re.findall(r":([a-zA-Z_][a-zA-Z_0-9]*)", statement)) == set(params)
            return [{str(key).lower(): value[key] for key in value.keys()}
                    for value in self.db.execute(statement.replace(" FOR UPDATE", ""), params).fetchall()]

        def query_one(self, statement, params):
            values = self.query(statement, params)
            return values[0] if values else None

        def run(self, callback):
            try:
                value = callback(self)
                self.db.commit()
                return value
            except Exception:
                self.db.rollback()
                raise

        def authority(self, tx, actor, target, operation):
            self.events.append((actor, target.continuity_id, operation))
            if actor != "human" or not all(self.grants.values()):
                raise PermissionError("Original resource authority denied")

        def count(self, table):
            return self.db.execute("SELECT COUNT(*) FROM " + table).fetchone()[0]

    value = Ledger()
    value.open()
    value.db.executescript("""
        CREATE TABLE CX_PRINCIPALS(PRINCIPAL_ID TEXT PRIMARY KEY,PRINCIPAL_TYPE TEXT,STATUS TEXT);
        CREATE TABLE CX_SECURITY_DOMAINS(SECURITY_DOMAIN_ID TEXT PRIMARY KEY,STATUS TEXT);
        CREATE TABLE CX_CONTEXT_ASSEMBLIES(ASSEMBLY_ID TEXT PRIMARY KEY);
        CREATE TABLE TASK_PLANS(PLAN_ID TEXT PRIMARY KEY,AGENT_ID TEXT,STATUS TEXT);
        CREATE TABLE CX_MODEL_ADMISSIONS(ADMISSION_ID TEXT PRIMARY KEY,STATUS TEXT,ACTOR_ID TEXT,SOURCE_ID TEXT,SOURCE_ATTEMPT_ID TEXT,INPUT_DIGEST TEXT,FENCING_TOKEN INTEGER);
        CREATE TABLE RECOVERY_AUDIT(ACTION_NAME TEXT,RESOURCE_ID TEXT);
        INSERT INTO CX_PRINCIPALS VALUES('human','HUMAN','ACTIVE'),('agent','AGENT','ACTIVE'),('other','HUMAN','ACTIVE');
        INSERT INTO CX_SECURITY_DOMAINS VALUES('domain','ACTIVE');
        INSERT INTO TASK_PLANS VALUES('plan','agent','RUNNING');
    """)
    for statement in task_continuity.schema_statements("pg") + processing_recovery_schema.schema_statements("pg"):
        value.db.execute(statement)
    value.db.commit()
    monkeypatch.setattr(connection, "execute_transaction_callback", value.run)
    monkeypatch.setattr(recovery, "_default_authority", value.authority)
    monkeypatch.setattr(identity_api, "_audit_tx", lambda tx, actor, action, kind, resource_id, decision, reason:
                        tx.execute("INSERT INTO RECOVERY_AUDIT(ACTION_NAME,RESOURCE_ID) VALUES(:action,:entity)", {"action": action, "entity": resource_id}))
    link = value.run(lambda tx: task_continuity.link_protocol_task(tx, actor="human", security_domain_id="domain", link_kind="RUNTIME", link_id="execution",
        canonical_task_id="plan", idempotency_key="original", request_digest="a" * 64, input_digest="b" * 64))
    attempt = value.run(lambda tx: task_continuity.claim_attempt(tx, continuity_id=link["continuity_id"], worker_id="worker", business_key="business", request_digest="a" * 64))
    value.target = {"continuity_id": link["continuity_id"], "attempt_id": attempt["attempt_id"], "target_kind": "RUNTIME", "target_id": "execution",
                    "target_revision": "a" * 64, "input_digest": "b" * 64, "business_key": "business",
                    "source_family": "SOURCE", "source_id": "source", "source_revision_id": "revision", "source_digest": "c" * 64}
    value.policy = {"max_requests": 50, "max_steps": 50, "max_tokens": 10000, "max_repeats": 3, "max_no_progress": 4}
    value.attempt = attempt
    value.run(lambda tx: recovery.ensure_budget(tx, actor="human", target=value.target, policy=value.policy))
    yield value
    value.db.close()


def observe(ledger, reason="BUDGET_REQUESTS", *, key="block", **kwargs):
    return ledger.run(lambda tx: recovery.observe(tx, actor="human", target=ledger.target, reason_code=reason, observation_key=key, **kwargs))


def finish(ledger, status="FAILED"):
    return ledger.run(lambda tx: task_continuity.finish_attempt(tx, attempt_id=ledger.attempt["attempt_id"], worker_id="worker", fencing_token=ledger.attempt["fencing_token"], status=status, request_digest="a" * 64))


def decision(ledger, block, **kwargs):
    return {"block_id": block["block_id"], "expected_version": int(block["version"]), "target": ledger.target, "reason_code": block["reason_code"],
            "add_requests": 2, "add_steps": 2, "add_tokens": 100, "decision_digest": "d" * 64, "idempotency_key": "retry", **kwargs}


def action(ledger, key, *, tool="search", arguments=None, **kwargs):
    return ledger.run(lambda tx: recovery.record_action(tx, actor="human", target=ledger.target, action_key=key, action_kind="TOOL_CALL", tool_name=tool,
        arguments=arguments or {"q": "same"}, token_count=10, **kwargs))


def admit(ledger):
    block = observe(ledger)
    finish(ledger)
    return block, recovery.admit_retry("human", decision(ledger, block))


def capacity(ledger, receipt, status="QUEUED", **kwargs):
    values = {"admission": "admission", "status": status, "actor": "human", "chain": receipt["successor_continuity_id"], "attempt": receipt["recovery_id"], "fingerprint": "b" * 64, "fence": 1, **kwargs}
    ledger.run(lambda tx: tx.execute("INSERT INTO CX_MODEL_ADMISSIONS(ADMISSION_ID,STATUS,ACTOR_ID,SOURCE_ID,SOURCE_ATTEMPT_ID,INPUT_DIGEST,FENCING_TOKEN) VALUES(:admission,:status,:actor,:chain,:attempt,:fingerprint,:fence)", values))


def test_schema_is_additive_typed_and_not_an_implicit_scheduler():
    statements = processing_recovery_schema.schema_statements("pg")
    assert len([sql for sql in statements if sql.startswith("CREATE TABLE")]) == 15
    for dialect in ("oracle", "postgresql", "yashandb"):
        assert len(processing_recovery_schema.schema_statements(dialect)) == len(statements)
    for sql in statements:
        assert "JSON" not in sql and "PASSWORD" not in sql
    assert "CX_PROCESSING_RECOVERIES" not in processing_recovery_schema.MUTABLE


def test_refresh_restart_and_policy_registration_preserve_usage(ledger):
    result = action(ledger, "action1")
    block = observe(ledger)
    before = ledger.db.total_changes
    first = ledger.run(lambda tx: recovery.read_diagnostics(tx, actor="human", continuity_id=ledger.target["continuity_id"]))
    assert ledger.db.total_changes == before
    ledger.restart()
    second = ledger.run(lambda tx: recovery.read_diagnostics(tx, actor="human", continuity_id=ledger.target["continuity_id"]))
    assert first == second
    assert second["consumed"] == {"requests": 1, "steps": 1, "tokens": 10}
    bound = ledger.run(lambda tx: recovery.ensure_budget(tx, actor="human", target=ledger.target, policy=ledger.policy))
    assert bound["budget_id"] == result["budget_id"] and bound["requests_used"] == 1
    with pytest.raises(ContinuityConflict, match="cannot be reset"):
        ledger.run(lambda tx: recovery.ensure_budget(tx, actor="human", target=ledger.target, policy={**ledger.policy, "max_requests": 100}))
    assert second["generation_requested"] is False
    assert second["observations"][0]["block_id"] == block["block_id"]


@pytest.mark.parametrize("reason", sorted(recovery.REASONS))
def test_typed_reasons_remain_distinct_and_observation_replay_is_exact(ledger, reason):
    first = observe(ledger, reason)
    replay = observe(ledger, reason)
    assert replay["block_id"] == first["block_id"] and replay["replayed"]
    assert first["category"] == recovery.REASONS[reason]
    assert ledger.count("CX_PROCESSING_BLOCKS") == 1
    with pytest.raises(ContinuityConflict):
        observe(ledger, "FAILED" if reason != "FAILED" else "WAITING_HUMAN")


@pytest.mark.parametrize("match", ["MATCHED", "EMPTY"])
def test_embedding_timeout_keeps_actual_textual_path_separate_from_match(ledger, match):
    block = observe(ledger, "EMBEDDING_TIMEOUT", retrieval_path="TEXTUAL", match_state=match)
    assert (block["reason_code"], block["retrieval_path"], block["match_state"], block["category"]) == ("EMBEDDING_TIMEOUT", "TEXTUAL", match, "DEGRADED")
    ledger.run(lambda tx: recovery.claim_gate(tx, ledger.target["continuity_id"]))


def test_equivalent_tool_proposals_and_calls_count_once_per_durable_event(ledger):
    first = action(ledger, "action1", arguments={"a": 1, "b": 2})
    replay = action(ledger, "action1", arguments={"b": 2, "a": 1})
    assert first["action_id"] == replay["action_id"] and replay["replayed"]
    assert ledger.count("CX_PROCESSING_ACTIONS") == 1
    with pytest.raises(ContinuityConflict):
        action(ledger, "action1", arguments={"a": 3})
    ledger.run(lambda tx: recovery.record_action(tx, actor="human", target=ledger.target, action_key="proposal", action_kind="TOOL_PROPOSAL", tool_name="search", arguments={"a": 1, "b": 2}, token_count=10))
    third = action(ledger, "action3", arguments={"a": 1, "b": 2})
    assert third["stop"]["reason_code"] == "REPEATED_ACTION"
    assert third["budget"]["requests_used"] == 3 and third["budget"]["tokens_used"] == 30
    assert third["content_approved"] is False


def test_no_progress_stop_is_durable_and_blocks_existing_claim(ledger):
    for number in range(4):
        result = action(ledger, "action" + str(number), tool="tool" + str(number))
    assert result["stop"]["reason_code"] == "NO_PROGRESS"
    ledger.restart()
    with pytest.raises(ContinuityConflict, match="explicit exact recovery"):
        ledger.run(lambda tx: task_continuity.claim_attempt(tx, continuity_id=ledger.target["continuity_id"], worker_id="worker", business_key="business", request_digest="a" * 64))
    assert ledger.count("CX_TASK_CONTINUITY_ATTEMPTS") == 1
    with pytest.raises(ContinuityConflict, match="stopped operation"):
        action(ledger, "past-bound", tool="new-tool")
    assert ledger.count("CX_PROCESSING_ACTIONS") == 4
    replay = action(ledger, "action3", tool="tool3")
    assert replay["stop"]["block_id"] == result["stop"]["block_id"]


def test_completed_action_replays_but_new_effect_is_refused(ledger):
    first = action(ledger, "done")
    finish(ledger, "SUCCEEDED")
    assert action(ledger, "done")["action_id"] == first["action_id"]
    with pytest.raises(ContinuityConflict, match="completed or unknown"):
        action(ledger, "new")
    assert ledger.count("CX_PROCESSING_ACTIONS") == 2  # tool event plus the actual completed Task attempt


def test_recovery_receipt_replays_and_successor_inherits_same_budget(ledger):
    action(ledger, "original-use")
    block, receipt = admit(ledger)
    ledger.restart()
    replay = recovery.admit_retry("human", decision(ledger, block))
    assert replay["recovery_id"] == receipt["recovery_id"] and replay["replayed"]
    assert replay["status"] == "ACCEPTED" and not replay["dispatched"]
    assert ledger.count("CX_PROCESSING_RECOVERIES") == 1
    assert ledger.count("CX_TASK_CONTINUITY_LINKS") == 2
    assert ledger.count("TASK_PLANS") == 1 and ledger.count("CX_PROCESSING_BUDGETS") == 1
    roots = ledger.query("SELECT BUDGET_ID FROM CX_PROCESSING_CHAINS", {})
    assert len({item["budget_id"] for item in roots}) == 1
    assert ledger.query_one("SELECT REQUESTS_USED FROM CX_PROCESSING_BUDGETS", {})["requests_used"] == 2
    with pytest.raises(ContinuityConflict):
        recovery.admit_retry("human", decision(ledger, block, add_requests=3))
    assert ledger.count("CX_TASK_CONTINUITY_ATTEMPTS") == 1


@pytest.mark.parametrize("field", ["actor", "agent", "domain", "credential", "source", "capability", "approval", "revision"])
def test_current_authority_denies_admission_read_and_dispatch(ledger, field):
    block, receipt = admit(ledger)
    capacity(ledger, receipt, "RESERVED")
    ledger.grants[field] = False
    with pytest.raises(PermissionError):
        recovery.admit_retry("human", decision(ledger, block))
    with pytest.raises(PermissionError):
        ledger.run(lambda tx: recovery.read_diagnostics(tx, actor="human", continuity_id=ledger.target["continuity_id"]))
    with pytest.raises(PermissionError):
        ledger.run(lambda tx: recovery.capacity_gate(tx, actor="human", recovery_id=receipt["recovery_id"], admission_id="admission"))
    assert ledger.query_one("SELECT STATUS FROM CX_PROCESSING_RECOVERY_STATES", {})["status"] == "ACCEPTED"


def test_retired_or_changed_target_is_not_substituted(ledger):
    block = observe(ledger)
    finish(ledger)
    for field, value in (("target_revision", "other"), ("target_id", "successor-source"), ("source_revision_id", "new-revision"), ("input_digest", "f" * 64)):
        target = {**ledger.target, field: value}
        with pytest.raises(ContinuityConflict):
            recovery.admit_retry("human", decision(ledger, block, target=target))
    assert ledger.count("CX_PROCESSING_RECOVERIES") == 0


def test_original_target_is_frozen_before_the_first_block(ledger):
    changed = {**ledger.target, "source_revision_id": "successor-revision"}
    with pytest.raises(ContinuityConflict, match="cannot be substituted"):
        ledger.run(lambda tx: recovery.observe(tx, actor="human", target=changed, reason_code="SOURCE_REVOKED", observation_key="changed"))
    assert ledger.count("CX_PROCESSING_BLOCKS") == 0


def test_default_runtime_authority_reuses_original_credential_and_source_checks(ledger, monkeypatch):
    from lib import continuity_runtime, continuity_execution_links, continuity_sources, native_runtime, continuity_work, model_credentials
    ledger.db.executescript("""
        CREATE TABLE CX_RUNTIME_CONTEXT_BINDINGS(EXECUTION_ID TEXT PRIMARY KEY,REQUESTED_BY TEXT,AGENT_ID TEXT,ASSEMBLY_ID TEXT);
        CREATE TABLE CX_RUNTIME_CONTEXT_CREDENTIALS(EXECUTION_ID TEXT PRIMARY KEY,TOKEN_DIGEST TEXT,INSTANCE_ID TEXT,FENCING_TOKEN INTEGER);
        INSERT INTO CX_RUNTIME_CONTEXT_BINDINGS VALUES('execution','human','agent','assembly');
        INSERT INTO CX_RUNTIME_CONTEXT_CREDENTIALS VALUES('execution','original-token-digest','original-instance',7);
        CREATE TABLE CX_RUNTIME_MODEL_CREDENTIALS(EXECUTION_ID TEXT PRIMARY KEY,ACTOR_ID TEXT,CREDENTIAL_KIND TEXT,CREDENTIAL_DIGEST TEXT,AUTH_METHOD TEXT,PERMISSION_VERSION INTEGER,MFA_LEVEL TEXT,NODE_ID TEXT,SESSION_CREATED_AT TEXT);
    """)
    ledger.db.execute("INSERT INTO CX_RUNTIME_MODEL_CREDENTIALS VALUES(?,?,?,?,?,?,?,?,?)", (
        'execution','human','WEB','e'*64,'LOCAL',1,'PASSWORD','node','2026-10-28T00:00:00'))
    calls = []
    monkeypatch.setattr(continuity_work, "_authorize", lambda *args, **kwargs: None)
    monkeypatch.setattr(continuity_execution_links, "authorize", lambda *args: None)
    monkeypatch.setattr(native_runtime, "get_execution", lambda *args, **kwargs: calls.append("execution-reader"))
    monkeypatch.setattr(continuity_runtime, "_authority", lambda *args: calls.append("current-agent-domain"))
    monkeypatch.setattr(continuity_runtime, "_requester_context", lambda *args: calls.append("requester-and-agent-source-intersection"))
    monkeypatch.setattr(continuity_sources, "resolve", lambda *args, **kwargs: calls.append("exact-source"))
    def model_credential(tx, binding):
        assert binding.actor == "human" and binding.credential_digest == "e" * 64
        if not ledger.grants["credential"]:
            raise PermissionError("Original credential revoked")
    monkeypatch.setattr(model_credentials, "recheck", model_credential)
    def credential(tx, actor, domain, value):
        assert value["token_digest"] == "original-token-digest" and value["fencing_token"] == 7
        calls.append("original-credential")
        if not ledger.grants["credential"]:
            raise PermissionError("Original credential revoked")
    monkeypatch.setattr(continuity_runtime, "_credential", credential)
    result = ledger.run(lambda tx: recovery.read_diagnostics(tx, actor="human", continuity_id=ledger.target["continuity_id"], authority=DEFAULT_AUTHORITY))
    assert result["generation_requested"] is False
    assert set(calls) == {"execution-reader", "current-agent-domain", "requester-and-agent-source-intersection", "exact-source", "original-credential"}
    ledger.grants["credential"] = False
    with pytest.raises(PermissionError, match="revoked"):
        ledger.run(lambda tx: recovery.read_diagnostics(tx, actor="human", continuity_id=ledger.target["continuity_id"], authority=DEFAULT_AUTHORITY))


def test_required_audit_failure_rolls_back_admission_receipt_and_successor(ledger, monkeypatch):
    from lib import identity_api
    block = observe(ledger)
    finish(ledger)
    monkeypatch.setattr(identity_api, "_audit_tx", lambda *args: (_ for _ in ()).throw(RuntimeError("audit unavailable")))
    with pytest.raises(RuntimeError, match="audit unavailable"):
        recovery.admit_retry("human", decision(ledger, block))
    assert ledger.count("CX_PROCESSING_RECOVERIES") == 0
    assert ledger.count("CX_PROCESSING_RECOVERY_STATES") == 0
    assert ledger.count("CX_TASK_CONTINUITY_LINKS") == 1
    assert ledger.query_one("SELECT STATUS,VERSION FROM CX_PROCESSING_BLOCKS", {}) == {"status": "OPEN", "version": 1}


def test_agent_cannot_admit_retry_or_change_budget(ledger):
    block = observe(ledger)
    finish(ledger)
    with pytest.raises(PermissionError, match="Human"):
        recovery.admit_retry("agent", decision(ledger, block))
    with pytest.raises(TypeError, match="return None"):
        recovery.admit_retry("human", decision(ledger, block), authority=lambda *args: {"allowed": True})
    assert ledger.count("CX_PROCESSING_RECOVERIES") == 0


def test_queued_recovery_has_no_worker_lease_or_external_dispatch(ledger):
    block, receipt = admit(ledger)
    capacity(ledger, receipt)
    queued = ledger.run(lambda tx: recovery.bind_capacity(tx, actor="human", recovery_id=receipt["recovery_id"], admission_id="admission"))
    assert queued["status"] == "QUEUED" and not queued["dispatched"]
    with pytest.raises(ContinuityConflict, match="awaits current endpoint"):
        ledger.run(lambda tx: task_continuity.claim_attempt(tx, continuity_id=receipt["successor_continuity_id"], worker_id="next", business_key="business", request_digest="a" * 64))
    with pytest.raises(PermissionError):
        ledger.run(lambda tx: recovery.capacity_gate(tx, actor="human", recovery_id=receipt["recovery_id"], admission_id="admission"))
    assert ledger.count("CX_TASK_CONTINUITY_LEASES") == 1
    assert ledger.count("CX_TASK_CONTINUITY_ATTEMPTS") == 1
    assert recovery.admit_retry("human", decision(ledger, block))["status"] == "QUEUED"


@pytest.mark.parametrize("field,value", [("actor", "other"), ("chain", "unrelated"), ("attempt", "other"), ("fingerprint", "e" * 64), ("fence", 0)])
def test_capacity_gate_checks_authoritative_exact_reservation(ledger, field, value):
    _, receipt = admit(ledger)
    capacity(ledger, receipt, "RESERVED", **{field: value})
    with pytest.raises(PermissionError, match="exact current capacity"):
        ledger.run(lambda tx: recovery.capacity_gate(tx, actor="human", recovery_id=receipt["recovery_id"], admission_id="admission"))


def test_dispatch_gate_only_allows_claim_after_capacity_commits_dispatching(ledger):
    block, receipt = admit(ledger)
    capacity(ledger, receipt, "RESERVED")
    ledger.run(lambda tx: recovery.capacity_gate(tx, actor="human", recovery_id=receipt["recovery_id"], admission_id="admission"))
    with pytest.raises(ContinuityConflict):
        ledger.run(lambda tx: recovery.claim_gate(tx, receipt["successor_continuity_id"]))
    ledger.run(lambda tx: tx.execute("UPDATE CX_MODEL_ADMISSIONS SET STATUS='DISPATCHING' WHERE ADMISSION_ID=:admission", {"admission": "admission"}))
    claimed = ledger.run(lambda tx: task_continuity.claim_attempt(tx, continuity_id=receipt["successor_continuity_id"], worker_id="next", business_key="business", request_digest="a" * 64))
    assert claimed["attempt_no"] == 1
    with pytest.raises((PermissionError, ContinuityConflict)):
        ledger.run(lambda tx: recovery.capacity_gate(tx, actor="human", recovery_id=receipt["recovery_id"], admission_id="admission"))
    assert recovery.admit_retry("human", decision(ledger, block))["recovery_id"] == receipt["recovery_id"]
    assert ledger.count("CX_TASK_CONTINUITY_ATTEMPTS") == 2


def test_successor_consumes_original_counters_and_its_exact_bounded_allowance(ledger):
    for number in range(3):
        stopped = action(ledger, "original" + str(number))
    block = stopped["stop"]
    finish(ledger)
    receipt = recovery.admit_retry("human", decision(ledger, block))
    capacity(ledger, receipt, "RESERVED")
    ledger.run(lambda tx: recovery.capacity_gate(tx, actor="human", recovery_id=receipt["recovery_id"], admission_id="admission"))
    ledger.run(lambda tx: tx.execute("UPDATE CX_MODEL_ADMISSIONS SET STATUS='DISPATCHING' WHERE ADMISSION_ID=:admission", {"admission": "admission"}))
    attempt = ledger.run(lambda tx: task_continuity.claim_attempt(tx, continuity_id=receipt["successor_continuity_id"], worker_id="worker", business_key="business", request_digest="a" * 64))
    ledger.target = {**ledger.target, "continuity_id": receipt["successor_continuity_id"], "attempt_id": attempt["attempt_id"]}
    first = action(ledger, "retry1")
    assert first["budget"]["requests_used"] == 5 and first["stop"] is None
    second = action(ledger, "retry2")
    assert second["budget"]["requests_used"] == 6 and second["stop"]["reason_code"] == "BUDGET_REQUESTS"
    with pytest.raises(ContinuityConflict, match="stopped operation"):
        action(ledger, "retry3")
    assert ledger.count("CX_PROCESSING_BUDGETS") == 1
    assert ledger.count("CX_PROCESSING_ACTIONS") == 6


def test_expired_successor_records_unknown_before_a_capacity_refusal(ledger):
    _, receipt = admit(ledger)
    capacity(ledger, receipt, "RESERVED")
    ledger.run(lambda tx: recovery.capacity_gate(tx, actor="human", recovery_id=receipt["recovery_id"], admission_id="admission"))
    ledger.run(lambda tx: tx.execute("UPDATE CX_MODEL_ADMISSIONS SET STATUS='DISPATCHING' WHERE ADMISSION_ID=:admission", {"admission": "admission"}))
    attempt = ledger.run(lambda tx: task_continuity.claim_attempt(tx, continuity_id=receipt["successor_continuity_id"], worker_id="next", business_key="business", request_digest="a" * 64))
    expired = (datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=2)).isoformat(sep=" ")
    ledger.run(lambda tx: (
        tx.execute("UPDATE CX_TASK_CONTINUITY_LEASES SET LEASE_EXPIRES_AT=:expires WHERE CONTINUITY_ID=:chain", {"expires": expired, "chain": receipt["successor_continuity_id"]}),
        tx.execute("UPDATE CX_TASK_CONTINUITY_ATTEMPTS SET LEASE_EXPIRES_AT=:expires WHERE ATTEMPT_ID=:attempt", {"expires": expired, "attempt": attempt["attempt_id"]}),
        tx.execute("UPDATE CX_MODEL_ADMISSIONS SET STATUS='UNKNOWN' WHERE ADMISSION_ID=:admission", {"admission": "admission"})))
    result = ledger.run(lambda tx: task_continuity.claim_attempt(tx, continuity_id=receipt["successor_continuity_id"], worker_id="replacement", business_key="business", request_digest="a" * 64))
    assert result["status"] == "UNOBSERVED" and result["reconciliation_required"]
    assert ledger.count("CX_TASK_CONTINUITY_ATTEMPTS") == 2
    assert ledger.query_one("SELECT STATUS FROM CX_TASK_CONTINUITY_ATTEMPTS WHERE ATTEMPT_ID=:attempt", {"attempt": attempt["attempt_id"]})["status"] == "UNOBSERVED"


def test_unknown_effect_requires_reconciliation_and_preserves_fencing(ledger):
    finish(ledger, "UNOBSERVED")
    block = observe(ledger, "POSSIBLE_SEND")
    with pytest.raises(ContinuityConflict, match="reconciled"):
        recovery.admit_retry("human", decision(ledger, block))
    reader = lambda tx, target: recovery.ReconciliationEvidence("LOCAL_LIFECYCLE", "e" * 64, "UNOBSERVED")
    assert recovery.reconcile("human", block["block_id"], read_evidence=reader)["status"] == "UNOBSERVED"
    with pytest.raises(ContinuityConflict):
        recovery.admit_retry("human", decision(ledger, block))
    proof = lambda tx, target: recovery.ReconciliationEvidence("OPERATOR_RESOLUTION", "f" * 64, "FAILED")
    result = recovery.reconcile("human", block["block_id"], read_evidence=proof)
    assert result["status"] == "FAILED" and result["generation_requested"] is False
    ledger.restart()
    assert recovery.reconcile("human", block["block_id"], read_evidence=proof)["replayed"]
    with pytest.raises(ContinuityConflict, match="stale"):
        finish(ledger, "SUCCEEDED")
    receipt = recovery.admit_retry("human", decision(ledger, block))
    assert receipt["status"] == "ACCEPTED"
    assert ledger.count("CX_TASK_CONTINUITY_ATTEMPTS") == 1


def test_plain_flags_are_not_original_request_reconciliation_evidence(ledger):
    finish(ledger, "UNOBSERVED")
    block = observe(ledger, "CLIENT_CLOSED")
    with pytest.raises(ContinuityError, match="Trusted exact"):
        recovery.reconcile("human", block["block_id"], read_evidence=lambda *args: {"completed": True})
    assert ledger.count("CX_PROCESSING_RESOLUTIONS") == 0
    assert ledger.query_one("SELECT STATUS FROM CX_TASK_CONTINUITY_ATTEMPTS", {})["status"] == "UNOBSERVED"


def test_capacity_unknown_must_reconcile_atomically_with_original_request(ledger):
    finish(ledger, "UNOBSERVED")
    block = observe(ledger, "POSSIBLE_SEND")
    ledger.run(lambda tx: tx.execute("INSERT INTO CX_MODEL_ADMISSIONS(ADMISSION_ID,STATUS,SOURCE_ID,SOURCE_ATTEMPT_ID) VALUES(:admission,'UNKNOWN',:chain,:attempt)", {"admission": "original-admission", "chain": ledger.target["continuity_id"], "attempt": ledger.target["attempt_id"]}))
    reader = lambda tx, target: recovery.ReconciliationEvidence("TERMINAL_RESPONSE", "f" * 64, "FAILED")
    with pytest.raises(ContinuityError, match="capacity lifecycle"):
        recovery.reconcile("human", block["block_id"], read_evidence=reader)
    with pytest.raises(ContinuityConflict, match="remains unknown"):
        recovery.reconcile("human", block["block_id"], read_evidence=reader, reconcile_capacity=lambda *args: None)
    assert ledger.count("CX_PROCESSING_RESOLUTIONS") == 0
    def resolve(tx, admissions, evidence):
        tx.execute("UPDATE CX_MODEL_ADMISSIONS SET STATUS='COMPLETED' WHERE ADMISSION_ID=:admission", {"admission": admissions[0]["admission_id"]})
    assert recovery.reconcile("human", block["block_id"], read_evidence=reader, reconcile_capacity=resolve)["status"] == "FAILED"
    assert ledger.query_one("SELECT STATUS FROM CX_MODEL_ADMISSIONS", {})["status"] == "COMPLETED"


def test_completed_original_replays_its_result_reference_after_restart(ledger):
    block = observe(ledger)
    finish(ledger, "SUCCEEDED")
    ledger.restart()
    result = recovery.admit_retry("human", decision(ledger, block))
    assert result == {"status": "COMPLETED", "replayed": True, "result_reference": {"link_kind": "RUNTIME", "link_id": "execution", "attempt_id": ledger.target["attempt_id"]}}
    assert ledger.count("CX_PROCESSING_RECOVERIES") == 0
    assert ledger.count("CX_TASK_CONTINUITY_ATTEMPTS") == 1


def test_successful_reconciliation_returns_result_without_another_idle_confirmation(ledger):
    finish(ledger, "UNOBSERVED")
    block = observe(ledger, "LEASE_EXPIRED")
    proof = lambda tx, target: recovery.ReconciliationEvidence("TERMINAL_RESPONSE", "f" * 64, "SUCCEEDED")
    assert recovery.reconcile("human", block["block_id"], read_evidence=proof)["status"] == "SUCCEEDED"
    assert recovery.reconcile("human", block["block_id"], read_evidence=proof)["replayed"]
    assert recovery.admit_retry("human", decision(ledger, block))["status"] == "COMPLETED"
    assert ledger.count("CX_TASK_CONTINUITY_ATTEMPTS") == 1


def test_recovery_gate_is_selected_by_explicit_release_contract(monkeypatch):
    from lib import edition_features
    class HistoricalTransaction:
        def __init__(self, status="SUCCEEDED"):
            self.status = status
        def query_one(self, statement, params):
            if "CX_PROCESSING_" in statement:
                raise AssertionError("Historical service queried a successor table")
            if "CX_TASK_CONTINUITY_LINKS" in statement:
                return {"status": self.status, "actor_id": "human", "request_digest": "a" * 64}
            return None
    monkeypatch.setattr(edition_features, "MODEL_RUNTIME_CONTEXT_ENABLED", False, raising=False)
    with pytest.raises(ContinuityError, match="terminal"):
        task_continuity.claim_attempt(HistoricalTransaction(), continuity_id="old", worker_id="worker", business_key="business", request_digest="a" * 64)
    monkeypatch.setattr(edition_features, "MODEL_RUNTIME_CONTEXT_ENABLED", True)
    with pytest.raises(AssertionError, match="successor table"):
        task_continuity.claim_attempt(HistoricalTransaction("PENDING"), continuity_id="new", worker_id="worker", business_key="business", request_digest="a" * 64)
