"""Legacy helpers must not duplicate sends or expose provider reasoning/errors."""
import ast
import json
from pathlib import Path
from types import SimpleNamespace
import urllib.request

import pytest
from lib import config, model_dispatch, model_endpoint_capacity

MESSAGES = [{"role": "user", "content": "Synthetic request"}]


def helpers(monkeypatch, *, reply=None, chunks=(), failure=None, done=True, controlled=False):
    from lib import model_coordinator_origin
    # Legacy direct transport is local; enrolled remote routes are exercised
    # against independent databases and an actual coordinator HTTP peer.
    monkeypatch.setattr(model_coordinator_origin, "selected_route", lambda profile: None)
    source = Path(__file__).resolve().parents[1] / "visualization/server.py"
    tree = ast.parse(source.read_text())
    selected = [node for node in tree.body if isinstance(node, ast.FunctionDef)
                and node.name in {"_call_llm", "_call_llm_stream"}]
    assert len(selected) == 2
    cfg = SimpleNamespace(llm=SimpleNamespace(api_url="https://provider.invalid/v1", model="synthetic-model", api_key="synthetic-secret"))
    monkeypatch.setattr(config, "get_config", lambda: cfg)
    monkeypatch.setattr(model_endpoint_capacity, "selected_group", lambda *_: "controlled" if controlled else None)
    monkeypatch.setattr(model_dispatch.connection, "execute_transaction_callback", lambda callback: callback(None))
    calls, logs, closed = [], [], []
    class Response:
        def __enter__(self):
            return self
        def __exit__(self, *_):
            closed.append(True)
        def read(self, *_):
            return json.dumps(reply).encode()
        def __iter__(self):
            for chunk in chunks:
                yield b"data: " + json.dumps(chunk).encode() + b"\n\n"
            if done:
                yield b"data: [DONE]\n\n"
    def open_request(request, **options):
        calls.append({"body": json.loads(request.data), "timeout": options["timeout"]})
        if failure:
            raise failure
        return Response()
    namespace = {"json": json,
                 "urllib": SimpleNamespace(request=SimpleNamespace(Request=urllib.request.Request, urlopen=open_request)),
                 "logger": SimpleNamespace(error=lambda fmt, value: logs.append(fmt % value))}
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(source), "exec"), namespace)
    return namespace, calls, logs, closed


@pytest.mark.parametrize("stream", [False, True])
def test_one_request_and_only_content_are_observed(monkeypatch, stream):
    namespace, calls, logs, closed = helpers(monkeypatch,
        reply={"model": "synthetic-model", "choices": [{"message": {"content": "Final answer", "reasoning_content": "private reasoning"}, "finish_reason": "stop"}]},
        chunks=[{"model": "synthetic-model", "choices": [{"delta": {"reasoning_content": "private reasoning"}}]},
                {"model": "synthetic-model", "choices": [{"delta": {"content": "Final answer"}}]},
                {"model": "synthetic-model", "choices": [{"delta": {}, "finish_reason": "stop"}]}])
    messages = [{"role": "user", "content": "Synthetic request"}]
    observed = "".join(namespace["_call_llm_stream"](messages)) if stream else namespace["_call_llm"](messages)
    assert observed == "Final answer"
    assert len(calls) == 1 and len(closed) == 1 and not logs
    assert calls[0]["body"]["stream"] is stream
    assert "reasoning_effort" not in calls[0]["body"]


@pytest.mark.parametrize("stream", [False, True])
def test_reasoning_only_output_is_not_a_final_answer(monkeypatch, stream):
    namespace, calls, logs, closed = helpers(monkeypatch,
        reply={"model": "synthetic-model", "choices": [{"message": {"content": "", "reasoning_content": "private reasoning"}, "finish_reason": "stop"}]},
        chunks=[{"model": "synthetic-model", "choices": [{"delta": {"reasoning_content": "private reasoning"}}]},
                {"model": "synthetic-model", "choices": [{"delta": {}, "finish_reason": "stop"}]}])
    observed = list(namespace["_call_llm_stream"](MESSAGES)) if stream else namespace["_call_llm"](MESSAGES)
    assert observed == ([] if stream else None)
    assert len(calls) == 1 and len(closed) == 1 and not logs


@pytest.mark.parametrize("stream", [False, True])
def test_transport_failure_is_never_resent_and_logs_only_a_local_category(monkeypatch, stream):
    namespace, calls, logs, closed = helpers(monkeypatch,
        failure=TimeoutError("private body synthetic-secret https://private.invalid"))
    observed = list(namespace["_call_llm_stream"](MESSAGES)) if stream else namespace["_call_llm"](MESSAGES)
    assert observed == ([] if stream else None)
    assert len(calls) == 1 and not closed
    assert logs == [("LLM stream error: " if stream else "LLM call error: ") + "TimeoutError"]


@pytest.mark.parametrize("stream", [False, True])
def test_registered_capacity_alias_cannot_use_legacy_direct_route(monkeypatch, stream):
    namespace, calls, logs, closed = helpers(monkeypatch, controlled=True)
    observed = list(namespace["_call_llm_stream"](MESSAGES)) if stream else namespace["_call_llm"](MESSAGES)
    assert observed == ([] if stream else None)
    assert not calls and not closed
    assert logs == [("LLM stream error: " if stream else "LLM call error: ") + "PermissionError"]


@pytest.mark.parametrize("finish", [None, "length", "content_filter", "tool_calls"])
def test_direct_nonstream_never_accepts_unfinished_or_nontext_result(monkeypatch, finish):
    namespace, calls, logs, closed = helpers(monkeypatch,
        reply={"model": "synthetic-model", "choices": [{"message": {"content": "answer"}, "finish_reason": finish}]})
    assert namespace["_call_llm"](MESSAGES) is None
    assert len(calls) == 1 and len(closed) == 1
    assert logs == ["LLM call error: ModelResultError"]


@pytest.mark.parametrize("done,finish", [(True, None), (False, "stop")])
def test_direct_stream_requires_finish_and_done_without_resending(monkeypatch, done, finish):
    namespace, calls, logs, closed = helpers(monkeypatch, done=done,
        chunks=[{"model": "synthetic-model", "choices": [{"delta": {"content": "partial"}}]},
                {"model": "synthetic-model", "choices": [{"delta": {}, "finish_reason": finish}]}])
    assert list(namespace["_call_llm_stream"](MESSAGES)) == []
    assert len(calls) == 1 and len(closed) == 1
    assert logs == ["LLM stream error: ModelResultError"]


@pytest.mark.parametrize("stream", [False, True])
def test_direct_helpers_reject_model_switch_without_exposing_reasoning(monkeypatch, stream):
    namespace, calls, logs, closed = helpers(monkeypatch,
        reply={"model": "another-model", "choices": [{"message": {"content": "private answer"}, "finish_reason": "stop"}]},
        chunks=[{"model": "another-model", "choices": [{"delta": {"content": "private answer", "reasoning_content": "private reasoning"}}]}])
    observed = list(namespace["_call_llm_stream"](MESSAGES)) if stream else namespace["_call_llm"](MESSAGES)
    assert observed == ([] if stream else None)
    assert len(calls) == 1 and len(closed) == 1
    assert logs == [("LLM stream error: " if stream else "LLM call error: ") + "ModelResultError"]


def test_stream_buffers_content_until_cross_chunk_output_check(monkeypatch):
    namespace, calls, logs, closed = helpers(monkeypatch, chunks=[
        {"model": "synthetic-model", "choices": [{"delta": {"content": "-----BEGIN "}}]},
        {"model": "synthetic-model", "choices": [{"delta": {"content": "PRIVATE KEY-----"}}]},
        {"model": "synthetic-model", "choices": [{"delta": {}, "finish_reason": "stop"}]}])
    assert list(namespace["_call_llm_stream"](MESSAGES)) == []
    assert len(calls) == len(closed) == 1
    assert logs == ["LLM stream error: ContentDenied"]
