"""Gateway review regressions with synthetic credentials and no provider I/O."""
import json

import pytest

from lib import edition_features, model_usage_api as gateway


MESSAGES = [{"role": "user", "content": "shared known question"}]
ORIGINAL_PROFILE = "profile-A"
ORIGINAL_AGENT = "agent-A"
ORIGINAL_CREDENTIAL = "credential-A"


@pytest.fixture
def review(monkeypatch):
    state = {"profile": ORIGINAL_PROFILE, "agent": ORIGINAL_AGENT, "credential": ORIGINAL_CREDENTIAL,
             "existing": True, "writes": [], "replays": [], "sends": [], "settlements": [],
             "profile_status": "ACTIVE", "agent_status": "ACTIVE", "credential_status": "ACTIVE",
             "revoke_on_transaction": None}
    monkeypatch.setattr(edition_features, "MODEL_RUNTIME_CONTEXT_ENABLED", True)

    def query(sql, params):
        if "FROM CX_MODEL_GATEWAY_CREDENTIALS" in sql:
            if state["credential_status"] != "ACTIVE":
                return None
            return {"credential_id": state["credential"], "created_by": "owner", "scopes_json": json.dumps([
                "model.forward", "profile:" + state["profile"], "agent:" + state["agent"]])}
        if "FROM CX_LLM_PROVIDER_PROFILES" in sql:
            return {"profile_id": state["profile"], "profile_key": "provider", "model_id": "model", "version": 1,
                    "status": state["profile_status"]}
        if "FROM CX_PRINCIPALS" in sql:
            return {"status": state["agent_status"]}
        if "FROM CX_MODEL_REQUESTS" in sql:
            if not state["existing"]:
                return None
            return {"request_id": "original-request", "input_digest": gateway._digest(MESSAGES), "status": "SUCCEEDED",
                    "profile_id": ORIGINAL_PROFILE, "agent_id": ORIGINAL_AGENT, "credential_id": ORIGINAL_CREDENTIAL,
                    "actor_principal_id": "owner"}
        raise AssertionError("Unexpected synthetic query")

    class InMemoryTransaction:
        def query_one(self, sql, params):
            return query(sql, params)

        def execute(self, sql, params):
            state["writes"].append((sql, dict(params)))
            return 1

    def replay(request, **kwargs):
        assert isinstance(kwargs.get("transaction"), InMemoryTransaction)
        state["replays"].append(request)
        return {"request_id": request, "content": "private original Agent A response"}

    def send(*args, **kwargs):
        state["sends"].append((args, kwargs))
        return {"content": "safe answer withheld on settlement failure", "model": "model", "finish_reason": "stop",
                "usage": {"prompt_tokens": 4, "completion_tokens": 2, "total_tokens": 6},
                "usage_observation": "PROVIDER_REPORTED", "usage_field_provenance": {},
                "request_complete": True, "request_id": "runtime-request"}

    monkeypatch.setattr(gateway.connection, "execute_query_one", query)
    def transaction(callback):
        if state["revoke_on_transaction"]:
            state[state["revoke_on_transaction"] + "_status"] = "REVOKED"
        return callback(InMemoryTransaction())
    monkeypatch.setattr(gateway.connection, "execute_transaction_callback", transaction)
    monkeypatch.setattr(gateway.connection, "execute", lambda sql, params: state["writes"].append((sql, dict(params))) or 1)
    monkeypatch.setattr(gateway.model_governance_api, "replay_snapshot", replay)
    monkeypatch.setattr(gateway.model_governance_api, "reserve_quota", lambda *_args: {"warnings": []})
    monkeypatch.setattr(gateway, "_gateway_send", send)
    return state


def forward(state, *, stream=False):
    options = {"agent_id": state["agent"], "gateway_token": "cxgw_synthetic", "idempotency_key": "known-original-key"}
    if stream:
        return list(gateway.stream_forward("", state["profile"], MESSAGES, **options))
    return gateway.forward("", state["profile"], MESSAGES, **options)


@pytest.mark.parametrize("field,replacement", (("profile", "profile-B"), ("agent", "agent-B"), ("credential", "credential-B")))
def test_scoped_credential_cannot_replay_another_original_resource_or_credential(review, field, replacement):
    # Real Gateway token parsing/scopes still run; only database I/O is replaced.
    # Knowing the original prompt and idempotency key must not grant its result.
    review[field] = replacement
    with pytest.raises((PermissionError, gateway.ModelUsageConflict)):
        forward(review)
    assert review["replays"] == review["sends"] == review["writes"] == []


def test_exact_original_gateway_binding_replays_without_new_generation(review):
    value = forward(review)
    assert value["request_id"] == "original-request"
    assert review["replays"] == ["original-request"] and review["sends"] == []


@pytest.mark.parametrize("resource", ("agent", "profile", "credential"))
def test_revocation_between_entry_authorization_and_replay_transaction_denies_disclosure(review, resource):
    review["revoke_on_transaction"] = resource
    with pytest.raises(PermissionError):
        forward(review)
    assert review["replays"] == review["sends"] == []


@pytest.mark.parametrize("stream", (False, True))
def test_continuous_settlement_failure_preserves_safe_result_and_updates_request(review, monkeypatch, stream):
    review["existing"] = False

    def unavailable(*args, **kwargs):
        review["settlements"].append(args)
        raise RuntimeError("synthetic private quota ledger failure")

    monkeypatch.setattr(gateway, "_write_usage", unavailable)
    with pytest.raises(gateway.ModelUsageError) as failure:
        forward(review, stream=stream)
    assert len(review["sends"]) == 1 and not review["replays"]
    assert "synthetic private" not in str(failure.value)
    updates = [(sql, params) for sql, params in review["writes"] if sql.startswith("UPDATE CX_MODEL_REQUESTS")]
    assert any(params.get("status") in {"FAILED", "INCOMPLETE"} or "STATUS='FAILED'" in sql or "STATUS='INCOMPLETE'" in sql
               for sql, params in updates)
    assert all(params.get("error") not in {"PROVIDER_UNAVAILABLE", "STREAM_INTERRUPTED"} for _sql, params in updates)
    # Error wrappers may preserve the safe observation on their cause. Never
    # retain the answer body or arbitrary underlying ledger exception text.
    observed = None
    error, seen = failure.value, set()
    while error is not None and id(error) not in seen:
        seen.add(id(error))
        observed = observed or getattr(error, "model_observation", None)
        error = error.__cause__ or error.__context__
    assert observed is not None and observed["request_complete"] is True
    assert observed["usage"]["total_tokens"] == 6
    assert "answer withheld" not in json.dumps(observed)
