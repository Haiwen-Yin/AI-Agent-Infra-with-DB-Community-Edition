"""Relational/process capacity fixtures; these are not native DB acceptance."""
import multiprocessing
import sqlite3

import pytest

from lib import model_endpoint_capacity as capacity
from lib import model_endpoint_schema as schema
from lib.continuity_state import ContinuityConflict


class Transaction:
    def __init__(self, db):
        self.db = db

    def execute(self, sql, params):
        return self.db.execute(sql.replace(" FOR UPDATE", ""), params).rowcount

    def query(self, sql, params):
        return [dict(record) for record in self.db.execute(sql.replace(" FOR UPDATE", ""), params)]

    def query_one(self, sql, params):
        rows = self.query(sql, params)
        return rows[0] if rows else None


def install_database(path):
    db = sqlite3.connect(path, timeout=15, check_same_thread=False)
    db.row_factory = lambda cursor, values: {col[0].lower(): value for col, value in zip(cursor.description, values)}
    db.execute("PRAGMA foreign_keys=ON")
    def transaction(callback):
        db.execute("BEGIN IMMEDIATE")
        try:
            result = callback(Transaction(db))
            db.commit()
            return result
        except BaseException:
            db.rollback()
            raise
    return db, transaction


def permissions(actor, action="platform.manage"):
    if actor not in {"admin", "origin-a", "origin-b"} or action == "model_gateway.manage" and actor != "admin":
        raise PermissionError("Denied")
    return {"decision": "ALLOW"}


def audit(tx, actor, action, family, resource_id, outcome, reason):
    tx.execute("INSERT INTO AUDIT(ACTOR_ID,ACTION_NAME,RESOURCE_ID) VALUES(:actor,:action_name,:resource_id)",
               {"actor": actor, "action_name": action, "resource_id": resource_id})


@pytest.fixture
def ledger(tmp_path, monkeypatch):
    path = tmp_path / "coordinator.sqlite"
    db, transaction = install_database(path)
    db.executescript("""
        CREATE TABLE CX_PRINCIPALS(PRINCIPAL_ID TEXT PRIMARY KEY, STATUS TEXT);
        CREATE TABLE CX_LLM_PROVIDER_PROFILES(PROFILE_ID TEXT PRIMARY KEY, VERSION INTEGER, MODEL_ID TEXT, PROVIDER_URL TEXT, STATUS TEXT);
        CREATE TABLE CX_MODEL_USAGE(USAGE_ID TEXT PRIMARY KEY);
        CREATE TABLE AUDIT(ACTOR_ID TEXT,ACTION_NAME TEXT,RESOURCE_ID TEXT);
        INSERT INTO CX_PRINCIPALS VALUES('admin','ACTIVE'),('origin-a','ACTIVE'),('origin-b','ACTIVE'),('outsider','ACTIVE');
        INSERT INTO CX_LLM_PROVIDER_PROFILES VALUES('profile',1,'model','http://model.test:12345/v1','ACTIVE');
        INSERT INTO CX_LLM_PROVIDER_PROFILES VALUES('profile-alias',1,'model','http://alias.test/v1','ACTIVE');
        INSERT INTO CX_LLM_PROVIDER_PROFILES VALUES('new-profile',1,'model','http://model.test:12345/v1','ACTIVE');
    """)
    for statement in schema.schema_statements("pg"):
        db.execute(statement)
    db.commit()
    clock = [1000000]
    monkeypatch.setattr(capacity.connection, "execute_transaction_callback", transaction)
    monkeypatch.setattr(capacity, "_now_ms", lambda tx: clock[0])
    monkeypatch.setattr(capacity, "authorize", permissions)
    monkeypatch.setattr(capacity.identity_api, "_audit_tx", audit)
    group = capacity.create_group("admin", dict(resource_key="resource", coordinator_id="shared-authority", reason="Test coordinator", idempotency_key="group"))
    group_id = group["group_id"]
    for suffix in ("a", "b"):
        capacity.register_origin("admin", group_id, dict(origin_id="installation-" + suffix, principal_id="origin-" + suffix,
                                 installation_key="product-" + suffix, reason="Explicit participant", idempotency_key="origin-" + suffix))
    capacity.register_alias("admin", group_id, dict(endpoint_url="http://MODEL.test:12345/v1/", profile_id="profile", expected_version=1,
                            reason="Selected resource", idempotency_key="alias"))
    capacity.register_alias("admin", group_id, dict(endpoint_url="http://alias.test/v1", profile_id="profile-alias", expected_version=2,
                            reason="Same inference resource", idempotency_key="second-alias"))
    yield db, group_id, clock, path
    db.close()


def admission(key="request-a", suffix="a", **overrides):
    return dict(origin_id="installation-" + suffix, profile_id="profile", profile_version=1, model_id="model",
                endpoint_url="http://model.test:12345/v1", input_digest="a" * 64, credential_digest="b" * 64,
                source_kind="NATIVE", source_id="task-" + key, source_attempt_id="attempt-" + key,
                idempotency_key=key, reason="Frozen authorized input", **overrides)


def claim(record, key="dispatch"):
    return dict(expected_version=record["version"], fencing_token=record["fencing_token"], worker_key="worker-a",
                credential_digest="b" * 64, reason="Fresh authority checked", idempotency_key=key)


def observation(record, key="completion", kind="COMPLETE_RESPONSE", **overrides):
    values = dict(expected_version=record["version"], attempt_id=record["attempt_id"], fencing_token=record["fencing_token"],
                  evidence_digest="c" * 64, evidence_kind=kind, finish_code="PROVIDER_RESPONSE_COMPLETE", reason="Exact lifecycle observation", idempotency_key=key)
    return values | overrides


def dispatch(group_id, key="request-a"):
    record = capacity.admit("origin-a", group_id, admission(key))
    return capacity.begin_dispatch("origin-a", record["admission_id"], claim(record, "dispatch-" + key), reauthorize=lambda tx, record: None)


def test_alias_canonicalization_is_bounded_and_preserves_paths():
    assert capacity.endpoint_url("HTTP://Example.test:80/v1/") == "http://example.test/v1"
    assert capacity.alias_key("http://example.test/v1") == capacity.alias_key("http://EXAMPLE.test:80/v1/")
    assert capacity.alias_key("https://example.test/V1") != capacity.alias_key("https://example.test/v1")
    assert capacity.endpoint_url("http://[::1]:8080/v1") == "http://[::1]:8080/v1"
    for value in ("http://user:secret@example.test/v1", "http://example.test/v1?key=secret", "file:///model", "http://169.254.169.254"):
        with pytest.raises(ValueError):
            capacity.endpoint_url(value)


def test_aliases_and_new_profiles_share_one_durable_slot(ledger):
    db, group_id, _, _ = ledger
    first = dispatch(group_id)
    second_request = admission("request-b", "b") | dict(profile_id="profile-alias", endpoint_url="http://alias.test/v1")
    second = capacity.admit("origin-b", group_id, second_request)
    third = capacity.admit("origin-b", group_id, admission("new-profile", "b") | dict(profile_id="new-profile"))
    assert first["dispatch_authorized"] and first["status"] == "DISPATCHING"
    assert second["status"] == third["status"] == "QUEUED"
    assert db.execute("SELECT COUNT(*) AS n FROM CX_MODEL_ADMISSIONS WHERE STATUS IN ('RESERVED','DISPATCHING','UNKNOWN')").fetchone()["n"] == 1
    assert capacity.observe_completion("origin-a", first["admission_id"], observation(first))["status"] == "COMPLETED"
    assert capacity.read_admission("origin-b", third["admission_id"], reserve=True)["status"] == "QUEUED"
    assert capacity.read_admission("origin-b", second["admission_id"], reserve=True)["status"] == "RESERVED"


def test_duplicate_admission_is_exact_and_dispatch_receipt_never_resends(ledger):
    _, group_id, _, _ = ledger
    request = admission()
    record = capacity.admit("origin-a", group_id, request)
    replay = capacity.admit("origin-a", group_id, request)
    assert replay["replayed"] and record["admission_id"] == replay["admission_id"]
    with pytest.raises(ContinuityConflict, match="different request"):
        capacity.admit("origin-a", group_id, request | dict(input_digest="d" * 64))
    command = claim(record)
    sent = capacity.begin_dispatch("origin-a", record["admission_id"], command, reauthorize=lambda tx, value: None)
    repeated = capacity.begin_dispatch("origin-a", record["admission_id"], command,
                                       reauthorize=lambda tx, value: pytest.fail("Replay rechecked or sent"))
    assert sent["dispatch_authorized"] is True
    assert repeated["replayed"] and repeated["dispatch_authorized"] is False


def test_cancel_queued_or_reserved_sends_nothing_and_preserves_receipt(ledger):
    _, group_id, _, _ = ledger
    first = dispatch(group_id)
    queued = capacity.admit("origin-b", group_id, admission("queued", "b"))
    command = dict(expected_version=queued["version"], reason="User cancelled", idempotency_key="cancel")
    cancelled = capacity.cancel_admission("origin-b", queued["admission_id"], command)
    assert cancelled["status"] == "CANCELLED" and cancelled["cancel_state"] == "QUEUE_CANCELLED"
    assert not cancelled["occupies_capacity"] and cancelled["attempt_id"] is None
    assert capacity.cancel_admission("origin-b", queued["admission_id"], command)["replayed"]
    capacity.observe_completion("origin-a", first["admission_id"], observation(first))
    reserved = capacity.admit("origin-b", group_id, admission("reserved", "b"))
    cancelled = capacity.cancel_admission("origin-b", reserved["admission_id"], command | dict(expected_version=reserved["version"], idempotency_key="cancel-reserved"))
    with pytest.raises(ContinuityConflict):
        capacity.begin_dispatch("origin-b", reserved["admission_id"], claim(reserved), reauthorize=lambda tx, record: pytest.fail("Cancelled request sent"))
    assert cancelled["attempt_id"] is None


def test_cancel_after_send_keeps_capacity_until_exact_reconciliation(ledger):
    db, group_id, clock, _ = ledger
    first = dispatch(group_id)
    unknown = capacity.cancel_admission("origin-a", first["admission_id"], dict(expected_version=first["version"], reason="Local cancelled", idempotency_key="cancel"))
    assert unknown["status"] == "UNKNOWN" and unknown["occupies_capacity"]
    clock[0] += 8000000
    second = capacity.admit("origin-b", group_id, admission("after-cancel", "b"))
    assert second["status"] == "QUEUED"
    with pytest.raises(PermissionError):
        capacity.observe_completion("origin-b", unknown["admission_id"], observation(unknown, kind="OPERATOR_CONFIRMATION"), reconcile=True)
    with pytest.raises(ContinuityConflict):
        capacity.observe_completion("admin", unknown["admission_id"], observation(unknown, kind="OPERATOR_CONFIRMATION", attempt_id="foreign-attempt"), reconcile=True)
    evidence = observation(unknown, kind="OPERATOR_CONFIRMATION")
    done = capacity.observe_completion("admin", unknown["admission_id"], evidence, reconcile=True)
    assert done["status"] == "COMPLETED" and not done["occupies_capacity"]
    assert capacity.observe_completion("admin", unknown["admission_id"], evidence, reconcile=True)["replayed"]
    assert capacity.read_admission("origin-b", second["admission_id"], reserve=True)["status"] == "RESERVED"
    assert db.execute("SELECT COUNT(*) AS n FROM CX_MODEL_CAP_EVIDENCE").fetchone()["n"] == 1


def test_deadline_only_expires_unconsumed_reservations_and_fences_old_worker(ledger):
    _, group_id, clock, _ = ledger
    old = capacity.admit("origin-a", group_id, admission())
    clock[0] += 30001
    second = capacity.admit("origin-b", group_id, admission("next", "b"))
    assert second["status"] == "RESERVED"
    assert capacity.read_admission("origin-a", old["admission_id"])["status"] == "EXPIRED"
    with pytest.raises(ContinuityConflict):
        capacity.begin_dispatch("origin-a", old["admission_id"], claim(old), reauthorize=lambda tx, record: pytest.fail("Expired worker sent"))


def test_dispatch_deadline_and_restart_never_release_possible_send(ledger):
    db, group_id, clock, path = ledger
    first = dispatch(group_id)
    clock[0] += 600001
    next_request = capacity.admit("origin-b", group_id, admission("later", "b"))
    assert next_request["status"] == "QUEUED"
    record = capacity.read_admission("origin-a", first["admission_id"])
    assert record["status"] == "UNKNOWN" and record["occupies_capacity"]
    other, transaction = install_database(path)
    try:
        rows = transaction(lambda tx: tx.query("SELECT STATUS FROM CX_MODEL_ADMISSIONS WHERE ADMISSION_ID=:admission_id", {"admission_id": first["admission_id"]}))
        assert rows == [{"status": "UNKNOWN"}]
    finally:
        other.close()
    assert db.execute("SELECT COUNT(*) AS n FROM CX_MODEL_CAP_ATTEMPTS").fetchone()["n"] == 1


def test_revocation_fresh_credential_and_source_checks_precede_dispatch(ledger):
    _, group_id, _, _ = ledger
    record = capacity.admit("origin-a", group_id, admission())
    with pytest.raises(ContinuityConflict, match="credential"):
        capacity.begin_dispatch("origin-a", record["admission_id"], claim(record) | dict(credential_digest="d" * 64), reauthorize=lambda tx, record: None)
    def deny(tx, record):
        raise PermissionError("Original source grant was revoked")
    rejected = capacity.begin_dispatch("origin-a", record["admission_id"], claim(record), reauthorize=deny)
    assert rejected["status"] == "REJECTED" and not rejected["dispatch_authorized"] and rejected["attempt_id"] is None


def test_foreign_origin_ids_never_authorize_and_revoke_is_current(ledger):
    db, group_id, _, _ = ledger
    with pytest.raises(PermissionError):
        capacity.admit("origin-a", group_id, admission(suffix="b"))
    record = capacity.admit("origin-a", group_id, admission())
    with pytest.raises(PermissionError):
        capacity.read_admission("origin-b", record["admission_id"])
    capacity.change_origin("admin", group_id, "installation-a", dict(expected_version=1, status="REVOKED", reason="Participant revoked", idempotency_key="revoke"))
    with pytest.raises(PermissionError):
        capacity.begin_dispatch("origin-a", record["admission_id"], claim(record), reauthorize=lambda tx, record: pytest.fail("Revoked origin sent"))
    assert db.execute("SELECT COUNT(*) AS n FROM CX_MODEL_CAP_ATTEMPTS").fetchone()["n"] == 0


def test_policy_changes_reject_old_reservations_but_preserve_unknown(ledger):
    _, group_id, _, _ = ledger
    first = dispatch(group_id)
    unknown = capacity.observe_completion("origin-a", first["admission_id"], observation(first, kind="TRANSPORT_UNKNOWN"))
    revision = dict(expected_version=3, policy=dict(capacity=1), status="DRAINING", reason="Drain resource", idempotency_key="drain")
    assert capacity.revise_group("admin", group_id, revision)["version"] == 4
    assert capacity.read_admission("origin-a", unknown["admission_id"])["occupies_capacity"]
    with pytest.raises(ContinuityConflict, match="no new"):
        capacity.admit("origin-b", group_id, admission("blocked", "b"))


def test_profile_url_or_version_changes_cannot_bypass_alias_binding(ledger):
    db, group_id, _, _ = ledger
    record = capacity.admit("origin-a", group_id, admission())
    db.execute("UPDATE CX_LLM_PROVIDER_PROFILES SET PROVIDER_URL='http://other.test/v1',VERSION=2 WHERE PROFILE_ID='profile'")
    db.commit()
    assert capacity.read_admission("origin-a", record["admission_id"], reserve=True)["status"] == "REJECTED"
    with pytest.raises(PermissionError):
        capacity.admit("origin-a", group_id, admission("changed"))


def test_known_completed_refusal_frees_transport_slot_and_unknown_retains_failure_evidence(ledger):
    db, group_id, _, _ = ledger
    record = dispatch(group_id)
    unknown = capacity.observe_completion("origin-a", record["admission_id"], observation(record, kind="TRANSPORT_UNKNOWN", finish_code="READ_TIMEOUT"))
    done = capacity.observe_completion("origin-a", unknown["admission_id"], observation(unknown, key="late-completion", finish_code="PROVIDER_REFUSAL"))
    assert done["status"] == "COMPLETED" and done["finish_code"] == "PROVIDER_REFUSAL"
    assert db.execute("SELECT COUNT(*) AS n FROM CX_MODEL_CAP_EVIDENCE").fetchone()["n"] == 2
    assert capacity.admit("origin-b", group_id, admission("next", "b"))["status"] == "RESERVED"


def test_required_audit_failure_rolls_back_admission_and_queue_counter(ledger, monkeypatch):
    db, group_id, _, _ = ledger
    def fail(*args):
        raise RuntimeError("Audit unavailable")
    monkeypatch.setattr(capacity.identity_api, "_audit_tx", fail)
    with pytest.raises(RuntimeError):
        capacity.admit("origin-a", group_id, admission())
    assert db.execute("SELECT COUNT(*) AS n FROM CX_MODEL_ADMISSIONS").fetchone()["n"] == 0
    assert db.execute("SELECT NEXT_SEQUENCE FROM CX_MODEL_CAP_GROUPS").fetchone()["next_sequence"] == 1


def test_capacity_management_http_uses_session_identity_and_bounded_contracts(ledger):
    from fastapi import FastAPI, HTTPException
    from fastapi.testclient import TestClient
    from lib import agent_extension_http
    _, group_id, _, _ = ledger
    actor = ["admin"]
    def require_action(action):
        def principal():
            try:
                permissions(actor[0], action)
            except PermissionError:
                raise HTTPException(status_code=403) from None
            return {"principal_id": actor[0]}
        return principal
    app = FastAPI()
    agent_extension_http.install(app, require_action)
    with TestClient(app) as client:
        groups = client.get("/api/model-endpoint-capacity/groups")
        assert groups.status_code == 200 and groups.json()["groups"][0]["group_id"] == group_id
        current = client.get("/api/model-endpoint-capacity/groups/" + group_id).json()
        assert current["coordination_scope"] == "ONE_DATABASE_AUTHORITY" and len(current["origins"]) == 2
        invalid = client.post("/api/model-endpoint-capacity/groups/" + group_id + "/origins", json=dict(
            origin_id="forged", principal_id="origin-b", installation_key="product", actor="admin", reason="Test", idempotency_key="forge"))
        assert invalid.status_code == 422
        record = dispatch(group_id)
        page = client.get(f"/api/model-endpoint-capacity/groups/{group_id}/admissions?limit=1")
        assert page.status_code == 200 and page.json()["items"][0]["admission_id"] == record["admission_id"]
        assert page.json()["next_sequence"] is None
        assert "credential_digest" not in page.text and "input_digest" not in page.text
        actor[0] = "origin-b"
        assert client.get("/api/model-endpoint-capacity/admissions/" + record["admission_id"]).status_code == 403
        assert client.post("/api/model-endpoint-capacity/admissions/" + record["admission_id"] + "/reconcile", json=observation(record, kind="OPERATOR_CONFIRMATION")).status_code == 403
        assert client.get("/api/model-endpoint-capacity/groups").status_code == 403
        assert client.get(f"/api/model-endpoint-capacity/groups/{group_id}/admissions").status_code == 403


def test_operator_admission_pages_are_bounded_and_do_not_mutate_requests(ledger):
    db, group_id, _, _ = ledger
    identifiers = [capacity.admit("origin-a", group_id, admission(f"page-{index}"))["admission_id"] for index in range(5)]
    initial = list(db.execute("SELECT STATUS,VERSION FROM CX_MODEL_ADMISSIONS ORDER BY QUEUE_SEQUENCE"))
    page = capacity.list_group_admissions("admin", group_id, limit=2)
    assert [value["admission_id"] for value in page["items"]] == identifiers[:2] and page["next_sequence"] == 2
    second = capacity.list_group_admissions("admin", group_id, after_sequence=2, limit=2)
    last = capacity.list_group_admissions("admin", group_id, after_sequence=second["next_sequence"], limit=2)
    assert [value["admission_id"] for value in last["items"]] == identifiers[4:] and last["next_sequence"] is None
    assert list(db.execute("SELECT STATUS,VERSION FROM CX_MODEL_ADMISSIONS ORDER BY QUEUE_SEQUENCE")) == initial
    with pytest.raises(PermissionError):
        capacity.list_group_admissions("origin-a", group_id)
    with pytest.raises(ValueError):
        capacity.list_group_admissions("admin", group_id, limit=51)


def test_historical_package_does_not_register_capacity_routes(monkeypatch):
    from fastapi import FastAPI
    from lib import agent_extension_http, edition_features
    monkeypatch.setattr(edition_features, "MODEL_RUNTIME_CONTEXT_ENABLED", False)
    app = FastAPI()
    agent_extension_http.install(app, lambda action: lambda: {"principal_id": "admin"})
    assert not any("/model-endpoint-capacity/" in route.path for route in app.routes)


def test_policy_revision_fences_an_unconsumed_reservation(ledger):
    _, group_id, _, _ = ledger
    reserved = capacity.admit("origin-a", group_id, admission())
    capacity.revise_group("admin", group_id, dict(expected_version=3, policy=dict(capacity=1), reason="Revise exact policy", idempotency_key="revision"))
    outcome = capacity.begin_dispatch("origin-a", reserved["admission_id"], claim(reserved), reauthorize=lambda tx, record: pytest.fail("Stale policy sent"))
    assert outcome["status"] == "REJECTED" and not outcome["dispatch_authorized"]


def test_queue_and_overall_deadlines_do_not_change_on_refresh(ledger):
    _, group_id, clock, _ = ledger
    dispatch(group_id)
    queued = capacity.admit("origin-b", group_id, admission("queued", "b"))
    deadlines = queued["queue_until_ms"], queued["overall_until_ms"]
    clock[0] += 59999
    for _ in range(3):
        assert capacity.read_admission("origin-b", queued["admission_id"], reserve=True)["queue_until_ms"] == deadlines[0]
    clock[0] += 2
    expired = capacity.read_admission("origin-b", queued["admission_id"], reserve=True)
    assert expired["status"] == "EXPIRED" and expired["overall_until_ms"] == deadlines[1] and expired["attempt_id"] is None


def test_reservation_denial_and_its_audit_roll_back_together(ledger, monkeypatch):
    db, group_id, _, _ = ledger
    reserved = capacity.admit("origin-a", group_id, admission())
    monkeypatch.setattr(capacity.identity_api, "_audit_tx", lambda *args: (_ for _ in ()).throw(RuntimeError("Audit unavailable")))
    with pytest.raises(RuntimeError):
        capacity.begin_dispatch("origin-a", reserved["admission_id"], claim(reserved), reauthorize=lambda tx, record: None)
    assert db.execute("SELECT STATUS FROM CX_MODEL_ADMISSIONS").fetchone()["status"] == "RESERVED"
    assert db.execute("SELECT COUNT(*) AS n FROM CX_MODEL_CAP_ATTEMPTS").fetchone()["n"] == 0


def test_credential_or_principal_revocation_blocks_replayed_dispatch(ledger):
    db, group_id, _, _ = ledger
    reserved = capacity.admit("origin-a", group_id, admission())
    db.execute("UPDATE CX_PRINCIPALS SET STATUS='REVOKED' WHERE PRINCIPAL_ID='origin-a'")
    db.commit()
    with pytest.raises(PermissionError):
        capacity.begin_dispatch("origin-a", reserved["admission_id"], claim(reserved), reauthorize=lambda tx, record: pytest.fail("Revoked principal sent"))
    assert db.execute("SELECT COUNT(*) AS n FROM CX_MODEL_CAP_ATTEMPTS").fetchone()["n"] == 0


def test_completion_reconciliation_race_preserves_one_resolution(ledger):
    db, group_id, _, _ = ledger
    sent = dispatch(group_id)
    unknown = capacity.observe_completion("origin-a", sent["admission_id"], observation(sent, kind="TRANSPORT_UNKNOWN"))
    capacity.observe_completion("admin", sent["admission_id"], observation(unknown, kind="OPERATOR_CONFIRMATION", key="reconcile"), reconcile=True)
    with pytest.raises(ContinuityConflict):
        capacity.observe_completion("origin-a", sent["admission_id"], observation(unknown, key="late-response"))
    assert db.execute("SELECT COUNT(*) AS n FROM CX_MODEL_CAP_EVIDENCE").fetchone()["n"] == 2


def test_timestamps_support_current_epoch_without_postgres_int32_overflow():
    statements = schema.schema_statements("pg")
    for statement in statements:
        if "CREATED_AT_MS" in statement:
            assert "CREATED_AT_MS DECIMAL(19,0)" in statement
    assert "DISPATCH_AT_MS DECIMAL(19,0)" in statements[6]


def test_selected_native_route_requires_authenticated_context_before_send(ledger, monkeypatch):
    from lib import config, model_dispatch, native_runtime, provider_capability_probes
    from types import SimpleNamespace
    _, _, _, _ = ledger
    profile = dict(profile_id="profile", version=1, provider_url="http://model.test:12345/v1", model_id="model")
    monkeypatch.setattr(config, "get_config", lambda: SimpleNamespace(llm=config.LLMConfig(request_timeout_seconds=180)))
    monkeypatch.setattr(provider_capability_probes, "apply_parameters", lambda profile, payload: payload)
    monkeypatch.setattr(native_runtime.urllib.request, "urlopen", lambda *args, **kwargs: pytest.fail("Unadapted route sent"))
    with pytest.raises(PermissionError, match="authenticated supported dispatch"):
        native_runtime._call_llm(profile, [{"role": "user", "content": "question"}])
    assert model_dispatch._context.get() is None


def test_selected_native_completions_release_transport_on_output_denial(ledger, monkeypatch):
    from lib import config, content_security, model_dispatch, native_runtime, provider_capability_probes
    from types import SimpleNamespace
    import json
    db, _, _, _ = ledger
    profile = dict(profile_id="profile", version=1, provider_url="http://model.test:12345/v1", model_id="model")
    monkeypatch.setattr(config, "get_config", lambda: SimpleNamespace(llm=config.LLMConfig(request_timeout_seconds=180)))
    monkeypatch.setattr(provider_capability_probes, "apply_parameters", lambda profile, payload: payload)
    sends = []
    class Response:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def read(self, size):
            return json.dumps({"model": "model", "choices": [{"message": {"content": "unsafe"}, "finish_reason": "stop"}]}).encode()
    def send(*args, **kwargs):
        sends.append(1)
        return Response()
    monkeypatch.setattr(model_dispatch, "open_controlled", send)
    original_enforce = content_security.enforce
    def deny(text, stage):
        if stage == "OUTPUT":
            raise content_security.ContentDenied({"code": "CONTENT_DENIED"})
        return original_enforce(text, stage)
    monkeypatch.setattr(content_security, "enforce", deny)
    with model_dispatch.authenticated_context("origin-a", "NATIVE", "execution", "attempt", credential_digest="b" * 64,
            worker_key="worker", reauthorize=lambda tx, record: None):
        with pytest.raises(content_security.ContentDenied):
            native_runtime._call_llm(profile, [{"role": "user", "content": "question"}])
    assert sends == [1]
    assert db.execute("SELECT STATUS FROM CX_MODEL_ADMISSIONS").fetchone()["status"] == "COMPLETED"
    assert model_dispatch._context.get() is None


def test_unknown_native_send_keeps_capacity_and_duplicate_never_sends(ledger, monkeypatch):
    from lib import config, model_dispatch, native_runtime, provider_capability_probes
    from types import SimpleNamespace
    db, group_id, _, _ = ledger
    profile = dict(profile_id="profile", version=1, provider_url="http://model.test:12345/v1", model_id="model")
    monkeypatch.setattr(config, "get_config", lambda: SimpleNamespace(llm=config.LLMConfig(request_timeout_seconds=180)))
    monkeypatch.setattr(provider_capability_probes, "apply_parameters", lambda profile, payload: payload)
    sends = []
    def send(*args, **kwargs):
        sends.append(1)
        raise TimeoutError("Unknown remote outcome")
    monkeypatch.setattr(model_dispatch, "open_controlled", send)
    with model_dispatch.authenticated_context("origin-a", "NATIVE", "execution", "attempt", credential_digest="b" * 64,
            worker_key="worker", reauthorize=lambda tx, record: None):
        with pytest.raises(RuntimeError, match="request failed"):
            native_runtime._call_llm(profile, [{"role": "user", "content": "question"}])
        with pytest.raises(ContinuityConflict):
            native_runtime._call_llm(profile, [{"role": "user", "content": "question"}])
    assert sends == [1]
    assert db.execute("SELECT STATUS FROM CX_MODEL_ADMISSIONS").fetchone()["status"] == "UNKNOWN"
    queued = capacity.admit("origin-b", group_id, admission("next", "b"))
    assert queued["status"] == "QUEUED"


def test_independent_local_http_peer_observes_serial_supported_requests(ledger, monkeypatch):
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from concurrent.futures import ThreadPoolExecutor
    from threading import Lock, Thread
    from types import SimpleNamespace
    from lib import config, model_dispatch, native_runtime, provider_capability_probes
    import json
    import time
    db, group_id, _, path = ledger
    active, maximum, sends = [0], [0], []
    lock = Lock()
    class Peer(BaseHTTPRequestHandler):
        def do_POST(self):
            payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            with lock:
                active[0] += 1
                maximum[0] = max(maximum[0], active[0])
                sends.append(payload)
            time.sleep(0.04)
            body = json.dumps({"model": "model", "choices": [{"message": {"content": "answer"}, "finish_reason": "stop"}]}).encode()
            with lock:
                active[0] -= 1
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        def log_message(self, *args):
            pass
    peer = ThreadingHTTPServer(("127.0.0.1", 0), Peer)
    thread = Thread(target=peer.serve_forever, daemon=True)
    thread.start()
    url = "http://127.0.0.1:" + str(peer.server_address[1]) + "/v1"
    db.execute("UPDATE CX_LLM_PROVIDER_PROFILES SET PROVIDER_URL=:endpoint_url WHERE PROFILE_ID='profile'", {"endpoint_url": url})
    db.commit()
    capacity.register_alias("admin", group_id, dict(endpoint_url=url, profile_id="profile", expected_version=3, reason="Independent local peer", idempotency_key="local-peer"))
    def transaction(callback):
        isolated, perform = install_database(path)
        try:
            return perform(callback)
        finally:
            isolated.close()
    monkeypatch.setattr(capacity.connection, "execute_transaction_callback", transaction)
    monkeypatch.setattr(config, "get_config", lambda: SimpleNamespace(llm=config.LLMConfig(request_timeout_seconds=180)))
    monkeypatch.setattr(provider_capability_probes, "apply_parameters", lambda profile, payload: payload)
    profile = dict(profile_id="profile", version=1, provider_url=url, model_id="model")
    def request(suffix):
        with model_dispatch.authenticated_context("origin-" + suffix, "NATIVE", "execution-" + suffix, "attempt-" + suffix,
                credential_digest="b" * 64, worker_key="worker-" + suffix, reauthorize=lambda tx, record: None):
            return native_runtime._call_llm(profile, [{"role": "user", "content": "question " + suffix}])
    try:
        with ThreadPoolExecutor(max_workers=2) as workers:
            futures = [workers.submit(request, suffix) for suffix in ("a", "b")]
            outputs = [future.result(timeout=15) for future in futures]
        assert [output["content"] for output in outputs] == ["answer", "answer"]
        assert all(output["request_id"] for output in outputs)
        assert maximum[0] == 1 and len(sends) == 2
        assert db.execute("SELECT COUNT(*) AS n FROM CX_MODEL_ADMISSIONS WHERE STATUS='COMPLETED'").fetchone()["n"] == 2
    finally:
        peer.shutdown()
        peer.server_close()
        thread.join(timeout=5)


def _process_competitor(path, group_id, suffix, ready, start, results):
    # Independent interpreters/connections share a single SQL coordinator.
    from lib import model_endpoint_capacity as service
    db, transaction = install_database(path)
    service.connection.execute_transaction_callback = transaction
    service.authorize = permissions
    service.identity_api._audit_tx = audit
    service._now_ms = lambda tx: 1000000
    ready.put(suffix)
    start.wait(15)
    try:
        record = service.admit("origin-" + suffix, group_id, admission("parallel-" + suffix, suffix))
        if record["status"] == "RESERVED":
            record = service.begin_dispatch("origin-" + suffix, record["admission_id"], claim(record, "dispatch-" + suffix), reauthorize=lambda tx, value: None)
        results.put((suffix, record["status"], record.get("dispatch_authorized", False)))
    except BaseException as exc:
        results.put((suffix, type(exc).__name__, False))
    finally:
        db.close()


def test_independent_processes_get_at_most_one_dispatch_authority(ledger):
    db, group_id, _, path = ledger
    context = multiprocessing.get_context("spawn")
    ready, results, start = context.Queue(), context.Queue(), context.Event()
    processes = [context.Process(target=_process_competitor, args=(str(path), group_id, suffix, ready, start, results)) for suffix in ("a", "b")]
    try:
        for process in processes:
            process.start()
        assert {ready.get(timeout=20), ready.get(timeout=20)} == {"a", "b"}
        start.set()
        observed = [results.get(timeout=20), results.get(timeout=20)]
        assert sorted(item[1] for item in observed) == ["DISPATCHING", "QUEUED"]
        assert sum(item[2] for item in observed) == 1
        assert db.execute("SELECT COUNT(*) AS n FROM CX_MODEL_CAP_ATTEMPTS").fetchone()["n"] == 1
    finally:
        for process in processes:
            process.join(timeout=10)
            if process.is_alive():
                process.terminate()
                process.join(timeout=5)
        for queue in (ready, results):
            queue.close()
            queue.join_thread()


@pytest.mark.parametrize("dialect", ["pg", "oracle", "yashandb"])
def test_schema_is_additive_typed_and_no_opaque_queue_authority(dialect):
    ddl = schema.schema_statements(dialect)
    assert len(ddl) == 18
    assert all(statement.startswith("CREATE TABLE ") for statement in ddl)
    assert all(" JSON" not in statement and " CIPHER" not in statement for statement in ddl)
    assert {statement.split()[2] for statement in ddl} == {
        "CX_MODEL_CAP_GROUPS", "CX_MODEL_CAP_REVISIONS", "CX_MODEL_CAP_ORIGINS", "CX_MODEL_CAP_ALIASES",
        "CX_MODEL_CAP_BINDINGS", "CX_MODEL_ADMISSIONS", "CX_MODEL_CAP_ATTEMPTS", "CX_MODEL_CAP_EVIDENCE",
        "CX_MODEL_CAP_REQUESTS", "CX_RUNTIME_MODEL_CREDENTIALS", "CX_MODEL_RUNTIME_OBSERVATIONS", "CX_MODEL_USAGE_DETAILS",
        "CX_MODEL_COORD_BINDINGS", "CX_MODEL_COORD_ROUTES", "CX_MODEL_ORIGIN_RECEIPTS", "CX_MODEL_COORD_REQUESTS", "CX_MODEL_ORIGIN_OBSERVATIONS", "CX_MODEL_ORIGIN_RESOLUTIONS",
    }
