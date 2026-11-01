"""Exact native-job recovery, using existing workers and the original Task.

Queueing never sends. The existing sender's capacity callback records dispatch;
neither a Human recovery decision nor a local failure proves remote completion.
"""
from __future__ import annotations

from . import connection, identity_api, model_credentials, processing_recovery as recovery
from .agent_extension_contracts import digest, row
from .continuity_state import ContinuityConflict, ContinuityError

MUTABLE = {"CX_ANSWER_QUALITY_CREDENTIALS": set(), "CX_ANSWER_QUALITY_RETRY_INPUTS": set(), "CX_AGENT_SYNC_CREDENTIALS": set()}


def schema_statements(database):
    if database not in {"pg", "postgresql", "oracle", "yashandb"}:
        raise ValueError("Unsupported database")
    body = "TEXT" if database in {"pg", "postgresql"} else "CLOB"
    return [
        "CREATE TABLE CX_ANSWER_QUALITY_CREDENTIALS (RUN_ID VARCHAR(128) PRIMARY KEY REFERENCES CX_ANSWER_QUALITY_RUNS(RUN_ID), "
        "ACTOR_ID VARCHAR(128) NOT NULL REFERENCES CX_PRINCIPALS(PRINCIPAL_ID), "
        "CREDENTIAL_KIND VARCHAR(8) NOT NULL CHECK(CREDENTIAL_KIND IN ('WEB','AGENT')), CREDENTIAL_DIGEST VARCHAR(64) NOT NULL, "
        "REQUIRED_SCOPE VARCHAR(128), INSTANCE_ID VARCHAR(128), FENCING_TOKEN INTEGER DEFAULT 0 NOT NULL CHECK(FENCING_TOKEN>=0), "
        "AUTH_METHOD VARCHAR(64), PERMISSION_VERSION INTEGER DEFAULT 0 NOT NULL CHECK(PERMISSION_VERSION>=0), "
        "MFA_LEVEL VARCHAR(32), NODE_ID VARCHAR(128), SESSION_CREATED_AT VARCHAR(64), "
        "CREATED_AT TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL, "
        "CHECK((CREDENTIAL_KIND='WEB' AND AUTH_METHOD IS NOT NULL AND PERMISSION_VERSION>0 AND SESSION_CREATED_AT IS NOT NULL) "
        "OR (CREDENTIAL_KIND='AGENT' AND INSTANCE_ID IS NOT NULL AND FENCING_TOKEN>0)))",
        "CREATE TABLE CX_ANSWER_QUALITY_RETRY_INPUTS (ATTEMPT_ID VARCHAR(128) PRIMARY KEY REFERENCES CX_TASK_CONTINUITY_ATTEMPTS(ATTEMPT_ID), "
        "RUN_ID VARCHAR(128) NOT NULL REFERENCES CX_ANSWER_QUALITY_RUNS(RUN_ID), "
        "CONTINUITY_ID VARCHAR(128) NOT NULL REFERENCES CX_TASK_CONTINUITY_LINKS(CONTINUITY_ID), "
        f"INPUT_CIPHER {body} NOT NULL, INPUT_DIGEST VARCHAR(64) NOT NULL, CREATED_AT TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL)",
        "CREATE TABLE CX_AGENT_SYNC_CREDENTIALS (JOB_ID VARCHAR(128) PRIMARY KEY REFERENCES CX_AGENT_SYNC_JOBS(JOB_ID), "
        "CREDENTIAL_REF VARCHAR(100), CREDENTIAL_DIGEST VARCHAR(64) NOT NULL, CREATED_AT TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL)",
    ]


def evaluation_credential(tx, actor, run_id, captured=None, *, required=False):
    """Persist once; successors always use the immutable original identity."""
    if not recovery.schema_enabled():
        return captured
    original = row(tx.query_one("SELECT * FROM CX_ANSWER_QUALITY_CREDENTIALS WHERE RUN_ID=:run", {"run": run_id}))
    if original:
        binding = model_credentials.binding_from_record(original)
        if binding.actor != actor:
            raise PermissionError("The original evaluation identity changed")
        model_credentials.recheck(tx, binding)
        return binding
    if captured is None:
        if required:
            raise ContinuityError("RECOVERY_CREDENTIAL_REQUIRED", "The original evaluation credential is required")
        return None
    model_credentials.recheck(tx, captured)
    if captured.actor != actor:
        raise PermissionError("The evaluation credential belongs to another principal")
    params = model_credentials.binding_record(captured) | {"run_id": run_id}
    names = tuple(params)
    tx.execute("INSERT INTO CX_ANSWER_QUALITY_CREDENTIALS(" + ",".join(name.upper() for name in names) + ") VALUES(" +
               ",".join(":" + name for name in names) + ")", params)
    return captured


def _original(tx, link):
    """Follow only typed immutable lineage, with a bounded cycle check."""
    seen = set()
    while True:
        identity = link["continuity_id"]
        if identity in seen or len(seen) >= 32:
            raise ContinuityConflict("RECOVERY_LINEAGE_INVALID", "The original processing lineage is invalid")
        seen.add(identity)
        chain = row(tx.query_one("SELECT ORIGINAL_CONTINUITY_ID FROM CX_PROCESSING_CHAINS WHERE CONTINUITY_ID=:chain", {"chain": identity}))
        if not chain or chain["original_continuity_id"] == identity:
            return link
        link = recovery._link(tx, chain["original_continuity_id"])


def source_credential(tx, job, configured, *, capture=False):
    """Freeze the original managed reference and secret digest, never its value."""
    if not recovery.schema_enabled():
        return
    from . import agent_source_sync as sync
    reference = configured.get('credential_ref') or None
    fingerprint = digest({'reference': reference, 'headers': sync._credential(configured)})
    saved = row(tx.query_one('SELECT CREDENTIAL_REF,CREDENTIAL_DIGEST FROM CX_AGENT_SYNC_CREDENTIALS WHERE JOB_ID=:job', {'job': job['job_id']}))
    if saved:
        if saved.get('credential_ref') != reference or saved['credential_digest'] != fingerprint:
            raise PermissionError('The original synchronization credential changed')
        return
    if not capture or recovery._link(tx, job['continuity_id'])['link_id'].startswith('recovery:'):
        raise ContinuityError('RECOVERY_CREDENTIAL_REQUIRED', 'The original synchronization credential receipt is required')
    tx.execute('INSERT INTO CX_AGENT_SYNC_CREDENTIALS(JOB_ID,CREDENTIAL_REF,CREDENTIAL_DIGEST) VALUES(:job,:reference,:digest)',
        {'job': job['job_id'], 'reference': reference, 'digest': fingerprint})


def _same_job(tx, current, original):
    link = recovery._link(tx, current)
    root = _original(tx, link)
    if (root["continuity_id"] != original["continuity_id"]
            or link["actor_id"] != original["actor_id"]
            or link["canonical_task_id"] != original["canonical_task_id"]
            or link["request_digest"] != original["request_digest"]
            or link["input_digest"] != original["input_digest"]):
        raise PermissionError("The native job no longer belongs to its original processing chain")


def _human_scope(tx, actor, original, *, write):
    from . import continuity_work as work
    from .continuity_execution_links import authorize
    if actor != original["actor_id"]:
        recovery._human(tx, actor)
    work._authorize(tx, actor, original["security_domain_id"], write=write)
    authorize(tx, actor, original["security_domain_id"], "TASK", original["canonical_task_id"])


def authorize_target(tx, actor, link, target, operation):
    """Current Human authority intersects original native principal authority."""
    original = _original(tx, link)
    source = original["link_id"]
    if (target.target_kind != "RUNTIME" or target.target_id != source
            or target.target_revision != original["request_digest"]):
        return False
    write = operation in {"RECOVER", "DISPATCH", "RECONCILE"}
    owner = original["actor_id"]
    _human_scope(tx, actor, original, write=write)
    if original["link_kind"] == "RUNTIME" and source.startswith("RJ_"):
        from . import continuity_retrospectives as retros
        job = row(tx.query_one("SELECT * FROM CX_RETROSPECTIVE_JOBS WHERE JOB_ID=:job", {"job": source}))
        if not job:
            raise PermissionError("The original retrospective is unavailable")
        _same_job(tx, job["continuity_id"], original)
        retros._authorize(tx, owner, job)
        retros._refs(tx, owner, job)
        if actor != owner:
            retros._refs(tx, actor, job)
        contract = retros._output_contract(tx, job)
        if write and contract.get("credential_binding") is None:
            raise ContinuityError("RECOVERY_CREDENTIAL_REQUIRED", "The original retrospective credential is required")
    elif original["link_kind"] == "RUNTIME" and source.startswith("SJ_"):
        from . import agent_source_sync as sync
        job, configured = sync._job(tx, owner, source, write=write)
        _same_job(tx, job["continuity_id"], original)
        sync._configuration(tx, configured)
        if write:
            source_credential(tx, job, configured)
        if actor != owner:
            sync._source(tx, actor, configured["source_id"], write=write)
        if operation in {"RECOVER", "DISPATCH"} and int(job["attempt_count"]) >= int(configured["max_attempts"]):
            raise ContinuityConflict("SYNC_CLOSED", "The original synchronization retry budget is exhausted")
    elif original["link_kind"] == "RUNTIME" and source.startswith("MTU_") and ":" in source:
        from . import governed_model_turns as turns
        turn_id, phase = source.rsplit(":", 1)
        if phase not in {"PROPOSAL", "FINAL"}:
            raise PermissionError("The original model stage is unavailable")
        stage = row(tx.query_one("SELECT * FROM CX_MODEL_TOOL_STAGES WHERE TURN_ID=:turn AND PHASE=:phase", {"turn": turn_id, "phase": phase}))
        if not stage:
            raise PermissionError("The original model stage is unavailable")
        _same_job(tx, stage["continuity_id"], original)
        root = turns._root(tx, turn_id, observer=actor)
        registered, tool = turns._authorize(tx, owner, root)
        if actor != owner:
            turns._authorize_read(tx, actor, root)
        if write and turns.tasks._utc_naive(root["deadline_at"]) <= turns.tasks._now():
            raise ContinuityConflict("TURN_EXPIRED", "The original model turn deadline expired")
        if write:
            profile = row(tx.query_one('SELECT PROFILE_ID,VERSION,MODEL_ID FROM CX_LLM_PROVIDER_PROFILES WHERE PROFILE_ID=:profile', {'profile': root['profile_id']}))
            schema = turns._parameters(registered)
            turns.contracts.require_contract(tx, profile, 'TOOL_PROPOSAL', schema, root['probe_id'], root['parameter_digest'], tool_name=turns._tool_name(registered))
            if turns.contracts.schema_digest(schema, tool_name=turns._tool_name(registered)) != root['schema_digest']:
                raise PermissionError('The frozen original model tool schema changed')
        if phase == "FINAL" and write:
            body, _, _ = turns._tool_result(tx, owner, root, registered, tool)
            if body is None:
                raise ContinuityConflict("TURN_APPROVAL_REQUIRED", "The exact approved original tool result is required")
    elif original["link_kind"] == "DIAGNOSTIC" and source.startswith("AQR_"):
        from . import answer_quality as quality
        job = row(tx.query_one("SELECT * FROM CX_ANSWER_QUALITY_RUNS WHERE RUN_ID=:run", {"run": source}))
        if not job or job["actor_id"] != owner:
            raise PermissionError("The original evaluation is unavailable")
        _same_job(tx, job["continuity_id"], original)
        quality._authority(tx, owner, job)
        quality._inputs(tx, job)
        quality._sources(tx, owner, job)
        if actor != owner:
            quality._authority(tx, actor, job)
            quality._sources(tx, actor, job)
        if write:
            evaluation_credential(tx, owner, source, required=True)
    else:
        return False
    return True


def _receipt(tx, actor, recovery_id):
    receipt = row(tx.query_one("SELECT * FROM CX_PROCESSING_RECOVERIES WHERE RECOVERY_ID=:recovery FOR UPDATE", {"recovery": recovery_id}))
    if not receipt or receipt["actor_id"] != actor:
        raise PermissionError("Native processing recovery access denied")
    block = row(tx.query_one("SELECT * FROM CX_PROCESSING_BLOCKS WHERE BLOCK_ID=:block FOR UPDATE", {"block": receipt["block_id"]}))
    target = recovery._target(block)
    original = _original(tx, recovery._link(tx, target.continuity_id))
    successor = recovery._link(tx, receipt['successor_continuity_id'])
    operation = 'READ' if successor['status'] in {'SUCCEEDED', 'FAILED', 'CANCELLED', 'UNOBSERVED'} else 'DISPATCH'
    if not authorize_target(tx, actor, original, target, operation):
        raise ContinuityError("RECOVERY_DISPATCH_ADAPTER_REQUIRED", "The original native execution adapter is required")
    recovery._validate_target(tx, target)
    return receipt, target, original


def dispatch_recovery(tx, actor, recovery_id):
    """Commit an executable native retry; transport remains the original sender."""
    receipt, target, original = _receipt(tx, actor, recovery_id)
    state = row(tx.query_one("SELECT * FROM CX_PROCESSING_RECOVERY_STATES WHERE RECOVERY_ID=:recovery FOR UPDATE", {"recovery": recovery_id}))
    if state["status"] in {"QUEUED", "DISPATCHED", "COMPLETED", "UNKNOWN"}:
        return recovery._recovery_view(tx, receipt, replayed=True)
    if state["status"] != "ACCEPTED" or state.get("admission_id"):
        raise ContinuityConflict("RECOVERY_ALREADY_DISPATCHED", "The original native retry cannot be replaced")
    stopped = recovery._link(tx, target.continuity_id, lock=True)
    if stopped["status"] not in {"FAILED", "CANCELLED", "WAITING"} or tx.query_one(
            "SELECT ATTEMPT_ID FROM CX_TASK_CONTINUITY_ATTEMPTS WHERE CONTINUITY_ID=:chain AND STATUS IN ('SENDING','UNOBSERVED')", {"chain": target.continuity_id}):
        raise ContinuityConflict("UNKNOWN_SEND", "The original native request requires a known stopped outcome")
    source, successor = original["link_id"], receipt["successor_continuity_id"]
    params = {"chain": successor, "source": source, "prior": target.continuity_id}
    if source.startswith("RJ_"):
        changed = tx.execute("UPDATE CX_RETROSPECTIVE_JOBS SET CONTINUITY_ID=:chain,STATUS='PENDING' WHERE JOB_ID=:source AND CONTINUITY_ID=:prior AND STATUS='FAILED' AND CANDIDATE_ID IS NULL", params)
    elif source.startswith("SJ_"):
        changed = tx.execute("UPDATE CX_AGENT_SYNC_JOBS SET CONTINUITY_ID=:chain,STATUS='PENDING' WHERE JOB_ID=:source AND CONTINUITY_ID=:prior AND STATUS IN ('FAILED','BLOCKED','PENDING')", params)
    elif source.startswith("MTU_"):
        turn_id, phase = source.rsplit(":", 1)
        root = row(tx.query_one("SELECT STATUS,ANSWER_DIGEST FROM CX_MODEL_TOOL_TURNS WHERE TURN_ID=:turn FOR UPDATE", {"turn": turn_id}))
        if root.get("answer_digest") or root["status"] not in {"FAILED", "UNOBSERVED"}:
            raise ContinuityConflict("TURN_STATE", "Only an exact stopped uncompleted model stage can resume")
        changed = tx.execute("UPDATE CX_MODEL_TOOL_STAGES SET CONTINUITY_ID=:chain,ATTEMPT_ID=NULL WHERE TURN_ID=:turn AND PHASE=:phase AND CONTINUITY_ID=:prior AND OUTPUT_DIGEST IS NULL", {"chain": successor, "turn": turn_id, "phase": phase, "prior": target.continuity_id})
        tx.execute("UPDATE CX_MODEL_TOOL_TURNS SET STATUS=:status WHERE TURN_ID=:turn", {"status": "PENDING" if phase == "PROPOSAL" else "TOOL_PENDING", "turn": turn_id})
    elif source.startswith("AQR_"):
        changed = tx.execute("UPDATE CX_ANSWER_QUALITY_RUNS SET CONTINUITY_ID=:chain,STATUS='PENDING',COMPLETED_AT=NULL WHERE RUN_ID=:source AND CONTINUITY_ID=:prior AND STATUS IN ('FAILED','UNOBSERVED') AND NOT EXISTS (SELECT 1 FROM CX_ANSWER_QUALITY_OUTPUTS WHERE RUN_ID=:source)", params)
    else:
        raise ContinuityError("RECOVERY_DISPATCH_ADAPTER_REQUIRED", "The original native execution adapter is required")
    if changed != 1:
        raise ContinuityConflict("RECOVERY_ORIGINAL_CHANGED", "The exact native job is completed or no longer stopped")
    tx.execute("UPDATE CX_PROCESSING_RECOVERY_STATES SET STATUS='QUEUED',VERSION=VERSION+1 WHERE RECOVERY_ID=:recovery", {"recovery": recovery_id})
    identity_api._audit_tx(tx, actor, "NATIVE_PROCESSING_RECOVERY_QUEUED", "PROCESSING_RECOVERY", recovery_id, "ALLOW", "Exact original native worker; no external send")
    return recovery._recovery_view(tx, receipt)


def claim_recovery_gate(tx, continuity_id, receipt):
    complete, target, original = _receipt(tx, row(tx.query_one("SELECT ACTOR_ID FROM CX_PROCESSING_RECOVERIES WHERE RECOVERY_ID=:recovery", {"recovery": receipt["recovery_id"]}))["actor_id"], receipt["recovery_id"])
    if complete["successor_continuity_id"] != continuity_id or receipt["status"] not in {"QUEUED", "DISPATCHED"}:
        raise ContinuityConflict("RECOVERY_QUEUED", "The native successor awaits explicit queue admission")
    if receipt.get("admission_id"):
        admission = row(tx.query_one("SELECT STATUS FROM CX_MODEL_ADMISSIONS WHERE ADMISSION_ID=:admission", {"admission": receipt["admission_id"]}))
        if admission.get("status") == "UNKNOWN":
            raise ContinuityConflict("UNKNOWN_SEND", "The original recovery model request is unknown")
    if original["link_id"].startswith("SJ_") and receipt["status"] == "QUEUED":
        tx.execute("UPDATE CX_PROCESSING_RECOVERY_STATES SET STATUS='DISPATCHED',VERSION=VERSION+1 WHERE RECOVERY_ID=:recovery", {"recovery": complete["recovery_id"]})


def dispatch_gate(tx, continuity_id, admission):
    """Run only in the original sender's capacity.begin_dispatch transaction."""
    if not recovery.schema_enabled():
        return
    receipt = row(tx.query_one("SELECT * FROM CX_PROCESSING_RECOVERIES WHERE SUCCESSOR_CONTINUITY_ID=:chain", {"chain": continuity_id}))
    if not receipt:
        return
    complete, target, original = _receipt(tx, receipt["actor_id"], receipt["recovery_id"])
    source = original["link_id"].rsplit(":", 1)[0] if original["link_id"].startswith("MTU_") else original["link_id"]
    attempt = row(tx.query_one("SELECT CONTINUITY_ID,STATUS FROM CX_TASK_CONTINUITY_ATTEMPTS WHERE ATTEMPT_ID=:attempt", {"attempt": admission["source_attempt_id"]}))
    state = row(tx.query_one("SELECT * FROM CX_PROCESSING_RECOVERY_STATES WHERE RECOVERY_ID=:recovery FOR UPDATE", {"recovery": receipt["recovery_id"]}))
    if (admission.get("status", "RESERVED") != "RESERVED" or admission["actor_id"] != original["actor_id"] or admission["source_id"] != source
            or attempt.get("continuity_id") != continuity_id or attempt.get("status") != "SENDING"
            or state["status"] != "QUEUED" or state.get("admission_id")):
        raise ContinuityConflict("RECOVERY_ALREADY_DISPATCHED", "One exact native attempt and current capacity reservation are required")
    if not admission.get("admission_id"):
        return
    tx.execute("UPDATE CX_PROCESSING_RECOVERY_STATES SET STATUS='DISPATCHED',ADMISSION_ID=:admission,VERSION=VERSION+1 WHERE RECOVERY_ID=:recovery", {"admission": admission["admission_id"], "recovery": receipt["recovery_id"]})


def account_source_read_failure(tx, job, attempt):
    """Retain a known read-only retry's step on its existing bounded policy."""
    if not recovery.schema_enabled():
        return
    frozen = row(tx.query_one("SELECT * FROM CX_PROCESSING_TARGETS WHERE CONTINUITY_ID=:chain", {"chain": job["continuity_id"]}))
    if not frozen:
        raise ContinuityError("PROCESSING_TARGET_REQUIRED", "The original source synchronization target is required")
    target = recovery._target(frozen).model_copy(update={"attempt_id": attempt["attempt_id"]})
    recovery.record_action(tx, actor=job["requested_by"], target=target, action_key="attempt:" + attempt["attempt_id"],
        action_kind="ITERATION", tool_name="task.attempt", arguments={"target_kind": target.target_kind,
            "target_id": target.target_id, "target_revision": target.target_revision, "input_digest": target.input_digest},
        request_count=0, step_count=1, token_count=0, authority=recovery._attempt_authority, _observed_completion=True)


def run_recovery(actor, recovery_id, *, worker_id="processing-runtime-worker"):
    """Trusted Worker entry after queue commit; restart retains the same lease."""
    def prepare(tx):
        receipt, target, original = _receipt(tx, actor, recovery_id)
        state = row(tx.query_one("SELECT STATUS FROM CX_PROCESSING_RECOVERY_STATES WHERE RECOVERY_ID=:recovery", {"recovery": recovery_id}))
        if state["status"] not in {"QUEUED", "DISPATCHED"}:
            return recovery._recovery_view(tx, receipt)
        return original["actor_id"], original["link_id"]
    prepared = connection.execute_transaction_callback(prepare)
    if isinstance(prepared, dict):
        return prepared
    owner, source = prepared
    if source.startswith("RJ_"):
        from .continuity_retrospectives import run_once
        return run_once(owner, source, worker_id)
    if source.startswith("SJ_"):
        from .agent_source_sync import run
        return run(owner, source)
    if source.startswith("MTU_"):
        from .governed_model_turns import run_once
        return run_once(owner, source.rsplit(":", 1)[0], worker_id)
    from .answer_quality import execute
    return execute(owner, source, worker_id=worker_id)


def read_evidence(tx, target):
    """Provider completion proves stop; business success needs its own receipt."""
    target = recovery.ExactTarget.model_validate(target)
    if not target.attempt_id:
        raise ContinuityError("RECONCILIATION_EVIDENCE_REQUIRED", "The exact original native attempt is required")
    link = recovery._link(tx, target.continuity_id)
    original = _original(tx, link)
    if not authorize_target(tx, original["actor_id"], original, target, "READ"):
        raise ContinuityError("RECONCILIATION_EVIDENCE_REQUIRED", "The original native reader is required")
    recovery._validate_target(tx, target)
    source = original["link_id"]
    model_source = source.rsplit(":", 1)[0] if source.startswith("MTU_") else source
    observations = [row(value) for value in tx.query("SELECT o.OBSERVATION_DIGEST,o.REQUEST_COMPLETE,o.RESULT_STATE,a.ADMISSION_ID FROM CX_MODEL_ADMISSIONS a JOIN CX_MODEL_RUNTIME_OBSERVATIONS o ON o.ADMISSION_ID=a.ADMISSION_ID WHERE a.SOURCE_ID=:source AND a.SOURCE_ATTEMPT_ID=:attempt AND a.ACTOR_ID=:actor", {"source": model_source, "attempt": target.attempt_id, "actor": original["actor_id"]})]
    remote = recovery.origin_evidence(tx, target)
    if len(observations) > 1:
        raise ContinuityError("RECONCILIATION_EVIDENCE_REQUIRED", "The exact native model attempt has ambiguous observations")
    attempt = row(tx.query_one("SELECT STATUS FROM CX_TASK_CONTINUITY_ATTEMPTS WHERE ATTEMPT_ID=:attempt", {"attempt": target.attempt_id}))
    # A committed native success and its successful real Task attempt are a
    # durable local result. A completed provider response alone proves only a
    # stopped generation, never accepted content or completed business effects.
    if attempt.get("status") == "SUCCEEDED":
        outcome = "SUCCEEDED"
    elif observations and observations[0]["request_complete"] == "Y" and observations[0]["result_state"] in {"COMPLETED", "REJECTED"}:
        outcome = "FAILED"
    elif remote and all(value.get("resolution") or (value.get("observation") and value["observation"]["request_complete"] == "Y"
            and value["observation"]["result_state"] in {"COMPLETED", "REJECTED"}) for value in remote):
        outcome = "FAILED"
    else:
        outcome = "UNOBSERVED"
    return recovery.ReconciliationEvidence("TERMINAL_RESPONSE" if observations else "LOCAL_LIFECYCLE", digest({"target": target.model_dump(), "observations": observations, "attempt": attempt, "remote": remote}), outcome)
