"""Versioned final-answer evaluation on the canonical task and fencing ledger.

Deterministic assertions measure only the approved rubric. They never substitute
for factual/citation review or certify a release by themselves.
"""
from __future__ import annotations

import json
import time

from pydantic import Field, StrictBool, StrictInt

from . import answer_evaluation, answer_planning, connection, continuity_work as work
from . import identity_api, knowledge_grounding, native_runtime, portal_grounding, task_continuity
from .agent_extension_contracts import bounded_json, canonical, digest, identifier, row
from .connection_crypto import decrypt_section, encrypt_section
from .continuity_contracts import Contract, Identifier, Reason, Revision
from .continuity_state import ContinuityConflict


class Rubric(Contract):
    required_phrases: tuple[str, ...] = Field(default=(), max_length=32)
    forbidden_phrases: tuple[str, ...] = Field(default=(), max_length=32)
    allowed_answer_sources: tuple[str, ...] = Field(min_length=1, max_length=6)
    minimum_characters: StrictInt = Field(default=10, ge=1, le=10000)
    require_real_model: StrictBool = True
    require_human_review: StrictBool = True
    strategy: str = Field(default="hybrid", pattern="^(keyword|fulltext|vector|hybrid)$")


class NewRun(Contract):
    case_id: Identifier
    case_version: Revision
    rubric_revision: Revision
    security_domain_id: Identifier
    agent_id: Identifier
    entry_kind: str = Field(pattern="^(PORTAL|CHANNEL)$")
    idempotency_key: Identifier
    reason: Reason


def schema_statements(database):
    if database not in {"pg", "postgresql", "oracle", "yashandb"}:
        raise ValueError("Unsupported database")
    body = "TEXT" if database in {"pg", "postgresql"} else "CLOB"
    return [
        "CREATE TABLE CX_ANSWER_RUBRICS (CASE_ID VARCHAR(128) NOT NULL, CASE_VERSION INTEGER NOT NULL, "
        "REVISION_NO INTEGER NOT NULL CHECK(REVISION_NO>0), RUBRIC_DIGEST VARCHAR(64) NOT NULL, "
        f"RUBRIC_JSON {body} NOT NULL, CREATED_BY VARCHAR(128) NOT NULL REFERENCES CX_PRINCIPALS(PRINCIPAL_ID), "
        "REASON VARCHAR(1000) NOT NULL, CREATED_AT TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL, "
        "PRIMARY KEY(CASE_ID,CASE_VERSION,REVISION_NO), FOREIGN KEY(CASE_ID,CASE_VERSION) REFERENCES CX_ANSWER_EVAL_CASES(CASE_ID,VERSION))",
        "CREATE TABLE CX_ANSWER_QUALITY_RUNS (RUN_ID VARCHAR(128) PRIMARY KEY, "
        "CONTINUITY_ID VARCHAR(128) NOT NULL UNIQUE REFERENCES CX_TASK_CONTINUITY_LINKS(CONTINUITY_ID), "
        "CASE_ID VARCHAR(128) NOT NULL, CASE_VERSION INTEGER NOT NULL, RUBRIC_REVISION INTEGER NOT NULL, "
        "CASE_DIGEST VARCHAR(64) NOT NULL, RUBRIC_DIGEST VARCHAR(64) NOT NULL, "
        "ACTOR_ID VARCHAR(128) NOT NULL REFERENCES CX_PRINCIPALS(PRINCIPAL_ID), "
        "SECURITY_DOMAIN_ID VARCHAR(128) NOT NULL REFERENCES CX_SECURITY_DOMAINS(SECURITY_DOMAIN_ID), "
        "AGENT_ID VARCHAR(128) NOT NULL REFERENCES CX_NATIVE_AGENTS(AGENT_ID), "
        "PROFILE_ID VARCHAR(128) NOT NULL REFERENCES CX_LLM_PROVIDER_PROFILES(PROFILE_ID), PROFILE_VERSION INTEGER NOT NULL CHECK(PROFILE_VERSION>0), "
        "POLICY_VERSION INTEGER NOT NULL CHECK(POLICY_VERSION>0), POLICY_DIGEST VARCHAR(64) NOT NULL, "
        "ENTRY_KIND VARCHAR(16) NOT NULL CHECK(ENTRY_KIND IN ('PORTAL','CHANNEL')), "
        "IDEMPOTENCY_KEY VARCHAR(128) NOT NULL, REQUEST_DIGEST VARCHAR(64) NOT NULL, "
        "STATUS VARCHAR(24) NOT NULL CHECK(STATUS IN ('PENDING','RUNNING','SUCCEEDED','FAILED','UNOBSERVED')), "
        "CREATED_AT TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL, COMPLETED_AT TIMESTAMP, "
        "UNIQUE(ACTOR_ID,IDEMPOTENCY_KEY), FOREIGN KEY(CASE_ID,CASE_VERSION,RUBRIC_REVISION) REFERENCES CX_ANSWER_RUBRICS(CASE_ID,CASE_VERSION,REVISION_NO))",
        "CREATE TABLE CX_ANSWER_QUALITY_INPUTS (RUN_ID VARCHAR(128) PRIMARY KEY REFERENCES CX_ANSWER_QUALITY_RUNS(RUN_ID), "
        "ATTEMPT_ID VARCHAR(128) NOT NULL REFERENCES CX_TASK_CONTINUITY_ATTEMPTS(ATTEMPT_ID), "
        f"INPUT_CIPHER {body} NOT NULL, INPUT_DIGEST VARCHAR(64) NOT NULL, CREATED_AT TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL)",
        "CREATE TABLE CX_ANSWER_QUALITY_SOURCES (RUN_ID VARCHAR(128) NOT NULL REFERENCES CX_ANSWER_QUALITY_RUNS(RUN_ID), "
        "ITEM_NO INTEGER NOT NULL CHECK(ITEM_NO>0), ENTITY_ID VARCHAR(128) NOT NULL, CONTENT_DIGEST VARCHAR(64) NOT NULL, "
        "PRIMARY KEY(RUN_ID,ITEM_NO), UNIQUE(RUN_ID,ENTITY_ID))",
        "CREATE TABLE CX_ANSWER_QUALITY_OUTPUTS (RUN_ID VARCHAR(128) PRIMARY KEY REFERENCES CX_ANSWER_QUALITY_RUNS(RUN_ID), "
        "ATTEMPT_ID VARCHAR(128) NOT NULL REFERENCES CX_TASK_CONTINUITY_ATTEMPTS(ATTEMPT_ID), FENCING_TOKEN INTEGER NOT NULL CHECK(FENCING_TOKEN>0), "
        f"OUTPUT_CIPHER {body} NOT NULL, OUTPUT_DIGEST VARCHAR(64) NOT NULL, MODEL_ID VARCHAR(256), "
        "GENERATION_KIND VARCHAR(24) NOT NULL CHECK(GENERATION_KIND IN ('REAL_MODEL','DETERMINISTIC')), "
        "LATENCY_MS INTEGER NOT NULL CHECK(LATENCY_MS>=0), ASSERTIONS_PASSED CHAR(1) NOT NULL CHECK(ASSERTIONS_PASSED IN ('Y','N')), "
        "CREATED_AT TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL)",
        "CREATE TABLE CX_ANSWER_QUALITY_REVIEWS (RUN_ID VARCHAR(128) NOT NULL REFERENCES CX_ANSWER_QUALITY_OUTPUTS(RUN_ID), "
        "REVIEWER_ID VARCHAR(128) NOT NULL REFERENCES CX_PRINCIPALS(PRINCIPAL_ID), "
        "OUTPUT_DIGEST VARCHAR(64) NOT NULL, FACTUAL_CORRECT CHAR(1) NOT NULL CHECK(FACTUAL_CORRECT IN ('Y','N')), "
        "CITATIONS_SUPPORTED CHAR(1) NOT NULL CHECK(CITATIONS_SUPPORTED IN ('Y','N')), REASON VARCHAR(1000) NOT NULL, "
        "CREATED_AT TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL, PRIMARY KEY(RUN_ID,REVIEWER_ID))",
    ]


def register_rubric(actor, case_id, case_version, value, reason):
    answer_evaluation._require_owner(actor)
    rubric = Rubric.model_validate(value)
    if (not isinstance(reason, str) or not 3 <= len(reason.strip()) <= 1000
            or any(not 1 <= len(phrase.strip()) <= 500 for phrase in (*rubric.required_phrases, *rubric.forbidden_phrases))
            or not set(rubric.allowed_answer_sources) <= answer_evaluation.OBSERVED_MODES):
        raise ValueError("Invalid evaluation rubric")
    value = rubric.model_dump(mode="json")
    fingerprint = digest(value)
    def save(tx):
        work._lock_actor(tx, actor)
        case = tx.query_one("SELECT STATUS FROM CX_ANSWER_EVAL_CASES WHERE CASE_ID=:case_id AND VERSION=:case_version",
                            {"case_id": case_id, "case_version": case_version})
        if not case or case["status"] != "ACTIVE":
            raise PermissionError("Evaluation case is unavailable")
        previous = tx.query_one("SELECT REVISION_NO,RUBRIC_DIGEST FROM CX_ANSWER_RUBRICS WHERE CASE_ID=:case_id AND CASE_VERSION=:case_version ORDER BY REVISION_NO DESC",
                                {"case_id": case_id, "case_version": case_version})
        if previous and previous["rubric_digest"] == fingerprint:
            return {"revision": int(previous["revision_no"]), "rubric_digest": fingerprint, "replayed": True}
        revision = int(previous["revision_no"]) + 1 if previous else 1
        tx.execute("INSERT INTO CX_ANSWER_RUBRICS(CASE_ID,CASE_VERSION,REVISION_NO,RUBRIC_DIGEST,RUBRIC_JSON,CREATED_BY,REASON) VALUES(:case_id,:case_version,:revision,:digest,:value,:actor,:reason)",
                   {"case_id": case_id, "case_version": case_version, "revision": revision, "digest": fingerprint,
                    "value": canonical(value), "actor": actor, "reason": reason.strip()})
        identity_api._audit_tx(tx, actor, "ANSWER_RUBRIC_REGISTERED", "ANSWER_EVAL_CASE", case_id, "ALLOW", reason)
        return {"revision": revision, "rubric_digest": fingerprint, "replayed": False}
    return connection.execute_transaction_callback(save)


def _authority(tx, actor, record):
    answer_evaluation._require_owner(actor)
    work._authorize(tx, actor, record["security_domain_id"], write=False)
    if not identity_api._agent_visible_to(actor, record["agent_id"]):
        raise PermissionError("Evaluation Agent is unavailable")
    agent = row(tx.query_one("SELECT STATUS,LLM_PROFILE_ID FROM CX_NATIVE_AGENTS WHERE AGENT_ID=:agent_id", {"agent_id": record["agent_id"]}))
    profile = row(tx.query_one("SELECT PROFILE_ID,VERSION,PROVIDER_URL,MODEL_ID,API_KEY_CIPHER,STATUS,HEALTH_STATE FROM CX_LLM_PROVIDER_PROFILES WHERE PROFILE_ID=:profile_id", {"profile_id": record["profile_id"]}))
    if (agent.get("status") != "ACTIVE" or agent.get("llm_profile_id") != record["profile_id"]
            or profile.get("status") != "ACTIVE" or profile.get("health_state") != "HEALTHY"
            or int(profile.get("version") or 0) != int(record["profile_version"])):
        raise PermissionError("Evaluation Agent/Profile revision is stale")
    knowledge_grounding.require_reader(actor, record["agent_id"])
    configured = portal_grounding.policy()
    if (int(configured["version"]) != int(record["policy_version"])
            or digest(configured) != record["policy_digest"]):
        raise PermissionError("Evaluation policy revision is stale")
    return profile, configured


def _inputs(tx, record):
    params = {"case_id": record["case_id"], "case_version": int(record["case_version"])}
    case = row(tx.query_one("SELECT * FROM CX_ANSWER_EVAL_CASES WHERE CASE_ID=:case_id AND VERSION=:case_version", params))
    rubric = row(tx.query_one("SELECT RUBRIC_JSON,RUBRIC_DIGEST FROM CX_ANSWER_RUBRICS WHERE CASE_ID=:case_id AND CASE_VERSION=:case_version AND REVISION_NO=:revision",
                              dict(params, revision=int(record["rubric_revision"]))))
    if (case.get("status") != "ACTIVE" or case.get("case_digest") != record["case_digest"]
            or rubric.get("rubric_digest") != record["rubric_digest"]):
        raise PermissionError("Evaluation case or rubric revision is stale")
    specification = Rubric.model_validate_json(rubric["rubric_json"])
    if digest(specification.model_dump(mode="json")) != record["rubric_digest"]:
        raise ValueError("Evaluation rubric integrity check failed")
    return case, specification


def enqueue(actor, value):
    request = NewRun.model_validate(value)
    answer_evaluation._require_owner(actor)
    fingerprint = digest(request.model_dump(mode="json"))
    def save(tx):
        work._authorize(tx, actor, request.security_domain_id, write=True)
        previous = row(tx.query_one("SELECT * FROM CX_ANSWER_QUALITY_RUNS WHERE ACTOR_ID=:actor AND IDEMPOTENCY_KEY=:idem", {"actor": actor, "idem": request.idempotency_key}))
        if previous:
            _authority(tx, actor, previous)
            if previous["request_digest"] != fingerprint:
                raise ContinuityConflict("IDEMPOTENCY_CONFLICT", "Evaluation request differs from its recorded facts")
            return {"run_id": previous["run_id"], "status": previous["status"], "replayed": True}
        agent = row(tx.query_one("SELECT LLM_PROFILE_ID FROM CX_NATIVE_AGENTS WHERE AGENT_ID=:agent_id", {"agent_id": request.agent_id}))
        profile = row(tx.query_one("SELECT VERSION FROM CX_LLM_PROVIDER_PROFILES WHERE PROFILE_ID=:profile_id", {"profile_id": agent.get("llm_profile_id")}))
        configured = portal_grounding.policy()
        record = request.model_dump()
        record.update(actor_id=actor, profile_id=agent.get("llm_profile_id"), profile_version=int(profile.get("version") or 0),
                      policy_version=int(configured["version"]), policy_digest=digest(configured))
        _authority(tx, actor, record)
        params = {"case_id": request.case_id, "case_version": request.case_version}
        case = row(tx.query_one("SELECT STATUS,CASE_DIGEST FROM CX_ANSWER_EVAL_CASES WHERE CASE_ID=:case_id AND VERSION=:case_version", params))
        rubric = row(tx.query_one("SELECT RUBRIC_DIGEST FROM CX_ANSWER_RUBRICS WHERE CASE_ID=:case_id AND CASE_VERSION=:case_version AND REVISION_NO=:revision", dict(params, revision=request.rubric_revision)))
        if case.get("status") != "ACTIVE" or not rubric:
            raise PermissionError("Approved evaluation case/rubric is unavailable")
        record.update(case_digest=case["case_digest"], rubric_digest=rubric["rubric_digest"])
        run_id = identifier("AQR")
        task_id = task_continuity.ensure_task_root(tx, actor, goal="Final-answer evaluation", preferred_agent_id=request.agent_id)
        link = task_continuity.link_protocol_task(tx, actor=actor, security_domain_id=request.security_domain_id,
            link_kind="DIAGNOSTIC", link_id=run_id, canonical_task_id=task_id, idempotency_key="aq:" + digest([actor, request.idempotency_key]), request_digest=fingerprint)
        tx.execute("INSERT INTO CX_ANSWER_QUALITY_RUNS(RUN_ID,CONTINUITY_ID,CASE_ID,CASE_VERSION,RUBRIC_REVISION,CASE_DIGEST,RUBRIC_DIGEST,ACTOR_ID,SECURITY_DOMAIN_ID,AGENT_ID,PROFILE_ID,PROFILE_VERSION,POLICY_VERSION,POLICY_DIGEST,ENTRY_KIND,IDEMPOTENCY_KEY,REQUEST_DIGEST,STATUS) VALUES(:run_id,:continuity,:case_id,:case_version,:rubric_revision,:case_digest,:rubric_digest,:actor,:domain,:agent_id,:profile_id,:profile_version,:policy_version,:policy_digest,:entry,:idem,:request_digest,'PENDING')",
            {"run_id": run_id, "continuity": link["continuity_id"], **{key: record[key] for key in ("case_id", "case_version", "rubric_revision", "case_digest", "rubric_digest", "agent_id", "profile_id", "profile_version", "policy_version", "policy_digest")},
             "actor": actor, "domain": request.security_domain_id, "entry": request.entry_kind, "idem": request.idempotency_key, "request_digest": fingerprint})
        identity_api._audit_tx(tx, actor, "ANSWER_QUALITY_QUEUED", "ANSWER_QUALITY_RUN", run_id, "ALLOW", request.reason)
        return {"run_id": run_id, "status": "PENDING", "replayed": False}
    return connection.execute_transaction_callback(save)


def assess(case, rubric, prepared, retrieval, answer, generation_kind):
    expected = set(json.loads(case["expected_entities_json"] or "[]"))
    observed = {str(item["entity_id"]) for item in prepared["citations"]}
    text = answer.casefold()
    checks = {"retrieval_mode": retrieval["status"] == case["expected_mode"],
              "exact_evidence_scope": expected == observed,
              "answer_source": prepared["answer_source"] in rubric.allowed_answer_sources,
              "answer_length": len(answer.strip()) >= rubric.minimum_characters,
              "required_phrases": all(phrase.casefold() in text for phrase in rubric.required_phrases),
              "forbidden_phrases": not any(phrase.casefold() in text for phrase in rubric.forbidden_phrases),
              "real_model": not rubric.require_real_model or generation_kind == "REAL_MODEL"}
    return {"checks": checks, "assertions_passed": all(checks.values()),
            "factual_review": "PENDING" if rubric.require_human_review else "NOT_REQUIRED_BY_RUBRIC",
            "scope": "Approved deterministic assertions only; not an independent factuality assessment."}


def _sources(tx, actor, record):
    for source in tx.query("SELECT ENTITY_ID,CONTENT_DIGEST FROM CX_ANSWER_QUALITY_SOURCES WHERE RUN_ID=:run_id ORDER BY ITEM_NO", {"run_id": record["run_id"]}):
        knowledge_grounding.citation(actor, record["agent_id"], source["entity_id"], source["content_digest"])


def execute(actor, run_id, *, worker_id="answer-quality-worker"):
    def claim(tx):
        work._lock_actor(tx, actor)
        record = row(tx.query_one("SELECT * FROM CX_ANSWER_QUALITY_RUNS WHERE RUN_ID=:run_id AND ACTOR_ID=:actor FOR UPDATE", {"run_id": run_id, "actor": actor}))
        if not record:
            raise PermissionError("Evaluation run is unavailable")
        profile, configured = _authority(tx, actor, record)
        case, rubric = _inputs(tx, record)
        if record["status"] == "RUNNING":
            expired = tx.query_one("SELECT CONTINUITY_ID FROM CX_TASK_CONTINUITY_LEASES WHERE CONTINUITY_ID=:continuity AND STATUS='ACTIVE' AND LEASE_EXPIRES_AT<=:utc_now",
                                   {"continuity": record["continuity_id"], "utc_now": task_continuity._now()})
            if expired:
                outcome = task_continuity.claim_attempt(tx, continuity_id=record["continuity_id"], worker_id=worker_id,
                    business_key=run_id, request_digest=record["request_digest"])
                if outcome.get("reconciliation_required"):
                    tx.execute("UPDATE CX_ANSWER_QUALITY_RUNS SET STATUS='UNOBSERVED',COMPLETED_AT=CURRENT_TIMESTAMP WHERE RUN_ID=:run_id AND STATUS='RUNNING'", {"run_id": run_id})
                    return {"run_id": run_id, "status": "UNOBSERVED", "replayed": True}
        if record["status"] != "PENDING":
            return {"run_id": run_id, "status": record["status"], "replayed": True}
        attempt = task_continuity.claim_attempt(tx, continuity_id=record["continuity_id"], worker_id=worker_id,
            business_key=run_id, request_digest=record["request_digest"], lease_seconds=300)
        if attempt.get("replayed") or attempt.get("reconciliation_required"):
            return {"run_id": run_id, "status": "UNOBSERVED" if attempt.get("reconciliation_required") else "RUNNING", "replayed": True}
        tx.execute("UPDATE CX_ANSWER_QUALITY_RUNS SET STATUS='RUNNING' WHERE RUN_ID=:run_id AND STATUS='PENDING'", {"run_id": run_id})
        return record, profile, configured, case, rubric, attempt
    claimed = connection.execute_transaction_callback(claim)
    if isinstance(claimed, dict):
        return claimed
    record, profile, configured, case, rubric, attempt = claimed
    started = time.monotonic()
    sent = False
    try:
        retrieval = answer_planning.retrieve(actor, record["agent_id"], case["query_text"], strategy=rubric.strategy)
        prepared = answer_planning.prepare(case["query_text"], record["profile_id"], configured, retrieval)
        frozen_input = {"entry_kind": record["entry_kind"], "messages": prepared["messages"], "knowledge_reply": prepared["knowledge_reply"],
                        "retrieval": retrieval, "prepared": {key: value for key, value in prepared.items() if key != "messages"}}
        bounded_json(frozen_input, maximum=1024 * 1024)
        def bind_input(tx):
            _authority(tx, actor, record)
            _inputs(tx, record)
            current = task_continuity.claim_attempt(tx, continuity_id=record["continuity_id"], worker_id=worker_id,
                business_key=run_id, request_digest=record["request_digest"], lease_seconds=300)
            if current.get("reconciliation_required"):
                tx.execute("UPDATE CX_ANSWER_QUALITY_RUNS SET STATUS='UNOBSERVED',COMPLETED_AT=CURRENT_TIMESTAMP WHERE RUN_ID=:run_id AND STATUS='RUNNING'", {"run_id": run_id})
                return False
            if current.get("attempt_id") != attempt["attempt_id"] or current.get("fencing_token") != attempt["fencing_token"]:
                raise ContinuityConflict("FENCING_MISMATCH", "Evaluation attempt was replaced before dispatch")
            for number, source in enumerate(prepared["citations"], 1):
                knowledge_grounding.citation(actor, record["agent_id"], source["entity_id"], source["digest"])
                tx.execute("INSERT INTO CX_ANSWER_QUALITY_SOURCES(RUN_ID,ITEM_NO,ENTITY_ID,CONTENT_DIGEST) VALUES(:run_id,:v_item_no,:entity,:digest)",
                    {"run_id": run_id, "v_item_no": number, "entity": source["entity_id"], "digest": source["digest"]})
            tx.execute("INSERT INTO CX_ANSWER_QUALITY_INPUTS(RUN_ID,ATTEMPT_ID,INPUT_CIPHER,INPUT_DIGEST) VALUES(:run_id,:attempt,:cipher,:digest)",
                {"run_id": run_id, "attempt": attempt["attempt_id"], "cipher": encrypt_section(frozen_input), "digest": digest(frozen_input)})
            return True
        if not connection.execute_transaction_callback(bind_input):
            return {"run_id": run_id, "status": "UNOBSERVED", "replayed": True}
        result = {"content": prepared["knowledge_reply"], "model": None, "usage": None, "usage_observation": "UNAVAILABLE"}
        if result["content"] is None:
            sent = True
            result = native_runtime._call_llm(profile, prepared["messages"])
        generation_kind = "REAL_MODEL" if sent else "DETERMINISTIC"
        answer = answer_planning.render_reply(str(result["content"]), prepared)
        assessment = assess(case, rubric, prepared, retrieval, answer, generation_kind)
        output = {"answer": answer, "answer_source": prepared["answer_source"], "retrieval_status": retrieval["status"],
                  "citations": prepared["citations"], "assessment": assessment, "model": result.get("model"),
                  "usage": result.get("usage"), "usage_observation": result.get("usage_observation", "UNAVAILABLE")}
        bounded_json(output, maximum=1024 * 1024)
        def finish(tx):
            _authority(tx, actor, record)
            _inputs(tx, record)
            _sources(tx, actor, record)
            accepted = task_continuity.finish_attempt(tx, attempt_id=attempt["attempt_id"], worker_id=worker_id,
                fencing_token=attempt["fencing_token"], status="SUCCEEDED", request_digest=record["request_digest"])
            if accepted.get("accepted") is False:
                tx.execute("UPDATE CX_ANSWER_QUALITY_RUNS SET STATUS='UNOBSERVED',COMPLETED_AT=CURRENT_TIMESTAMP WHERE RUN_ID=:run_id", {"run_id": run_id})
                return {"run_id": run_id, "status": "UNOBSERVED"}
            tx.execute("INSERT INTO CX_ANSWER_QUALITY_OUTPUTS(RUN_ID,ATTEMPT_ID,FENCING_TOKEN,OUTPUT_CIPHER,OUTPUT_DIGEST,MODEL_ID,GENERATION_KIND,LATENCY_MS,ASSERTIONS_PASSED) VALUES(:run_id,:attempt,:fence,:cipher,:digest,:model,:kind,:latency,:passed)",
                {"run_id": run_id, "attempt": attempt["attempt_id"], "fence": attempt["fencing_token"], "cipher": encrypt_section(output),
                 "digest": digest(output), "model": result.get("model"), "kind": generation_kind,
                 "latency": max(0, round((time.monotonic() - started) * 1000)), "passed": "Y" if assessment["assertions_passed"] else "N"})
            tx.execute("UPDATE CX_ANSWER_QUALITY_RUNS SET STATUS='SUCCEEDED',COMPLETED_AT=CURRENT_TIMESTAMP WHERE RUN_ID=:run_id", {"run_id": run_id})
            identity_api._audit_tx(tx, actor, "ANSWER_QUALITY_OBSERVED", "ANSWER_QUALITY_RUN", run_id, "ALLOW", generation_kind)
            return {"run_id": run_id, "status": "SUCCEEDED", "assertions_passed": assessment["assertions_passed"], "factual_review": assessment["factual_review"]}
        return connection.execute_transaction_callback(finish)
    except Exception:
        outcome = "UNOBSERVED" if sent else "FAILED"
        def fail(tx):
            observed = task_continuity.finish_attempt(tx, attempt_id=attempt["attempt_id"], worker_id=worker_id,
                fencing_token=attempt["fencing_token"], status=outcome, request_digest=record["request_digest"], error_code="EVALUATION_UNOBSERVED" if sent else "EVALUATION_FAILED",
                error_message="Evaluation did not produce an accepted observation")
            tx.execute("UPDATE CX_ANSWER_QUALITY_RUNS SET STATUS=:status,COMPLETED_AT=CURRENT_TIMESTAMP WHERE RUN_ID=:run_id AND STATUS='RUNNING'", {"status": observed["status"], "run_id": run_id})
        connection.execute_transaction_callback(fail)
        raise


def reconcile(*, limit=20):
    """Persist expired send uncertainty without generating or disclosing content."""
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError("Reconciliation limit is out of range")
    def expire(tx):
        candidates = tx.query("SELECT r.RUN_ID,r.ACTOR_ID,r.CONTINUITY_ID,r.REQUEST_DIGEST FROM CX_ANSWER_QUALITY_RUNS r JOIN CX_TASK_CONTINUITY_LEASES l ON l.CONTINUITY_ID=r.CONTINUITY_ID WHERE r.STATUS='RUNNING' AND l.STATUS='ACTIVE' AND l.LEASE_EXPIRES_AT<=:utc_now ORDER BY r.CREATED_AT" + identity_api._limit_clause("batch_limit"),
                              {"batch_limit": limit, "utc_now": task_continuity._now()})
        count = 0
        for record in candidates:
            tx.query_one("SELECT PRINCIPAL_ID FROM CX_PRINCIPALS WHERE PRINCIPAL_ID=:actor FOR UPDATE", {"actor": record["actor_id"]})
            current = tx.query_one("SELECT STATUS FROM CX_ANSWER_QUALITY_RUNS WHERE RUN_ID=:run_id FOR UPDATE", {"run_id": record["run_id"]})
            if not current or current["status"] != "RUNNING":
                continue
            result = task_continuity.claim_attempt(tx, continuity_id=record["continuity_id"], worker_id="answer-quality-reconciler",
                business_key=record["run_id"], request_digest=record["request_digest"])
            if result.get("reconciliation_required"):
                count += tx.execute("UPDATE CX_ANSWER_QUALITY_RUNS SET STATUS='UNOBSERVED',COMPLETED_AT=CURRENT_TIMESTAMP WHERE RUN_ID=:run_id AND STATUS='RUNNING'", {"run_id": record["run_id"]})
        return count
    return connection.execute_transaction_callback(expire)


def read_run(actor, run_id):
    def read(tx):
        record = row(tx.query_one("SELECT * FROM CX_ANSWER_QUALITY_RUNS WHERE RUN_ID=:run_id", {"run_id": run_id}))
        if not record:
            raise PermissionError("Evaluation run is unavailable")
        _authority(tx, actor, record)
        _sources(tx, actor, record)
        output = row(tx.query_one("SELECT OUTPUT_CIPHER,OUTPUT_DIGEST,GENERATION_KIND,LATENCY_MS FROM CX_ANSWER_QUALITY_OUTPUTS WHERE RUN_ID=:run_id", {"run_id": run_id}))
        value = decrypt_section(output.pop("output_cipher")) if output else None
        if value is not None and digest(value) != output["output_digest"]:
            raise ValueError("Evaluation output integrity check failed")
        reviews = tx.query("SELECT REVIEWER_ID,OUTPUT_DIGEST,FACTUAL_CORRECT,CITATIONS_SUPPORTED,REASON,CREATED_AT FROM CX_ANSWER_QUALITY_REVIEWS WHERE RUN_ID=:run_id ORDER BY CREATED_AT", {"run_id": run_id})
        return {"run": record, "output": value, "observation": output, "reviews": reviews,
                "release_acceptance": "NOT_ESTABLISHED_BY_THIS_RUN"}
    return connection.execute_transaction_callback(read)


def review(actor, run_id, output_digest, factual_correct, citations_supported, reason):
    if (type(factual_correct) is not bool or type(citations_supported) is not bool
            or not isinstance(reason, str) or not 3 <= len(reason.strip()) <= 1000):
        raise ValueError("A factual and citation review with a reason is required")
    def save(tx):
        record = row(tx.query_one("SELECT * FROM CX_ANSWER_QUALITY_RUNS WHERE RUN_ID=:run_id FOR UPDATE", {"run_id": run_id}))
        if not record:
            raise PermissionError("Evaluation run is unavailable")
        _authority(tx, actor, record)
        _sources(tx, actor, record)
        reviewer = row(tx.query_one("SELECT PRINCIPAL_TYPE FROM CX_PRINCIPALS WHERE PRINCIPAL_ID=:actor", {"actor": actor}))
        if reviewer.get("principal_type") != "HUMAN" or actor == record["actor_id"]:
            raise PermissionError("An independent authorized human reviewer is required")
        observed = tx.query_one("SELECT OUTPUT_DIGEST FROM CX_ANSWER_QUALITY_OUTPUTS WHERE RUN_ID=:run_id", {"run_id": run_id})
        if not observed or observed["output_digest"] != output_digest:
            raise ContinuityConflict("STALE_OUTPUT", "The reviewed output digest is stale")
        tx.execute("INSERT INTO CX_ANSWER_QUALITY_REVIEWS(RUN_ID,REVIEWER_ID,OUTPUT_DIGEST,FACTUAL_CORRECT,CITATIONS_SUPPORTED,REASON) VALUES(:run_id,:actor,:digest,:facts,:citations,:reason)",
                   {"run_id": run_id, "actor": actor, "digest": output_digest, "facts": "Y" if factual_correct else "N", "citations": "Y" if citations_supported else "N", "reason": reason.strip()})
        identity_api._audit_tx(tx, actor, "ANSWER_QUALITY_REVIEWED", "ANSWER_QUALITY_RUN", run_id, "ALLOW", reason)
        return {"run_id": run_id, "reviewer_id": actor, "recorded": True}
    return connection.execute_transaction_callback(save)
