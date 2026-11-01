"""Same-transaction DB4A2A branch accounting over the original dispatch.

A branch is a local database effect. Its original native reader, reference
policy and participant checks still decide authority. No model slot or remote
cancellation is invented for a local branch transaction.
"""
from . import processing_recovery as recovery, task_continuity as tasks
from .agent_extension_contracts import digest, row
from .continuity_state import ContinuityConflict, ContinuityError


FIELDS = ("dispatch_id", "task_id", "sender_principal_id", "receiver_agent_id", "context_ref", "snapshot_digest",
          "expected_version", "scope_ref", "source_branch", "branch_policy", "transport")


def _dispatch(tx, dispatch_id):
    item = row(tx.query_one("SELECT * FROM CX_DB4A2A_DISPATCHES WHERE DISPATCH_ID=:dispatch FOR UPDATE", {"dispatch": dispatch_id}))
    if not item:
        raise PermissionError("The original DB4A2A dispatch is unavailable")
    return item


def _revision(item):
    values = {key: item.get(key) for key in FIELDS}
    values["source_branch"] = values["source_branch"] or ""
    values["expected_version"] = int(values["expected_version"])
    return digest(values)


def authorize_target(tx, actor, target, operation):
    from . import db4a2a, continuity_native_sources
    item = _dispatch(tx, target.target_id)
    root = row(tx.query_one("SELECT * FROM CX_TASK_CONTINUITY_LINKS WHERE LINK_KIND='DB4A2A' AND LINK_ID=:dispatch",
                            {"dispatch": target.target_id}))
    if not root:
        raise ContinuityError("RECOVERY_AUTHORITY_ADAPTER_REQUIRED", "The original DB4A2A admission is required")
    frozen = row(tx.query_one("SELECT TARGET_REVISION FROM CX_PROCESSING_TARGETS WHERE CONTINUITY_ID=:chain", {"chain": root["continuity_id"]}))
    if frozen and frozen["target_revision"] != _revision(item):
        raise ContinuityConflict("STALE_TARGET", "The original DB4A2A dispatch facts changed")
    continuity_native_sources._authorize(tx, actor, root["security_domain_id"], "DB4A2A", target.target_id)
    current = tasks._row(tx.query_one("SELECT * FROM CX_TASK_CONTINUITY_LINKS WHERE CONTINUITY_ID=:chain", {"chain": target.continuity_id}))
    if target.business_key == target.target_id:
        if target.target_revision != _revision(item) or target.input_digest != root["input_digest"]:
            raise ContinuityConflict("STALE_TARGET", "The original DB4A2A reference changed")
    elif (target.business_key != target.target_id + ":branch" or not current
          or current["request_digest"] != target.target_revision or current["input_digest"] != target.input_digest):
        raise ContinuityConflict("STALE_TARGET", "The exact original DB4A2A branch input changed")
    if item["transport"] == "DB_MEDIATED":
        for participant in sorted({item["sender_principal_id"], item["receiver_agent_id"]}):
            db4a2a._lock_reader_policy(tx, participant, item["context_ref"])
        context = db4a2a._check_context(tx, item)
        db4a2a._check_context_reader(item["receiver_agent_id"], item["context_ref"])
        db4a2a._check_context_sender(tx, item["sender_principal_id"], context)


def bind_dispatch(tx, actor, continuity_id, dispatch_id):
    item = _dispatch(tx, dispatch_id)
    link = tasks._row(tx.query_one("SELECT * FROM CX_TASK_CONTINUITY_LINKS WHERE CONTINUITY_ID=:chain", {"chain": continuity_id}))
    target = recovery.ExactTarget(continuity_id=continuity_id, target_kind="PROTOCOL", target_id=dispatch_id,
        target_revision=_revision(item), input_digest=link["input_digest"], business_key=dispatch_id)
    return recovery.bind_server_policy(tx, actor=actor, target=target)


def begin_branch(tx, actor, dispatch_id, branch_name, purpose):
    root = tasks._row(tx.query_one("SELECT * FROM CX_TASK_CONTINUITY_LINKS WHERE LINK_KIND='DB4A2A' AND LINK_ID=:dispatch",
                                  {"dispatch": dispatch_id}))
    if not root:
        raise ContinuityError("PROCESSING_POLICY_REQUIRED", "The original DB4A2A admission is required")
    item = _dispatch(tx, dispatch_id)
    frozen = row(tx.query_one("SELECT * FROM CX_PROCESSING_TARGETS WHERE CONTINUITY_ID=:chain", {"chain": root["continuity_id"]}))
    if not frozen:
        raise ContinuityError("PROCESSING_TARGET_REQUIRED", "The original DB4A2A target is required")
    recovery._authorize(tx, actor, recovery._target(frozen), "OBSERVE", None)
    budget = recovery._budget(tx, root["continuity_id"])
    if tx.query_one("SELECT BLOCK_ID FROM CX_PROCESSING_BLOCKS WHERE BUDGET_ID=:budget AND CATEGORY IN ('BLOCKED','UNKNOWN') AND STATUS IN ('OPEN','RECOVERY_ACCEPTED')",
                    {"budget": budget["budget_id"]}):
        raise ContinuityConflict("PROCESSING_BLOCKED", "The original DB4A2A budget requires exact recovery")
    fingerprint = digest({"dispatch_revision": _revision(item), "branch_name": branch_name, "purpose": purpose})
    child = tasks.link_protocol_task(tx, actor=root["actor_id"], security_domain_id=root["security_domain_id"],
        link_kind="DB4A2A", link_id="db4branch:" + digest(dispatch_id), canonical_task_id=root["canonical_task_id"],
        idempotency_key="db4branch:" + digest(dispatch_id), request_digest=fingerprint, input_digest=fingerprint,
        effect_class="REVERSIBLE", reason="Exact atomic DB4A2A branch")
    if not child.get("replayed"):
        tx.execute("INSERT INTO CX_PROCESSING_CHAINS(CONTINUITY_ID,BUDGET_ID,ORIGINAL_CONTINUITY_ID) VALUES(:chain,:budget,:original)",
                   {"chain": child["continuity_id"], "budget": budget["budget_id"], "original": root["continuity_id"]})
        recovery._store_target(tx, recovery.ExactTarget(continuity_id=child["continuity_id"], target_kind="PROTOCOL",
            target_id=dispatch_id, target_revision=fingerprint, input_digest=fingerprint, business_key=dispatch_id + ":branch"))
    attempt = tasks.claim_attempt(tx, continuity_id=child["continuity_id"], worker_id="db4branch:" + digest(dispatch_id),
        business_key=dispatch_id + ":branch", request_digest=fingerprint)
    if attempt.get("reconciliation_required"):
        raise ContinuityConflict("UNKNOWN_SEND", "The original DB4A2A branch requires reconciliation")
    return {"attempt": attempt, "request_digest": fingerprint, "worker_id": "db4branch:" + digest(dispatch_id)}


def finish_branch(tx, execution):
    attempt = execution["attempt"]
    return tasks.finish_attempt(tx, attempt_id=attempt["attempt_id"], worker_id=execution["worker_id"],
        fencing_token=attempt["fencing_token"], status="SUCCEEDED", request_digest=execution["request_digest"])
