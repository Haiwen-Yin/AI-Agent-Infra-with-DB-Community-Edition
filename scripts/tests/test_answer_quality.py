"""Final-answer evaluation uses durable cases, exact inputs and fenced sends."""
import json
import sqlite3
from datetime import datetime, timedelta

import pytest

from lib import answer_quality as quality, task_continuity


@pytest.fixture
def database(monkeypatch):
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    db.executescript("""
        CREATE TABLE CX_PRINCIPALS(PRINCIPAL_ID TEXT PRIMARY KEY, PRINCIPAL_TYPE TEXT, STATUS TEXT);
        INSERT INTO CX_PRINCIPALS VALUES('owner','HUMAN','ACTIVE'),('reviewer','HUMAN','ACTIVE'),('agent','AGENT','ACTIVE');
        CREATE TABLE CX_SECURITY_DOMAINS(SECURITY_DOMAIN_ID TEXT PRIMARY KEY,STATUS TEXT);
        INSERT INTO CX_SECURITY_DOMAINS VALUES('domain','ACTIVE');
        CREATE TABLE CX_DOMAIN_MEMBERS(SECURITY_DOMAIN_ID TEXT,PRINCIPAL_ID TEXT,STATUS TEXT,MEMBERSHIP_TIER TEXT,VALID_UNTIL TIMESTAMP);
        INSERT INTO CX_DOMAIN_MEMBERS VALUES('domain','owner','ACTIVE','OWNER',NULL),('domain','reviewer','ACTIVE','ADMIN',NULL);
        CREATE TABLE TASK_PLANS(PLAN_ID TEXT PRIMARY KEY,AGENT_ID TEXT,GOAL TEXT,STATUS TEXT,PRIORITY INTEGER,STRATEGY TEXT);
        CREATE TABLE AGENT_REGISTRY(AGENT_ID TEXT PRIMARY KEY);
        INSERT INTO AGENT_REGISTRY VALUES('agent');
        CREATE TABLE CX_AGENT_INSTANCES(INSTANCE_ID TEXT PRIMARY KEY);
        CREATE TABLE CX_CONTEXT_ASSEMBLIES(ASSEMBLY_ID TEXT PRIMARY KEY);
        CREATE TABLE CX_NATIVE_AGENTS(AGENT_ID TEXT PRIMARY KEY,LLM_PROFILE_ID TEXT,STATUS TEXT);
        INSERT INTO CX_NATIVE_AGENTS VALUES('agent','profile','ACTIVE');
        CREATE TABLE CX_LLM_PROVIDER_PROFILES(PROFILE_ID TEXT PRIMARY KEY,VERSION INTEGER,STATUS TEXT,HEALTH_STATE TEXT,PROVIDER_URL TEXT,MODEL_ID TEXT,API_KEY_CIPHER TEXT);
        INSERT INTO CX_LLM_PROVIDER_PROFILES VALUES('profile',3,'ACTIVE','HEALTHY','https://model.invalid/v1','model',NULL);
        CREATE TABLE CX_ANSWER_EVAL_CASES(CASE_ID TEXT,VERSION INTEGER,QUERY_TEXT TEXT,EXPECTED_MODE TEXT,EXPECTED_ENTITIES_JSON TEXT,STATUS TEXT,CASE_DIGEST TEXT,PRIMARY KEY(CASE_ID,VERSION));
        INSERT INTO CX_ANSWER_EVAL_CASES VALUES('case',1,'What is quantum tunneling?','NO_MATCH','[]','ACTIVE','case-digest');
        CREATE TABLE AUDIT(ACTION TEXT,RESOURCE TEXT);
    """)
    for statement in task_continuity.schema_statements("pg") + quality.schema_statements("pg"):
        db.execute(statement)
    class Tx:
        def execute(self, sql, params):
            return db.execute(sql.replace(" FOR UPDATE", ""), params).rowcount
        def query(self, sql, params):
            return [{key.lower(): value[key] for key in value.keys()} for value in db.execute(sql.replace(" FOR UPDATE", ""), params)]
        def query_one(self, sql, params):
            rows = self.query(sql, params)
            return rows[0] if rows else None
    def transaction(callback):
        try:
            result = callback(Tx())
            db.commit()
            return result
        except Exception:
            db.rollback()
            raise
    monkeypatch.setattr(quality.connection, "execute_transaction_callback", transaction)
    monkeypatch.setattr(quality.connection, "DATABASE_DIALECT", "oracle")
    monkeypatch.setattr(quality.answer_evaluation, "_require_owner", lambda _: None)
    monkeypatch.setattr(quality.identity_api, "effective_access", lambda *_a, **_k: {"decision": "ALLOW"})
    monkeypatch.setattr(quality.identity_api, "_agent_visible_to", lambda *_: True)
    monkeypatch.setattr(quality.identity_api, "_audit_tx", lambda tx, actor, action, family, resource, *rest: tx.execute("INSERT INTO AUDIT VALUES(:action,:resource)", {"action": action, "resource": resource}))
    monkeypatch.setattr(quality.knowledge_grounding, "require_reader", lambda *_: None)
    monkeypatch.setattr(quality, "encrypt_section", lambda value: "encrypted:" + json.dumps(value))
    monkeypatch.setattr(quality, "decrypt_section", lambda value: json.loads(value.removeprefix("encrypted:")))
    monkeypatch.setattr(quality.portal_grounding, "policy", lambda: {"version": 2, "mode": "KNOWLEDGE_FIRST", "allow_model_supplement": "Y", "disclosure_profiles": ["profile"]})
    monkeypatch.setattr(quality.answer_planning, "retrieve", lambda *_a, **_k: {"status": "NO_MATCH", "items": [], "missing_parts": []})
    monkeypatch.setattr(quality.native_runtime, "_call_llm", lambda *_: {"content": "Quantum tunneling crosses a potential barrier.", "model": "model", "usage": {"total_tokens": 32}, "usage_observation": "PROVIDER_REPORTED"})
    db.commit()
    yield db
    db.close()


def rubric(**changes):
    return {"required_phrases": ["tunneling"], "forbidden_phrases": ["company policy"],
            "allowed_answer_sources": ["MODEL_SUPPLEMENT"], **changes}


def request(**changes):
    return {"case_id": "case", "case_version": 1, "rubric_revision": 1,
            "security_domain_id": "domain", "agent_id": "agent", "entry_kind": "PORTAL",
            "idempotency_key": "first", "reason": "Approved isolated evaluation", **changes}


def enqueue():
    quality.register_rubric("owner", "case", 1, rubric(), "Fixed before execution")
    return quality.enqueue("owner", request())["run_id"]


def test_final_generation_persists_exact_input_output_and_usage(database):
    run_id = enqueue()
    result = quality.execute("owner", run_id)
    assert result["status"] == "SUCCEEDED" and result["assertions_passed"]
    observed = quality.read_run("owner", run_id)
    assert observed["output"]["answer"].startswith("Quantum tunneling")
    assert observed["output"]["usage"] == {"total_tokens": 32}
    assert observed["output"]["assessment"]["factual_review"] == "PENDING"
    assert observed["observation"]["generation_kind"] == "REAL_MODEL"
    assert observed["release_acceptance"] == "NOT_ESTABLISHED_BY_THIS_RUN"
    stored = database.execute("SELECT INPUT_CIPHER,INPUT_DIGEST FROM CX_ANSWER_QUALITY_INPUTS").fetchone()
    assert stored[0].startswith("encrypted:") and len(stored[1]) == 64
    assert database.execute("SELECT STATUS FROM CX_TASK_CONTINUITY_LINKS").fetchone()[0] == "SUCCEEDED"
    assert database.execute("SELECT COUNT(*) FROM TASK_PLANS").fetchone()[0] == 1


@pytest.mark.parametrize('correct', [False, True])
def test_mixed_scope_is_persisted_without_supplying_missing_answer_content(database, monkeypatch, correct):
    database.execute("UPDATE CX_ANSWER_EVAL_CASES SET QUERY_TEXT='Atlas routing and explain tunneling',EXPECTED_MODE='PARTIAL_MATCH',EXPECTED_ENTITIES_JSON='[\"route\"]'")
    database.commit()
    monkeypatch.setattr(quality.answer_planning, 'retrieve', lambda *a, **kw: {
        'status': 'PARTIAL_MATCH', 'missing_parts': ['explain tunneling'],
        'items': [{'entity_id': 'route', 'title': 'Atlas routing', 'content': 'route-742', 'digest': 'd1'}]})
    monkeypatch.setattr(quality.knowledge_grounding, 'citation', lambda *a: {})
    raw = 'Atlas uses route-742 [1]. ' + ('Quantum tunneling crosses a potential barrier.' if correct else 'No explanation.')
    monkeypatch.setattr(quality.native_runtime, '_call_llm', lambda *a: {'content': raw, 'model': 'test'})
    quality.register_rubric('owner', 'case', 1, rubric(allowed_answer_sources=['MIXED_SOURCES']), 'Fixed before execution')
    run_id = quality.enqueue('owner', request())['run_id']
    result = quality.execute('owner', run_id)
    observed = quality.read_run('owner', run_id)['output']
    assert observed['answer'].endswith(raw)
    assert 'question part(s) 2 have no authorized evidence' in observed['answer']
    assert 'tunneling' not in observed['answer'].removesuffix(raw)
    assert observed['assessment']['checks']['required_phrases'] is correct
    assert result['assertions_passed'] is correct


@pytest.mark.parametrize("field,value", [("case_version", 2), ("entry_kind", "CHANNEL")])
def test_replay_never_reinterprets_same_key(database, field, value):
    run_id = enqueue()
    assert quality.enqueue("owner", request())["replayed"]
    with pytest.raises(quality.ContinuityConflict):
        quality.enqueue("owner", request(**{field: value}))
    quality.execute("owner", run_id)
    assert quality.execute("owner", run_id)["replayed"]
    assert database.execute("SELECT COUNT(*) FROM CX_ANSWER_QUALITY_OUTPUTS").fetchone()[0] == 1


def test_wrong_final_answer_fails_despite_correct_retrieval(database, monkeypatch):
    run_id = enqueue()
    monkeypatch.setattr(quality.native_runtime, "_call_llm", lambda *_: {"content": "Unrelated company policy content.", "model": "model"})
    assert not quality.execute("owner", run_id)["assertions_passed"]
    observed = quality.read_run("owner", run_id)["output"]
    assert observed["assessment"]["checks"]["retrieval_mode"]
    assert not observed["assessment"]["checks"]["required_phrases"]
    assert not observed["assessment"]["checks"]["forbidden_phrases"]
    assert observed["usage"] is None and observed["usage_observation"] == "UNAVAILABLE"


@pytest.mark.parametrize('session_offset', [-4, 8])
@pytest.mark.parametrize('recovery', ['execute', 'reconcile'])
def test_expired_utc_evaluation_persists_unobserved_without_second_send(database, monkeypatch, session_offset, recovery):
    clock = [datetime(2030, 6, 1, 12)]
    monkeypatch.setattr(task_continuity, '_now', lambda: clock[0])
    database.create_function('current_timestamp', 0,
                            lambda: (clock[0] + timedelta(hours=session_offset)).isoformat(sep=' '))
    monkeypatch.setattr(quality.identity_api, '_limit_clause', lambda key: ' LIMIT :' + key)
    run_id = enqueue()
    record = dict(database.execute('SELECT * FROM CX_ANSWER_QUALITY_RUNS WHERE RUN_ID=?', (run_id,)).fetchone())
    attempt = quality.connection.execute_transaction_callback(lambda tx: task_continuity.claim_attempt(
        tx, continuity_id=record['CONTINUITY_ID'], worker_id='interrupted-worker', business_key=run_id,
        request_digest=record['REQUEST_DIGEST'], lease_seconds=1))
    database.execute("UPDATE CX_ANSWER_QUALITY_RUNS SET STATUS='RUNNING' WHERE RUN_ID=?", (run_id,))
    database.commit()
    monkeypatch.setattr(quality.native_runtime, '_call_llm', lambda *_: pytest.fail('An uncertain send cannot be retried'))
    clock[0] += timedelta(seconds=2)
    if recovery == 'execute':
        assert quality.execute('owner', run_id)['status'] == 'UNOBSERVED'
    else:
        assert quality.reconcile() == 1
        assert quality.reconcile() == 0
    assert database.execute('SELECT STATUS FROM CX_ANSWER_QUALITY_RUNS').fetchone()[0] == 'UNOBSERVED'
    attempts = database.execute('SELECT ATTEMPT_ID,STATUS,FENCING_TOKEN FROM CX_TASK_CONTINUITY_ATTEMPTS').fetchall()
    assert [tuple(item) for item in attempts] == [(attempt['attempt_id'], 'UNOBSERVED', 1)]
    assert database.execute('SELECT COUNT(*) FROM CX_ANSWER_QUALITY_OUTPUTS').fetchone()[0] == 0
    assert quality.execute('owner', run_id)['status'] == 'UNOBSERVED'


def test_unknown_send_is_durable_and_not_retried(database, monkeypatch):
    run_id = enqueue()
    calls = []
    def fail(*_):
        calls.append(True)
        raise RuntimeError("Synthetic provider timeout")
    monkeypatch.setattr(quality.native_runtime, "_call_llm", fail)
    with pytest.raises(RuntimeError):
        quality.execute("owner", run_id)
    assert quality.execute("owner", run_id)["status"] == "UNOBSERVED"
    assert len(calls) == 1
    assert database.execute("SELECT STATUS FROM CX_TASK_CONTINUITY_ATTEMPTS").fetchone()[0] == "UNOBSERVED"
    assert database.execute("SELECT COUNT(*) FROM CX_ANSWER_QUALITY_OUTPUTS").fetchone()[0] == 0


@pytest.mark.parametrize("change", ["profile", "permission", "case", "policy"])
def test_revocation_or_revision_change_before_send_prevents_generation(database, monkeypatch, change):
    run_id = enqueue()
    calls = []
    monkeypatch.setattr(quality.native_runtime, "_call_llm", lambda *_: calls.append(True))
    if change == "profile":
        database.execute("UPDATE CX_LLM_PROVIDER_PROFILES SET VERSION=4")
    elif change == "permission":
        database.execute("UPDATE CX_DOMAIN_MEMBERS SET STATUS='REVOKED' WHERE PRINCIPAL_ID='owner'")
    elif change == "case":
        database.execute("UPDATE CX_ANSWER_EVAL_CASES SET STATUS='RETIRED'")
    else:
        monkeypatch.setattr(quality.portal_grounding, "policy", lambda: {"version": 3})
    database.commit()
    with pytest.raises(PermissionError):
        quality.execute("owner", run_id)
    assert not calls


def test_revocation_during_model_call_prevents_output_disclosure(database, monkeypatch):
    run_id = enqueue()
    def generate(*_):
        database.execute("UPDATE CX_DOMAIN_MEMBERS SET STATUS='REVOKED' WHERE PRINCIPAL_ID='owner'")
        database.commit()
        return {"content": "Quantum tunneling answer.", "model": "model"}
    monkeypatch.setattr(quality.native_runtime, "_call_llm", generate)
    with pytest.raises(PermissionError):
        quality.execute("owner", run_id)
    assert database.execute("SELECT STATUS FROM CX_ANSWER_QUALITY_RUNS").fetchone()[0] == "UNOBSERVED"
    assert database.execute("SELECT COUNT(*) FROM CX_ANSWER_QUALITY_OUTPUTS").fetchone()[0] == 0


def test_independent_human_review_binds_exact_output(database):
    run_id = enqueue()
    quality.execute("owner", run_id)
    fingerprint = quality.read_run("reviewer", run_id)["observation"]["output_digest"]
    with pytest.raises(PermissionError):
        quality.review("owner", run_id, fingerprint, True, True, "Self review is refused")
    with pytest.raises(quality.ContinuityConflict):
        quality.review("reviewer", run_id, "0" * 64, True, True, "Stale review")
    assert quality.review("reviewer", run_id, fingerprint, True, True, "Reviewed actual answer and sources")["recorded"]
    assert quality.read_run("owner", run_id)["reviews"][0]["reviewer_id"] == "reviewer"


def test_assessment_and_audit_commit_atomically(database, monkeypatch):
    quality.register_rubric("owner", "case", 1, rubric(), "Fixed before execution")
    def fail(*_):
        raise RuntimeError("Synthetic audit failure")
    monkeypatch.setattr(quality.identity_api, "_audit_tx", fail)
    with pytest.raises(RuntimeError):
        quality.enqueue("owner", request())
    assert database.execute("SELECT COUNT(*) FROM CX_ANSWER_QUALITY_RUNS").fetchone()[0] == 0
    assert database.execute("SELECT COUNT(*) FROM TASK_PLANS").fetchone()[0] == 0


def test_unapproved_profile_cannot_be_used_for_knowledge_disclosure(database, monkeypatch):
    run_id = enqueue()
    # No-match model supplementation is permitted by policy; a grounded answer
    # additionally requires the disclosure allowlist at preparation time.
    monkeypatch.setattr(quality.answer_planning, "retrieve", lambda *_a, **_k: {"status": "MATCHED", "items": [{"entity_id": "private", "digest": "a"*64, "content": "Private fact"}], "missing_parts": []})
    policy = {"version": 2, "mode": "KNOWLEDGE_FIRST", "allow_model_supplement": "Y", "disclosure_profiles": []}
    monkeypatch.setattr(quality.portal_grounding, "policy", lambda: policy)
    with pytest.raises(PermissionError):
        quality.execute("owner", run_id)
    assert database.execute("SELECT COUNT(*) FROM CX_ANSWER_QUALITY_OUTPUTS").fetchone()[0] == 0


def test_changed_or_incomplete_rubric_cannot_be_silently_accepted(database):
    with pytest.raises(ValueError):
        quality.register_rubric("owner", "case", 1, rubric(required_phrases=[""]), "No empty assertions")
    enqueue()
    assert quality.register_rubric("owner", "case", 1, rubric(), "Replay approved rubric")["replayed"]
    assert quality.register_rubric("owner", "case", 1, rubric(minimum_characters=50), "A separately reviewed stricter rubric")["revision"] == 2
    assert database.execute("SELECT COUNT(*) FROM CX_ANSWER_RUBRICS").fetchone()[0] == 2
