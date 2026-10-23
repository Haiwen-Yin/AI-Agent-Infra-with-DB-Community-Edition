"""Legacy helpers must not duplicate sends or expose provider reasoning/errors."""
import ast
import json
from pathlib import Path
from types import SimpleNamespace
import urllib.request

import pytest
from lib import config


def helpers(monkeypatch, *, reply=None, chunks=(), failure=None):
    source = Path(__file__).resolve().parents[1] / "visualization/server.py"
    tree = ast.parse(source.read_text())
    selected = [node for node in tree.body if isinstance(node, ast.FunctionDef)
                and node.name in {"_call_llm", "_call_llm_stream"}]
    assert len(selected) == 2
    cfg = SimpleNamespace(llm=SimpleNamespace(api_url="https://provider.invalid/v1", model="synthetic-model", api_key="synthetic-secret"))
    monkeypatch.setattr(config, "get_config", lambda: cfg)
    calls, logs, closed = [], [], []
    class Response:
        def __enter__(self):
            return self
        def __exit__(self, *_):
            closed.append(True)
        def read(self):
            return json.dumps(reply).encode()
        def __iter__(self):
            for chunk in chunks:
                yield b"data: " + json.dumps(chunk).encode() + b"\n"
            yield b"data: [DONE]\n"
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
        reply={"choices": [{"message": {"content": "Final answer", "reasoning_content": "private reasoning"}}]},
        chunks=[{"choices": [{"delta": {"reasoning_content": "private reasoning"}}]},
                {"choices": [{"delta": {"content": "Final answer"}}]}])
    messages = [{"role": "user", "content": "Synthetic request"}]
    observed = "".join(namespace["_call_llm_stream"](messages)) if stream else namespace["_call_llm"](messages)
    assert observed == "Final answer"
    assert len(calls) == 1 and len(closed) == 1 and not logs
    assert calls[0]["body"]["stream"] is stream
    assert "reasoning_effort" not in calls[0]["body"]


@pytest.mark.parametrize("stream", [False, True])
def test_reasoning_only_output_is_not_a_final_answer(monkeypatch, stream):
    namespace, calls, logs, closed = helpers(monkeypatch,
        reply={"choices": [{"message": {"reasoning_content": "private reasoning"}}]},
        chunks=[{"choices": [{"delta": {"reasoning_content": "private reasoning"}}]}])
    observed = list(namespace["_call_llm_stream"]([])) if stream else namespace["_call_llm"]([])
    assert observed == ([] if stream else None)
    assert len(calls) == 1 and len(closed) == 1 and not logs


@pytest.mark.parametrize("stream", [False, True])
def test_transport_failure_is_never_resent_and_logs_only_a_local_category(monkeypatch, stream):
    namespace, calls, logs, closed = helpers(monkeypatch,
        failure=TimeoutError("private body synthetic-secret https://private.invalid"))
    observed = list(namespace["_call_llm_stream"]([])) if stream else namespace["_call_llm"]([])
    assert observed == ([] if stream else None)
    assert len(calls) == 1 and not closed
    assert logs == [("LLM stream error: " if stream else "LLM call error: ") + "TimeoutError"]
