"""Actual Task hooks and diagnostic transactions; no native/model calls."""
from datetime import datetime, timedelta

import pytest

from lib import agent_diagnostics, connection, identity_api, model_observations, model_coordinator_observations, native_runtime
from lib import processing_recovery as recovery, task_continuity
from lib.continuity_state import ContinuityConflict, ContinuityError
from .test_v502_processing_recovery import ledger


def automatic_attempt(ledger, source="EXE_automatic", kind="RUNTIME"):
    from lib import model_coordinator_schema
    for sql in model_coordinator_schema.schema_statements('pg'):
        ledger.db.execute(sql)
    ledger.db.execute("CREATE TABLE IF NOT EXISTS CX_MODEL_RUNTIME_OBSERVATIONS(ADMISSION_ID TEXT PRIMARY KEY,TOTAL_TOKENS INTEGER)")
    link = ledger.run(lambda tx: task_continuity.link_protocol_task(tx, actor="human", security_domain_id="domain",
        link_kind=kind, link_id=source, canonical_task_id="plan", idempotency_key=source,
        request_digest="e" * 64, input_digest="f" * 64))
    attempt = ledger.run(lambda tx: task_continuity.claim_attempt(tx, continuity_id=link["continuity_id"],
        worker_id="automatic-worker", business_key="automatic-business", request_digest="e" * 64))
    return link, attempt


def complete(ledger, attempt, status="SUCCEEDED", **values):
    return ledger.run(lambda tx: task_continuity.finish_attempt(tx, attempt_id=attempt["attempt_id"],
        worker_id="automatic-worker", fencing_token=attempt["fencing_token"], status=status,
        request_digest="e" * 64, **values))


def observation(ledger, name, source, attempt, tokens, actor="human"):
    ledger.run(lambda tx: tx.execute("INSERT INTO CX_MODEL_ADMISSIONS VALUES(:admission,'COMPLETED',:actor,:source,:attempt,:fingerprint,1)",
        {"admission": name, "actor": actor, "source": source, "attempt": attempt, "fingerprint": "f" * 64}))
    ledger.run(lambda tx: tx.execute("INSERT INTO CX_MODEL_RUNTIME_OBSERVATIONS VALUES(:admission,:tokens)",
        {"admission": name, "tokens": tokens}))


@pytest.mark.parametrize("source,kind", [("EXE_automatic", "RUNTIME"), ("RJ_automatic", "RUNTIME"),
    ("MTU_automatic:FINAL", "RUNTIME"), ("AQR_automatic", "DIAGNOSTIC")])
def test_native_task_admission_freezes_server_policy_and_exact_usage_once(ledger, source, kind):
    link, attempt = automatic_attempt(ledger, source, kind)
    chain = link["continuity_id"]
    budget = ledger.run(lambda tx: recovery._budget(tx, chain, lock=False))
    assert {key: budget[key] for key in ("max_requests", "max_steps", "max_tokens", "max_repeats", "max_no_progress")} == recovery.server_policy().model_dump()
    frozen = ledger.query_one("SELECT * FROM CX_PROCESSING_TARGETS WHERE CONTINUITY_ID=:chain", {"chain": chain})
    assert frozen["target_id"] == source and frozen["input_digest"] == "f" * 64
    replay = ledger.run(lambda tx: task_continuity.claim_attempt(tx, continuity_id=chain, worker_id="automatic-worker",
        business_key="automatic-business", request_digest="e" * 64))
    assert replay["attempt_id"] == attempt["attempt_id"] and replay["replayed"]
    usage_source = source.rsplit(":", 1)[0] if source.startswith("MTU_") else source
    observation(ledger, "actual", usage_source, attempt["attempt_id"], 23)
    observation(ledger, "wrong-actor", usage_source, attempt["attempt_id"], 999, actor="other")
    observation(ledger, "wrong-source", "other", attempt["attempt_id"], 999)
    observation(ledger, "wrong-attempt", usage_source, "other", 999)
    assert complete(ledger, attempt)["status"] == "SUCCEEDED"
    ledger.restart()
    result = ledger.run(lambda tx: recovery.read_diagnostics(tx, actor="human", continuity_id=chain))
    assert result["consumed"] == {"requests": 1, "steps": 1, "tokens": 23}
    assert result["content_approved"] is False and result["no_progress_count"] == 0
    assert ledger.query_one("SELECT COUNT(*) AS N FROM CX_PROCESSING_ACTIONS WHERE CONTINUITY_ID=:chain", {"chain": chain})["n"] == 1
    with pytest.raises(ContinuityConflict, match="already been completed"):
        complete(ledger, attempt)


def test_local_sync_consumes_a_step_without_inventing_a_model_request(ledger):
    link, attempt = automatic_attempt(ledger, "SJ_automatic")
    complete(ledger, attempt)
    result = ledger.run(lambda tx: recovery.read_diagnostics(tx, actor="human", continuity_id=link["continuity_id"]))
    assert result["consumed"] == {"requests": 0, "steps": 1, "tokens": 0}
    assert result["token_accounting"]["missing_usage"] == "UNOBSERVED"


def test_task_failure_keeps_typed_cause_and_missing_usage_unobserved(ledger):
    link, attempt = automatic_attempt(ledger)
    observation(ledger, "missing", "EXE_automatic", attempt["attempt_id"], None)
    complete(ledger, attempt, "FAILED", error_code="MODEL_READ_TIMEOUT")
    result = ledger.run(lambda tx: recovery.read_diagnostics(tx, actor="human", continuity_id=link["continuity_id"]))
    assert result["consumed"] == {"requests": 1, "steps": 1, "tokens": 0}
    assert [(item["reason_code"], item["category"]) for item in result["observations"]] == [("REQUEST_TIMEOUT", "BLOCKED")]
    assert result["token_accounting"]["missing_usage"] == "UNOBSERVED"


def test_expired_task_persists_unknown_and_accounting_without_reclaiming(ledger):
    link, attempt = automatic_attempt(ledger)
    expired = datetime.now() - timedelta(days=1)
    for table in ("CX_TASK_CONTINUITY_ATTEMPTS", "CX_TASK_CONTINUITY_LEASES"):
        ledger.run(lambda tx: tx.execute("UPDATE " + table + " SET LEASE_EXPIRES_AT=:expiry WHERE CONTINUITY_ID=:chain",
            {"expiry": expired, "chain": link["continuity_id"]}))
    result = ledger.run(lambda tx: task_continuity.claim_attempt(tx, continuity_id=link["continuity_id"],
        worker_id="next-worker", business_key="automatic-business", request_digest="e" * 64))
    assert result["status"] == "UNOBSERVED" and result["reconciliation_required"]
    ledger.restart()
    detail = ledger.run(lambda tx: recovery.read_diagnostics(tx, actor="human", continuity_id=link["continuity_id"]))
    assert detail["consumed"] == {"requests": 1, "steps": 1, "tokens": 0}
    assert [(item["reason_code"], item["category"]) for item in detail["observations"]] == [("LEASE_EXPIRED", "UNKNOWN")]
    with pytest.raises(ContinuityConflict, match="Reconcile"):
        ledger.run(lambda tx: task_continuity.claim_attempt(tx, continuity_id=link["continuity_id"],
            worker_id="next-worker", business_key="automatic-business", request_digest="e" * 64))
    assert ledger.query_one("SELECT COUNT(*) AS N FROM CX_TASK_CONTINUITY_ATTEMPTS WHERE CONTINUITY_ID=:chain",
        {"chain": link["continuity_id"]})["n"] == 1


def test_required_diagnosis_audit_rolls_back_actual_task_finish_and_budget(ledger, monkeypatch):
    link, attempt = automatic_attempt(ledger)
    def fail_audit(*args):
        raise RuntimeError("audit unavailable")
    monkeypatch.setattr(identity_api, "_audit_tx", fail_audit)
    with pytest.raises(RuntimeError, match="audit unavailable"):
        complete(ledger, attempt, "FAILED", error_code="PROVIDER_UNAVAILABLE")
    assert ledger.query_one("SELECT STATUS FROM CX_TASK_CONTINUITY_ATTEMPTS WHERE ATTEMPT_ID=:attempt",
        {"attempt": attempt["attempt_id"]})["status"] == "SENDING"
    assert ledger.run(lambda tx: recovery._budget(tx, link["continuity_id"], lock=False))["requests_used"] == 0
    assert not ledger.query("SELECT ACTION_ID FROM CX_PROCESSING_ACTIONS WHERE CONTINUITY_ID=:chain", {"chain": link["continuity_id"]})


def test_model_turn_stage_resolution_cannot_leave_whole_turn_capacity_unknown(ledger):
    link, attempt = automatic_attempt(ledger, "MTU_automatic:FINAL")
    observation(ledger, "turn-capacity", "MTU_automatic", attempt["attempt_id"], None)
    ledger.run(lambda tx: tx.execute("UPDATE CX_MODEL_ADMISSIONS SET STATUS='UNKNOWN' WHERE ADMISSION_ID=:admission", {"admission": "turn-capacity"}))
    complete(ledger, attempt, "UNOBSERVED")
    block = ledger.query_one("SELECT BLOCK_ID FROM CX_PROCESSING_BLOCKS WHERE CONTINUITY_ID=:chain", {"chain": link["continuity_id"]})
    evidence = recovery.ReconciliationEvidence("OPERATOR_RESOLUTION", "d" * 64, "FAILED")
    with pytest.raises(ContinuityError, match="capacity lifecycle must reconcile atomically"):
        recovery.reconcile("human", block["block_id"], read_evidence=lambda *_: evidence)
    assert ledger.query_one("SELECT STATUS FROM CX_TASK_CONTINUITY_ATTEMPTS WHERE ATTEMPT_ID=:attempt", {"attempt": attempt["attempt_id"]})["status"] == "UNOBSERVED"
    def capacity(tx, admissions, original):
        assert [item["admission_id"] for item in admissions] == ["turn-capacity"] and original == evidence
        tx.execute("UPDATE CX_MODEL_ADMISSIONS SET STATUS='FAILED' WHERE ADMISSION_ID=:admission", {"admission": "turn-capacity"})
    assert recovery.reconcile("human", block["block_id"], read_evidence=lambda *_: evidence,
        reconcile_capacity=capacity)["status"] == "FAILED"


def test_execution_progress_uses_same_transaction_and_original_source_authority(monkeypatch):
    calls = []
    class Transaction:
        def query_one(self, sql, params):
            calls.append(("observation", params))
            return {"FINISH_CODE": "COMPLETED"}
        def query(self, sql, params):
            return [{"CONTINUITY_ID": "chain"}]
    transaction = Transaction()
    def execution(actor, source, **kwargs):
        assert kwargs["transaction"] is transaction and actor == "human" and source == "EXE_current"
        calls.append(("authorization", source))
        return {"status": "SUCCEEDED", "output": "private result", "input_json": "private prompt"}
    def observations(actor, kind, source, **kwargs):
        assert kwargs["transaction"] is transaction
        kwargs["authorize_source"](transaction, actor, source)
        calls.append(("model", kind))
        return [{"source_kind": kind, "total_tokens": None}]
    monkeypatch.setattr(native_runtime, "get_execution", execution)
    monkeypatch.setattr(recovery, "schema_enabled", lambda: True)
    monkeypatch.setattr(recovery, "read_diagnostics", lambda tx, **kwargs: {"generation_requested": False})
    monkeypatch.setattr(model_observations, "read_for_source", observations)
    monkeypatch.setattr(model_coordinator_observations, "read_for_source", observations)
    monkeypatch.setattr(connection, "execute_query_one", lambda *args: pytest.fail("global query escaped transaction"))
    monkeypatch.setattr(connection, "execute_transaction_callback", lambda *args: pytest.fail("nested transaction"))
    result = agent_diagnostics.progress("human", "EXE_current", transaction=transaction)
    assert result["execution"] == {"status": "SUCCEEDED"}
    assert len(result["model_observations"]) == 4
    assert [item for item in calls if item[0] == "authorization"] == [("authorization", "EXE_current")] * 5
    assert result["remote_cancellation_confirmed"] is False
