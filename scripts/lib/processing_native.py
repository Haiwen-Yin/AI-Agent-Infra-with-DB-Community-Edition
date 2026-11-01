"""Trusted native Worker lifecycle mapped to real Task processing attempts.

The native queue remains authoritative. NMA provider identities are immutable
children of real Task attempts; they never stand in for Task attempt IDs.
"""
from . import connection, identity_api, task_continuity as tasks, processing_recovery as recovery
from .agent_extension_contracts import digest, row
from .continuity_state import ContinuityConflict, ContinuityError

INTERNAL_ANCHOR = "CX_NATIVE_RUNTIME_ANCHOR"
ANCHOR = dict(security_domain_id=INTERNAL_ANCHOR, domain_name="Native runtime accounting anchor",
    classification="INTERNAL", purpose="Internal accounting only; no membership or collaboration authorization",
    status="INTERNAL_ANCHOR")


def reserved_domain(domain_id):
    return str(domain_id or "").strip().upper() == INTERNAL_ANCHOR


def is_projection(agent_id, *, transaction=None):
    """Typed metadata projections never constitute external Agent identities."""
    if not recovery.schema_enabled():
        return False
    query = transaction.query_one if transaction is not None else connection.execute_query_one
    return bool(query("SELECT AGENT_ID FROM CX_PROCESSING_NATIVE_AGENTS WHERE AGENT_ID=:agent", {"agent": agent_id}))


def require_external_identity(agent_id, *, transaction=None):
    if is_projection(agent_id, transaction=transaction):
        raise PermissionError("A native Task accounting projection cannot enroll or authenticate as an external Agent")


def _check_projection(tx, agent_id):
    typed = row(tx.query_one("SELECT * FROM CX_PROCESSING_NATIVE_AGENTS WHERE AGENT_ID=:agent", {"agent": agent_id}))
    if typed:
        registry = row(tx.query_one("SELECT AGENT_ID,AGENT_NAME,STATUS,AGENT_ROLE FROM AGENT_REGISTRY WHERE AGENT_ID=:agent", {"agent": agent_id}))
        if not registry or registry["status"] != "DORMANT" or typed["native_agent_id"] != agent_id or typed["registry_digest"] != digest(registry):
            raise ContinuityConflict("NATIVE_PROJECTION_INVALID", "The inert native accounting projection changed")


def _root(tx, execution_id):
    return row(tx.query_one("SELECT * FROM CX_TASK_CONTINUITY_LINKS WHERE LINK_KIND='RUNTIME' AND LINK_ID=:execution",
        {"execution": execution_id}))


def _execution(tx, execution_id):
    value = row(tx.query_one("SELECT * FROM CX_RUNTIME_EXECUTIONS WHERE EXECUTION_ID=:execution FOR UPDATE", {"execution": execution_id}))
    if not value:
        raise PermissionError("The original native execution is unavailable")
    return value


def _anchor(tx):
    value = row(tx.query_one("SELECT SECURITY_DOMAIN_ID,DOMAIN_NAME,CLASSIFICATION,PURPOSE,STATUS FROM CX_SECURITY_DOMAINS "
        "WHERE SECURITY_DOMAIN_ID=:domain_id FOR UPDATE", {"domain_id": INTERNAL_ANCHOR}))
    typed = row(tx.query_one("SELECT * FROM CX_PROCESSING_NATIVE_ANCHORS WHERE SECURITY_DOMAIN_ID=:domain_id", {"domain_id": INTERNAL_ANCHOR}))
    if value or typed:
        if value != ANCHOR or not typed or typed["anchor_kind"] != "UNSCOPED_RUNTIME" or typed["domain_digest"] != digest(ANCHOR):
            raise ContinuityConflict("NATIVE_ANCHOR_INVALID", "The typed internal accounting anchor changed")
    else:
        tx.execute("INSERT INTO CX_SECURITY_DOMAINS(SECURITY_DOMAIN_ID,DOMAIN_NAME,CLASSIFICATION,PURPOSE,STATUS) "
            "VALUES(:security_domain_id,:domain_name,:classification,:purpose,:status)", ANCHOR)
        tx.execute("INSERT INTO CX_PROCESSING_NATIVE_ANCHORS(SECURITY_DOMAIN_ID,ANCHOR_KIND,DOMAIN_DIGEST) "
            "VALUES(:domain_id,'UNSCOPED_RUNTIME',:fingerprint)", {"domain_id": INTERNAL_ANCHOR, "fingerprint": digest(ANCHOR)})
    if (tx.query_one("SELECT PRINCIPAL_ID FROM CX_DOMAIN_MEMBERS WHERE SECURITY_DOMAIN_ID=:domain_id", {"domain_id": INTERNAL_ANCHOR})
            or tx.query_one("SELECT CHANNEL_ID FROM CX_CHANNELS WHERE SECURITY_DOMAIN_ID=:domain_id", {"domain_id": INTERNAL_ANCHOR})):
        raise ContinuityConflict("NATIVE_ANCHOR_INVALID", "An accounting anchor cannot contain members or Channels")
    return INTERNAL_ANCHOR


def bind_execution(tx, actor, execution, payload):
    from . import native_runtime, native_agent_api
    execution_id = execution["execution_id"]
    revision = native_runtime._runtime_execution_digest(execution, payload)
    existing = _root(tx, execution_id)
    if existing:
        if existing["actor_id"] != actor or existing["request_digest"] != revision or existing["input_digest"] != native_agent_api._digest(payload):
            raise ContinuityConflict("STALE_TARGET", "The original native processing binding cannot change")
        return existing
    context = row(tx.query_one("SELECT SECURITY_DOMAIN_ID FROM CX_RUNTIME_CONTEXT_BINDINGS WHERE EXECUTION_ID=:execution", {"execution": execution_id}))
    dispatch = native_runtime._channel_dispatch(payload)
    if context:
        domain = context["security_domain_id"]
    elif isinstance(payload.get("framework_dispatch"), dict):
        from . import framework_execution
        framework = framework_execution.binding(execution_id, tx=tx) or {}
        domain = framework.get("security_domain_id")
    elif dispatch:
        channel = row(tx.query_one("SELECT SECURITY_DOMAIN_ID FROM CX_CHANNELS WHERE CHANNEL_ID=:channel_id", {"channel_id": dispatch["channel_id"]}))
        domain = channel.get("security_domain_id")
    else:
        domain = _anchor(tx)
    if not domain:
        raise ContinuityError("NATIVE_ANCHOR_REQUIRED", "The original execution anchor is unavailable")
    registry = row(tx.query_one("SELECT AGENT_ID,AGENT_NAME,STATUS,AGENT_ROLE FROM AGENT_REGISTRY WHERE AGENT_ID=:agent", {"agent": execution["agent_id"]}))
    typed_registry = row(tx.query_one("SELECT * FROM CX_PROCESSING_NATIVE_AGENTS WHERE AGENT_ID=:agent", {"agent": execution["agent_id"]}))
    if typed_registry and (not registry or typed_registry["registry_digest"] != digest(registry)
            or registry["status"] != "DORMANT" or typed_registry["native_agent_id"] != execution["agent_id"]):
        raise ContinuityConflict("NATIVE_PROJECTION_INVALID", "The inert native accounting projection changed")
    if not registry:
        projection = dict(agent_id=execution["agent_id"], agent_name="Native Task accounting projection", status="DORMANT", agent_role="WORKER")
        tx.execute("INSERT INTO AGENT_REGISTRY(AGENT_ID,AGENT_NAME,STATUS,AGENT_ROLE) VALUES(:agent_id,:agent_name,:status,:agent_role)", projection)
        tx.execute("INSERT INTO CX_PROCESSING_NATIVE_AGENTS(AGENT_ID,NATIVE_AGENT_ID,REGISTRY_DIGEST) VALUES(:agent,:native,:fingerprint)",
            {"agent": execution["agent_id"], "native": execution["agent_id"], "fingerprint": digest(projection)})
    task_id = tasks.ensure_task_root(tx, actor, preferred_agent_id=execution["agent_id"], goal="Native execution " + execution_id)
    linked = tasks.link_protocol_task(tx, actor=actor, security_domain_id=domain, link_kind="RUNTIME", link_id=execution_id,
        canonical_task_id=task_id, idempotency_key="native:" + execution_id, request_digest=revision,
        input_digest=native_agent_api._digest(payload), effect_class="CONSEQUENTIAL", reason="Original native execution accounting")
    target = recovery.ExactTarget(continuity_id=linked["continuity_id"], target_kind="RUNTIME", target_id=execution_id,
        target_revision=revision, input_digest=native_agent_api._digest(payload), business_key=execution_id)
    recovery.bind_server_policy(tx, actor=actor, target=target, authority=recovery._attempt_authority)
    return linked


def authorize_target(tx, actor, target, operation):
    from . import native_runtime, native_agent_api, model_credentials
    execution = _execution(tx, target.target_id)
    base = _root(tx, target.target_id)
    if not base:
        raise PermissionError("The original native Task binding is unavailable")
    _check_projection(tx, execution["agent_id"])
    if reserved_domain(base["security_domain_id"]):
        _anchor(tx)
    payload = native_runtime._parse(execution.get("input_json"), {})
    if (target.target_revision != native_runtime._runtime_execution_digest(execution, payload)
            or target.input_digest != native_agent_api._digest(payload) or base["request_digest"] != target.target_revision):
        raise ContinuityConflict("STALE_TARGET", "The original native execution or input changed")
    # The internal anchor never grants a permission and does not require an
    # unrelated Task PRIMARY_OWNER role from a delegated native requester.
    native_runtime.get_execution(actor, target.target_id, transaction=tx)
    if actor != base["actor_id"]:
        native_runtime.get_execution(base["actor_id"], target.target_id, transaction=tx)
    receipt, binding = native_runtime._runtime_model_receipt(target.target_id, tx=tx)
    if operation != "READ" and not binding:
        raise ContinuityError("RECOVERY_CREDENTIAL_REQUIRED", "The original native credential is required")
    if binding:
        if (binding.actor != base["actor_id"] or receipt["execution_digest"] != target.target_revision
                or receipt["input_digest"] != target.input_digest
                or receipt.get("source_digest") != native_runtime._runtime_channel_source(tx, payload)):
            raise PermissionError("The original native credential or source changed")
        model_credentials.recheck(tx, binding)
        agent = row(tx.query_one("SELECT STATUS,LLM_PROFILE_ID,DEPLOYMENT_TARGET_ID FROM CX_NATIVE_AGENTS WHERE AGENT_ID=:agent", {"agent": execution["agent_id"]}))
        profile = row(tx.query_one("SELECT PROFILE_ID,VERSION,STATUS FROM CX_LLM_PROVIDER_PROFILES WHERE PROFILE_ID=:profile", {"profile": receipt.get("profile_id")}))
        deployed = row(tx.query_one("SELECT STATUS FROM CX_DEPLOYMENT_TARGETS WHERE TARGET_ID=:target", {"target": execution["target_id"]}))
        if (not agent or agent["status"] != "ACTIVE" or agent["llm_profile_id"] != receipt.get("profile_id")
                or agent["deployment_target_id"] != execution["target_id"] or not profile or profile["status"] != "ACTIVE"
                or int(profile["version"]) != int(receipt.get("profile_version") or 0) or not deployed or deployed["status"] != "ACTIVE"):
            raise PermissionError("The original native Agent, Profile revision or target is no longer current")
        dispatch = native_runtime._channel_dispatch(payload)
        if dispatch:
            for principal in (base["actor_id"], execution["agent_id"]):
                identity_api._assert_channel_member(principal, dispatch["channel_id"], "channels.write", transaction=tx)
                if dispatch.get("thread_id"):
                    identity_api._assert_thread_member(principal, dispatch["thread_id"], "channels.write", transaction=tx)
            if dispatch.get("kind") != "BUSINESS_MENTION":
                from . import admin_management
                if identity_api.effective_access(base["actor_id"], "platform.manage").get("decision") != "ALLOW" or not tx.query_one(
                        "SELECT MEMBER_ID FROM CX_ADMIN_AGENT_MEMBERS WHERE GROUP_ID=:group_id AND AGENT_ID=:agent AND STATUS='ACTIVE' AND VOTING_ENABLED='Y'",
                        {"group_id": admin_management.ADMIN_GROUP_ID, "agent": execution["agent_id"]}):
                    raise PermissionError("The original management Agent admission changed")
    if operation != "READ" and identity_api.effective_access(actor, "agents.operate").get("decision") != "ALLOW":
        raise PermissionError("Native recovery permission denied")


def _current_chain(tx, execution_id):
    receipts = [row(value) for value in tx.query("SELECT r.SUCCESSOR_CONTINUITY_ID FROM CX_PROCESSING_RECOVERIES r "
        "JOIN CX_PROCESSING_BLOCKS b ON b.BLOCK_ID=r.BLOCK_ID JOIN CX_PROCESSING_RECOVERY_STATES s ON s.RECOVERY_ID=r.RECOVERY_ID "
        "JOIN CX_TASK_CONTINUITY_LINKS c ON c.CONTINUITY_ID=r.SUCCESSOR_CONTINUITY_ID "
        "WHERE b.TARGET_KIND='RUNTIME' AND b.TARGET_ID=:execution AND s.STATUS IN ('QUEUED','DISPATCHED') AND c.STATUS IN ('PENDING','RUNNING')",
        {"execution": execution_id})]
    if len(receipts) > 1:
        raise ContinuityConflict("RECOVERY_IN_PROGRESS", "The native execution has ambiguous active recovery")
    return recovery._link(tx, receipts[0]["successor_continuity_id"]) if receipts else _root(tx, execution_id)


def claim_recovery_gate(tx, continuity_id, receipt):
    state = row(tx.query_one("SELECT STATUS FROM CX_PROCESSING_RECOVERY_STATES WHERE RECOVERY_ID=:recovery", {"recovery": receipt["recovery_id"]}))
    frozen = row(tx.query_one("SELECT TARGET_ID FROM CX_PROCESSING_TARGETS WHERE CONTINUITY_ID=:chain", {"chain": continuity_id}))
    execution = _execution(tx, frozen["target_id"])
    if state.get("status") not in {"QUEUED", "DISPATCHED"} or execution["status"] not in {"PENDING", "CLAIMED"}:
        raise ContinuityConflict("RECOVERY_NOT_DISPATCHED", "The exact native retry has not been dispatched")


def claim(tx, execution):
    chain = _current_chain(tx, execution["execution_id"])
    if not chain:
        raise ContinuityError("NATIVE_PROCESSING_REQUIRED", "A native execution requires its original Task binding")
    _check_projection(tx, execution["agent_id"])
    if reserved_domain(chain["security_domain_id"]):
        _anchor(tx)
    frozen = row(tx.query_one("SELECT * FROM CX_PROCESSING_TARGETS WHERE CONTINUITY_ID=:chain", {"chain": chain["continuity_id"]}))
    target = recovery._target(frozen)
    from . import native_runtime
    if native_runtime._runtime_execution_digest(execution, native_runtime._parse(execution.get("input_json"), {})) != target.target_revision:
        raise ContinuityConflict("STALE_TARGET", "The native execution changed before Worker claim")
    # Native TIMESTAMP columns retain the database session's wall time. The
    # selected adapter projects this deadline to UTC without reinterpreting
    # historical native leases or changing the database session timezone.
    until = tasks._utc_naive(execution["lease_expires_at_utc"])
    if until is None:
        raise ContinuityError("INVALID_LEASE", "The native UTC lease deadline is unavailable")
    attempt = tasks.claim_attempt(tx, continuity_id=chain["continuity_id"], worker_id=execution["worker_id"],
        business_key=target.business_key, request_digest=chain["request_digest"], lease_expires_at=until)
    if not attempt.get("attempt_id"):
        raise ContinuityConflict("UNKNOWN_SEND", "The original native attempt requires reconciliation")
    params = dict(execution=execution["execution_id"], fence=int(execution["fencing_token"]), chain=chain["continuity_id"],
        attempt=attempt["attempt_id"], worker=execution["worker_id"], node=execution["node_id"])
    tx.execute("INSERT INTO CX_PROCESSING_NATIVE_ATTEMPTS(EXECUTION_ID,NATIVE_FENCING_TOKEN,CONTINUITY_ID,TASK_ATTEMPT_ID,WORKER_ID,NODE_ID) "
        "VALUES(:execution,:fence,:chain,:attempt,:worker,:node)", params)
    return attempt


def _attempt(tx, execution):
    mapped = row(tx.query_one("SELECT * FROM CX_PROCESSING_NATIVE_ATTEMPTS WHERE EXECUTION_ID=:execution AND NATIVE_FENCING_TOKEN=:fence",
        {"execution": execution["execution_id"], "fence": int(execution["fencing_token"])}))
    if not mapped or mapped["worker_id"] != execution["worker_id"] or mapped["node_id"] != execution["node_id"]:
        raise ContinuityConflict("FENCING_MISMATCH", "The original native-to-Task attempt mapping is unavailable")
    return mapped


def begin_call(tx, execution, source_attempt_id, source_kind, provider_no, messages):
    mapped = _attempt(tx, execution)
    frozen = row(tx.query_one("SELECT * FROM CX_PROCESSING_TARGETS WHERE CONTINUITY_ID=:chain", {"chain": mapped["continuity_id"]}))
    target = recovery._target(frozen).model_copy(update={"attempt_id": mapped["task_attempt_id"]})
    expected = "NMA_" + digest([execution["execution_id"], int(execution["fencing_token"]), provider_no])
    if source_attempt_id != expected or source_kind not in {"NATIVE", "CHANNEL"}:
        raise ContinuityConflict("NATIVE_PROVIDER_BINDING", "The provider event differs from its real native attempt")
    fingerprint = digest(messages)
    prior = row(tx.query_one("SELECT * FROM CX_PROCESSING_NATIVE_CALLS WHERE SOURCE_ATTEMPT_ID=:source", {"source": source_attempt_id}))
    if prior and (prior["task_attempt_id"] != mapped["task_attempt_id"] or prior["source_kind"] != source_kind
            or int(prior["provider_no"]) != provider_no or prior["input_digest"] != fingerprint):
        raise ContinuityConflict("IDEMPOTENCY_CONFLICT", "The original native Provider event cannot change")
    action = recovery.record_action(tx, actor=recovery._link(tx, target.continuity_id)["actor_id"], target=target,
        action_key="native-call:" + source_attempt_id, action_kind="MODEL_REQUEST", tool_name="native.model",
        arguments={"input_digest": fingerprint}, request_count=1, step_count=0, authority=recovery._attempt_authority)
    if not prior:
        tx.execute("INSERT INTO CX_PROCESSING_NATIVE_CALLS(SOURCE_ATTEMPT_ID,TASK_ATTEMPT_ID,PROVIDER_NO,SOURCE_KIND,INPUT_DIGEST) "
            "VALUES(:source,:attempt,:provider_no,:kind,:fingerprint)", dict(source=source_attempt_id, attempt=mapped["task_attempt_id"],
            provider_no=provider_no, kind=source_kind, fingerprint=fingerprint))
    return not bool(action["stop"])


def dispatch_gate(tx, execution, source_attempt_id, admission):
    mapped = _attempt(tx, execution)
    call = row(tx.query_one("SELECT * FROM CX_PROCESSING_NATIVE_CALLS WHERE SOURCE_ATTEMPT_ID=:source AND TASK_ATTEMPT_ID=:attempt",
        {"source": source_attempt_id, "attempt": mapped["task_attempt_id"]}))
    if (not call or admission["source_id"] != execution["execution_id"] or admission["source_attempt_id"] != source_attempt_id
            or admission["source_kind"] != call["source_kind"] or admission.get("status", "RESERVED") != "RESERVED"
            or admission["actor_id"] != recovery._link(tx, mapped["continuity_id"])["actor_id"]):
        raise PermissionError("The native Provider admission differs from its original Task attempt")
    if not admission.get("admission_id"):
        # Remote prepare/final-authorization checks have no local admission.
        # The immutable Origin receipt records its final dispatch separately.
        return
    tx.execute("UPDATE CX_PROCESSING_RECOVERY_STATES SET STATUS='DISPATCHED',ADMISSION_ID=:admission,VERSION=VERSION+1 "
        "WHERE STATUS='QUEUED' AND RECOVERY_ID IN (SELECT RECOVERY_ID FROM CX_PROCESSING_RECOVERIES WHERE SUCCESSOR_CONTINUITY_ID=:chain)",
        {"admission": admission["admission_id"], "chain": mapped["continuity_id"]})


def authorize_origin_receipt(tx, actor, receipt):
    """Trusted callback for explicit exact remote-lifecycle reconciliation."""
    from . import native_runtime
    mapped = row(tx.query_one("SELECT n.*,c.SOURCE_KIND FROM CX_PROCESSING_NATIVE_CALLS c JOIN CX_PROCESSING_NATIVE_ATTEMPTS n "
        "ON n.TASK_ATTEMPT_ID=c.TASK_ATTEMPT_ID WHERE c.SOURCE_ATTEMPT_ID=:source AND n.EXECUTION_ID=:execution",
        {"source": receipt["source_attempt_id"], "execution": receipt["source_id"]}))
    if not mapped or mapped["source_kind"] != receipt["source_kind"]:
        raise PermissionError("The Origin receipt differs from its exact native provider event")
    frozen = row(tx.query_one("SELECT * FROM CX_PROCESSING_TARGETS WHERE CONTINUITY_ID=:chain", {"chain": mapped["continuity_id"]}))
    target = recovery._target(frozen).model_copy(update={"attempt_id": mapped["task_attempt_id"]})
    authorize_target(tx, actor, target, "RECONCILE")
    original = recovery._link(tx, mapped["continuity_id"])
    credential, _ = native_runtime._runtime_model_receipt(receipt["source_id"], tx=tx)
    item = _execution(tx, receipt["source_id"])
    profile = row(tx.query_one("SELECT MODEL_ID FROM CX_LLM_PROVIDER_PROFILES WHERE PROFILE_ID=:profile", {"profile": receipt["profile_id"]}))
    if (not credential or receipt["actor_id"] != original["actor_id"]
            or receipt["original_credential_digest"] != credential["credential_digest"]
            or receipt["profile_id"] != credential["profile_id"] or int(receipt["profile_version"]) != int(credential["profile_version"])
            or not profile or receipt["model_id"] != profile["model_id"] or receipt["worker_key"] != mapped["worker_id"]
            or int(receipt["origin_fencing_token"]) != int(mapped["native_fencing_token"])
            or int(item["fencing_token"]) not in {int(mapped["native_fencing_token"]), int(mapped["native_fencing_token"]) + 1}
            or item["status"] not in {"UNOBSERVED", "FAILED", "CANCELLED"}):
        raise PermissionError("The exact original native credential, Profile or Worker fence changed")


def context_retry(tx, execution):
    """An explicit Task successor may reread the frozen original context.

    Preserve the historical one-use context receipt. The successor's native
    mapping and Provider event record this separately authorized input attempt.
    """
    mapped = _attempt(tx, execution)
    receipt = row(tx.query_one("SELECT r.*,s.STATUS AS RECOVERY_STATUS FROM CX_PROCESSING_RECOVERIES r "
        "JOIN CX_PROCESSING_RECOVERY_STATES s ON s.RECOVERY_ID=r.RECOVERY_ID WHERE r.SUCCESSOR_CONTINUITY_ID=:chain",
        {"chain": mapped["continuity_id"]}))
    if not receipt:
        return False
    block = row(tx.query_one("SELECT * FROM CX_PROCESSING_BLOCKS WHERE BLOCK_ID=:block", {"block": receipt["block_id"]}))
    stopped = row(tx.query_one("SELECT STATUS FROM CX_TASK_CONTINUITY_ATTEMPTS WHERE ATTEMPT_ID=:attempt", {"attempt": block["attempt_id"]}))
    if (receipt["recovery_status"] not in {"QUEUED", "DISPATCHED"} or block["target_id"] != execution["execution_id"]
            or stopped.get("status") not in {"FAILED", "CANCELLED"}):
        raise ContinuityConflict("UNKNOWN_SEND", "The exact original context attempt must be stopped before its explicit retry")
    return True


def observe_call(tx, execution, source_attempt_id):
    mapped = _attempt(tx, execution)
    call = row(tx.query_one("SELECT * FROM CX_PROCESSING_NATIVE_CALLS WHERE SOURCE_ATTEMPT_ID=:source AND TASK_ATTEMPT_ID=:attempt",
        {"source": source_attempt_id, "attempt": mapped["task_attempt_id"]}))
    if not call:
        raise ContinuityConflict("NATIVE_PROVIDER_BINDING", "The original provider-to-Task mapping is unavailable")
    observations = [row(value) for value in tx.query("SELECT a.ADMISSION_ID,o.TOTAL_TOKENS FROM CX_MODEL_ADMISSIONS a "
        "JOIN CX_MODEL_RUNTIME_OBSERVATIONS o ON o.ADMISSION_ID=a.ADMISSION_ID WHERE a.ACTOR_ID=:actor AND a.SOURCE_KIND=:kind "
        "AND a.SOURCE_ID=:execution AND a.SOURCE_ATTEMPT_ID=:source", dict(actor=recovery._link(tx, mapped["continuity_id"])["actor_id"],
        kind=call["source_kind"], execution=execution["execution_id"], source=source_attempt_id))]
    remote = [row(value) for value in tx.query("SELECT r.ORIGIN_RECEIPT_ID AS ADMISSION_ID,o.TOTAL_TOKENS FROM CX_MODEL_ORIGIN_RECEIPTS r "
        "JOIN CX_MODEL_ORIGIN_OBSERVATIONS o ON o.ORIGIN_RECEIPT_ID=r.ORIGIN_RECEIPT_ID WHERE r.ACTOR_ID=:actor AND r.SOURCE_KIND=:kind "
        "AND r.SOURCE_ID=:execution AND r.SOURCE_ATTEMPT_ID=:source AND o.REQUEST_COMPLETE='Y' AND o.RESULT_STATE IN ('COMPLETED','REJECTED')",
        dict(actor=recovery._link(tx, mapped["continuity_id"])["actor_id"], kind=call["source_kind"], execution=execution["execution_id"], source=source_attempt_id))]
    observations.extend(remote)
    if len(observations) > 1:
        raise ContinuityConflict("PROCESSING_USAGE_BOUND", "The native provider event has ambiguous observations")
    if not observations:
        return
    frozen = row(tx.query_one("SELECT * FROM CX_PROCESSING_TARGETS WHERE CONTINUITY_ID=:chain", {"chain": mapped["continuity_id"]}))
    recovery.record_action(tx, actor=recovery._link(tx, mapped["continuity_id"])["actor_id"],
        target=recovery._target(frozen).model_copy(update={"attempt_id": mapped["task_attempt_id"]}),
        action_key="native-usage:" + source_attempt_id, action_kind="MODEL_REQUEST", tool_name="native.usage",
        arguments={"admission_id": observations[0]["admission_id"]}, request_count=0, step_count=0,
        token_count=int(observations[0]["total_tokens"] or 0), authority=recovery._attempt_authority, _observed_completion=True)


def finish(tx, execution, status, error_code=None):
    mapped = _attempt(tx, execution)
    attempt = row(tx.query_one("SELECT * FROM CX_TASK_CONTINUITY_ATTEMPTS WHERE ATTEMPT_ID=:attempt", {"attempt": mapped["task_attempt_id"]}))
    if attempt["status"] != "SENDING":
        return
    outcome = "SUCCEEDED" if status == "COMPLETED" else status
    result = tasks.finish_attempt(tx, attempt_id=attempt["attempt_id"], worker_id=mapped["worker_id"],
        fencing_token=attempt["fencing_token"], status=outcome, request_digest=attempt["request_digest"], error_code=error_code)
    tx.execute("UPDATE CX_PROCESSING_RECOVERY_STATES SET STATUS=:state,VERSION=VERSION+1 WHERE RECOVERY_ID IN "
        "(SELECT RECOVERY_ID FROM CX_PROCESSING_RECOVERIES WHERE SUCCESSOR_CONTINUITY_ID=:chain)",
        {"state": "UNKNOWN" if result["status"] == "UNOBSERVED" else "COMPLETED", "chain": mapped["continuity_id"]})


def dispatch_recovery(tx, actor, recovery_id):
    receipt = row(tx.query_one("SELECT * FROM CX_PROCESSING_RECOVERIES WHERE RECOVERY_ID=:recovery FOR UPDATE", {"recovery": recovery_id}))
    block = row(tx.query_one("SELECT * FROM CX_PROCESSING_BLOCKS WHERE BLOCK_ID=:block", {"block": receipt["block_id"]}))
    target = recovery._target(block)
    authorize_target(tx, actor, target, "DISPATCH")
    state = row(tx.query_one("SELECT * FROM CX_PROCESSING_RECOVERY_STATES WHERE RECOVERY_ID=:recovery FOR UPDATE", {"recovery": recovery_id}))
    if state["status"] in {"QUEUED", "DISPATCHED", "COMPLETED", "UNKNOWN"}:
        return recovery._recovery_view(tx, receipt, replayed=True)
    execution = _execution(tx, target.target_id)
    if execution["status"] not in {"FAILED", "CANCELLED"}:
        raise ContinuityConflict("UNKNOWN_SEND", "The original native request must be terminal before dispatch")
    if tx.query_one("SELECT ADMISSION_ID FROM CX_MODEL_ADMISSIONS WHERE SOURCE_ID=:execution AND STATUS IN ('DISPATCHING','UNKNOWN')", {"execution": target.target_id}):
        raise ContinuityConflict("UNKNOWN_SEND", "The original native Provider request remains occupied")
    if any(value["status"] in {"UNKNOWN", "DISPATCHING"} and not value.get("resolution") for value in recovery.origin_evidence(tx, target)):
        raise ContinuityConflict("UNKNOWN_SEND", "The original registered coordinator request remains unresolved")
    tx.execute("UPDATE CX_RUNTIME_EXECUTIONS SET STATUS='PENDING',WORKER_ID=NULL,NODE_ID=NULL,LEASE_EXPIRES_AT=NULL,"
        "OUTPUT_JSON=NULL,FAILURE_REASON=NULL,COMPLETED_AT=NULL,UPDATED_AT=CURRENT_TIMESTAMP WHERE EXECUTION_ID=:execution",
        {"execution": target.target_id})
    tx.execute("UPDATE CX_PROCESSING_RECOVERY_STATES SET STATUS='QUEUED',VERSION=VERSION+1 WHERE RECOVERY_ID=:recovery", {"recovery": recovery_id})
    identity_api._audit_tx(tx, actor, "PROCESSING_NATIVE_DISPATCH", "RUNTIME_EXECUTION", target.target_id, "ALLOW", "Exact original Worker retry")
    return recovery._recovery_view(tx, receipt)


def read_evidence(tx, target):
    item = _execution(tx, target.target_id)
    mapped = row(tx.query_one("SELECT * FROM CX_PROCESSING_NATIVE_ATTEMPTS WHERE TASK_ATTEMPT_ID=:attempt", {"attempt": target.attempt_id}))
    # A committed local success proves this exact local effect. A failed or
    # expired record alone cannot establish remote Provider termination.
    observations = [row(value) for value in tx.query("SELECT o.OBSERVATION_DIGEST,o.REQUEST_COMPLETE,o.RESULT_STATE FROM CX_PROCESSING_NATIVE_CALLS c "
        "JOIN CX_MODEL_ADMISSIONS a ON a.SOURCE_ATTEMPT_ID=c.SOURCE_ATTEMPT_ID AND a.SOURCE_KIND=c.SOURCE_KIND "
        "JOIN CX_MODEL_RUNTIME_OBSERVATIONS o ON o.ADMISSION_ID=a.ADMISSION_ID "
        "WHERE c.TASK_ATTEMPT_ID=:attempt AND a.SOURCE_ID=:execution AND a.ACTOR_ID=:actor", dict(attempt=target.attempt_id,
        execution=target.target_id, actor=recovery._link(tx, target.continuity_id)["actor_id"]))]
    outcome = "SUCCEEDED" if mapped and item["status"] == "COMPLETED" and int(item["fencing_token"]) == int(mapped["native_fencing_token"]) else "UNOBSERVED"
    remote = recovery.origin_evidence(tx, target)
    calls = tx.query("SELECT SOURCE_ATTEMPT_ID FROM CX_PROCESSING_NATIVE_CALLS WHERE TASK_ATTEMPT_ID=:attempt", {"attempt": target.attempt_id})
    settled = len(observations) + len(remote) == len(calls) and bool(calls)
    remote_stopped = all(value.get("resolution") or (value.get("observation") and value["observation"]["request_complete"] == "Y"
        and value["observation"]["result_state"] in {"COMPLETED", "REJECTED"}) for value in remote)
    if outcome == "UNOBSERVED" and settled and remote_stopped and all(value["request_complete"] == "Y" and value["result_state"] in {"COMPLETED", "REJECTED"} for value in observations):
        outcome = "FAILED"
    return recovery.ReconciliationEvidence("LOCAL_LIFECYCLE", digest(dict(target=target.model_dump(),
        native_status=item["status"], native_fence=item["fencing_token"], observations=observations, remote=remote)), outcome)


def reconcile_business(tx, target, evidence):
    """Settle only the original fenced native row after trusted Task resolution."""
    mapped = row(tx.query_one("SELECT * FROM CX_PROCESSING_NATIVE_ATTEMPTS WHERE TASK_ATTEMPT_ID=:attempt AND EXECUTION_ID=:execution",
        {"attempt": target.attempt_id, "execution": target.target_id}))
    item = _execution(tx, target.target_id)
    if not mapped:
        raise ContinuityConflict("FENCING_MISMATCH", "The exact native reconciliation mapping is unavailable")
    # Expiry increments the native fence once, permanently excluding the old
    # Worker. A newer claim can never be resolved by an older processing block.
    allowed_fences = {int(mapped["native_fencing_token"]), int(mapped["native_fencing_token"]) + 1}
    if item["status"] != "UNOBSERVED" or int(item["fencing_token"]) not in allowed_fences:
        raise ContinuityConflict("FENCING_MISMATCH", "The original native unknown lifecycle changed")
    if evidence.outcome == "SUCCEEDED":
        # A Human resolution of remote termination does not invent native
        # output or publish a Channel reply. The Task may record that decision.
        status = "COMPLETED"
    else:
        status = evidence.outcome
    tx.execute("UPDATE CX_RUNTIME_EXECUTIONS SET STATUS=:status,FAILURE_REASON=:reason,WORKER_ID=NULL,NODE_ID=NULL,"
        "LEASE_EXPIRES_AT=NULL,FENCING_TOKEN=FENCING_TOKEN+1,COMPLETED_AT=CURRENT_TIMESTAMP,UPDATED_AT=CURRENT_TIMESTAMP "
        "WHERE EXECUTION_ID=:execution AND STATUS='UNOBSERVED' AND FENCING_TOKEN=:fence",
        {"status": status, "reason": "PROCESSING_" + evidence.outcome, "execution": target.target_id, "fence": item["fencing_token"]})
