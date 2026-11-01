"""Offline native Graph/Task processing joins with persistent local receipts."""
from datetime import datetime, timedelta
import json
import re
import sqlite3

import pytest

from lib import processing_graph as graph, processing_recovery as recovery
from lib import task_continuity as tasks, processing_recovery_schema, graph_runtime
from lib.continuity_state import ContinuityConflict, ContinuityError


@pytest.fixture
def ledger(tmp_path, monkeypatch):
    from lib import connection, edition_features, identity_api
    monkeypatch.setattr(edition_features, "MODEL_RUNTIME_CONTEXT_ENABLED", True, raising=False)
    monkeypatch.setattr(connection, "DATABASE_DIALECT", "oracle")

    class Ledger:
        path = tmp_path / "graph-processing.sqlite"
        authorized = True
        checks = []

        def __init__(self):
            self.open()

        def open(self):
            self.db = sqlite3.connect(self.path)
            self.db.row_factory = sqlite3.Row
            self.db.execute("PRAGMA foreign_keys=ON")

        def restart(self):
            self.db.close()
            self.open()

        def query(self, sql, params):
            assert set(re.findall(r":([a-zA-Z_]\w*)", sql)) == set(params)
            return [{str(key).lower(): value for key, value in dict(item).items()}
                    for item in self.db.execute(sql.replace(" FOR UPDATE", ""), params)]

        def query_one(self, sql, params):
            values = self.query(sql, params)
            return values[0] if values else None

        def execute(self, sql, params):
            assert set(re.findall(r":([a-zA-Z_]\w*)", sql)) == set(params)
            return self.db.execute(sql.replace(" FOR UPDATE", ""), params).rowcount

        def run(self, callback):
            try:
                result = callback(self)
                self.db.commit()
                return result
            except Exception:
                self.db.rollback()
                raise

        def authorize(self, *_args, **_kwargs):
            self.checks.append((_args, _kwargs))
            if not self.authorized:
                raise PermissionError("Original Graph authority revoked")

        def native_attempt(self, attempt="ga1", *, run="run", node="node", input_value=None):
            self.run(lambda tx: tx.execute("INSERT INTO GRAPH_ATTEMPTS(ATTEMPT_ID,RUN_ID,NODE_RUN_ID,WORKER_ID,STATUS,FENCING_TOKEN,INPUT_STATE_JSON,IDEMPOTENCY_KEY) "
                "VALUES(:id,:run,:node,'worker','RUNNING',1,:input,:id)",
                {"id": attempt, "run": run, "node": node, "input": json.dumps(input_value or {"input": "same"})}))
            return self.run(lambda tx: graph.claim(tx, attempt, 120))

    value = Ledger()
    value.db.executescript("""
        CREATE TABLE CX_PRINCIPALS(PRINCIPAL_ID TEXT PRIMARY KEY,PRINCIPAL_TYPE TEXT,STATUS TEXT);
        CREATE TABLE CX_SECURITY_DOMAINS(SECURITY_DOMAIN_ID TEXT PRIMARY KEY,STATUS TEXT);
        CREATE TABLE CX_DOMAIN_MEMBERS(PRINCIPAL_ID TEXT,SECURITY_DOMAIN_ID TEXT,STATUS TEXT,VALID_UNTIL TIMESTAMP);
        CREATE TABLE CX_CONTEXT_ASSEMBLIES(ASSEMBLY_ID TEXT PRIMARY KEY);
        CREATE TABLE TASK_PLANS(PLAN_ID TEXT PRIMARY KEY,AGENT_ID TEXT,STATUS TEXT);
        CREATE TABLE CX_MODEL_ADMISSIONS(ADMISSION_ID TEXT PRIMARY KEY,STATUS TEXT,SOURCE_ID TEXT,SOURCE_ATTEMPT_ID TEXT);
        CREATE TABLE GRAPH_RUNS(RUN_ID TEXT PRIMARY KEY,ACTOR_ID TEXT,GRAPH_VERSION_ID TEXT,PLAN_ID TEXT,
            DEFINITION_DIGEST TEXT,PLAN_DIGEST TEXT,INPUT_STATE_JSON TEXT,STATUS TEXT,
            ERROR_CODE TEXT,ERROR_MESSAGE TEXT,COMPLETED_AT TIMESTAMP,UPDATED_AT TIMESTAMP);
        CREATE TABLE GRAPH_NODES(GRAPH_VERSION_ID TEXT,NODE_KEY TEXT,SIDE_EFFECT_CLASS TEXT);
        CREATE TABLE GRAPH_NODE_RUNS(NODE_RUN_ID TEXT PRIMARY KEY,RUN_ID TEXT,NODE_KEY TEXT,ITERATION_NO INTEGER,
            STATUS TEXT,OUTPUT_CHECKPOINT_ID TEXT,UPDATED_AT TIMESTAMP);
        CREATE TABLE GRAPH_ATTEMPTS(ATTEMPT_ID TEXT PRIMARY KEY,RUN_ID TEXT,NODE_RUN_ID TEXT,WORKER_ID TEXT,
            STATUS TEXT,FENCING_TOKEN INTEGER,INPUT_STATE_JSON TEXT,IDEMPOTENCY_KEY TEXT,COMPLETION_DIGEST TEXT);
        CREATE TABLE GRAPH_READY_NODES(READY_ID TEXT PRIMARY KEY,NODE_RUN_ID TEXT,STATUS TEXT,CLAIMED_AT TIMESTAMP,AVAILABLE_AT TIMESTAMP);
        CREATE TABLE GRAPH_CHECKPOINTS(CHECKPOINT_ID TEXT PRIMARY KEY,RUN_ID TEXT,STATE_HASH TEXT);
        CREATE TABLE GRAPH_STATE_EVENTS(CHECKPOINT_ID TEXT,RUN_ID TEXT,SOURCE_ATTEMPT_ID TEXT);
        INSERT INTO CX_PRINCIPALS VALUES('human','HUMAN','ACTIVE'),('agent','AGENT','ACTIVE');
        INSERT INTO CX_SECURITY_DOMAINS VALUES('domain','ACTIVE');
        INSERT INTO CX_DOMAIN_MEMBERS VALUES('human','domain','ACTIVE',NULL);
        INSERT INTO TASK_PLANS VALUES('plan','agent','RUNNING');
        INSERT INTO GRAPH_RUNS(RUN_ID,ACTOR_ID,GRAPH_VERSION_ID,PLAN_ID,DEFINITION_DIGEST,PLAN_DIGEST,INPUT_STATE_JSON,STATUS)
            VALUES('run','human','version','compiled','definition','plan-digest','{"input":"same"}','RUNNING');
        INSERT INTO GRAPH_NODE_RUNS VALUES('node','run','tool',0,'RUNNING',NULL,NULL);
        INSERT INTO GRAPH_NODES VALUES('version','tool','NONE');
        INSERT INTO GRAPH_READY_NODES VALUES('ready','node','CLAIMED',NULL,NULL);
    """)
    for sql in tasks.schema_statements("pg") + processing_recovery_schema.schema_statements("pg"):
        value.db.execute(sql)
    value.db.commit()
    monkeypatch.setattr(connection, "execute_transaction_callback", value.run)
    monkeypatch.setattr(identity_api, "_audit_tx", lambda *_args: None)
    monkeypatch.setattr(graph.work, "_authorize", value.authorize)
    monkeypatch.setattr(graph.execution_links, "authorize", value.authorize)
    monkeypatch.setattr(recovery, "_default_authority", graph.authorize_target)
    value.run(lambda tx: graph.bind_run(tx, "run", domain_id="domain", canonical_task_id="plan"))
    yield value
    value.db.close()


def info(ledger, attempt="ga1"):
    return ledger.run(lambda tx: graph._target_for_attempt(tx, attempt))


def failed(ledger, attempt="ga1", *, unknown=False, retry=False):
    ledger.run(lambda tx: tx.execute("UPDATE GRAPH_ATTEMPTS SET STATUS='FAILED' WHERE ATTEMPT_ID=:attempt", {"attempt": attempt}))
    ledger.run(lambda tx: tx.execute("UPDATE GRAPH_NODE_RUNS SET STATUS='REVIEW_REQUIRED' WHERE NODE_RUN_ID='node'", {}))
    return ledger.run(lambda tx: graph.finish(tx, attempt, outcome="UNOBSERVED" if unknown else "FAILED",
                                             error_code="POSSIBLE_SEND" if unknown else "FAILED", retry=retry))


def retry_receipt(ledger):
    attempt, link, shadow, target = info(ledger)
    block = ledger.query_one("SELECT * FROM CX_PROCESSING_BLOCKS WHERE CONTINUITY_ID=:chain", {"chain": link["continuity_id"]})
    request = {"block_id": block["block_id"], "expected_version": block["version"], "target": target.model_dump(),
               "reason_code": block["reason_code"], "add_requests": 1, "add_steps": 3, "add_tokens": 100,
               "decision_digest": "d" * 64, "idempotency_key": "human-retry"}
    return recovery.admit_retry("human", request)


def test_real_graph_attempt_has_distinct_task_attempt_and_persistent_frozen_tuple(ledger):
    claimed = ledger.native_attempt()
    native, link, task, target = info(ledger)
    assert claimed["allowed"] and task["attempt_id"] != native["attempt_id"]
    assert target.business_key == native["attempt_id"]
    assert target.attempt_id == task["attempt_id"]
    assert link["link_kind"] == "GRAPH" and link["link_id"] == native["attempt_id"]
    budget = ledger.run(lambda tx: recovery._budget(tx, link["continuity_id"]))
    assert budget["steps_used"] == 1 and budget["requests_used"] == 0
    ledger.restart()
    assert info(ledger)[3] == target


@pytest.mark.parametrize("field", ("input_state_json", "plan_digest", "graph_version_id"))
def test_changed_graph_input_or_revision_is_rejected(ledger, field):
    ledger.native_attempt()
    target = info(ledger)[3]
    if field == "input_state_json":
        ledger.run(lambda tx: tx.execute("UPDATE GRAPH_ATTEMPTS SET INPUT_STATE_JSON='{}' WHERE ATTEMPT_ID='ga1'", {}))
    else:
        ledger.run(lambda tx: tx.execute("UPDATE GRAPH_RUNS SET " + field.upper() + "='changed' WHERE RUN_ID='run'", {}))
    with pytest.raises(ContinuityConflict, match="revision or input changed"):
        ledger.run(lambda tx: graph.authorize_target(tx, "human", target, "RECOVER"))


def test_current_original_graph_authority_is_required_for_every_observation(ledger):
    ledger.native_attempt()
    target = info(ledger)[3]
    ledger.authorized = False
    with pytest.raises(PermissionError):
        ledger.run(lambda tx: graph.authorize_target(tx, "human", target, "READ"))
    with pytest.raises(PermissionError):
        ledger.native_attempt("denied-new-attempt")


def test_new_graph_attempt_cannot_rebind_changed_run_revision_to_original_budget(ledger):
    ledger.run(lambda tx: tx.execute("UPDATE GRAPH_RUNS SET PLAN_DIGEST='changed' WHERE RUN_ID='run'", {}))
    with pytest.raises(ContinuityConflict, match="revision or input changed"):
        ledger.native_attempt()
    assert ledger.query_one("SELECT COUNT(*) AS count FROM CX_TASK_CONTINUITY_ATTEMPTS", {})["count"] == 0


def test_ambiguous_domain_cannot_be_guessed_and_missing_bindings_fail_closed(ledger):
    ledger.run(lambda tx: tx.execute("INSERT INTO CX_DOMAIN_MEMBERS VALUES('human','other','ACTIVE',NULL)", {}))
    ledger.run(lambda tx: tx.execute("INSERT INTO CX_SECURITY_DOMAINS VALUES('other','ACTIVE')", {}))
    with pytest.raises(ContinuityError, match="exact original"):
        ledger.run(lambda tx: graph._domain(tx, "human", None))
    with pytest.raises(ContinuityError, match="original processing binding"):
        ledger.run(lambda tx: graph.control_gate(tx, "legacy"))


def test_known_retryable_failure_inherits_budget_without_new_stop(ledger):
    ledger.native_attempt()
    failed(ledger, retry=True)
    second = ledger.native_attempt("ga2")
    assert second["allowed"]
    old = ledger.run(lambda tx: recovery._budget(tx, info(ledger)[1]["continuity_id"]))
    current = ledger.run(lambda tx: recovery._budget(tx, info(ledger, "ga2")[1]["continuity_id"]))
    assert current["budget_id"] == old["budget_id"] and current["steps_used"] == 2


def test_unknown_blocks_other_node_retry_and_fork_after_restart(ledger):
    ledger.native_attempt()
    failed(ledger, unknown=True)
    ledger.restart()
    for callback in (lambda tx: graph.control_gate(tx, "run"), lambda tx: graph.claim(tx, "ga1", 120)):
        with pytest.raises(ContinuityConflict, match="Reconcile"):
            ledger.run(callback)
    assert ledger.query_one("SELECT COUNT(*) AS count FROM CX_TASK_CONTINUITY_ATTEMPTS", {})["count"] == 1
    with pytest.raises(ContinuityConflict):
        retry_receipt(ledger)


def test_finished_checkpoint_counts_tokens_once_and_never_approves_output(ledger):
    ledger.native_attempt()
    result = ledger.run(lambda tx: graph.finish(tx, "ga1", outcome="SUCCEEDED", token_count=14, checkpoint_digest="c" * 64))
    replay = ledger.run(lambda tx: graph.finish(tx, "ga1", outcome="SUCCEEDED", token_count=14, checkpoint_digest="c" * 64))
    assert result["status"] == "SUCCEEDED" and replay["replayed"]
    budget = ledger.run(lambda tx: recovery._budget(tx, info(ledger)[1]["continuity_id"]))
    assert budget["tokens_used"] == 14 and budget["steps_used"] == 1
    assert ledger.query_one("SELECT COUNT(*) AS count FROM CX_PROCESSING_ACTIONS", {})["count"] == 2


def test_explicit_pure_node_dispatch_uses_exact_successor_and_retains_root_usage(ledger):
    ledger.native_attempt()
    failed(ledger)
    receipt = retry_receipt(ledger)
    assert receipt["status"] == "ACCEPTED" and not receipt["dispatched"]
    dispatched = ledger.run(lambda tx: graph.dispatch_recovery(tx, "human", receipt["recovery_id"]))
    assert dispatched["status"] == "DISPATCHED" and dispatched["admission_id"] is None
    assert ledger.run(lambda tx: graph.dispatch_recovery(tx, "human", receipt["recovery_id"]))["replayed"]
    claimed = ledger.native_attempt("ga2")
    assert claimed["continuity_id"] == receipt["successor_continuity_id"]
    target = info(ledger, "ga2")[3]
    assert target.business_key == "ga1" and target.attempt_id != info(ledger)[3].attempt_id
    budget = ledger.run(lambda tx: recovery._budget(tx, claimed["continuity_id"]))
    assert budget["steps_used"] == 2
    ledger.run(lambda tx: graph.finish(tx, "ga2", outcome="SUCCEEDED", checkpoint_digest="e" * 64))
    assert ledger.query_one("SELECT STATUS FROM CX_PROCESSING_RECOVERY_STATES WHERE RECOVERY_ID=:id", {"id": receipt["recovery_id"]})["status"] == "COMPLETED"
    ledger.run(lambda tx: graph.control_gate(tx, "run"))


def test_recovery_cannot_substitute_node_input_or_enable_external_effect(ledger):
    ledger.native_attempt()
    failed(ledger)
    receipt = retry_receipt(ledger)
    ledger.run(lambda tx: tx.execute("UPDATE GRAPH_NODES SET SIDE_EFFECT_CLASS='NON_IDEMPOTENT'", {}))
    with pytest.raises(ContinuityError, match="stopped pure Graph"):
        ledger.run(lambda tx: graph.dispatch_recovery(tx, "human", receipt["recovery_id"]))
    ledger.run(lambda tx: tx.execute("UPDATE GRAPH_NODES SET SIDE_EFFECT_CLASS='NONE'", {}))
    ledger.run(lambda tx: graph.dispatch_recovery(tx, "human", receipt["recovery_id"]))
    with pytest.raises(ContinuityConflict, match="replace the original"):
        ledger.native_attempt("ga2", input_value={"input": "substitution"})
    assert ledger.query_one("SELECT COUNT(*) AS count FROM CX_TASK_CONTINUITY_ATTEMPTS", {})["count"] == 1


def test_fork_retains_frozen_server_budget_and_cannot_reset_with_user_limits(ledger):
    ledger.native_attempt()
    ledger.run(lambda tx: graph.finish(tx, "ga1", outcome="SUCCEEDED", token_count=7, checkpoint_digest="c" * 64))
    ledger.run(lambda tx: tx.execute("INSERT INTO GRAPH_RUNS SELECT 'fork',ACTOR_ID,GRAPH_VERSION_ID,PLAN_ID,DEFINITION_DIGEST," 
        "PLAN_DIGEST,INPUT_STATE_JSON,'RUNNING',NULL,NULL,NULL,NULL FROM GRAPH_RUNS WHERE RUN_ID='run'", {}))
    child = ledger.run(lambda tx: graph.bind_run(tx, "fork", parent_run_id="run"))
    original = ledger.run(lambda tx: recovery._budget(tx, graph._root(tx, "run")["continuity_id"]))
    inherited = ledger.run(lambda tx: recovery._budget(tx, child["continuity_id"]))
    assert inherited["budget_id"] == original["budget_id"]
    assert inherited["tokens_used"] == 7


def test_only_native_successful_checkpoint_is_trusted_terminal_reconciliation(ledger):
    ledger.native_attempt()
    target = info(ledger)[3]
    assert ledger.run(lambda tx: graph.read_evidence(tx, target)).outcome == "UNOBSERVED"
    ledger.run(lambda tx: tx.execute("UPDATE GRAPH_ATTEMPTS SET STATUS='FAILED',COMPLETION_DIGEST='fake' WHERE ATTEMPT_ID='ga1'", {}))
    assert ledger.run(lambda tx: graph.read_evidence(tx, target)).outcome == "UNOBSERVED"
    ledger.run(lambda tx: tx.execute("INSERT INTO GRAPH_CHECKPOINTS VALUES('checkpoint','run',:digest)", {"digest": "f" * 64}))
    ledger.run(lambda tx: tx.execute("INSERT INTO GRAPH_STATE_EVENTS VALUES('checkpoint','run','ga1')", {}))
    ledger.run(lambda tx: tx.execute("UPDATE GRAPH_NODE_RUNS SET OUTPUT_CHECKPOINT_ID='checkpoint' WHERE NODE_RUN_ID='node'", {}))
    ledger.run(lambda tx: tx.execute("UPDATE GRAPH_ATTEMPTS SET STATUS='SUCCEEDED',COMPLETION_DIGEST='commit' WHERE ATTEMPT_ID='ga1'", {}))
    evidence = ledger.run(lambda tx: graph.read_evidence(tx, target))
    assert evidence.kind == "LOCAL_LIFECYCLE" and evidence.outcome == "SUCCEEDED"


def test_native_heartbeat_extends_same_task_lease_and_never_revives_expired_lease(ledger):
    ledger.native_attempt()
    expires = tasks._now() + timedelta(minutes=10)
    assert ledger.run(lambda tx: graph.heartbeat(tx, "ga1", expires))
    assert tasks._utc_naive(info(ledger)[2]["lease_expires_at"]) == expires
    ledger.run(lambda tx: tx.execute("UPDATE CX_TASK_CONTINUITY_LEASES SET LEASE_EXPIRES_AT=:expires",
                                    {"expires": tasks._now() - timedelta(minutes=1)}))
    assert not ledger.run(lambda tx: graph.heartbeat(tx, "ga1", expires))
    assert info(ledger)[2]["status"] == "UNOBSERVED"


@pytest.mark.parametrize("effect", ("NONE", "IDEMPOTENT_EXTERNAL", "NON_IDEMPOTENT"))
def test_native_reaper_uses_retry_policy_and_never_readies_unobserved_v502_attempt(monkeypatch, effect):
    from lib import connection
    events = []

    class Native:
        def query(self, sql, params):
            if "FROM GRAPH_ATTEMPTS" in sql:
                return [{"attempt_id": "native", "run_id": "run", "node_run_id": "node", "fencing_token": 2}]
            return []

        def query_one(self, sql, params):
            if "SIDE_EFFECT_CLASS" in sql:
                return {"side_effect_class": effect, "config_json": '{"retry_policy":{"max_attempts":3}}'}
            return {"attempt_count": 1}

        def execute(self, sql, params):
            events.append((sql, params))
            return 1

    monkeypatch.setattr(connection, "execute_transaction_callback", lambda callback: callback(Native()))
    monkeypatch.setattr(graph, "enabled", lambda: True)
    monkeypatch.setattr(graph, "finish", lambda *_args, **kwargs: {"status": "UNOBSERVED", "allowed": False})
    monkeypatch.setattr(graph_runtime, "_trace_tx", lambda *_args, **kwargs: None)
    assert graph_runtime.reap_expired_leases() == 1
    assert any("UPDATE GRAPH_NODE_RUNS" in sql and params.get("status") == "REVIEW_REQUIRED" for sql, params in events)
    assert not any("UPDATE GRAPH_READY_NODES" in sql and params.get("status") == "READY" for sql, params in events)


def test_native_resume_and_retry_call_processing_gate_in_their_transaction(monkeypatch):
    from lib import connection
    transactions = []
    tx = object()
    monkeypatch.setattr(connection, "execute_transaction_callback", lambda callback: callback(tx))
    monkeypatch.setattr(graph, "enabled", lambda: True)

    def denied(actual, run_id):
        assert actual is tx and run_id == "run"
        transactions.append(actual)
        raise ContinuityConflict("UNKNOWN_SEND", "Explicit reconciliation required")

    monkeypatch.setattr(graph, "control_gate", denied)
    monkeypatch.setattr(graph_runtime, "_plan_for_run", lambda *_args: {})
    with pytest.raises(ContinuityConflict):
        graph_runtime.resume_run("run", "human", "Resume")
    with pytest.raises(ContinuityConflict):
        graph_runtime.retry_node("run", "node", "human", "Retry")
    assert transactions == [tx, tx]


def test_native_reassign_records_unknown_and_does_not_ready_another_attempt(ledger, monkeypatch):
    ledger.native_attempt()
    ledger.db.executescript("""
        ALTER TABLE GRAPH_ATTEMPTS ADD COLUMN ERROR_CODE TEXT;
        ALTER TABLE GRAPH_ATTEMPTS ADD COLUMN ERROR_MESSAGE TEXT;
        ALTER TABLE GRAPH_ATTEMPTS ADD COLUMN COMPLETED_AT TIMESTAMP;
        CREATE TABLE GRAPH_LEASE_TOKENS(ATTEMPT_ID TEXT,FENCING_TOKEN INTEGER,REVOKED_AT TIMESTAMP);
        INSERT INTO GRAPH_LEASE_TOKENS VALUES('ga1',1,NULL);
    """)
    ledger.db.commit()
    monkeypatch.setattr(graph_runtime, "_intervention_tx", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(graph_runtime, "_trace_tx", lambda *_args, **_kwargs: None)
    assert graph_runtime.reassign_attempt("ga1", "human", "Worker disconnected", "other-worker")
    assert info(ledger)[2]["status"] == "UNOBSERVED"
    assert ledger.query_one("SELECT STATUS FROM GRAPH_NODE_RUNS WHERE NODE_RUN_ID='node'", {})["status"] == "REVIEW_REQUIRED"
    assert ledger.query_one("SELECT STATUS FROM GRAPH_READY_NODES WHERE READY_ID='ready'", {})["status"] == "WAITING"
    assert ledger.query_one("SELECT REVOKED_AT FROM GRAPH_LEASE_TOKENS", {})["revoked_at"]
    with pytest.raises(ContinuityConflict, match="Reconcile"):
        ledger.native_attempt("ga2")


@pytest.mark.parametrize("operation", ("skip", "force"))
def test_native_skip_and_route_interventions_cannot_bypass_active_or_unknown_attempts(ledger, operation):
    ledger.native_attempt()
    invoke = (lambda: graph_runtime.skip_node("run", "node", "human", "Skip")) if operation == "skip" else (
        lambda: graph_runtime.force_route("run", "node", "edge", "human", "Route"))
    with pytest.raises(ContinuityConflict, match="active native attempt"):
        invoke()
    failed(ledger, unknown=True)
    with pytest.raises(ContinuityConflict, match="Reconcile"):
        invoke()


def test_fork_run_id_cannot_disguise_the_same_repeated_native_action(ledger):
    ledger.native_attempt()
    ledger.run(lambda tx: tx.execute("INSERT INTO GRAPH_RUNS SELECT 'fork',ACTOR_ID,GRAPH_VERSION_ID,PLAN_ID,DEFINITION_DIGEST,PLAN_DIGEST,INPUT_STATE_JSON,STATUS,ERROR_CODE,ERROR_MESSAGE,COMPLETED_AT,UPDATED_AT FROM GRAPH_RUNS WHERE RUN_ID='run'", {}))
    ledger.run(lambda tx: tx.execute("INSERT INTO GRAPH_NODE_RUNS VALUES('fork-node','fork','tool',0,'RUNNING',NULL,NULL)", {}))
    ledger.run(lambda tx: graph.bind_run(tx, "fork", parent_run_id="run"))
    ledger.native_attempt("fork-attempt", run="fork", node="fork-node")
    signatures = ledger.query(
        "SELECT ACTION_SIGNATURE FROM CX_PROCESSING_ACTIONS WHERE ACTION_KEY IN (:first,:second)",
        {"first": "graph-claim:ga1", "second": "graph-claim:fork-attempt"})
    assert len(signatures) == 2 and signatures[0] == signatures[1]
