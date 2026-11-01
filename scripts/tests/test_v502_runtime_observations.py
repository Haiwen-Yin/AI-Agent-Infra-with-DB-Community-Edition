"""Real relational dispatch observations with synthetic bounded HTTP replies."""
import io
import json
from types import SimpleNamespace

import pytest

from lib import config, model_credentials, model_dispatch, model_observations, native_runtime, provider_capability_probes
from .test_v502_model_capacity import ledger


@pytest.fixture
def route(ledger, monkeypatch):
    db, _, _, _ = ledger
    monkeypatch.setattr(config, "get_config", lambda: SimpleNamespace(llm=config.LLMConfig(request_timeout_seconds=180)))
    monkeypatch.setattr(provider_capability_probes, "apply_parameters", lambda profile, payload: payload)
    profile = dict(profile_id="profile", version=1, provider_url="http://model.test:12345/v1", model_id="model")
    sends = []
    def install(reply):
        class Response(io.BytesIO):
            read1 = None  # Synthetic finite body; production uses bounded sockets.
            def __enter__(self): return self
            def __exit__(self, *_): self.close()
        def send(*args, **kwargs):
            sends.append(1)
            return Response(reply if isinstance(reply, bytes) else json.dumps(reply).encode())
        monkeypatch.setattr(model_dispatch, "open_controlled", send)
    def authorization():
        return model_dispatch.authenticated_context("origin-a", "NATIVE", "execution", "attempt", credential_digest="b" * 64,
            worker_key="worker", reauthorize=lambda tx, record: None)
    return db, profile, sends, install, authorization


def reply(finish="stop", usage=None):
    return {"model": "model", "choices": [{"message": {"content": "safe answer", "reasoning_content": "hidden reasoning"},
            "finish_reason": finish}], **({"usage": usage} if usage is not None else {})}


def test_native_observation_reuses_exact_source_request_and_retains_counts(route):
    db, profile, sends, install, authorization = route
    install(reply(usage={"prompt_tokens": 100, "completion_tokens": 20, "prompt_tokens_details": {"cached_tokens": 40},
                         "completion_tokens_details": {"reasoning_tokens": 5}, "cache_creation_input_tokens": 3}))
    with authorization():
        result = native_runtime._call_llm(profile, [{"role": "user", "content": "protected input"}])
    record = db.execute("SELECT a.SOURCE_ID,a.SOURCE_ATTEMPT_ID,o.* FROM CX_MODEL_ADMISSIONS a "
                        "JOIN CX_MODEL_RUNTIME_OBSERVATIONS o ON o.ADMISSION_ID=a.ADMISSION_ID").fetchone()
    assert result["request_id"] == record["admission_id"] and record["source_id"] == "execution"
    assert record["source_attempt_id"] == "attempt" and record["result_state"] == "COMPLETED"
    assert record["total_tokens"] == 120 and record["cached_tokens"] == 40 and record["cache_write_tokens"] == 3
    assert record["reasoning_tokens"] == 5 and record["usage_provenance"] == "DERIVED_TOTAL"
    assert record["first_content_ms"] is None and record["queue_ms"] == 0
    assert record["total_ms"] == record["provider_ms"] >= 0
    encoded = json.dumps(record)
    assert all(secret not in encoded for secret in ("protected input", "safe answer", "hidden reasoning", "b" * 64))
    assert sends == [1] and db.execute("SELECT COUNT(*) AS n FROM CX_MODEL_USAGE").fetchone()["n"] == 0


def test_truncated_provider_counts_survive_business_failure(route):
    db, profile, sends, install, authorization = route
    install(reply("length", {"prompt_tokens": 4, "completion_tokens": 2, "total_tokens": 6}))
    with authorization(), pytest.raises(ValueError, match="OUTPUT_TRUNCATED"):
        native_runtime._call_llm(profile, [{"role": "user", "content": "question"}])
    record = db.execute("SELECT * FROM CX_MODEL_RUNTIME_OBSERVATIONS").fetchone()
    assert record["result_state"] == "REJECTED" and record["request_complete"] == "Y"
    assert record["finish_code"] == "OUTPUT_TRUNCATED" and record["total_tokens"] == 6 and sends == [1]


def test_unknown_transport_observation_does_not_become_zero_or_release_slot(route, monkeypatch):
    db, profile, sends, _, authorization = route
    def timeout(*args, **kwargs):
        sends.append(1)
        raise TimeoutError("request outcome unknown")
    monkeypatch.setattr(model_dispatch, "open_controlled", timeout)
    with authorization(), pytest.raises(RuntimeError):
        native_runtime._call_llm(profile, [{"role": "user", "content": "question"}])
    record = db.execute("SELECT * FROM CX_MODEL_RUNTIME_OBSERVATIONS").fetchone()
    assert record["result_state"] == "UNKNOWN" and record["request_complete"] == "N"
    assert record["total_tokens"] is None and record["first_content_ms"] is None
    assert record["usage_provenance"] == "INCOMPLETE" and sends == [1]
    assert db.execute("SELECT STATUS FROM CX_MODEL_ADMISSIONS").fetchone()["status"] == "UNKNOWN"


def test_observation_storage_failure_keeps_dispatch_occupied(route):
    db, profile, sends, install, authorization = route
    db.execute("CREATE TRIGGER deny_observation BEFORE INSERT ON CX_MODEL_RUNTIME_OBSERVATIONS "
               "BEGIN SELECT RAISE(ABORT,'observation unavailable'); END")
    db.commit()
    install(reply(usage={"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7}))
    with authorization(), pytest.raises(Exception, match="observation unavailable") as failure:
        native_runtime._call_llm(profile, [{"role": "user", "content": "question"}])
    assert failure.value.model_ledger_failed is True
    assert failure.value.model_observation["request_complete"] is True
    assert failure.value.model_observation["usage"]["total_tokens"] == 7
    assert "safe answer" not in json.dumps(failure.value.model_observation)
    assert sends == [1]
    assert db.execute("SELECT STATUS FROM CX_MODEL_ADMISSIONS").fetchone()["status"] == "DISPATCHING"
    assert db.execute("SELECT COUNT(*) AS n FROM CX_MODEL_RUNTIME_OBSERVATIONS").fetchone()["n"] == 0


def test_business_view_rechecks_resource_authority_before_metadata(route):
    _, profile, _, install, authorization = route
    install(reply())
    with authorization():
        native_runtime._call_llm(profile, [{"role": "user", "content": "question"}])
    calls = []
    def allow(tx, actor, source):
        calls.append((actor, source))
    values = model_observations.read_for_source("origin-a", "NATIVE", "execution", authorize_source=allow)
    assert len(values) == 1 and calls == [("origin-a", "execution")]
    def deny(*args):
        raise PermissionError("source access revoked")
    with pytest.raises(PermissionError, match="revoked"):
        model_observations.read_for_source("origin-a", "NATIVE", "execution", authorize_source=deny)


def test_nonstream_missing_usage_and_observed_zero_remain_distinct(route):
    db, profile, _, install, authorization = route
    install(reply(usage={"prompt_tokens": 0}))
    with authorization():
        native_runtime._call_llm(profile, [{"role": "user", "content": "question"}])
    record = db.execute("SELECT * FROM CX_MODEL_RUNTIME_OBSERVATIONS").fetchone()
    assert record["prompt_tokens"] == 0 and record["total_tokens"] is None
    assert record["usage_provenance"] == "PARTIAL"


def test_missing_original_credential_cannot_borrow_an_ambient_dispatch_identity(route):
    db, profile, sends, install, authorization = route
    install(reply())
    with authorization():
        original = model_dispatch._context.get()
        with model_credentials.dispatch_context(None, "PORTAL", "different-request", "different-attempt",
                reauthorize=lambda tx, admission: None, worker_key="portal"):
            with pytest.raises(PermissionError, match="authenticated supported dispatch"):
                native_runtime._call_llm(profile, [{"role": "user", "content": "question"}])
        assert model_dispatch._context.get() is original
    assert sends == [] and db.execute("SELECT COUNT(*) AS n FROM CX_MODEL_ADMISSIONS").fetchone()["n"] == 0
