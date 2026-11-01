"""Typed processing facts and exact recovery over existing Task continuity.

This module never sends, probes, evaluates model output or schedules work.
Trusted execution adapters supply actual durable attempt/action identities and
their existing current-authority checks.  Recovery creates an explicit successor
in the existing ledger and inherits its original immutable budget root.  Native
Worker integration and capacity transport remain their owners' responsibility.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Annotated, Literal

from pydantic import Field, StringConstraints, TypeAdapter, model_validator

from . import connection, identity_api, task_continuity, continuity_work as work
from .agent_extension_contracts import digest, identifier, row, safe_key
from .continuity_contracts import Contract
from .continuity_state import ContinuityConflict, ContinuityError

Key = Annotated[str, StringConstraints(strict=True, min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$")]
Fingerprint = Annotated[str, StringConstraints(strict=True, pattern=r"^[0-9a-f]{64}$")]
Positive = Annotated[int, Field(strict=True, ge=1, le=1000000)]

REASONS = {
    "UNMATCHED": "BLOCKED", "REQUEST_TIMEOUT": "BLOCKED", "PROVIDER_UNAVAILABLE": "BLOCKED",
    "ENDPOINT_QUEUED": "BLOCKED", "BUDGET_REQUESTS": "BLOCKED", "BUDGET_STEPS": "BLOCKED",
    "BUDGET_TOKENS": "BLOCKED", "REPEATED_ACTION": "BLOCKED", "NO_PROGRESS": "BLOCKED",
    "SOURCE_REVOKED": "BLOCKED", "WAITING_HUMAN": "BLOCKED", "FAILED": "BLOCKED",
    "CAPABILITY_UNAVAILABLE": "BLOCKED", "POLICY_BLOCKED": "BLOCKED",
    "EMBEDDING_TIMEOUT": "DEGRADED", "SEMANTIC_UNAVAILABLE": "DEGRADED", "TEXTUAL_FALLBACK": "DEGRADED",
    "POSSIBLE_SEND": "UNKNOWN", "LEASE_EXPIRED": "UNKNOWN", "EXTERNAL_OUTCOME_UNKNOWN": "UNKNOWN",
    "CLIENT_CLOSED": "UNKNOWN",
}


class BudgetPolicy(Contract):
    max_requests: Positive
    max_steps: Positive
    max_tokens: Annotated[int, Field(strict=True, ge=1, le=1000000000)]
    max_repeats: Annotated[int, Field(strict=True, ge=1, le=1000)]
    max_no_progress: Annotated[int, Field(strict=True, ge=1, le=1000)]


class ExactTarget(Contract):
    continuity_id: Key
    attempt_id: Key | None = None
    target_kind: Literal["RUNTIME", "GRAPH", "LOOP", "TASK_STEP", "PROTOCOL"]
    target_id: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=256)]
    target_revision: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=128)]
    input_digest: Fingerprint
    business_key: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=256)]
    source_family: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=24)] | None = None
    source_id: Key | None = None
    source_revision_id: Key | None = None
    source_digest: Fingerprint | None = None

    @model_validator(mode="after")
    def complete_source(self):
        values = (self.source_family, self.source_id, self.source_revision_id, self.source_digest)
        if any(value is not None for value in values) and not all(value is not None for value in values):
            raise ValueError("An exact source requires family, identity, revision and digest")
        return self


class RetryDecision(Contract):
    block_id: Key
    expected_version: Positive
    target: ExactTarget
    reason_code: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=64)]
    add_requests: Annotated[int, Field(strict=True, ge=1, le=10000)]
    add_steps: Annotated[int, Field(strict=True, ge=1, le=10000)]
    add_tokens: Annotated[int, Field(strict=True, ge=1, le=10000000)]
    decision_digest: Fingerprint
    idempotency_key: Key


class ReconcileDecision(Contract):
    expected_version: Positive
    target: ExactTarget
    mode: Literal["READ_ORIGINAL", "OPERATOR_RESOLUTION"] = "READ_ORIGINAL"
    outcome: Literal["SUCCEEDED", "FAILED", "CANCELLED", "UNOBSERVED"] | None = None
    reason: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=1000)]
    idempotency_key: Key

    @model_validator(mode="after")
    def explicit_resolution(self):
        if (self.mode == "OPERATOR_RESOLUTION") != (self.outcome is not None):
            raise ValueError("Only an explicit operator resolution supplies an outcome")
        return self


@dataclass(frozen=True)
class ReconciliationEvidence:
    """Internal observation returned by a trusted original-request reader.

    HTTP payloads and dictionaries are deliberately not accepted as evidence.
    OPERATOR_RESOLUTION is an explicit Human decision, not a model claim.
    """
    kind: Literal["TERMINAL_RESPONSE", "LOCAL_LIFECYCLE", "OPERATOR_RESOLUTION"]
    evidence_digest: str
    outcome: Literal["SUCCEEDED", "FAILED", "CANCELLED", "UNOBSERVED"]


def schema_enabled():
    """Select by the explicit release contract; never catch missing-table errors.

    The build generates this release-specific contract. Historical packages
    explicitly disable it; missing required new tables must fail closed.
    """
    from . import edition_features
    return getattr(edition_features, "MODEL_RUNTIME_CONTEXT_ENABLED", False) is True


def server_policy():
    """The initial release policy is selected by trusted server code only.

    Its digest and limits freeze on the original root. HTTP accepts no initial
    policy, and recovery adds an explicit bounded allowance to that same root.
    """
    return BudgetPolicy(max_requests=32, max_steps=128, max_tokens=262144,
                        max_repeats=3, max_no_progress=8)


def _link(tx, continuity_id, *, lock=False):
    record = row(tx.query_one("SELECT * FROM CX_TASK_CONTINUITY_LINKS WHERE CONTINUITY_ID=:chain" + (" FOR UPDATE" if lock else ""), {"chain": continuity_id}))
    if not record:
        raise ContinuityError("PROCESSING_NOT_FOUND", "Processing resource is unavailable")
    return record


def _target(record):
    return ExactTarget.model_validate({key: record.get(key) for key in ExactTarget.model_fields})


def _validate_target(tx, target):
    link = _link(tx, target.continuity_id, lock=True)
    if link["input_digest"] != target.input_digest:
        raise ContinuityConflict("STALE_TARGET", "Processing input differs from its original request")
    frozen = row(tx.query_one("SELECT * FROM CX_PROCESSING_TARGETS WHERE CONTINUITY_ID=:chain", {"chain": target.continuity_id}))
    if frozen and any(frozen.get(key) != value for key, value in target.model_dump(exclude={"attempt_id"}).items()):
        raise ContinuityConflict("STALE_TARGET", "The exact original processing target cannot be substituted")
    if target.attempt_id:
        attempt = row(tx.query_one("SELECT * FROM CX_TASK_CONTINUITY_ATTEMPTS WHERE ATTEMPT_ID=:attempt FOR UPDATE", {"attempt": target.attempt_id}))
        if (not attempt or attempt["continuity_id"] != target.continuity_id
                or attempt["business_key"] != target.business_key or attempt["request_digest"] != link["request_digest"]):
            raise ContinuityConflict("STALE_TARGET", "Processing attempt differs from its original request")
    return link


def _default_authority(tx, actor, target, operation):
    """Existing policies remain authoritative; unsupported adapters deny.

    A trusted runtime adapter may supply a stricter check for its own Task,
    Loop, Graph or protocol path.  Such Python callbacks are not HTTP inputs.
    """
    link = _link(tx, target.continuity_id)
    seen = set()
    while link["continuity_id"] not in seen:
        seen.add(link["continuity_id"])
        chain = row(tx.query_one("SELECT ORIGINAL_CONTINUITY_ID FROM CX_PROCESSING_CHAINS WHERE CONTINUITY_ID=:chain", {"chain": link["continuity_id"]}))
        if not chain or chain["original_continuity_id"] == link["continuity_id"]:
            break
        if chain["original_continuity_id"] in seen:
            raise ContinuityError("PROCESSING_LINEAGE_INVALID", "Processing recovery lineage contains a cycle")
        if len(seen) >= 32:
            raise ContinuityError("PROCESSING_LINEAGE_INVALID", "Processing recovery lineage exceeds its bound")
        link = _link(tx, chain["original_continuity_id"])
    domain = link["security_domain_id"]
    if target.target_kind == "RUNTIME" and target.target_id.startswith("EXE_"):
        from .processing_native import authorize_target
        authorize_target(tx, actor, target, operation)
        return
    write = operation != "READ"
    work._authorize(tx, actor, domain, write=write)
    work._authorize(tx, link["actor_id"], domain, write=False)
    if link.get("canonical_task_id") and link["link_kind"] not in {"DB4A2A", "DIAGNOSTIC"}:
        from .continuity_execution_links import authorize
        authorize(tx, actor, domain, "TASK", link["canonical_task_id"])
    if target.target_kind == "RUNTIME" and _runtime_job_authority(tx, actor, link, target, operation):
        pass
    elif target.target_kind == "RUNTIME" and link["link_kind"] == "RUNTIME" and target.target_id == link["link_id"]:
        if target.target_revision != link["request_digest"]:
            raise ContinuityConflict("STALE_TARGET", "The original runtime request revision changed")
        from . import native_runtime, continuity_runtime
        native_runtime.get_execution(actor, target.target_id, transaction=tx)
        from . import model_credentials
        receipt = row(tx.query_one("SELECT * FROM CX_RUNTIME_MODEL_CREDENTIALS WHERE EXECUTION_ID=:execution", {"execution": target.target_id}))
        if not receipt or receipt["actor_id"] != link["actor_id"]:
            raise ContinuityError("RECOVERY_CREDENTIAL_REQUIRED", "The original runtime credential receipt is required")
        model_credentials.recheck(tx, model_credentials.binding_from_record(receipt))
        binding = row(tx.query_one("SELECT * FROM CX_RUNTIME_CONTEXT_BINDINGS WHERE EXECUTION_ID=:execution", {"execution": target.target_id}))
        if binding:
            continuity_runtime._authority(tx, binding["requested_by"], binding["agent_id"], domain)
            credential = row(tx.query_one("SELECT * FROM CX_RUNTIME_CONTEXT_CREDENTIALS WHERE EXECUTION_ID=:execution", {"execution": target.target_id}))
            if credential:
                continuity_runtime._credential(tx, binding["requested_by"], domain, credential)
            continuity_runtime._requester_context(tx, binding["requested_by"], binding["agent_id"], domain, binding["assembly_id"])
    elif target.target_kind == "PROTOCOL" and link["link_kind"] == "MCP" and target.target_id == link["link_id"]:
        from . import registered_protocols
        call = row(tx.query_one("SELECT * FROM CX_PROTOCOL_CALLS WHERE CALL_ID=:call", {"call": target.target_id}))
        if not call:
            raise PermissionError("Processing resource access denied")
        if target.target_revision != str(call["revision_no"]):
            raise ContinuityConflict("STALE_TARGET", "The original protocol target revision changed")
        registered_protocols._call_authority(tx, call)
    elif target.target_kind == "GRAPH":
        from .processing_graph import authorize_target
        authorize_target(tx, actor, target, operation)
    elif target.target_kind in {"LOOP", "TASK_STEP"}:
        from .processing_legacy import authorize_target
        authorize_target(tx, actor, target, operation)
    elif target.target_kind == "PROTOCOL" and link["link_kind"] == "DB4A2A":
        from .processing_db4a2a import authorize_target
        authorize_target(tx, actor, target, operation)
    else:
        raise ContinuityError("RECOVERY_AUTHORITY_ADAPTER_REQUIRED", "The original execution authority adapter is required")
    if target.source_family:
        from .continuity_sources import resolve
        source = {"family": target.source_family, "entity_id": target.source_id, "revision_id": target.source_revision_id, "content_digest": target.source_digest}
        resolve(tx, actor, domain, source, purpose="RUNTIME_CONTEXT")
        if actor != link["actor_id"]:
            resolve(tx, link["actor_id"], domain, source, purpose="RUNTIME_CONTEXT")


def _runtime_job_authority(tx, actor, link, target, operation):
    """Dispatch by exact persisted job family, never by a caller-supplied grant."""
    from .processing_runtime import authorize_target
    if authorize_target(tx, actor, link, target, operation):
        return True
    source = link["link_id"]
    if target.target_id != source or target.target_revision != link["request_digest"]:
        return False
    if link["link_kind"] == "RUNTIME" and source.startswith("RJ_"):
        from . import continuity_retrospectives as retros
        job = row(tx.query_one("SELECT * FROM CX_RETROSPECTIVE_JOBS WHERE JOB_ID=:job", {"job": source}))
        if not job or job["continuity_id"] != link["continuity_id"]:
            raise PermissionError("The original retrospective is unavailable")
        retros._authorize(tx, actor, job)
        retros._refs(tx, actor, job)
        contract = retros._output_contract(tx, job)
        if operation in {"RECOVER", "DISPATCH", "RECONCILE"} and contract.get("credential_binding") is None:
            raise ContinuityError("RECOVERY_CREDENTIAL_REQUIRED", "The original retrospective credential is required")
        return True
    if link["link_kind"] == "RUNTIME" and source.startswith("SJ_"):
        from . import agent_source_sync as sync
        job, configured = sync._job(tx, actor, source, write=operation != "READ")
        if job["continuity_id"] != link["continuity_id"]:
            raise PermissionError("The original synchronization is unavailable")
        sync._configuration(tx, configured)
        return True
    if link["link_kind"] == "RUNTIME" and source.startswith("MTU_") and ":" in source:
        from . import governed_model_turns as turns
        turn_id, phase = source.rsplit(":", 1)
        stage = row(tx.query_one("SELECT * FROM CX_MODEL_TOOL_STAGES WHERE TURN_ID=:turn AND PHASE=:phase", {"turn": turn_id, "phase": phase}))
        if not stage or stage["continuity_id"] != link["continuity_id"]:
            raise PermissionError("The original model turn stage is unavailable")
        turns._authorize(tx, actor, turns._root(tx, turn_id))
        return True
    if link["link_kind"] == "DIAGNOSTIC" and source.startswith("AQR_"):
        from . import answer_quality as quality
        job = row(tx.query_one("SELECT * FROM CX_ANSWER_QUALITY_RUNS WHERE RUN_ID=:run", {"run": source}))
        if not job or job["continuity_id"] != link["continuity_id"] or actor != job["actor_id"]:
            raise PermissionError("The original evaluation is unavailable")
        quality._authority(tx, actor, job)
        quality._inputs(tx, job)
        quality._sources(tx, actor, job)
        if operation in {"RECOVER", "DISPATCH", "RECONCILE"}:
            raise ContinuityError("RECOVERY_CREDENTIAL_ADAPTER_REQUIRED", "The original evaluation credential adapter is required")
        return True
    return False


def prepare_attempt(tx, continuity_id, business_key):
    """Bind known original Task adapters once, before the existing lease claim."""
    frozen = row(tx.query_one("SELECT * FROM CX_PROCESSING_TARGETS WHERE CONTINUITY_ID=:chain", {"chain": continuity_id}))
    if frozen:
        if frozen["target_kind"] not in {"GRAPH", "LOOP", "TASK_STEP"}:
            _attempt_authority(tx, _link(tx, continuity_id)["actor_id"], _target(frozen), "OBSERVE")
        return
    link = _link(tx, continuity_id)
    source = link["link_id"]
    eligible = (link["link_kind"] == "RUNTIME" and source.startswith(("RJ_", "SJ_", "MTU_", "EXE_"))
                or link["link_kind"] == "DIAGNOSTIC" and source.startswith("AQR_"))
    if eligible:
        target = ExactTarget(continuity_id=continuity_id, target_kind="RUNTIME", target_id=source,
            target_revision=link["request_digest"], input_digest=link["input_digest"], business_key=str(business_key))
        # The existing business adapter owns its admission and pre-send checks.
        # This internal hook freezes accounting without moving those checks or
        # changing the adapter's known-not-sent failure/receipt transaction.
        bind_server_policy(tx, actor=link["actor_id"], target=target, authority=_attempt_authority)


def _authorize(tx, actor, target, operation, authority):
    # The callback must perform its original-resource checks or raise. Neither
    # a caller's Boolean nor an arbitrary returned dictionary grants authority.
    result = (authority or _default_authority)(tx, actor, target, operation)
    if result is not None:
        raise TypeError("Processing authority callbacks must check and return None")


def _human(tx, actor):
    principal = row(tx.query_one("SELECT STATUS,PRINCIPAL_TYPE FROM CX_PRINCIPALS WHERE PRINCIPAL_ID=:actor FOR UPDATE", {"actor": actor}))
    if principal.get("status") != "ACTIVE" or principal.get("principal_type") != "HUMAN":
        raise PermissionError("An active Human recovery decision is required")


def _budget(tx, continuity_id, *, lock=True):
    value = row(tx.query_one("SELECT b.* FROM CX_PROCESSING_BUDGETS b JOIN CX_PROCESSING_CHAINS c ON c.BUDGET_ID=b.BUDGET_ID WHERE c.CONTINUITY_ID=:chain" + (" FOR UPDATE" if lock else ""), {"chain": continuity_id}))
    if not value:
        raise ContinuityError("PROCESSING_POLICY_REQUIRED", "The original durable processing budget is required")
    return value


def ensure_budget(tx, *, actor, target, policy, authority=None):
    """Register a server-selected frozen policy; never replace an existing one."""
    target = ExactTarget.model_validate(target)
    policy = BudgetPolicy.model_validate(policy)
    _authorize(tx, actor, target, "OBSERVE", authority)
    _validate_target(tx, target)
    existing = row(tx.query_one("SELECT b.* FROM CX_PROCESSING_BUDGETS b JOIN CX_PROCESSING_CHAINS c ON c.BUDGET_ID=b.BUDGET_ID WHERE c.CONTINUITY_ID=:chain FOR UPDATE", {"chain": target.continuity_id}))
    fingerprint = digest(policy.model_dump())
    if existing:
        if existing["policy_digest"] != fingerprint:
            raise ContinuityConflict("FROZEN_PROCESSING_POLICY", "The durable processing policy cannot be reset")
        return existing
    budget_id = identifier("PBU")
    tx.execute("INSERT INTO CX_PROCESSING_BUDGETS(BUDGET_ID,ROOT_CONTINUITY_ID,POLICY_DIGEST,MAX_REQUESTS,MAX_STEPS,MAX_TOKENS,MAX_REPEATS,MAX_NO_PROGRESS) VALUES(:budget,:chain,:fingerprint,:requests,:steps,:tokens,:repeats,:progress)",
               {"budget": budget_id, "chain": target.continuity_id, "fingerprint": fingerprint, "requests": policy.max_requests, "steps": policy.max_steps, "tokens": policy.max_tokens, "repeats": policy.max_repeats, "progress": policy.max_no_progress})
    tx.execute("INSERT INTO CX_PROCESSING_CHAINS(CONTINUITY_ID,BUDGET_ID,ORIGINAL_CONTINUITY_ID) VALUES(:chain,:budget,:original)", {"chain": target.continuity_id, "budget": budget_id, "original": target.continuity_id})
    _store_target(tx, target)
    identity_api._audit_tx(tx, actor, "PROCESSING_POLICY_BOUND", "TASK_CONTINUITY", target.continuity_id, "ALLOW", fingerprint)
    return _budget(tx, target.continuity_id)


def bind_server_policy(tx, *, actor, target, authority=None):
    """Trusted admission hook; callers cannot choose or reset initial limits."""
    return ensure_budget(tx, actor=actor, target=target, policy=server_policy(), authority=authority)


def _store_target(tx, target):
    tx.execute("INSERT INTO CX_PROCESSING_TARGETS(CONTINUITY_ID,TARGET_KIND,TARGET_ID,TARGET_REVISION,INPUT_DIGEST,BUSINESS_KEY,SOURCE_FAMILY,SOURCE_ID,SOURCE_REVISION_ID,SOURCE_DIGEST) VALUES(:continuity_id,:target_kind,:target_id,:target_revision,:input_digest,:business_key,:source_family,:source_id,:source_revision_id,:source_digest)", target.model_dump(exclude={"attempt_id"}))


def _block(tx, actor, target, reason_code, observation_key, *, retrieval_path="NOT_APPLICABLE", match_state="NOT_APPLICABLE"):
    if reason_code not in REASONS:
        raise ContinuityError("PROCESSING_REASON_INVALID", "Unknown typed processing reason")
    if retrieval_path not in {"NOT_APPLICABLE", "SEMANTIC", "TEXTUAL", "HYBRID", "UNAVAILABLE"} or match_state not in {"NOT_APPLICABLE", "MATCHED", "EMPTY", "UNKNOWN"}:
        raise ContinuityError("PROCESSING_RETRIEVAL_INVALID", "Unknown retrieval observation")
    observation_key = TypeAdapter(Key).validate_python(observation_key)
    event_digest = digest({"target": target.model_dump(), "reason": reason_code, "path": retrieval_path, "match": match_state})
    previous = row(tx.query_one("SELECT * FROM CX_PROCESSING_BLOCKS WHERE CONTINUITY_ID=:chain AND OBSERVATION_KEY=:event_key", {"chain": target.continuity_id, "event_key": observation_key}))
    if previous:
        if previous["observation_digest"] != event_digest:
            raise ContinuityConflict("IDEMPOTENCY_CONFLICT", "The processing observation key has different content")
        return previous | {"replayed": True}
    budget = _budget(tx, target.continuity_id)
    block_id = identifier("PBL")
    params = target.model_dump() | {"block": block_id, "budget": budget["budget_id"], "event_key": observation_key, "event_digest": event_digest,
        "reason_code": reason_code, "category": REASONS[reason_code], "path": retrieval_path, "match_state": match_state,
        "policy": budget["policy_digest"], "requests": budget["requests_used"], "steps": budget["steps_used"], "tokens": budget["tokens_used"]}
    tx.execute("INSERT INTO CX_PROCESSING_BLOCKS(BLOCK_ID,BUDGET_ID,CONTINUITY_ID,ATTEMPT_ID,OBSERVATION_KEY,OBSERVATION_DIGEST,TARGET_KIND,TARGET_ID,TARGET_REVISION,INPUT_DIGEST,SOURCE_FAMILY,SOURCE_ID,SOURCE_REVISION_ID,SOURCE_DIGEST,BUSINESS_KEY,REASON_CODE,CATEGORY,RETRIEVAL_PATH,MATCH_STATE,POLICY_DIGEST,REQUESTS_USED,STEPS_USED,TOKENS_USED,STATUS) "
               "VALUES(:block,:budget,:continuity_id,:attempt_id,:event_key,:event_digest,:target_kind,:target_id,:target_revision,:input_digest,:source_family,:source_id,:source_revision_id,:source_digest,:business_key,:reason_code,:category,:path,:match_state,:policy,:requests,:steps,:tokens,'OPEN')", params)
    identity_api._audit_tx(tx, actor, "PROCESSING_OBSERVATION", "PROCESSING_BLOCK", block_id, "ALLOW", reason_code)
    return row(tx.query_one("SELECT * FROM CX_PROCESSING_BLOCKS WHERE BLOCK_ID=:block", {"block": block_id})) | {"replayed": False}


def observe(tx, *, actor, target, reason_code, observation_key, retrieval_path="NOT_APPLICABLE", match_state="NOT_APPLICABLE", authority=None):
    target = ExactTarget.model_validate(target)
    _authorize(tx, actor, target, "OBSERVE", authority)
    _validate_target(tx, target)
    return _block(tx, actor, target, reason_code, observation_key, retrieval_path=retrieval_path, match_state=match_state)


def record_action(tx, *, actor, target, action_key, action_kind, tool_name, arguments,
                  request_count=1, step_count=1, token_count=0, progress_digest=None, authority=None,
                  _observed_completion=False):
    """Consume a durable observed event exactly once, including proposals.

    Call only from the existing executor with its persisted attempt identity.
    A progress digest references independent Task/Graph/candidate evidence; it
    is not an LLM's passed flag. No content correctness is decided here.
    """
    target = ExactTarget.model_validate(target)
    action_key = TypeAdapter(Key).validate_python(action_key)
    if not target.attempt_id or action_kind not in {"TOOL_PROPOSAL", "TOOL_CALL", "ITERATION", "MODEL_REQUEST"}:
        raise ContinuityError("PROCESSING_ACTION_INVALID", "A durable actual attempt and typed action are required")
    for value, maximum in ((request_count, 1000000), (step_count, 1000000), (token_count, 1000000000)):
        if type(value) is not int or not 0 <= value <= maximum:
            raise ContinuityError("PROCESSING_USAGE_INVALID", "Processing usage must be a bounded integer")
    if progress_digest is not None:
        TypeAdapter(Fingerprint).validate_python(progress_digest)
    from .agent_extension_contracts import bounded_json
    bounded_json(arguments, maximum=65536, depth=16)
    safe_key(tool_name)
    _authorize(tx, actor, target, "OBSERVE", authority)
    link = _validate_target(tx, target)
    budget = _budget(tx, target.continuity_id)
    signature = digest({"tool": tool_name, "arguments": arguments})
    event = {"target": target.model_dump(), "kind": action_kind, "signature": signature, "requests": request_count,
             "steps": step_count, "tokens": token_count, "progress": progress_digest}
    event_digest = digest(event)
    previous = row(tx.query_one("SELECT * FROM CX_PROCESSING_ACTIONS WHERE BUDGET_ID=:budget AND ACTION_KEY=:event_key", {"budget": budget["budget_id"], "event_key": action_key}))
    if previous:
        if previous["event_digest"] != event_digest:
            raise ContinuityConflict("IDEMPOTENCY_CONFLICT", "The processing action key has different content")
        stop = row(tx.query_one("SELECT * FROM CX_PROCESSING_BLOCKS WHERE CONTINUITY_ID=:chain AND OBSERVATION_KEY=:event_key", {"chain": target.continuity_id, "event_key": previous["action_id"]})) or None
        return {"action_id": previous["action_id"], "budget_id": budget["budget_id"], "replayed": True, "budget": budget, "stop": stop, "content_approved": False}
    if not _observed_completion and tx.query_one("SELECT BLOCK_ID FROM CX_PROCESSING_BLOCKS WHERE CONTINUITY_ID=:chain AND CATEGORY IN ('BLOCKED','UNKNOWN') AND STATUS IN ('OPEN','RECOVERY_ACCEPTED')", {"chain": target.continuity_id}):
        raise ContinuityConflict("PROCESSING_BLOCKED", "The stopped operation requires explicit exact recovery")
    attempt = row(tx.query_one("SELECT STATUS FROM CX_TASK_CONTINUITY_ATTEMPTS WHERE ATTEMPT_ID=:attempt", {"attempt": target.attempt_id}))
    if link["status"] in {"SUCCEEDED", "FAILED", "CANCELLED", "UNOBSERVED"} or attempt.get("status") != "SENDING":
        raise ContinuityConflict("PROCESSING_TERMINAL", "A completed or unknown operation cannot consume another action")
    action_id = identifier("PAC")
    action_no = int(row(tx.query_one("SELECT COALESCE(MAX(ACTION_NO),0) AS LAST_ACTION FROM CX_PROCESSING_ACTIONS WHERE BUDGET_ID=:budget", {"budget": budget["budget_id"]}))["last_action"]) + 1
    tx.execute("INSERT INTO CX_PROCESSING_ACTIONS(ACTION_ID,BUDGET_ID,CONTINUITY_ID,ATTEMPT_ID,ACTION_KEY,ACTION_KIND,ACTION_NO,ACTION_SIGNATURE,REQUEST_DIGEST,EVENT_DIGEST,REQUEST_COUNT,STEP_COUNT,TOKEN_COUNT,PROGRESS_DIGEST) VALUES(:action,:budget,:chain,:attempt,:event_key,:kind,:action_no,:signature,:request_digest,:event_digest,:requests,:steps,:tokens,:progress)",
               {"action": action_id, "budget": budget["budget_id"], "chain": target.continuity_id, "attempt": target.attempt_id,
                "event_key": action_key, "kind": action_kind, "action_no": action_no, "signature": signature, "request_digest": link["request_digest"], "event_digest": event_digest,
                "requests": request_count, "steps": step_count, "tokens": token_count, "progress": progress_digest})
    no_progress = int(budget["no_progress_count"]) + 1
    if progress_digest is not None and progress_digest != budget.get("last_progress_digest"):
        no_progress = 0
    tx.execute("UPDATE CX_PROCESSING_BUDGETS SET REQUESTS_USED=REQUESTS_USED+:requests,STEPS_USED=STEPS_USED+:steps,TOKENS_USED=TOKENS_USED+:tokens,NO_PROGRESS_COUNT=:no_progress,LAST_PROGRESS_DIGEST=:progress,VERSION=VERSION+1 WHERE BUDGET_ID=:budget",
               {"requests": request_count, "steps": step_count, "tokens": token_count, "no_progress": no_progress,
                "progress": progress_digest or budget.get("last_progress_digest"), "budget": budget["budget_id"]})
    budget = _budget(tx, target.continuity_id)
    receipt = row(tx.query_one("SELECT r.ACTION_NO_BASELINE,r.NO_PROGRESS_BASELINE,r.PROGRESS_BASELINE_DIGEST,r.ADD_REQUESTS,r.ADD_STEPS,r.ADD_TOKENS FROM CX_PROCESSING_RECOVERIES r WHERE r.SUCCESSOR_CONTINUITY_ID=:chain", {"chain": target.continuity_id}))
    baseline = int(receipt.get("action_no_baseline") or 0)
    repeats = row(tx.query_one("SELECT COUNT(*) AS REPEAT_COUNT FROM CX_PROCESSING_ACTIONS WHERE BUDGET_ID=:budget AND ACTION_SIGNATURE=:signature AND ACTION_NO>:baseline", {"budget": budget["budget_id"], "signature": signature, "baseline": baseline}))["repeat_count"]
    no_progress_delta = no_progress
    retry_usage = {}
    if receipt:
        if budget.get("last_progress_digest") == receipt.get("progress_baseline_digest"):
            no_progress_delta = max(0, no_progress - int(receipt["no_progress_baseline"]))
        retry_usage = row(tx.query_one("SELECT COALESCE(SUM(REQUEST_COUNT),0) AS REQUESTS,COALESCE(SUM(STEP_COUNT),0) AS STEPS,COALESCE(SUM(TOKEN_COUNT),0) AS TOKENS FROM CX_PROCESSING_ACTIONS WHERE CONTINUITY_ID=:chain", {"chain": target.continuity_id}))
    limits = _limits(tx, budget)
    reason = next((code for condition, code in (
        (int(budget["requests_used"]) >= limits["requests"] or (receipt and int(retry_usage["requests"]) >= int(receipt["add_requests"])), "BUDGET_REQUESTS"),
        (int(budget["steps_used"]) >= limits["steps"] or (receipt and int(retry_usage["steps"]) >= int(receipt["add_steps"])), "BUDGET_STEPS"),
        (int(budget["tokens_used"]) >= limits["tokens"] or (receipt and int(retry_usage["tokens"]) >= int(receipt["add_tokens"])), "BUDGET_TOKENS"),
        (int(repeats) >= int(budget["max_repeats"]), "REPEATED_ACTION"),
        (no_progress_delta >= int(budget["max_no_progress"]), "NO_PROGRESS")) if condition), None)
    block = _block(tx, actor, target, reason, action_id) if reason else None
    return {"action_id": action_id, "budget_id": budget["budget_id"], "replayed": False,
            "budget": budget, "stop": block, "content_approved": False}


def _attempt_authority(tx, actor, target, operation):
    """Internal fenced-executor accounting, never a public resource grant."""
    if _link(tx, target.continuity_id)["actor_id"] != actor:
        raise PermissionError("Attempt accounting belongs to its original Principal")
    _validate_target(tx, target)


def on_attempt_finished(tx, *, continuity_id, attempt_id, status, error_code=None):
    """Atomic lifecycle hook, called while the original fenced attempt sends.

    Graph owns its native run/node tuple and records its own events. Other
    adapters must first bind a server policy and exact target at admission.
    Missing usage stays unobserved; no token number is invented from text.
    """
    frozen = row(tx.query_one("SELECT * FROM CX_PROCESSING_TARGETS WHERE CONTINUITY_ID=:chain", {"chain": continuity_id}))
    if not frozen or frozen["target_kind"] in {"GRAPH", "LOOP", "TASK_STEP"}:
        return
    target = _target(frozen).model_copy(update={"attempt_id": attempt_id})
    link = _link(tx, continuity_id)
    actor = link["actor_id"]
    tokens = 0
    native_mapping = tx.query_one("SELECT TASK_ATTEMPT_ID FROM CX_PROCESSING_NATIVE_ATTEMPTS WHERE TASK_ATTEMPT_ID=:attempt", {"attempt": attempt_id})
    source_id = target.target_id
    if not native_mapping and link["link_kind"] in {"RUNTIME", "DIAGNOSTIC"} and source_id.startswith(("RJ_", "MTU_", "EXE_", "AQR_")):
        source = source_id.rsplit(":", 1)[0] if source_id.startswith("MTU_") else source_id
        counts = tx.query("SELECT o.TOTAL_TOKENS FROM CX_MODEL_ADMISSIONS a JOIN CX_MODEL_RUNTIME_OBSERVATIONS o ON o.ADMISSION_ID=a.ADMISSION_ID "
            "WHERE a.ACTOR_ID=:actor AND a.SOURCE_ID=:source AND a.SOURCE_ATTEMPT_ID=:attempt", {"actor": actor, "source": source, "attempt": attempt_id})
        counts.extend(tx.query("SELECT o.TOTAL_TOKENS FROM CX_MODEL_ORIGIN_RECEIPTS r JOIN CX_MODEL_ORIGIN_OBSERVATIONS o ON o.ORIGIN_RECEIPT_ID=r.ORIGIN_RECEIPT_ID "
            "WHERE r.ACTOR_ID=:actor AND r.SOURCE_ID=:source AND r.SOURCE_ATTEMPT_ID=:attempt AND o.REQUEST_COMPLETE='Y' AND o.RESULT_STATE IN ('COMPLETED','REJECTED')",
            {"actor": actor, "source": source, "attempt": attempt_id}))
        if len(counts) > 2:
            raise ContinuityError("PROCESSING_USAGE_BOUND", "The original attempt exceeds its observation bound")
        tokens = sum(int(row(value)["total_tokens"]) for value in counts if row(value).get("total_tokens") is not None)
    result = record_action(tx, actor=actor, target=target, action_key="attempt:" + attempt_id,
        action_kind="ITERATION", tool_name="task.attempt", arguments={"target_kind": target.target_kind,
            "target_id": target.target_id, "target_revision": target.target_revision, "input_digest": target.input_digest},
        request_count=1 if not native_mapping and target.target_kind == "RUNTIME" and not source_id.startswith("SJ_") else 0, step_count=1, token_count=tokens,
        progress_digest=digest({"attempt_id": attempt_id, "status": status}) if status == "SUCCEEDED" else None,
        authority=_attempt_authority, _observed_completion=True)
    unknown = status == "UNOBSERVED"
    if status not in {"FAILED", "UNOBSERVED"}:
        return result
    category = "UNKNOWN" if unknown else "BLOCKED"
    existing = tx.query_one("SELECT BLOCK_ID FROM CX_PROCESSING_BLOCKS WHERE CONTINUITY_ID=:chain AND ATTEMPT_ID=:attempt AND CATEGORY=:category AND STATUS='OPEN'",
                            {"chain": continuity_id, "attempt": attempt_id, "category": category})
    if not existing:
        reason = ("LEASE_EXPIRED" if error_code == "LEASE_EXPIRED" else "POSSIBLE_SEND") if unknown else {
            "REQUEST_TIMEOUT": "REQUEST_TIMEOUT", "MODEL_READ_TIMEOUT": "REQUEST_TIMEOUT", "PROVIDER_UNAVAILABLE": "PROVIDER_UNAVAILABLE",
            "SOURCE_REVOKED": "SOURCE_REVOKED", "CAPABILITY_UNAVAILABLE": "CAPABILITY_UNAVAILABLE",
            "WAITING_HUMAN": "WAITING_HUMAN", "UNMATCHED": "UNMATCHED"}.get(error_code, "FAILED")
        observe(tx, actor=actor, target=target, reason_code=reason, observation_key="lifecycle:" + attempt_id,
                authority=_attempt_authority)
    return result


def _limits(tx, budget):
    extra = row(tx.query_one("SELECT COALESCE(SUM(r.ADD_REQUESTS),0) AS EXTRA_REQUESTS,COALESCE(SUM(r.ADD_STEPS),0) AS EXTRA_STEPS,COALESCE(SUM(r.ADD_TOKENS),0) AS EXTRA_TOKENS FROM CX_PROCESSING_RECOVERIES r JOIN CX_PROCESSING_BLOCKS b ON b.BLOCK_ID=r.BLOCK_ID WHERE b.BUDGET_ID=:budget", {"budget": budget["budget_id"]}))
    return {name: int(budget["max_" + name]) + int(extra["extra_" + name]) for name in ("requests", "steps", "tokens")}


def admit_retry(actor, value, *, transaction=None, authority=None):
    request = RetryDecision.model_validate(value)
    fingerprint = digest({"actor": actor, "request": request.model_dump()})
    def perform(tx):
        _human(tx, actor)
        _authorize(tx, actor, request.target, "RECOVER", authority)
        prior = row(tx.query_one("SELECT * FROM CX_PROCESSING_RECOVERIES WHERE ACTOR_ID=:actor AND IDEMPOTENCY_KEY=:event_key", {"actor": actor, "event_key": request.idempotency_key}))
        if prior:
            if prior["request_digest"] != fingerprint:
                raise ContinuityConflict("IDEMPOTENCY_CONFLICT", "The recovery key has different content")
            return _recovery_view(tx, prior, replayed=True)
        link = _validate_target(tx, request.target)
        block = row(tx.query_one("SELECT * FROM CX_PROCESSING_BLOCKS WHERE BLOCK_ID=:block FOR UPDATE", {"block": request.block_id}))
        if not block or _target(block) != request.target or block["reason_code"] != request.reason_code:
            raise ContinuityConflict("STALE_TARGET", "The recovery must bind its exact original block and target")
        if link["status"] == "SUCCEEDED":
            return {"status": "COMPLETED", "replayed": True, "result_reference": {"link_kind": link["link_kind"], "link_id": link["link_id"], "attempt_id": request.target.attempt_id}}
        if int(block["version"]) != request.expected_version or block["status"] != "OPEN":
            raise ContinuityConflict("STALE_BLOCK", "The processing block changed")
        unknown = tx.query_one("SELECT ATTEMPT_ID FROM CX_TASK_CONTINUITY_ATTEMPTS WHERE CONTINUITY_ID=:chain AND STATUS IN ('UNOBSERVED','SENDING')", {"chain": request.target.continuity_id})
        if unknown or link["status"] == "UNOBSERVED" or (block["category"] == "UNKNOWN" and not tx.query_one("SELECT RESOLUTION_ID FROM CX_PROCESSING_RESOLUTIONS WHERE BLOCK_ID=:block AND OUTCOME<>'UNOBSERVED'", {"block": block["block_id"]})):
            raise ContinuityConflict("UNKNOWN_SEND", "The original request must be reconciled before recovery")
        if block["category"] == "DEGRADED":
            raise ContinuityConflict("RECOVERY_NOT_REQUIRED", "A degraded observation is not a stopped operation")
        budget = _budget(tx, request.target.continuity_id)
        if block["policy_digest"] != budget["policy_digest"]:
            raise ContinuityConflict("PROCESSING_POLICY_CHANGED", "The original processing policy changed")
        active = tx.query_one("SELECT r.RECOVERY_ID FROM CX_PROCESSING_RECOVERIES r JOIN CX_PROCESSING_BLOCKS b ON b.BLOCK_ID=r.BLOCK_ID JOIN CX_TASK_CONTINUITY_LINKS c ON c.CONTINUITY_ID=r.SUCCESSOR_CONTINUITY_ID WHERE b.BUDGET_ID=:budget AND c.STATUS NOT IN ('SUCCEEDED','FAILED','CANCELLED')", {"budget": budget["budget_id"]})
        if active:
            raise ContinuityConflict("RECOVERY_IN_PROGRESS", "The same processing budget already has an active recovery")
        last_action = int(row(tx.query_one("SELECT COALESCE(MAX(ACTION_NO),0) AS LAST_ACTION FROM CX_PROCESSING_ACTIONS WHERE BUDGET_ID=:budget", {"budget": budget["budget_id"]}))["last_action"])
        recovery_id = identifier("PRC")
        successor = task_continuity.link_protocol_task(tx, actor=link["actor_id"], security_domain_id=link["security_domain_id"],
            link_kind=link["link_kind"], link_id="recovery:" + recovery_id, canonical_task_id=link["canonical_task_id"],
            idempotency_key="recovery:" + recovery_id, request_digest=link["request_digest"], input_digest=link["input_digest"],
            effect_class=link["effect_class"], authorization_version=int(link["authorization_version"]), capability_version=int(link["capability_version"]),
            protocol_version=link.get("protocol_version"), sdk_version=link.get("sdk_version"), reason="Explicit bounded recovery")
        tx.execute("INSERT INTO CX_PROCESSING_CHAINS(CONTINUITY_ID,BUDGET_ID,ORIGINAL_CONTINUITY_ID) VALUES(:chain,:budget,:original)", {"chain": successor["continuity_id"], "budget": budget["budget_id"], "original": request.target.continuity_id})
        _store_target(tx, request.target.model_copy(update={"continuity_id": successor["continuity_id"], "attempt_id": None}))
        tx.execute("INSERT INTO CX_PROCESSING_RECOVERIES(RECOVERY_ID,BLOCK_ID,BLOCK_VERSION,ORIGINAL_ATTEMPT_ID,SUCCESSOR_CONTINUITY_ID,ACTOR_ID,IDEMPOTENCY_KEY,REQUEST_DIGEST,REASON_CODE,ADD_REQUESTS,ADD_STEPS,ADD_TOKENS,DECISION_DIGEST,ACTION_NO_BASELINE,NO_PROGRESS_BASELINE,PROGRESS_BASELINE_DIGEST) VALUES(:recovery,:block,:revision,:attempt,:chain,:actor,:event_key,:fingerprint,:reason_code,:requests,:steps,:tokens,:decision,:action_base,:progress_base,:progress_digest)",
                   {"recovery": recovery_id, "block": block["block_id"], "revision": request.expected_version, "attempt": request.target.attempt_id,
                    "chain": successor["continuity_id"], "actor": actor, "event_key": request.idempotency_key, "fingerprint": fingerprint,
                    "reason_code": request.reason_code, "requests": request.add_requests, "steps": request.add_steps, "tokens": request.add_tokens, "decision": request.decision_digest,
                    "action_base": last_action, "progress_base": budget["no_progress_count"], "progress_digest": budget.get("last_progress_digest")})
        tx.execute("INSERT INTO CX_PROCESSING_RECOVERY_STATES(RECOVERY_ID,STATUS) VALUES(:recovery,'ACCEPTED')", {"recovery": recovery_id})
        tx.execute("UPDATE CX_PROCESSING_BLOCKS SET STATUS='RECOVERY_ACCEPTED',VERSION=VERSION+1 WHERE BLOCK_ID=:block", {"block": block["block_id"]})
        identity_api._audit_tx(tx, actor, "PROCESSING_RECOVERY_ACCEPTED", "PROCESSING_RECOVERY", recovery_id, "ALLOW", request.reason_code)
        return _recovery_view(tx, row(tx.query_one("SELECT * FROM CX_PROCESSING_RECOVERIES WHERE RECOVERY_ID=:recovery", {"recovery": recovery_id})))
    return perform(transaction) if transaction is not None else connection.execute_transaction_callback(perform)


def _recovery_view(tx, receipt, *, replayed=False):
    state = row(tx.query_one("SELECT * FROM CX_PROCESSING_RECOVERY_STATES WHERE RECOVERY_ID=:recovery", {"recovery": receipt["recovery_id"]}))
    successor = _link(tx, receipt["successor_continuity_id"])
    status = {"SUCCEEDED": "COMPLETED", "FAILED": "REJECTED", "CANCELLED": "REJECTED", "UNOBSERVED": "UNKNOWN"}.get(successor["status"], state["status"])
    return {"recovery_id": receipt["recovery_id"], "block_id": receipt["block_id"], "original_attempt_id": receipt.get("original_attempt_id"),
            "successor_continuity_id": receipt["successor_continuity_id"], "status": status, "admission_id": state.get("admission_id"),
            "replayed": replayed, "dispatched": state["status"] in {"DISPATCHED", "COMPLETED", "UNKNOWN"}, "content_approved": False}


def bind_capacity(tx, *, actor, recovery_id, admission_id, authority=None):
    """Record accepted/queued observation only; never acquire a Worker lease."""
    receipt = row(tx.query_one("SELECT * FROM CX_PROCESSING_RECOVERIES WHERE RECOVERY_ID=:recovery FOR UPDATE", {"recovery": recovery_id}))
    if not receipt or receipt["actor_id"] != actor:
        raise PermissionError("Recovery admission access denied")
    block = row(tx.query_one("SELECT * FROM CX_PROCESSING_BLOCKS WHERE BLOCK_ID=:block", {"block": receipt["block_id"]}))
    _authorize(tx, actor, _target(block), "RECOVER", authority)
    admission = row(tx.query_one("SELECT * FROM CX_MODEL_ADMISSIONS WHERE ADMISSION_ID=:admission FOR UPDATE", {"admission": admission_id}))
    if (not admission or admission["status"] not in {"QUEUED", "RESERVED"} or admission["actor_id"] != actor
            or admission["source_id"] != receipt["successor_continuity_id"] or admission["source_attempt_id"] != recovery_id
            or admission["input_digest"] != block["input_digest"]):
        raise PermissionError("An exact current capacity admission is required")
    state = row(tx.query_one("SELECT * FROM CX_PROCESSING_RECOVERY_STATES WHERE RECOVERY_ID=:recovery FOR UPDATE", {"recovery": recovery_id}))
    if state.get("admission_id") == admission_id and state["status"] == "QUEUED":
        return _recovery_view(tx, receipt, replayed=True)
    if state["status"] != "ACCEPTED" or state.get("admission_id"):
        raise ContinuityConflict("RECOVERY_ALREADY_DISPATCHED", "Recovery admission cannot be replaced")
    tx.execute("UPDATE CX_PROCESSING_RECOVERY_STATES SET STATUS='QUEUED',ADMISSION_ID=:admission,VERSION=VERSION+1 WHERE RECOVERY_ID=:recovery", {"admission": admission_id, "recovery": recovery_id})
    identity_api._audit_tx(tx, actor, "PROCESSING_RECOVERY_QUEUED", "PROCESSING_RECOVERY", recovery_id, "ALLOW", "Accepted; no Worker lease or external send")
    return _recovery_view(tx, receipt)


def capacity_gate(tx, *, actor, recovery_id, admission_id, authority=None):
    """Trusted begin_dispatch callback; authorize from the locked DB facts.

    Invoke inside model_endpoint_capacity.begin_dispatch's reauthorize(tx,...).
    Capacity owns the transition to DISPATCHING and its one-shot send decision;
    this function never returns a Boolean or creates Worker leases.
    """
    receipt = row(tx.query_one("SELECT * FROM CX_PROCESSING_RECOVERIES WHERE RECOVERY_ID=:recovery FOR UPDATE", {"recovery": recovery_id}))
    if not receipt or receipt["actor_id"] != actor:
        raise PermissionError("Recovery admission access denied")
    block = row(tx.query_one("SELECT * FROM CX_PROCESSING_BLOCKS WHERE BLOCK_ID=:block", {"block": receipt["block_id"]}))
    _authorize(tx, actor, _target(block), "DISPATCH", authority)
    _validate_target(tx, _target(block))
    original = _link(tx, block["continuity_id"])
    if original["status"] == "SUCCEEDED" or tx.query_one("SELECT ATTEMPT_ID FROM CX_TASK_CONTINUITY_ATTEMPTS WHERE CONTINUITY_ID=:chain AND STATUS IN ('SENDING','UNOBSERVED')", {"chain": original["continuity_id"]}):
        raise ContinuityConflict("RECOVERY_ORIGINAL_CHANGED", "The original request cannot be resent")
    admission = row(tx.query_one("SELECT * FROM CX_MODEL_ADMISSIONS WHERE ADMISSION_ID=:admission FOR UPDATE", {"admission": admission_id}))
    if (not admission or admission["status"] != "RESERVED" or admission["actor_id"] != actor
            or admission["source_id"] != receipt["successor_continuity_id"] or admission["source_attempt_id"] != recovery_id
            or admission["input_digest"] != block["input_digest"] or int(admission["fencing_token"]) < 1):
        raise PermissionError("An exact current capacity reservation is required")
    state = row(tx.query_one("SELECT * FROM CX_PROCESSING_RECOVERY_STATES WHERE RECOVERY_ID=:recovery FOR UPDATE", {"recovery": recovery_id}))
    if state["status"] not in {"ACCEPTED", "QUEUED"} or (state.get("admission_id") and state["admission_id"] != admission_id):
        raise ContinuityConflict("RECOVERY_ALREADY_DISPATCHED", "Recovery dispatch is not repeatable")
    tx.execute("UPDATE CX_PROCESSING_RECOVERY_STATES SET STATUS='DISPATCHED',ADMISSION_ID=:admission,VERSION=VERSION+1 WHERE RECOVERY_ID=:recovery", {"admission": admission_id, "recovery": recovery_id})
    identity_api._audit_tx(tx, actor, "PROCESSING_RECOVERY_DISPATCH", "PROCESSING_RECOVERY", recovery_id, "ALLOW", "Current exact capacity and authority")


def claim_gate(tx, continuity_id):
    """Existing Task claim calls this before leasing; old chains stay unchanged."""
    chain = row(tx.query_one("SELECT * FROM CX_PROCESSING_CHAINS WHERE CONTINUITY_ID=:chain", {"chain": continuity_id}))
    if not chain:
        return
    blocked = tx.query_one("SELECT BLOCK_ID FROM CX_PROCESSING_BLOCKS WHERE CONTINUITY_ID=:chain AND CATEGORY IN ('BLOCKED','UNKNOWN') AND STATUS IN ('OPEN','RECOVERY_ACCEPTED')", {"chain": continuity_id})
    if blocked:
        raise ContinuityConflict("PROCESSING_BLOCKED", "The original processing block requires explicit exact recovery")
    recovery = row(tx.query_one("SELECT r.RECOVERY_ID,s.STATUS,s.ADMISSION_ID FROM CX_PROCESSING_RECOVERIES r JOIN CX_PROCESSING_RECOVERY_STATES s ON s.RECOVERY_ID=r.RECOVERY_ID WHERE r.SUCCESSOR_CONTINUITY_ID=:chain", {"chain": continuity_id}))
    if recovery:
        frozen = row(tx.query_one("SELECT TARGET_KIND,TARGET_ID FROM CX_PROCESSING_TARGETS WHERE CONTINUITY_ID=:chain", {"chain": continuity_id}))
        if frozen.get("target_kind") == "GRAPH":
            from .processing_graph import claim_recovery_gate
            return claim_recovery_gate(tx, continuity_id, recovery)
        if frozen.get("target_kind") == "RUNTIME" and frozen["target_id"].startswith("EXE_"):
            from .processing_native import claim_recovery_gate
            return claim_recovery_gate(tx, continuity_id, recovery)
        if frozen.get("target_kind") == "RUNTIME" and frozen["target_id"].startswith(("RJ_", "SJ_", "MTU_", "AQR_")):
            from .processing_runtime import claim_recovery_gate
            return claim_recovery_gate(tx, continuity_id, recovery)
        admission = row(tx.query_one("SELECT STATUS,SOURCE_ID,SOURCE_ATTEMPT_ID FROM CX_MODEL_ADMISSIONS WHERE ADMISSION_ID=:admission", {"admission": recovery.get("admission_id")}))
        if admission.get("status") == "UNKNOWN":
            raise ContinuityConflict("UNKNOWN_SEND", "Recovery send outcome is unknown and requires reconciliation")
        if (recovery["status"] != "DISPATCHED" or admission.get("status") != "DISPATCHING"
                or admission.get("source_id") != continuity_id or admission.get("source_attempt_id") != recovery["recovery_id"]):
            raise ContinuityConflict("RECOVERY_QUEUED", "Recovery is accepted and awaits current endpoint admission")


def read_diagnostics(tx, *, actor, continuity_id, authority=None, after="", limit=100):
    """No repair, enqueue, budget reset, source body or credential disclosure."""
    chain = row(tx.query_one("SELECT * FROM CX_PROCESSING_CHAINS WHERE CONTINUITY_ID=:chain", {"chain": continuity_id}))
    if not chain:
        return None
    if type(limit) is not int or not 1 <= limit <= 100 or (after and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", after)):
        raise ValueError("Invalid processing observation page")
    blocks = [row(value) for value in tx.query("SELECT * FROM (SELECT b.*,ROW_NUMBER() OVER(ORDER BY BLOCK_ID) AS PROCESSING_ROW "
        "FROM CX_PROCESSING_BLOCKS b WHERE CONTINUITY_ID=:chain AND BLOCK_ID>:after_id) page WHERE PROCESSING_ROW<=:page_limit ORDER BY PROCESSING_ROW",
        {"chain": continuity_id, "after_id": after or "!", "page_limit": limit + 1})]
    more = len(blocks) > limit
    blocks = blocks[:limit]
    for block in blocks:
        _authorize(tx, actor, _target(block), "READ", authority)
    if not blocks:
        frozen = row(tx.query_one("SELECT * FROM CX_PROCESSING_TARGETS WHERE CONTINUITY_ID=:chain", {"chain": continuity_id}))
        if not frozen:
            raise ContinuityError("PROCESSING_TARGET_REQUIRED", "The original exact processing target is required")
        _authorize(tx, actor, _target(frozen), "READ", authority)
    link = _link(tx, continuity_id)
    budget = _budget(tx, continuity_id, lock=False)
    recoveries = [_recovery_view(tx, row(value)) for value in tx.query("SELECT r.* FROM CX_PROCESSING_RECOVERIES r JOIN CX_PROCESSING_BLOCKS b ON b.BLOCK_ID=r.BLOCK_ID "
        "WHERE b.CONTINUITY_ID=:chain AND b.BLOCK_ID>:after_id AND b.BLOCK_ID<=:last_id ORDER BY r.CREATED_AT,r.RECOVERY_ID",
        {"chain": continuity_id, "after_id": after or "!", "last_id": blocks[-1]["block_id"]})] if blocks else []
    allowed = {"block_id", "continuity_id", "attempt_id", "target_kind", "target_id", "target_revision", "reason_code", "category",
               "retrieval_path", "match_state", "status", "version", "requests_used", "steps_used", "tokens_used"}
    frozen = row(tx.query_one("SELECT * FROM CX_PROCESSING_TARGETS WHERE CONTINUITY_ID=:chain", {"chain": continuity_id}))
    return {"continuity_id": continuity_id, "budget_id": budget["budget_id"], "policy_digest": budget["policy_digest"], "lifecycle_status": link["status"], "canonical_task_id": link["canonical_task_id"],
            "target": _target(frozen).model_dump() if frozen else None,
            "consumed": {key: int(budget[key + "_used"]) for key in ("requests", "steps", "tokens")},
            "no_progress_count": int(budget["no_progress_count"]), "limits": _limits(tx, budget),
            "token_accounting": {"reported_or_executor_observed_only": True, "missing_usage": "UNOBSERVED"},
            "next_cursor": blocks[-1]["block_id"] if more else None,
            "observations": [{**{key: value for key, value in block.items() if key in allowed}, "target": _target(block).model_dump()} for block in blocks],
            "recoveries": recoveries, "generation_requested": False, "content_approved": False}


def reconcile(actor, block_id, *, read_evidence, transaction=None, authority=None, reconcile_capacity=None):
    """Reconcile original observations; no retry or idle-generation probe.

    A trusted reader returns typed evidence bound to this exact block. Unknown
    observations stay unknown. Matching capacity lifecycles must reconcile in
    the same transaction; absent a matching adapter the operation fails closed.
    """
    def perform(tx):
        _human(tx, actor)
        block = row(tx.query_one("SELECT * FROM CX_PROCESSING_BLOCKS WHERE BLOCK_ID=:block FOR UPDATE", {"block": block_id}))
        if not block or block["category"] != "UNKNOWN" or not block.get("attempt_id"):
            raise ContinuityConflict("RECONCILIATION_NOT_REQUIRED", "An exact unknown attempt is required")
        _authorize(tx, actor, _target(block), "RECONCILE", authority)
        link = _validate_target(tx, _target(block))
        evidence = read_evidence(tx, _target(block))
        if (not isinstance(evidence, ReconciliationEvidence) or evidence.kind not in {"TERMINAL_RESPONSE", "LOCAL_LIFECYCLE", "OPERATOR_RESOLUTION"}
                or evidence.outcome not in {"SUCCEEDED", "FAILED", "CANCELLED", "UNOBSERVED"} or not re.fullmatch(r"[0-9a-f]{64}", str(evidence.evidence_digest))):
            raise ContinuityError("RECONCILIATION_EVIDENCE_REQUIRED", "Trusted exact original-request evidence is required")
        prior = row(tx.query_one("SELECT * FROM CX_PROCESSING_RESOLUTIONS WHERE BLOCK_ID=:block AND EVIDENCE_KIND=:kind AND EVIDENCE_DIGEST=:fingerprint", {"block": block_id, "kind": evidence.kind, "fingerprint": evidence.evidence_digest}))
        if prior:
            if prior["outcome"] != evidence.outcome:
                raise ContinuityConflict("IDEMPOTENCY_CONFLICT", "Reconciliation evidence has a different outcome")
            return {"block_id": block_id, "status": prior["outcome"], "replayed": True, "generation_requested": False}
        attempt = row(tx.query_one("SELECT * FROM CX_TASK_CONTINUITY_ATTEMPTS WHERE ATTEMPT_ID=:attempt FOR UPDATE", {"attempt": block["attempt_id"]}))
        if attempt["status"] != "UNOBSERVED":
            raise ContinuityConflict("NOT_UNOBSERVED", "The original attempt is no longer unobserved")
        if evidence.outcome != "UNOBSERVED":
            remote = origin_evidence(tx, _target(block))
            if any(value["status"] in {"UNKNOWN", "DISPATCHING"} and not value.get("resolution") for value in remote):
                raise ContinuityError("CAPACITY_RECONCILIATION_REQUIRED", "The exact remote capacity lifecycle needs its registered coordinator resolution")
            if remote and evidence.outcome == "SUCCEEDED":
                raise ContinuityError("BUSINESS_SUCCESS_EVIDENCE_REQUIRED", "Remote transport termination does not establish committed business success")
            model_source = block["target_id"]
            if block["target_kind"] == "RUNTIME" and model_source.startswith("MTU_") and ":" in model_source:
                # Native model-turn stages have separate Task links while
                # endpoint admission retains the original whole-turn source.
                model_source = model_source.rsplit(":", 1)[0]
            capacity_params = {"chain": block["continuity_id"], "target": model_source, "attempt": block["attempt_id"]}
            exact_attempt = "SOURCE_ATTEMPT_ID=:attempt"
            if block["target_kind"] == "RUNTIME" and model_source.startswith("EXE_"):
                exact_attempt = "SOURCE_ATTEMPT_ID IN (SELECT SOURCE_ATTEMPT_ID FROM CX_PROCESSING_NATIVE_CALLS WHERE TASK_ATTEMPT_ID=:attempt)"
            capacity_sql = "SELECT * FROM CX_MODEL_ADMISSIONS WHERE (SOURCE_ID=:chain OR SOURCE_ID=:target) AND " + exact_attempt + " AND STATUS='UNKNOWN'"
            admissions = [row(value) for value in tx.query(capacity_sql, capacity_params)]
            if admissions:
                if reconcile_capacity is None:
                    raise ContinuityError("CAPACITY_RECONCILIATION_REQUIRED", "The original capacity lifecycle must reconcile atomically")
                reconcile_capacity(tx, admissions, evidence)
                if tx.query_one(capacity_sql, capacity_params):
                    raise ContinuityConflict("CAPACITY_STILL_UNKNOWN", "The original capacity lifecycle remains unknown")
            task_continuity.reconcile_unobserved(tx, continuity_id=block["continuity_id"], business_key=block["business_key"], actor=actor, request_digest=link["request_digest"], outcome=evidence.outcome)
            if block["target_kind"] == "RUNTIME" and block["target_id"].startswith("EXE_"):
                from .processing_native import reconcile_business
                reconcile_business(tx, _target(block), evidence)
            tx.execute("UPDATE CX_TASK_CONTINUITY_LEASES SET STATUS='RELEASED',FENCING_TOKEN=FENCING_TOKEN+1 WHERE CONTINUITY_ID=:chain", {"chain": block["continuity_id"]})
            if evidence.outcome == "SUCCEEDED":
                tx.execute("UPDATE CX_PROCESSING_BLOCKS SET STATUS='RESOLVED',VERSION=VERSION+1 WHERE BLOCK_ID=:block", {"block": block_id})
        tx.execute("INSERT INTO CX_PROCESSING_RESOLUTIONS(RESOLUTION_ID,BLOCK_ID,ATTEMPT_ID,ACTOR_ID,BUSINESS_KEY,REQUEST_DIGEST,EVIDENCE_KIND,EVIDENCE_DIGEST,OUTCOME) VALUES(:resolution,:block,:attempt,:actor,:business,:request_digest,:kind,:fingerprint,:outcome)",
                   {"resolution": identifier("PRS"), "block": block_id, "attempt": block["attempt_id"], "actor": actor, "business": block["business_key"],
                    "request_digest": link["request_digest"], "kind": evidence.kind, "fingerprint": evidence.evidence_digest, "outcome": evidence.outcome})
        identity_api._audit_tx(tx, actor, "PROCESSING_RECONCILED", "PROCESSING_BLOCK", block_id, "ALLOW", evidence.kind + ":" + evidence.outcome)
        return {"block_id": block_id, "status": evidence.outcome, "replayed": False, "generation_requested": False}
    return perform(transaction) if transaction is not None else connection.execute_transaction_callback(perform)


def read_processing(actor, continuity_id, *, transaction=None, after="", limit=100):
    def perform(tx):
        result = read_diagnostics(tx, actor=actor, continuity_id=TypeAdapter(Key).validate_python(continuity_id), after=after, limit=limit)
        if result is None:
            raise ContinuityError("PROCESSING_NOT_FOUND", "Processing resource is unavailable")
        return result
    return perform(transaction) if transaction is not None else connection.execute_transaction_callback(perform)


def reconcile_decision(actor, block_id, value, *, transaction=None):
    """HTTP-safe explicit Human resolution, never caller-claimed transport proof."""
    request = ReconcileDecision.model_validate(value)
    fingerprint = digest({"actor": actor, "block_id": block_id, "decision": request.model_dump()})
    def perform(tx):
        _human(tx, actor)
        block = row(tx.query_one("SELECT * FROM CX_PROCESSING_BLOCKS WHERE BLOCK_ID=:block FOR UPDATE", {"block": block_id}))
        if not block or _target(block) != request.target:
            raise ContinuityConflict("STALE_TARGET", "The resolution must bind its exact original target")
        _authorize(tx, actor, request.target, "RECONCILE", None)
        if request.mode == "READ_ORIGINAL":
            attempt = row(tx.query_one("SELECT STATUS,REQUEST_DIGEST,BUSINESS_KEY FROM CX_TASK_CONTINUITY_ATTEMPTS WHERE ATTEMPT_ID=:attempt",
                                       {"attempt": request.target.attempt_id}))
            if not attempt or attempt.get("business_key") != request.target.business_key:
                raise ContinuityError("RECONCILIATION_EVIDENCE_REQUIRED", "The original attempt reader is unavailable")
            # A local unknown observation is truthful, but cannot prove remote
            # termination or authorize another send.
            if request.target.target_kind == "GRAPH":
                from .processing_graph import read_evidence
                evidence = read_evidence(tx, request.target)
            elif request.target.target_kind == "RUNTIME" and request.target.target_id.startswith("EXE_"):
                from .processing_native import read_evidence
                evidence = read_evidence(tx, request.target)
            elif request.target.target_kind == "RUNTIME" and request.target.target_id.startswith(("RJ_", "SJ_", "MTU_", "AQR_")):
                from .processing_runtime import read_evidence
                evidence = read_evidence(tx, request.target)
            else:
                evidence = ReconciliationEvidence("LOCAL_LIFECYCLE", fingerprint, "UNOBSERVED")
        else:
            evidence = ReconciliationEvidence("OPERATOR_RESOLUTION", fingerprint, request.outcome)
        prior = tx.query_one("SELECT RESOLUTION_ID FROM CX_PROCESSING_RESOLUTIONS WHERE BLOCK_ID=:block AND EVIDENCE_DIGEST=:fingerprint",
                             {"block": block_id, "fingerprint": evidence.evidence_digest})
        if not prior and int(block["version"]) != request.expected_version:
            raise ContinuityConflict("STALE_BLOCK", "The processing block changed")
        def reconcile_capacity(exact_tx, admissions, trusted_evidence):
            from . import model_endpoint_capacity
            for admission in admissions:
                native = request.target.target_kind == "RUNTIME" and request.target.target_id.startswith("EXE_")
                original = _link(exact_tx, request.target.continuity_id)
                if native:
                    mapped = row(exact_tx.query_one("SELECT c.SOURCE_KIND FROM CX_PROCESSING_NATIVE_CALLS c "
                        "JOIN CX_PROCESSING_NATIVE_ATTEMPTS n ON n.TASK_ATTEMPT_ID=c.TASK_ATTEMPT_ID "
                        "WHERE c.SOURCE_ATTEMPT_ID=:source AND c.TASK_ATTEMPT_ID=:attempt AND n.EXECUTION_ID=:execution",
                        {"source": admission["source_attempt_id"], "attempt": request.target.attempt_id, "execution": request.target.target_id}))
                    exact = bool(mapped and mapped["source_kind"] == admission["source_kind"] and admission["source_id"] == request.target.target_id)
                else:
                    exact = admission["source_attempt_id"] == request.target.attempt_id
                if not exact or admission["actor_id"] != original["actor_id"]:
                    raise PermissionError("Capacity evidence differs from the exact original processing attempt")
                attempt = row(exact_tx.query_one("SELECT ATTEMPT_ID,FENCING_TOKEN FROM CX_MODEL_CAP_ATTEMPTS WHERE ADMISSION_ID=:admission",
                                                {"admission": admission["admission_id"]}))
                if not attempt:
                    raise ContinuityError("RECONCILIATION_EVIDENCE_REQUIRED", "The exact capacity dispatch attempt is unavailable")
                model_endpoint_capacity.observe_completion(actor, admission["admission_id"], dict(
                    expected_version=int(admission["version"]), attempt_id=attempt["attempt_id"], fencing_token=int(attempt["fencing_token"]),
                    evidence_digest=trusted_evidence.evidence_digest,
                    evidence_kind="OPERATOR_CONFIRMATION" if trusted_evidence.kind == "OPERATOR_RESOLUTION" else "LOCAL_LIFECYCLE",
                    finish_code="PROCESSING_" + trusted_evidence.outcome, reason=request.reason,
                    idempotency_key="processing:" + digest([block_id, admission["admission_id"], trusted_evidence.evidence_digest])[:64]),
                    reconcile=True, transaction=exact_tx)
        return reconcile(actor, block_id, read_evidence=lambda _tx, _target: evidence, transaction=tx, reconcile_capacity=reconcile_capacity)
    return perform(transaction) if transaction is not None else connection.execute_transaction_callback(perform)


def dispatch_retry(actor, recovery_id, *, transaction=None):
    """Only an installed original-domain adapter may execute an accepted receipt."""
    runtime_worker = []
    def perform(tx):
        _human(tx, actor)
        receipt = row(tx.query_one("SELECT * FROM CX_PROCESSING_RECOVERIES WHERE RECOVERY_ID=:recovery FOR UPDATE", {"recovery": recovery_id}))
        if not receipt:
            raise PermissionError("Recovery receipt is unavailable")
        block = row(tx.query_one("SELECT * FROM CX_PROCESSING_BLOCKS WHERE BLOCK_ID=:block", {"block": receipt["block_id"]}))
        target = _target(block)
        _authorize(tx, actor, target, "DISPATCH", None)
        if target.target_kind == "GRAPH":
            from .processing_graph import dispatch_recovery
            return dispatch_recovery(tx, actor, recovery_id)
        if target.target_kind == "RUNTIME" and target.target_id.startswith("EXE_"):
            from .processing_native import dispatch_recovery
            return dispatch_recovery(tx, actor, recovery_id)
        if target.target_kind == "RUNTIME" and target.target_id.startswith(("RJ_", "SJ_", "MTU_", "AQR_")):
            from .processing_runtime import dispatch_recovery
            result = dispatch_recovery(tx, actor, recovery_id)
            runtime_worker.append(True)
            return result
        raise ContinuityError("RECOVERY_DISPATCH_ADAPTER_REQUIRED", "The original execution dispatch adapter is required")
    if transaction is not None:
        return perform(transaction)
    result = connection.execute_transaction_callback(perform)
    if runtime_worker:
        from .processing_runtime import run_recovery
        run_recovery(actor, recovery_id)
        return connection.execute_transaction_callback(lambda tx: _recovery_view(tx, row(tx.query_one(
            "SELECT * FROM CX_PROCESSING_RECOVERIES WHERE RECOVERY_ID=:recovery", {"recovery": recovery_id}))))
    return result


def on_origin_dispatch(tx, receipt):
    """Final Origin authorization uses its typed receipt, never a local quota."""
    if not schema_enabled():
        return
    if receipt["source_kind"] in {"NATIVE", "CHANNEL"} and receipt["source_id"].startswith("EXE_"):
        attempt = row(tx.query_one("SELECT n.CONTINUITY_ID,n.TASK_ATTEMPT_ID AS ATTEMPT_ID FROM CX_PROCESSING_NATIVE_CALLS c "
            "JOIN CX_PROCESSING_NATIVE_ATTEMPTS n ON n.TASK_ATTEMPT_ID=c.TASK_ATTEMPT_ID WHERE c.SOURCE_ATTEMPT_ID=:source "
            "AND c.SOURCE_KIND=:kind AND n.EXECUTION_ID=:execution", dict(source=receipt["source_attempt_id"], kind=receipt["source_kind"], execution=receipt["source_id"])))
    else:
        attempt = row(tx.query_one("SELECT CONTINUITY_ID,ATTEMPT_ID FROM CX_TASK_CONTINUITY_ATTEMPTS WHERE ATTEMPT_ID=:attempt",
            {"attempt": receipt["source_attempt_id"]}))
    if not attempt:
        return
    original = _link(tx, attempt["continuity_id"])
    actual = row(tx.query_one("SELECT STATUS FROM CX_TASK_CONTINUITY_ATTEMPTS WHERE ATTEMPT_ID=:attempt", {"attempt": attempt["attempt_id"]}))
    if original["actor_id"] != receipt["actor_id"] or actual.get("status") != "SENDING":
        raise PermissionError("The final Origin receipt differs from its original real Task attempt")
    tx.execute("UPDATE CX_PROCESSING_RECOVERY_STATES SET STATUS='DISPATCHED',VERSION=VERSION+1 WHERE STATUS='QUEUED' "
        "AND ADMISSION_ID IS NULL AND RECOVERY_ID IN (SELECT RECOVERY_ID FROM CX_PROCESSING_RECOVERIES WHERE SUCCESSOR_CONTINUITY_ID=:chain)",
        {"chain": attempt["continuity_id"]})


def origin_evidence(tx, target):
    """Only exact real-attempt receipts can settle a remote transport outcome."""
    if target.target_kind != "RUNTIME" or not target.target_id.startswith(("EXE_", "RJ_", "MTU_", "AQR_")) or not target.attempt_id:
        return []
    source = target.target_id.rsplit(":", 1)[0] if target.target_id.startswith("MTU_") else target.target_id
    attempt_sql = "r.SOURCE_ATTEMPT_ID=:attempt"
    if source.startswith("EXE_"):
        attempt_sql = "r.SOURCE_ATTEMPT_ID IN (SELECT SOURCE_ATTEMPT_ID FROM CX_PROCESSING_NATIVE_CALLS WHERE TASK_ATTEMPT_ID=:attempt)"
    params = dict(source=source, attempt=target.attempt_id, actor=_link(tx, target.continuity_id)["actor_id"])
    values = [row(value) for value in tx.query("SELECT r.* FROM CX_MODEL_ORIGIN_RECEIPTS r WHERE r.SOURCE_ID=:source AND r.ACTOR_ID=:actor AND " + attempt_sql, params)]
    from . import model_coordinator_origin
    for value in values:
        value["resolution"] = model_coordinator_origin.resolution_for_receipt(tx, value)
        value["observation"] = row(tx.query_one("SELECT OBSERVATION_DIGEST,REQUEST_COMPLETE,RESULT_STATE FROM CX_MODEL_ORIGIN_OBSERVATIONS WHERE ORIGIN_RECEIPT_ID=:receipt",
            {"receipt": value["origin_receipt_id"]})) or None
    return values


def authorize_origin_receipt(tx, actor, receipt):
    """Recheck exact original business authority for remote status resolution."""
    if receipt["source_kind"] in {"NATIVE", "CHANNEL"} and receipt["source_id"].startswith("EXE_"):
        from .processing_native import authorize_origin_receipt as native_authority
        return native_authority(tx, actor, receipt)
    from . import processing_runtime as adapter, model_credentials
    attempt = row(tx.query_one("SELECT * FROM CX_TASK_CONTINUITY_ATTEMPTS WHERE ATTEMPT_ID=:attempt FOR UPDATE",
        {"attempt": receipt["source_attempt_id"]}))
    if not attempt:
        raise PermissionError("The exact original Origin Task attempt is unavailable")
    link = _link(tx, attempt["continuity_id"])
    original = adapter._original(tx, link)
    frozen = row(tx.query_one("SELECT * FROM CX_PROCESSING_TARGETS WHERE CONTINUITY_ID=:chain", {"chain": link["continuity_id"]}))
    if not frozen:
        raise PermissionError("The original processing target is unavailable")
    target = _target(frozen).model_copy(update={"attempt_id": attempt["attempt_id"]})
    _validate_target(tx, target)
    source = original["link_id"]
    model_source = source.rsplit(":", 1)[0] if source.startswith("MTU_") else source
    kind = "RETROSPECTIVE" if source.startswith("RJ_") else "EVALUATION" if source.startswith("AQR_") else "NATIVE"
    if (receipt["source_id"] != model_source or receipt["source_kind"] != kind or receipt["actor_id"] != original["actor_id"]
            or int(receipt["origin_fencing_token"]) != int(attempt["fencing_token"]) or attempt["status"] not in {"UNOBSERVED", "FAILED", "CANCELLED"}
            or not adapter.authorize_target(tx, actor, link, target, "READ")):
        raise PermissionError("The Origin receipt differs from its exact original business attempt")
    lease = row(tx.query_one("SELECT * FROM CX_TASK_CONTINUITY_LEASES WHERE CONTINUITY_ID=:chain FOR UPDATE", {"chain": link["continuity_id"]}))
    if (not lease or lease["lease_owner"] != receipt["worker_key"] or int(lease["fencing_token"]) not in
            {int(attempt["fencing_token"]), int(attempt["fencing_token"]) + 1}):
        raise PermissionError("The original Origin Worker was replaced")
    if source.startswith("RJ_"):
        from . import continuity_retrospectives as retros
        job = row(tx.query_one("SELECT * FROM CX_RETROSPECTIVE_JOBS WHERE JOB_ID=:source", {"source": source}))
        binding = retros._output_contract(tx, job).get("credential_binding")
        profile_id, profile_version = job["profile_id"], job["profile_version"]
    elif source.startswith("AQR_"):
        job = row(tx.query_one("SELECT * FROM CX_ANSWER_QUALITY_RUNS WHERE RUN_ID=:source", {"source": source}))
        binding = adapter.evaluation_credential(tx, original["actor_id"], source, required=True)
        profile_id, profile_version = job["profile_id"], job["profile_version"]
    elif source.startswith("MTU_"):
        from . import governed_model_turns as turns
        job = turns._root(tx, model_source, observer=actor)
        binding = model_credentials.CredentialBinding(original["actor_id"], "AGENT", job["token_digest"],
            instance_id=job["instance_id"], fencing_token=int(job["fencing_token"]), required_scope="actions.propose")
        profile_id, profile_version = job["profile_id"], job["profile_version"]
    else:
        raise ContinuityError("RECOVERY_DISPATCH_ADAPTER_REQUIRED", "The original Origin source adapter is required")
    if not binding or binding.actor != original["actor_id"] or binding.credential_digest != receipt["original_credential_digest"]:
        raise PermissionError("The exact original Origin credential changed")
    model_credentials.recheck(tx, binding)
    profile = row(tx.query_one("SELECT MODEL_ID FROM CX_LLM_PROVIDER_PROFILES WHERE PROFILE_ID=:profile", {"profile": profile_id}))
    if (receipt["profile_id"] != profile_id or int(receipt["profile_version"]) != int(profile_version)
            or not profile or receipt["model_id"] != profile["model_id"]):
        raise PermissionError("The original Origin model Profile changed")
