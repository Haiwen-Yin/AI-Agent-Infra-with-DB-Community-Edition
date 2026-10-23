"""Slow-provider waits propagate without provider options or automatic retries."""
from __future__ import annotations

import ast
import importlib.util
import json
import logging
from pathlib import Path
import sys
from types import SimpleNamespace
import urllib.request

import pytest

from lib import config, llm_transport, model_usage_api, native_runtime, provider_capability_probes


ROOT = Path(__file__).resolve().parents[2]
SOURCE = (ROOT / "adapters").is_dir()
CONFIGURATIONS = ("shared", "oracle", "pg", "yashandb") if SOURCE else ("packaged",)


@pytest.fixture(params=CONFIGURATIONS)
def configuration(request, monkeypatch):
    if request.param == "packaged":
        return config
    path = ROOT / ("shared/lib/config.py" if request.param == "shared"
                   else f"adapters/{request.param}/config_db.py")
    name = "lib._transport_test_config_" + request.param
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, module)
    spec.loader.exec_module(module)
    return module


def _raw_config(monkeypatch, module, value):
    reader = "_read_config" if hasattr(module, "_read_config") else "_load_config_file"
    monkeypatch.setattr(module, reader, lambda: value)


def test_every_configuration_loads_default_and_explicit_numeric_wait(configuration, monkeypatch):
    _raw_config(monkeypatch, configuration, {})
    assert configuration.load_config().llm.request_timeout_seconds == 180
    _raw_config(monkeypatch, configuration, {"llm": {"request_timeout_seconds": 271.5}})
    assert configuration.load_config().llm.request_timeout_seconds == 271.5


def test_encrypted_llm_resolution_preserves_the_transport_setting(configuration, monkeypatch):
    _raw_config(monkeypatch, configuration, {"llm": {"_encrypted": "synthetic", "request_timeout_seconds": 180}})
    resolved = lambda _: {"request_timeout_seconds": 239, "model": "demo"}
    if hasattr(configuration, "_decrypt_llm_section"):
        monkeypatch.setattr(configuration, "_decrypt_llm_section", resolved)
    else:
        from lib import connection_crypto
        monkeypatch.setattr(connection_crypto, "decrypt_llm_section", resolved)
    assert configuration.load_config().llm.request_timeout_seconds == 239


@pytest.mark.parametrize("value", [True, False, None, "180", 0, 601, float("nan"), float("inf"), -float("inf"), 10**500])
def test_invalid_wait_is_rejected_by_loaders_and_direct_construction(configuration, monkeypatch, value):
    _raw_config(monkeypatch, configuration, {"llm": {"request_timeout_seconds": value}})
    with pytest.raises(ValueError, match="llm.request_timeout_seconds"):
        configuration.load_config()
    with pytest.raises(ValueError, match="llm.request_timeout_seconds"):
        configuration.LLMConfig(request_timeout_seconds=value)


@pytest.mark.parametrize("value", [1, 1.5, 180, 600])
def test_allowed_wait_bounds_and_runtime_revalidation(value):
    assert llm_transport.request_timeout_seconds(SimpleNamespace(request_timeout_seconds=value)) == value
    with pytest.raises(ValueError):
        llm_transport.request_timeout_seconds(SimpleNamespace(request_timeout_seconds=True))


class Response:
    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self, *_):
        return json.dumps({"model": "demo", "choices": [{"message": {"content": "answer"}}],
                           "usage": {"prompt_tokens": 2, "completion_tokens": 1, "total_tokens": 3}}).encode()

    def __iter__(self):
        yield b'data: {"model":"demo","choices":[{"delta":{"content":"answer"}}]}\n'
        yield b'data: [DONE]\n'


def _legacy_helper(stream):
    path = Path(__file__).resolve().parents[1] / "visualization/server.py"
    name = "_call_llm_stream" if stream else "_call_llm"
    node = next(item for item in ast.parse(path.read_text()).body if isinstance(item, ast.FunctionDef) and item.name == name)
    namespace = {"urllib": urllib, "json": json, "logger": logging.getLogger(__name__)}
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), "exec"), namespace)
    return namespace[name]


@pytest.fixture
def dispatch(monkeypatch):
    configured = config.LLMConfig(api_url="http://example.test/v1", model="demo", request_timeout_seconds=247.5)
    monkeypatch.setattr(config, "get_config", lambda: SimpleNamespace(llm=configured))
    monkeypatch.setattr(provider_capability_probes, "apply_parameters", lambda _profile, payload: dict(payload))
    monkeypatch.setattr(model_usage_api, "_forward_context", lambda *_: {"actor": "actor", "credential_id": ""})
    monkeypatch.setattr(model_usage_api.connection, "execute_query_one", lambda *_: {
        "profile_id": "profile", "profile_key": "demo", "provider_url": configured.api_url, "model_id": "demo"})
    monkeypatch.setattr(model_usage_api.connection, "execute", lambda *_: 1)
    monkeypatch.setattr(model_usage_api, "_idempotent_replay", lambda *_: None)
    monkeypatch.setattr(model_usage_api, "_reserve_idempotency", lambda *_: None)
    monkeypatch.setattr(model_usage_api, "_write_usage", lambda *_: {})
    monkeypatch.setattr(model_usage_api.model_governance_api, "reserve_quota", lambda *_: {"warnings": []})
    monkeypatch.setattr(model_usage_api.model_governance_api, "release_quota", lambda *_: None)
    monkeypatch.setattr(model_usage_api.model_governance_api, "settle_quota", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(model_usage_api.model_governance_api, "finalize_replayable_success", lambda *_: None)

    def invoke(route, stream):
        messages = [{"role": "user", "content": "question"}]
        if route == "native":
            profile = {"provider_url": configured.api_url, "model_id": "demo"}
            return (native_runtime._stream_llm(profile, messages, lambda _: None) if stream
                    else native_runtime._call_llm(profile, messages))
        if route == "gateway":
            return list(model_usage_api.stream_forward("actor", "profile", messages)) if stream else model_usage_api.forward("actor", "profile", messages)
        helper = _legacy_helper(stream)
        return list(helper(messages)) if stream else helper(messages)
    return invoke


@pytest.mark.parametrize("route", ["native", "gateway", "legacy"])
@pytest.mark.parametrize("stream", [False, True])
def test_every_model_path_uses_one_validated_local_wait(dispatch, monkeypatch, route, stream):
    observed = []

    def open_request(request, *, timeout):
        observed.append((timeout, json.loads(request.data)))
        return Response()

    monkeypatch.setattr(urllib.request, "urlopen", open_request)
    result = dispatch(route, stream)
    assert result
    assert len(observed) == 1 and observed[0][0] == 247.5
    assert observed[0][1]["model"] == "demo" and observed[0][1]["stream"] is stream
    assert observed[0][1]["messages"] == [{"role": "user", "content": "question"}]
    assert "request_timeout_seconds" not in observed[0][1] and "timeout" not in observed[0][1]


@pytest.mark.parametrize("route", ["native", "gateway", "legacy"])
@pytest.mark.parametrize("stream", [False, True])
def test_a_transport_timeout_does_not_retry_an_uncertain_send(dispatch, monkeypatch, route, stream):
    sends = []

    def timeout(request, **_):
        sends.append(request)
        raise TimeoutError("synthetic local wait expired")

    monkeypatch.setattr(urllib.request, "urlopen", timeout)
    if route == "legacy":
        assert not dispatch(route, stream)
    else:
        with pytest.raises(RuntimeError, match="request failed"):
            dispatch(route, stream)
    assert len(sends) == 1
