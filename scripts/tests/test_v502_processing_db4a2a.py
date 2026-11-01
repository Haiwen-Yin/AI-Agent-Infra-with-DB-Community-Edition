"""Atomic local branch effects retain native DB4A2A policy and shared budgets."""
import pytest

from lib import processing_recovery as recovery, processing_db4a2a as adapter, db4a2a, task_continuity as tasks
from lib.continuity_state import ContinuityConflict
from .test_v502_processing_recovery import ledger, DEFAULT_AUTHORITY


@pytest.fixture
def dispatch(ledger, monkeypatch):
    from lib import branch_api, continuity_work, continuity_native_sources, identity_api
    ledger.db.executescript("""
        CREATE TABLE CX_DB4A2A_DISPATCHES(DISPATCH_ID TEXT PRIMARY KEY,TASK_ID TEXT,SENDER_PRINCIPAL_ID TEXT,
          RECEIVER_AGENT_ID TEXT,CONTEXT_REF TEXT,SNAPSHOT_DIGEST TEXT,EXPECTED_VERSION INTEGER,SCOPE_REF TEXT,
          SOURCE_BRANCH TEXT,BRANCH_POLICY TEXT,TRANSPORT TEXT,STATUS TEXT,CHILD_BRANCH_ID TEXT,
          CREATED_AT TIMESTAMP DEFAULT CURRENT_TIMESTAMP,UPDATED_AT TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
        INSERT INTO CX_DB4A2A_DISPATCHES VALUES('dispatch','business-task','human','agent','context','snapshot',1,
          'scope',NULL,'CHILD_BRANCH_WRITE','DB_MEDIATED','DISPATCHED',NULL,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP);
        CREATE TABLE BRANCH_EFFECTS(BRANCH_ID TEXT PRIMARY KEY);
    """)
    ledger.db.commit()
    calls = []
    monkeypatch.setattr(continuity_work, "_authorize", lambda *_a, **_kw: None)
    monkeypatch.setattr(continuity_native_sources, "_authorize", lambda tx, actor, domain, family, entity: calls.append(("native", actor, domain, family, entity)))
    monkeypatch.setattr(identity_api, "effective_access", lambda *_a, **_kw: {"decision": "ALLOW"})
    monkeypatch.setattr(db4a2a, "_lock_reader_policy", lambda tx, actor, context: calls.append(("policy", actor, context)))
    monkeypatch.setattr(db4a2a, "_check_context", lambda tx, item: {"workspace_id": "workspace", "agent_id": "agent", "branch_id": None})
    def reader(actor, context):
        assert actor == "agent" and context == "context"
        calls.append(("reader", actor, context))
        if not ledger.grants["source"]:
            raise PermissionError("Original native reference reader denied")
    monkeypatch.setattr(db4a2a, "_check_context_reader", reader)
    monkeypatch.setattr(db4a2a, "_check_context_sender", lambda tx, actor, context: calls.append(("sender", actor)))
    def fork(tx, **kwargs):
        assert kwargs["fork_context_id"] == "context" and kwargs["agent_id"] == "agent"
        tx.execute("INSERT INTO BRANCH_EFFECTS(BRANCH_ID) VALUES(:branch)", {"branch": "branch"})
        return "branch"
    monkeypatch.setattr(branch_api, "fork_branch_tx", fork)
    monkeypatch.setattr(recovery, "_default_authority", DEFAULT_AUTHORITY)
    link = ledger.run(lambda tx: tasks.link_protocol_task(tx, actor="human", security_domain_id="domain", link_kind="DB4A2A",
        link_id="dispatch", canonical_task_id="plan", idempotency_key="dispatch", request_digest="d" * 64,
        input_digest="e" * 64, effect_class="REVERSIBLE"))
    policy = ledger.run(lambda tx: adapter.bind_dispatch(tx, "human", link["continuity_id"], "dispatch"))
    ledger.dispatch_link = link
    ledger.dispatch_budget = policy["budget_id"]
    ledger.native_calls = calls
    return ledger


def test_branch_original_effect_task_attempt_and_accounting_commit_together(dispatch):
    result = db4a2a.create_dispatch_branch("human", "dispatch", "child", "bounded original branch")
    assert result["branch_id"] == "branch"
    assert dispatch.count("BRANCH_EFFECTS") == 1
    chains = dispatch.query("SELECT CONTINUITY_ID FROM CX_PROCESSING_CHAINS WHERE BUDGET_ID=:budget", {"budget": dispatch.dispatch_budget})
    assert len(chains) == 2
    actions = dispatch.query("SELECT * FROM CX_PROCESSING_ACTIONS WHERE BUDGET_ID=:budget", {"budget": dispatch.dispatch_budget})
    assert len(actions) == 1 and actions[0]["step_count"] == 1 and actions[0]["request_count"] == 0
    assert dispatch.query_one("SELECT STATUS FROM CX_TASK_CONTINUITY_ATTEMPTS WHERE ATTEMPT_ID=:attempt", {"attempt": actions[0]["attempt_id"]})["status"] == "SUCCEEDED"
    assert ("reader", "agent", "context") in dispatch.native_calls
    dispatch.restart()
    replay = db4a2a.create_dispatch_branch("human", "dispatch", "different label", "replay")
    assert replay["idempotent"] and dispatch.count("BRANCH_EFFECTS") == 1
    assert len(dispatch.query("SELECT ACTION_ID FROM CX_PROCESSING_ACTIONS WHERE BUDGET_ID=:budget", {"budget": dispatch.dispatch_budget})) == 1


def test_native_reader_revocation_cannot_be_repaired_by_owner_database_session(dispatch):
    dispatch.grants["source"] = False
    with pytest.raises(PermissionError, match="native reference reader"):
        db4a2a.create_dispatch_branch("human", "dispatch", "child", "bounded")
    assert dispatch.count("BRANCH_EFFECTS") == 0
    assert not dispatch.query("SELECT ACTION_ID FROM CX_PROCESSING_ACTIONS WHERE BUDGET_ID=:budget", {"budget": dispatch.dispatch_budget})


def test_changed_dispatch_facts_and_durable_blocks_deny_new_branch(dispatch):
    dispatch.run(lambda tx: tx.execute("UPDATE CX_DB4A2A_DISPATCHES SET EXPECTED_VERSION=2 WHERE DISPATCH_ID='dispatch'", {}))
    with pytest.raises(ContinuityConflict, match="dispatch facts changed"):
        db4a2a.create_dispatch_branch("human", "dispatch", "child", "bounded")
    assert dispatch.count("BRANCH_EFFECTS") == 0


def test_original_budget_block_cannot_be_bypassed_by_new_branch_input(dispatch):
    frozen = dispatch.query_one("SELECT * FROM CX_PROCESSING_TARGETS WHERE CONTINUITY_ID=:chain",
        {"chain": dispatch.dispatch_link["continuity_id"]})
    dispatch.run(lambda tx: recovery.observe(tx, actor="human", target=recovery._target(frozen),
        reason_code="BUDGET_STEPS", observation_key="stopped-root"))
    with pytest.raises(ContinuityConflict, match="budget requires exact recovery"):
        db4a2a.create_dispatch_branch("human", "dispatch", "brand-new-child", "different branch purpose")
    assert dispatch.count("BRANCH_EFFECTS") == 0
    assert len(dispatch.query("SELECT CONTINUITY_ID FROM CX_PROCESSING_CHAINS WHERE BUDGET_ID=:budget",
        {"budget": dispatch.dispatch_budget})) == 1


def test_required_finish_audit_failure_rolls_back_branch_and_shadow_attempt(dispatch, monkeypatch):
    from lib import identity_api
    prior = identity_api._audit_tx
    def audit(tx, actor, action, *args):
        if action == "PROCESSING_OBSERVATION":
            raise RuntimeError("audit unavailable")
        if action == "DB4A2A_BRANCH":
            raise RuntimeError("audit unavailable")
        return prior(tx, actor, action, *args)
    monkeypatch.setattr(identity_api, "_audit_tx", audit)
    with pytest.raises(RuntimeError, match="audit unavailable"):
        db4a2a.create_dispatch_branch("human", "dispatch", "child", "bounded")
    assert dispatch.count("BRANCH_EFFECTS") == 0
    assert len(dispatch.query("SELECT CONTINUITY_ID FROM CX_PROCESSING_CHAINS WHERE BUDGET_ID=:budget", {"budget": dispatch.dispatch_budget})) == 1
