"""Transaction-bound processing receipts for the existing Graph scheduler.

Graph attempts and Task attempts have different identities. A Graph attempt
gets its own continuity child and a real fenced Task attempt; all children and
forks retain the Run's original processing budget. This adapter neither sends
requests nor runs a second scheduler.
"""
from __future__ import annotations

import json
from . import processing_recovery as recovery, task_continuity as tasks
from . import continuity_work as work, continuity_execution_links as execution_links
from .agent_extension_contracts import digest, row
from .continuity_state import ContinuityConflict, ContinuityError


def enabled():
    return recovery.schema_enabled()


def _json(value):
    if hasattr(value, "read"):
        value = value.read()
    from .graph_compat import _portable_json_value
    # Native JSON NUMBER values can be Decimal. Receipt digests must use
    # the same finite representation as text JSON and Graph definitions.
    return _portable_json_value(json.loads(value) if isinstance(value, str) else value or {})


def _run(tx, run_id):
    value = row(tx.query_one("SELECT * FROM GRAPH_RUNS WHERE RUN_ID=:run FOR UPDATE", {"run": run_id}))
    if not value:
        raise ContinuityError("GRAPH_PROCESSING_UNAVAILABLE", "The original Graph Run is unavailable")
    return value


def _root(tx, run_id):
    return row(tx.query_one("SELECT * FROM CX_TASK_CONTINUITY_LINKS WHERE LINK_KIND='GRAPH' AND LINK_ID=:run",
                            {"run": run_id}))


def _revision(run, node=None):
    value = {name: run[name] for name in ("graph_version_id", "plan_id", "definition_digest", "plan_digest")}
    if node is not None:
        value.update(node_run_id=node["node_run_id"], node_key=node["node_key"], iteration_no=int(node.get("iteration_no") or 0))
    return digest(value)


def _domain(tx, actor, selected):
    rows = [row(value) for value in tx.query(
        "SELECT m.SECURITY_DOMAIN_ID FROM CX_DOMAIN_MEMBERS m JOIN CX_SECURITY_DOMAINS d "
        "ON d.SECURITY_DOMAIN_ID=m.SECURITY_DOMAIN_ID WHERE m.PRINCIPAL_ID=:actor AND m.STATUS='ACTIVE' "
        "AND d.STATUS='ACTIVE' AND (m.VALID_UNTIL IS NULL OR m.VALID_UNTIL>CURRENT_TIMESTAMP)", {"actor": actor})]
    domains = {value["security_domain_id"] for value in rows}
    if selected:
        if selected not in domains:
            raise PermissionError("The Graph's original Security Domain is unavailable")
        return selected
    if len(domains) != 1:
        raise ContinuityError("GRAPH_PROCESSING_DOMAIN_REQUIRED", "An exact original Graph Security Domain is required")
    return next(iter(domains))


def resolve_domain(actor, selected=None, *, transaction=None):
    """Resolve existing authority before a legacy API creates an execution row.

    No domain or membership is created. The Graph transaction rechecks this
    same authority when it stores the immutable processing binding.
    """
    def perform(tx):
        domain = _domain(tx, actor, selected)
        work._authorize(tx, actor, domain, write=True)
        return domain
    if transaction is not None:
        return perform(transaction)
    from . import connection
    return connection.execute_transaction_callback(perform)


def authorize_target(tx, actor, target, operation):
    """Recheck current original-domain authority and the frozen native tuple."""
    target = recovery.ExactTarget.model_validate(target)
    run = _run(tx, target.target_id)
    root = _root(tx, target.target_id)
    if not root or target.target_kind != "GRAPH":
        raise PermissionError("An original Graph processing binding is required")
    domain = root["security_domain_id"]
    work._authorize(tx, actor, domain, write=operation != "READ")
    work._authorize(tx, run["actor_id"], domain, write=False)
    execution_links.authorize(tx, actor, domain, "GRAPH", target.target_id)
    if root["actor_id"] != run["actor_id"]:
        raise PermissionError("The Graph's original actor changed")
    if target.business_key == "graph-run:" + target.target_id:
        expected_revision, expected_input = _revision(run), digest(_json(run["input_state_json"]))
    else:
        attempt = row(tx.query_one("SELECT * FROM GRAPH_ATTEMPTS WHERE ATTEMPT_ID=:attempt AND RUN_ID=:run",
                                   {"attempt": target.business_key, "run": target.target_id}))
        if not attempt:
            raise PermissionError("The original Graph attempt is unavailable")
        node = row(tx.query_one("SELECT * FROM GRAPH_NODE_RUNS WHERE NODE_RUN_ID=:node AND RUN_ID=:run",
                                {"node": attempt["node_run_id"], "run": target.target_id}))
        if not node:
            raise PermissionError("The original Graph node is unavailable")
        expected_revision, expected_input = _revision(run, node), digest(_json(attempt["input_state_json"]))
    if target.target_revision != expected_revision or target.input_digest != expected_input:
        raise ContinuityConflict("STALE_TARGET", "The original Graph revision or input changed")


def bind_run(tx, run_id, *, domain_id=None, canonical_task_id=None, parent_run_id=None):
    run = _run(tx, run_id)
    prior = _root(tx, run_id)
    if prior:
        return prior
    actor = run["actor_id"]
    parent = _root(tx, parent_run_id) if parent_run_id else None
    if parent_run_id and not parent:
        raise ContinuityError("GRAPH_PROCESSING_PARENT_REQUIRED", "A fork requires its original processing budget")
    if parent:
        control_gate(tx, parent_run_id)
        domain_id = parent["security_domain_id"]
        canonical_task_id = parent["canonical_task_id"]
    domain = _domain(tx, actor, domain_id)
    work._authorize(tx, actor, domain, write=True)
    canonical_task_id = tasks.ensure_task_root(tx, actor, canonical_task_id, goal="Graph Run: " + run_id)
    fingerprint = digest({"run": run_id, "revision": _revision(run), "input": digest(_json(run["input_state_json"]))})
    linked = tasks.link_protocol_task(tx, actor=actor, security_domain_id=domain, link_kind="GRAPH", link_id=run_id,
        canonical_task_id=canonical_task_id, idempotency_key="graph-run:" + run_id, request_digest=fingerprint,
        input_digest=digest(_json(run["input_state_json"])), status="WAITING" if run["status"] == "PAUSED" else "RUNNING",
        reason="Graph processing admission")
    target = recovery.ExactTarget(continuity_id=linked["continuity_id"], target_kind="GRAPH", target_id=run_id,
        target_revision=_revision(run), input_digest=digest(_json(run["input_state_json"])), business_key="graph-run:" + run_id)
    if parent:
        budget = recovery._budget(tx, parent["continuity_id"])
        tx.execute("INSERT INTO CX_PROCESSING_CHAINS(CONTINUITY_ID,BUDGET_ID,ORIGINAL_CONTINUITY_ID) VALUES(:chain,:budget,:original)",
                   {"chain": linked["continuity_id"], "budget": budget["budget_id"], "original": parent["continuity_id"]})
        recovery._store_target(tx, target)
    else:
        recovery.ensure_budget(tx, actor=actor, target=target, policy=recovery.server_policy(), authority=authorize_target)
    return _root(tx, run_id)


def control_gate(tx, run_id, *, recovery_id=None):
    """A native resume/retry/fork cannot reset or bypass the original budget."""
    root = _root(tx, run_id)
    if not root:
        raise ContinuityError("GRAPH_PROCESSING_BINDING_REQUIRED", "The Graph Run requires an original processing binding")
    frozen = row(tx.query_one("SELECT * FROM CX_PROCESSING_TARGETS WHERE CONTINUITY_ID=:chain", {"chain": root["continuity_id"]}))
    if not frozen:
        raise ContinuityError("GRAPH_PROCESSING_BINDING_REQUIRED", "The Graph Run requires its frozen original target")
    authorize_target(tx, root["actor_id"], recovery._target(frozen), "OBSERVE")
    budget = recovery._budget(tx, root["continuity_id"])
    blocks = [row(value) for value in tx.query("SELECT BLOCK_ID FROM CX_PROCESSING_BLOCKS WHERE BUDGET_ID=:budget "
                           "AND CATEGORY IN ('BLOCKED','UNKNOWN') AND STATUS IN ('OPEN','RECOVERY_ACCEPTED')",
                           {"budget": budget["budget_id"]})]
    permitted = row(tx.query_one("SELECT BLOCK_ID FROM CX_PROCESSING_RECOVERIES WHERE RECOVERY_ID=:recovery",
                                 {"recovery": recovery_id})) if recovery_id else {}
    blocked = any(value["block_id"] != permitted.get("block_id") for value in blocks)
    unknown = tx.query_one("SELECT a.ATTEMPT_ID FROM CX_TASK_CONTINUITY_ATTEMPTS a JOIN CX_PROCESSING_CHAINS c "
                           "ON c.CONTINUITY_ID=a.CONTINUITY_ID WHERE c.BUDGET_ID=:budget AND a.STATUS='UNOBSERVED'",
                           {"budget": budget["budget_id"]})
    if unknown:
        raise ContinuityConflict("UNKNOWN_SEND", "Reconcile the original Graph attempt before recovery")
    if blocked:
        raise ContinuityConflict("PROCESSING_BLOCKED", "Explicit bounded processing recovery is required")
    return root, budget


def dispatch_recovery(tx, actor, recovery_id):
    """Explicit Human dispatch of a bounded pure native Graph successor."""
    recovery._human(tx, actor)
    receipt = row(tx.query_one("SELECT * FROM CX_PROCESSING_RECOVERIES WHERE RECOVERY_ID=:recovery FOR UPDATE",
                               {"recovery": recovery_id}))
    if not receipt or receipt["actor_id"] != actor:
        raise PermissionError("Graph recovery access denied")
    block = row(tx.query_one("SELECT * FROM CX_PROCESSING_BLOCKS WHERE BLOCK_ID=:block FOR UPDATE",
                             {"block": receipt["block_id"]}))
    target = recovery._target(block)
    authorize_target(tx, actor, target, "RECOVER")
    recovery._validate_target(tx, target)
    if target.target_kind != "GRAPH":
        raise ContinuityError("GRAPH_RECOVERY_REQUIRED", "A native Graph recovery is required")
    state = row(tx.query_one("SELECT * FROM CX_PROCESSING_RECOVERY_STATES WHERE RECOVERY_ID=:recovery FOR UPDATE",
                             {"recovery": recovery_id}))
    if state["status"] == "DISPATCHED":
        return recovery._recovery_view(tx, receipt, replayed=True)
    if state["status"] != "ACCEPTED" or state.get("admission_id"):
        raise ContinuityConflict("RECOVERY_ALREADY_DISPATCHED", "Graph recovery dispatch is not repeatable")
    original = recovery._link(tx, block["continuity_id"], lock=True)
    if original["status"] not in {"FAILED", "CANCELLED"}:
        raise ContinuityConflict("UNKNOWN_SEND", "The original Graph attempt requires a known terminal outcome")
    run = _run(tx, target.target_id)
    attempt = row(tx.query_one("SELECT * FROM GRAPH_ATTEMPTS WHERE ATTEMPT_ID=:attempt AND RUN_ID=:run FOR UPDATE",
                               {"attempt": target.business_key, "run": target.target_id}))
    node = row(tx.query_one("SELECT nr.*,n.SIDE_EFFECT_CLASS FROM GRAPH_NODE_RUNS nr JOIN GRAPH_RUNS r ON r.RUN_ID=nr.RUN_ID "
                            "JOIN GRAPH_NODES n ON n.GRAPH_VERSION_ID=r.GRAPH_VERSION_ID AND n.NODE_KEY=nr.NODE_KEY "
                            "WHERE nr.NODE_RUN_ID=:node AND nr.RUN_ID=:run FOR UPDATE",
                            {"node": attempt["node_run_id"], "run": target.target_id}))
    if (run["status"] in {"SUCCEEDED", "CANCELLED"} or attempt["status"] == "RUNNING"
            or node.get("side_effect_class") != "NONE" or node["status"] not in {"FAILED", "REVIEW_REQUIRED", "WAITING"}):
        raise ContinuityError("GRAPH_RECOVERY_ADAPTER_REQUIRED", "Only an exact stopped pure Graph node supports native recovery dispatch")
    control_gate(tx, target.target_id, recovery_id=recovery_id)
    tx.execute("UPDATE GRAPH_NODE_RUNS SET STATUS='READY',UPDATED_AT=CURRENT_TIMESTAMP WHERE NODE_RUN_ID=:node",
               {"node": node["node_run_id"]})
    changed = tx.execute("UPDATE GRAPH_READY_NODES SET STATUS='READY',CLAIMED_AT=NULL,AVAILABLE_AT=CURRENT_TIMESTAMP "
                         "WHERE NODE_RUN_ID=:node AND STATUS<>'DONE'", {"node": node["node_run_id"]})
    if not changed:
        raise ContinuityError("GRAPH_RECOVERY_READY_REQUIRED", "The original native Graph Ready row is required")
    tx.execute("UPDATE GRAPH_RUNS SET STATUS='RUNNING',ERROR_CODE=NULL,ERROR_MESSAGE=NULL,COMPLETED_AT=NULL," 
               "UPDATED_AT=CURRENT_TIMESTAMP WHERE RUN_ID=:run", {"run": target.target_id})
    tx.execute("UPDATE CX_PROCESSING_RECOVERY_STATES SET STATUS='DISPATCHED',VERSION=VERSION+1 WHERE RECOVERY_ID=:recovery",
               {"recovery": recovery_id})
    from . import identity_api
    identity_api._audit_tx(tx, actor, "GRAPH_PROCESSING_RECOVERY_DISPATCH", "PROCESSING_RECOVERY", recovery_id, "ALLOW", "Exact pure native Graph Ready admission")
    return recovery._recovery_view(tx, receipt)


def claim_recovery_gate(tx, continuity_id, receipt):
    """Called by Task's claim gate after native Graph dispatch, never by HTTP."""
    complete = row(tx.query_one("SELECT * FROM CX_PROCESSING_RECOVERIES WHERE RECOVERY_ID=:recovery",
                                {"recovery": receipt["recovery_id"]}))
    state = row(tx.query_one("SELECT * FROM CX_PROCESSING_RECOVERY_STATES WHERE RECOVERY_ID=:recovery",
                             {"recovery": receipt["recovery_id"]}))
    block = row(tx.query_one("SELECT * FROM CX_PROCESSING_BLOCKS WHERE BLOCK_ID=:block", {"block": complete["block_id"]}))
    if complete["successor_continuity_id"] != continuity_id or state["status"] != "DISPATCHED" or state.get("admission_id"):
        raise ContinuityConflict("RECOVERY_QUEUED", "The native Graph successor awaits explicit dispatch")
    target = recovery._target(block)
    authorize_target(tx, complete["actor_id"], target, "DISPATCH")
    attempts = tx.query("SELECT ATTEMPT_ID FROM GRAPH_ATTEMPTS WHERE RUN_ID=:run AND IDEMPOTENCY_KEY=:key AND STATUS='RUNNING'",
                        {"run": target.target_id, "key": "processing-recovery:" + complete["recovery_id"]})
    if len(attempts) != 1:
        raise ContinuityConflict("RECOVERY_NATIVE_ATTEMPT_REQUIRED", "An exact native Graph attempt must own the successor claim")
    control_gate(tx, target.target_id, recovery_id=complete["recovery_id"])


def _target_for_attempt(tx, graph_attempt_id):
    attempt = row(tx.query_one("SELECT * FROM GRAPH_ATTEMPTS WHERE ATTEMPT_ID=:attempt FOR UPDATE", {"attempt": graph_attempt_id}))
    if not attempt:
        raise ContinuityError("GRAPH_PROCESSING_UNAVAILABLE", "The original Graph attempt is unavailable")
    recovery_id = str(attempt.get("idempotency_key") or "").removeprefix("processing-recovery:") if str(attempt.get("idempotency_key") or "").startswith("processing-recovery:") else None
    receipt = row(tx.query_one("SELECT * FROM CX_PROCESSING_RECOVERIES WHERE RECOVERY_ID=:recovery", {"recovery": recovery_id})) if recovery_id else {}
    link = recovery._link(tx, receipt["successor_continuity_id"]) if receipt else row(tx.query_one("SELECT * FROM CX_TASK_CONTINUITY_LINKS WHERE LINK_KIND='GRAPH' AND LINK_ID=:attempt",
                            {"attempt": graph_attempt_id}))
    if not link:
        raise ContinuityError("GRAPH_PROCESSING_BINDING_REQUIRED", "The Graph attempt requires its original Task attempt")
    frozen = row(tx.query_one("SELECT * FROM CX_PROCESSING_TARGETS WHERE CONTINUITY_ID=:chain", {"chain": link["continuity_id"]}))
    task_attempt = row(tx.query_one("SELECT * FROM CX_TASK_CONTINUITY_ATTEMPTS WHERE CONTINUITY_ID=:chain AND BUSINESS_KEY=:business ORDER BY ATTEMPT_NO DESC",
                                    {"chain": link["continuity_id"], "business": frozen["business_key"]})) if frozen else {}
    if not task_attempt or not frozen:
        raise ContinuityError("GRAPH_PROCESSING_BINDING_REQUIRED", "The exact original Graph processing tuple is required")
    return attempt, link, task_attempt, recovery._target(frozen).model_copy(update={"attempt_id": task_attempt["attempt_id"]})


def claim(tx, graph_attempt_id, lease_seconds):
    attempt = row(tx.query_one("SELECT * FROM GRAPH_ATTEMPTS WHERE ATTEMPT_ID=:attempt FOR UPDATE", {"attempt": graph_attempt_id}))
    run = _run(tx, attempt["run_id"])
    candidates = [row(value) for value in tx.query("SELECT r.* FROM CX_PROCESSING_RECOVERIES r JOIN CX_PROCESSING_RECOVERY_STATES s ON s.RECOVERY_ID=r.RECOVERY_ID "
        "JOIN CX_PROCESSING_BLOCKS b ON b.BLOCK_ID=r.BLOCK_ID JOIN GRAPH_ATTEMPTS ga ON ga.ATTEMPT_ID=b.BUSINESS_KEY "
        "JOIN CX_TASK_CONTINUITY_LINKS c ON c.CONTINUITY_ID=r.SUCCESSOR_CONTINUITY_ID "
        "WHERE b.TARGET_KIND='GRAPH' AND b.TARGET_ID=:run AND ga.NODE_RUN_ID=:node AND s.STATUS='DISPATCHED' AND c.STATUS='PENDING'",
        {"run": run["run_id"], "node": attempt["node_run_id"]})]
    if len(candidates) > 1:
        raise ContinuityConflict("RECOVERY_IN_PROGRESS", "Only one exact Graph successor may own the native node")
    receipt = candidates[0] if candidates else None
    root, budget = control_gate(tx, run["run_id"], recovery_id=receipt["recovery_id"] if receipt else None)
    node = row(tx.query_one("SELECT * FROM GRAPH_NODE_RUNS WHERE NODE_RUN_ID=:node AND RUN_ID=:run",
                            {"node": attempt["node_run_id"], "run": run["run_id"]}))
    input_digest = digest(_json(attempt["input_state_json"]))
    request_digest = digest({"run": run["run_id"], "node": node["node_run_id"], "graph_attempt": graph_attempt_id,
                             "revision": _revision(run, node), "input": input_digest})
    if receipt:
        linked = recovery._link(tx, receipt["successor_continuity_id"])
        frozen = row(tx.query_one("SELECT * FROM CX_PROCESSING_TARGETS WHERE CONTINUITY_ID=:chain", {"chain": linked["continuity_id"]}))
        target = recovery._target(frozen)
        if target.input_digest != input_digest or target.target_revision != _revision(run, node):
            raise ContinuityConflict("STALE_TARGET", "Recovery cannot replace the original native node input")
        tx.execute("UPDATE GRAPH_ATTEMPTS SET IDEMPOTENCY_KEY=:key WHERE ATTEMPT_ID=:attempt",
                   {"key": "processing-recovery:" + receipt["recovery_id"], "attempt": graph_attempt_id})
        request_digest = linked["request_digest"]
    else:
        linked = tasks.link_protocol_task(tx, actor=root["actor_id"], security_domain_id=root["security_domain_id"],
        link_kind="GRAPH", link_id=graph_attempt_id, canonical_task_id=root["canonical_task_id"],
        idempotency_key="graph-attempt:" + graph_attempt_id, request_digest=request_digest, input_digest=input_digest,
        effect_class="CONSEQUENTIAL", reason="Exact native Graph attempt")
        target = recovery.ExactTarget(continuity_id=linked["continuity_id"], target_kind="GRAPH", target_id=run["run_id"],
            target_revision=_revision(run, node), input_digest=input_digest, business_key=graph_attempt_id)
    if not tx.query_one("SELECT CONTINUITY_ID FROM CX_PROCESSING_CHAINS WHERE CONTINUITY_ID=:chain", {"chain": target.continuity_id}):
        tx.execute("INSERT INTO CX_PROCESSING_CHAINS(CONTINUITY_ID,BUDGET_ID,ORIGINAL_CONTINUITY_ID) VALUES(:chain,:budget,:original)",
                   {"chain": target.continuity_id, "budget": budget["budget_id"], "original": root["continuity_id"]})
        recovery._store_target(tx, target)
    task_attempt = tasks.claim_attempt(tx, continuity_id=target.continuity_id, worker_id=attempt["worker_id"],
        business_key=target.business_key, request_digest=request_digest, lease_seconds=lease_seconds)
    if not task_attempt.get("attempt_id"):
        return {"allowed": False, "reason": "LEASE_EXPIRED"}
    target = target.model_copy(update={"attempt_id": task_attempt["attempt_id"]})
    action = recovery.record_action(tx, actor=root["actor_id"], target=target, action_key="graph-claim:" + graph_attempt_id,
        action_kind="ITERATION", tool_name="graph.node", arguments={"node_key": node["node_key"], "input_digest": input_digest},
        request_count=0, step_count=1, progress_digest=input_digest, authority=authorize_target)
    if action["stop"]:
        tasks.finish_attempt(tx, attempt_id=task_attempt["attempt_id"], worker_id=attempt["worker_id"],
            fencing_token=task_attempt["fencing_token"], status="CANCELLED", request_digest=request_digest,
            error_code=action["stop"]["reason_code"], error_message="Graph processing budget stopped before execution")
        return {"allowed": False, "reason": action["stop"]["reason_code"]}
    return {"allowed": True, "continuity_id": target.continuity_id, "task_attempt_id": task_attempt["attempt_id"]}


def finish(tx, graph_attempt_id, *, outcome, error_code=None, token_count=0, checkpoint_digest=None, retry=False):
    attempt, link, task_attempt, target = _target_for_attempt(tx, graph_attempt_id)
    if task_attempt["status"] != "SENDING":
        return {"status": task_attempt["status"], "allowed": task_attempt["status"] == "SUCCEEDED", "replayed": True}
    if type(token_count) is not int or not 0 <= token_count <= 1000000000:
        raise ContinuityError("PROCESSING_USAGE_INVALID", "Graph token usage must be a bounded integer")
    # Token counts are the authenticated Graph Worker's receipt. They are
    # distinct from provider-observed model usage and never approve content.
    result = None
    if outcome == "SUCCEEDED":
        result = recovery.record_action(tx, actor=link["actor_id"], target=target,
            action_key="graph-result:" + graph_attempt_id, action_kind="ITERATION", tool_name="graph.result",
            arguments={"graph_attempt": graph_attempt_id, "checkpoint": checkpoint_digest},
            request_count=0, step_count=0, token_count=token_count, progress_digest=checkpoint_digest,
            authority=authorize_target)
    finished = tasks.finish_attempt(tx, attempt_id=task_attempt["attempt_id"], worker_id=attempt["worker_id"],
        fencing_token=task_attempt["fencing_token"], status=outcome, request_digest=link["request_digest"],
        error_code=error_code, error_message="Native Graph attempt lifecycle")
    reason = None
    if finished["status"] == "UNOBSERVED":
        reason = "LEASE_EXPIRED" if error_code == "LEASE_EXPIRED" else "POSSIBLE_SEND"
    elif outcome == "FAILED" and not retry:
        reason = "FAILED"
    if reason:
        recovery.observe(tx, actor=link["actor_id"], target=target, reason_code=reason,
                         observation_key="graph-finish:" + graph_attempt_id, authority=authorize_target)
    if str(attempt.get("idempotency_key") or "").startswith("processing-recovery:"):
        recovery_id = attempt["idempotency_key"].split(":", 1)[1]
        status = "UNKNOWN" if finished["status"] == "UNOBSERVED" else "COMPLETED" if outcome == "SUCCEEDED" else "REJECTED"
        tx.execute("UPDATE CX_PROCESSING_RECOVERY_STATES SET STATUS=:status,VERSION=VERSION+1 WHERE RECOVERY_ID=:recovery",
                   {"status": status, "recovery": recovery_id})
        if status == "COMPLETED":
            tx.execute("UPDATE CX_PROCESSING_BLOCKS SET STATUS='RESOLVED',VERSION=VERSION+1 WHERE BLOCK_ID IN "
                       "(SELECT BLOCK_ID FROM CX_PROCESSING_RECOVERIES WHERE RECOVERY_ID=:recovery)", {"recovery": recovery_id})
    return {"status": finished["status"], "allowed": not reason and not (result and result["stop"]), "replayed": False}


def heartbeat(tx, graph_attempt_id, expires):
    """Extend the exact shadow lease inside the native heartbeat transaction."""
    attempt, link, task_attempt, target = _target_for_attempt(tx, graph_attempt_id)
    if attempt["status"] != "RUNNING" or task_attempt["status"] != "SENDING":
        return False
    lease = row(tx.query_one("SELECT * FROM CX_TASK_CONTINUITY_LEASES WHERE CONTINUITY_ID=:chain FOR UPDATE",
                             {"chain": link["continuity_id"]}))
    current = tasks._utc_naive(lease.get("lease_expires_at"))
    if (lease.get("status") != "ACTIVE" or lease.get("lease_owner") != attempt["worker_id"]
            or int(lease.get("fencing_token") or 0) != int(task_attempt["fencing_token"])):
        raise ContinuityConflict("FENCING_MISMATCH", "The Graph's original Task lease changed")
    if current is None or current <= tasks._now():
        finish(tx, graph_attempt_id, outcome="UNOBSERVED", error_code="LEASE_EXPIRED")
        return False
    tx.execute("UPDATE CX_TASK_CONTINUITY_ATTEMPTS SET LEASE_EXPIRES_AT=:expires WHERE ATTEMPT_ID=:attempt AND STATUS='SENDING'",
               {"expires": expires, "attempt": task_attempt["attempt_id"]})
    tx.execute("UPDATE CX_TASK_CONTINUITY_LEASES SET LEASE_EXPIRES_AT=:expires,UPDATED_AT=CURRENT_TIMESTAMP WHERE CONTINUITY_ID=:chain AND FENCING_TOKEN=:token",
               {"expires": expires, "chain": link["continuity_id"], "token": task_attempt["fencing_token"]})
    return True


def read_evidence(tx, target):
    """Read the exact native terminal commit; failure labels do not prove stop."""
    target = recovery.ExactTarget.model_validate(target)
    authorize_target(tx, recovery._link(tx, target.continuity_id)["actor_id"], target, "READ")
    # For a recovery, the immutable target still identifies the original
    # business input; only the native attempt bound to this receipt may settle
    # a successor's unknown result.
    receipt = row(tx.query_one("SELECT RECOVERY_ID FROM CX_PROCESSING_RECOVERIES WHERE SUCCESSOR_CONTINUITY_ID=:chain",
                               {"chain": target.continuity_id}))
    if receipt:
        attempts = [row(value) for value in tx.query("SELECT * FROM GRAPH_ATTEMPTS WHERE RUN_ID=:run AND IDEMPOTENCY_KEY=:key",
            {"run": target.target_id, "key": "processing-recovery:" + receipt["recovery_id"]})]
        if len(attempts) != 1:
            raise ContinuityError("RECONCILIATION_EVIDENCE_REQUIRED", "One exact native Graph recovery attempt is required")
        attempt = attempts[0]
    else:
        attempt = row(tx.query_one("SELECT * FROM GRAPH_ATTEMPTS WHERE ATTEMPT_ID=:attempt AND RUN_ID=:run",
                                  {"attempt": target.business_key, "run": target.target_id}))
    if not attempt:
        raise ContinuityError("RECONCILIATION_EVIDENCE_REQUIRED", "The exact native Graph attempt is required")
    checkpoint = row(tx.query_one("SELECT c.CHECKPOINT_ID,c.STATE_HASH FROM GRAPH_STATE_EVENTS e JOIN GRAPH_CHECKPOINTS c "
        "ON c.CHECKPOINT_ID=e.CHECKPOINT_ID AND c.RUN_ID=e.RUN_ID WHERE e.SOURCE_ATTEMPT_ID=:attempt AND e.RUN_ID=:run",
        {"attempt": attempt["attempt_id"], "run": target.target_id}))
    outcome = "SUCCEEDED" if attempt["status"] == "SUCCEEDED" and checkpoint and attempt.get("completion_digest") else "UNOBSERVED"
    return recovery.ReconciliationEvidence("LOCAL_LIFECYCLE", digest({"graph_attempt": attempt["attempt_id"],
        "status": attempt["status"], "completion": attempt.get("completion_digest"), "checkpoint": checkpoint}), outcome)


def sync_run(tx, run_id):
    run, root = _run(tx, run_id), _root(tx, run_id)
    status = {"SUCCEEDED": "SUCCEEDED", "FAILED": "FAILED", "CANCELLED": "CANCELLED", "REVIEW_REQUIRED": "WAITING", "PAUSED": "WAITING"}.get(run["status"], "RUNNING")
    if root and root["status"] not in {"SUCCEEDED", "FAILED", "CANCELLED", "UNOBSERVED"}:
        tasks._transition(tx, root["continuity_id"], root["actor_id"], status, "Native Graph Run projection", root["request_digest"])
