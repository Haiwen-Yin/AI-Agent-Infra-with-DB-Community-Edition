"""HTTP contracts keep recovery Human-only and never accept transport proofs."""
from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.testclient import TestClient
import pytest

from lib import processing_recovery as recovery, processing_recovery_http as http
from lib.continuity_state import ContinuityError
from .test_v502_processing_recovery import ledger, observe, finish, decision


@pytest.fixture
def endpoint(ledger):
    identity = {"principal_id": "human"}
    actions = []
    def require_action(action):
        actions.append(action)
        return lambda: identity
    def invoke(operation, session, *args, **kwargs):
        try:
            return operation(session["principal_id"], *args, **kwargs)
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc
        except ContinuityError as exc:
            raise HTTPException(409, {"code": exc.code, "message": str(exc)}) from exc
    app = FastAPI()
    router = APIRouter()
    http.install(router, "/api/agent-extensions", invoke, require_action)
    app.include_router(router)
    return ledger, TestClient(app), identity, actions


ROOT = "/api/agent-extensions/processing"


def test_read_is_paginated_metadata_and_does_not_mutate_or_generate(endpoint):
    ledger, client, _, actions = endpoint
    for number in range(3):
        observe(ledger, "FAILED", key="failure" + str(number))
    before = ledger.db.total_changes
    response = client.get(ROOT + "/" + ledger.target["continuity_id"], params={"limit": 2})
    assert response.status_code == 200
    page = response.json()
    assert len(page["observations"]) == 2 and page["next_cursor"]
    assert page["observations"][0]["target"]["attempt_id"] == ledger.attempt["attempt_id"]
    assert page["generation_requested"] is False
    assert "workspaces.read" in actions and "workspaces.write" in actions
    assert ledger.db.total_changes == before
    next_page = client.get(ROOT + "/" + ledger.target["continuity_id"], params={"after": page["next_cursor"], "limit": 2}).json()
    assert len(next_page["observations"]) == 1
    assert not set(item["block_id"] for item in page["observations"]) & set(item["block_id"] for item in next_page["observations"])


def test_retry_receipt_replays_and_does_not_dispatch(endpoint):
    ledger, client, _, _ = endpoint
    block = observe(ledger)
    finish(ledger)
    body = decision(ledger, block)
    first = client.post(ROOT + "/retries", json=body)
    second = client.post(ROOT + "/retries", json=body)
    assert first.status_code == second.status_code == 200
    assert first.json()["recovery_id"] == second.json()["recovery_id"]
    assert second.json()["replayed"] and not first.json()["dispatched"]
    assert ledger.count("CX_TASK_CONTINUITY_ATTEMPTS") == 1


@pytest.mark.parametrize("field,value", [("max_requests", 999999), ("policy", {"max_steps": 100}), ("passed", True)])
def test_http_cannot_choose_initial_policy_or_approve_its_own_result(endpoint, field, value):
    ledger, client, _, _ = endpoint
    block = observe(ledger)
    finish(ledger)
    assert client.post(ROOT + "/retries", json={**decision(ledger, block), field: value}).status_code == 422
    assert ledger.count("CX_PROCESSING_RECOVERIES") == 0


def test_agent_cannot_admit_human_retry_even_with_route_scope(endpoint):
    ledger, client, identity, _ = endpoint
    block = observe(ledger)
    finish(ledger)
    identity["principal_id"] = "agent"
    assert client.post(ROOT + "/retries", json=decision(ledger, block)).status_code == 403
    assert ledger.count("CX_PROCESSING_RECOVERIES") == 0


def resolution_body(ledger, block, **values):
    return dict(expected_version=int(block["version"]), target=ledger.target, reason="Explicit original request review",
                idempotency_key="resolution", **values)


@pytest.mark.parametrize("value", [{"mode": "TERMINAL_RESPONSE"}, {"evidence_kind": "TERMINAL_RESPONSE"}, {"request_complete": True}])
def test_http_cannot_claim_provider_terminal_evidence(endpoint, value):
    ledger, client, _, _ = endpoint
    finish(ledger, "UNOBSERVED")
    block = observe(ledger, "POSSIBLE_SEND")
    assert client.post(ROOT + "/blocks/" + block["block_id"] + "/reconcile", json=resolution_body(ledger, block, **value)).status_code == 422
    assert ledger.count("CX_PROCESSING_RESOLUTIONS") == 0


def test_read_original_preserves_unknown_and_explicit_human_resolution_retains_its_kind(endpoint):
    ledger, client, _, _ = endpoint
    finish(ledger, "UNOBSERVED")
    block = observe(ledger, "POSSIBLE_SEND")
    path = ROOT + "/blocks/" + block["block_id"] + "/reconcile"
    unknown = client.post(path, json=resolution_body(ledger, block))
    assert unknown.status_code == 200 and unknown.json()["status"] == "UNOBSERVED"
    body = resolution_body(ledger, block, mode="OPERATOR_RESOLUTION", outcome="FAILED")
    result = client.post(path, json=body)
    replay = client.post(path, json=body)
    assert result.status_code == replay.status_code == 200
    assert result.json()["status"] == "FAILED" and replay.json()["replayed"]
    facts = ledger.query("SELECT EVIDENCE_KIND,OUTCOME FROM CX_PROCESSING_RESOLUTIONS ORDER BY CREATED_AT", {})
    assert {item["evidence_kind"] for item in facts} == {"LOCAL_LIFECYCLE", "OPERATOR_RESOLUTION"}
    assert ledger.count("CX_TASK_CONTINUITY_ATTEMPTS") == 1


def test_native_dispatch_without_trusted_original_adapter_fails_closed(endpoint):
    ledger, client, _, _ = endpoint
    block = observe(ledger)
    finish(ledger)
    receipt = client.post(ROOT + "/retries", json=decision(ledger, block)).json()
    result = client.post(ROOT + "/recoveries/" + receipt["recovery_id"] + "/dispatch", json={})
    assert result.status_code == 409
    assert result.json()["detail"]["code"] == "RECOVERY_DISPATCH_ADAPTER_REQUIRED"
    assert ledger.count("CX_TASK_CONTINUITY_ATTEMPTS") == 1


def test_historical_release_installs_no_new_routes(monkeypatch):
    from lib import edition_features
    monkeypatch.setattr(edition_features, "MODEL_RUNTIME_CONTEXT_ENABLED", False, raising=False)
    router = APIRouter()
    http.install(router, "/api", None, None)
    assert not router.routes
