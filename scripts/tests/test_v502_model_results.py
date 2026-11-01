"""Protocol evidence, accounting provenance and disclosure regressions, offline."""
from __future__ import annotations

import copy
import io
import json
from types import SimpleNamespace

import pytest

from lib import config, model_results as results, model_usage_api as gateway
from lib import native_runtime, provider_capability_probes


MODEL = "test-model"
USAGE = {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150,
         "prompt_tokens_details": {"cached_tokens": 30},
         "cache_creation_input_tokens": 10,
         "completion_tokens_details": {"reasoning_tokens": 20}}


def completion(content="answer", finish="stop", **message):
    return {"model": MODEL, "choices": [{"index": 0, "finish_reason": finish,
            "message": {"role": "assistant", "content": content, **message}}], "usage": copy.deepcopy(USAGE)}


def chunk(content=None, finish=None, **delta):
    return {"model": MODEL, "choices": [{"index": 0, "finish_reason": finish,
            "delta": {**({"content": content} if content is not None else {}), **delta}}]}


def event_bytes(events):
    return b"".join(b"data: " + (event.encode() if isinstance(event, str) else json.dumps(event).encode())
                    + b"\n\n" for event in events)


def parsed_stream(events, **options):
    parser = results.ChatCompletionStream(MODEL, **options)
    for event in events:
        parser.feed(event)
    return parser.finish()


def tool(identifier="call-1", arguments='{"query":"value"}'):
    return {"id": identifier, "type": "function", "function": {"name": "search", "arguments": arguments}}


def test_complete_text_retains_only_permitted_content_and_safe_usage():
    value = results.parse_completion(completion(reasoning_content="private thought"), MODEL)
    assert value["content"] == "answer" and value["request_complete"]
    assert value["reasoning_present"] and "private thought" not in json.dumps(value)
    assert value["usage"] == dict(prompt_tokens=100, completion_tokens=50, total_tokens=150,
                                  cached_tokens=30, cache_write_tokens=10, reasoning_tokens=20)
    assert value["usage_observation"] == "PROVIDER_REPORTED"


@pytest.mark.parametrize("finish,code,complete", [
    (None, "INCOMPLETE_COMPLETION", False), ("unknown", "INCOMPLETE_COMPLETION", False),
    ("length", "OUTPUT_TRUNCATED", True), ("content_filter", "PROVIDER_REFUSAL", True),
    ("tool_calls", "INCOMPLETE_COMPLETION", True)])
def test_plausible_body_requires_correct_terminal(finish, code, complete):
    with pytest.raises(results.ModelResultError, match=code) as caught:
        results.parse_completion(completion(finish=finish), MODEL)
    assert caught.value.request_complete is complete
    assert caught.value.observation["usage"]["total_tokens"] == 150


@pytest.mark.parametrize("content", [None, 42, ["answer"], {}, "", " ", "\ud800"])
def test_invalid_text_cannot_become_a_final_answer(content):
    with pytest.raises(results.ModelResultError):
        results.parse_completion(completion(content), MODEL)


def test_refusal_is_safe_completed_failure_even_if_expected_body_exists():
    with pytest.raises(results.ModelResultError, match="PROVIDER_REFUSAL") as caught:
        results.parse_completion(completion(refusal="private refusal text"), MODEL)
    assert caught.value.request_complete
    assert "private" not in str(caught.value) and "private" not in json.dumps(caught.value.observation)


@pytest.mark.parametrize("mutation", [
    lambda value: value.update(model="other-model"),
    lambda value: value.update(error={"message": "provider secret"}),
    lambda value: value.update(choices=[]),
    lambda value: value["choices"].append(value["choices"][0]),
    lambda value: value["choices"][0].update(index=False),
    lambda value: value["choices"][0].update(index=1),
    lambda value: value["choices"][0].update(finish_reason=[]),
    lambda value: value["choices"][0]["message"].update(role="user"),
    lambda value: value["choices"][0].update(message="answer"),
])
def test_invalid_envelopes_are_rejected(mutation):
    value = completion()
    mutation(value)
    with pytest.raises(results.ModelResultError):
        results.parse_completion(value, MODEL)


def test_configured_matching_policy_is_explicit_and_does_not_replace_configuration():
    value = completion()
    value["model"] = "test-model-alias"
    assert results.parse_completion(value, MODEL, model_matches=lambda configured, observed:
        configured == MODEL and observed == "test-model-alias")["model"] == "test-model-alias"
    with pytest.raises(results.ModelResultError, match="MODEL_MISMATCH"):
        results.parse_completion(value, MODEL)


@pytest.mark.parametrize("raw", ['{"x":1,"x":2}', '{"x":NaN}', '{"x":Infinity}', '{', b"\xff", '"\ud800"'])
def test_json_decoder_rejects_ambiguous_or_malformed_values(raw):
    with pytest.raises(results.ModelResultError):
        results.decode_json(raw)


def test_json_and_final_content_have_independent_byte_bounds():
    with pytest.raises(results.ModelResultError, match="RESPONSE_TOO_LARGE"):
        results.decode_json('"中文"', max_bytes=7)
    with pytest.raises(results.ModelResultError, match="RESPONSE_TOO_LARGE"):
        results.parse_completion(completion("中文"), MODEL, max_content_bytes=5)


def test_structured_result_requires_actual_complete_json():
    assert results.parse_completion(completion('{"ok":true}'), MODEL, output_kind="structured")["structured"] == {"ok": True}
    with pytest.raises(results.ModelResultError, match="INVALID_STRUCTURED_OUTPUT") as caught:
        results.parse_completion(completion('{"ok":'), MODEL, output_kind="structured")
    assert caught.value.request_complete


def test_tool_round_allows_empty_content_but_text_contract_rejects_tools():
    response = completion(None, "tool_calls", tool_calls=[tool()])
    value = results.parse_completion(response, MODEL, output_kind="tool")
    assert value["content"] == "" and value["tool_calls"] == [tool()]
    with pytest.raises(results.ModelResultError):
        results.parse_completion(response, MODEL)
    with pytest.raises(results.ModelResultError, match="UNEXPECTED_TOOL_PROPOSAL"):
        results.parse_completion(completion(tool_calls=[tool()]), MODEL)


@pytest.mark.parametrize("calls", [[], [tool(), tool()], [tool(identifier="")],
    [{"type": "function", "function": {"name": "search", "arguments": "{}"}}],
    [tool(arguments='{"query":')], [tool(arguments="[]")], [tool(arguments='{"x":1,"x":2}')],
    [tool(arguments="null")], [tool(arguments='{"x":NaN}')]])
def test_incomplete_or_ambiguous_tools_are_never_executable(calls):
    with pytest.raises(results.ModelResultError) as caught:
        results.parse_completion(completion(None, "tool_calls", tool_calls=calls), MODEL, output_kind="tool")
    assert caught.value.request_complete


def test_missing_tool_identifier_is_probe_only_compatibility():
    call = tool()
    call.pop("id")
    assert results.parse_completion(completion(None, tool_calls=[call]), MODEL, output_kind="tool",
                                    require_tool_ids=False)["tool_calls"] == [call]
    with pytest.raises(results.ModelResultError):
        results.parse_completion(completion(None, tool_calls=[call]), MODEL, output_kind="tool")


def test_assembled_tool_proposals_obey_one_total_byte_budget():
    response = completion(None, "tool_calls", tool_calls=[tool("a"),tool("b")])
    with pytest.raises(results.ModelResultError, match="RESPONSE_TOO_LARGE"):
        results.parse_completion(response, MODEL, output_kind="tool", max_content_bytes=35)


@pytest.mark.parametrize("invalid", [True, False, -1, 1.5, "3", 2**63, float("inf"), None])
def test_usage_counts_do_not_coerce_invalid_measurements(invalid):
    assert all(value is None for value in results.normalize_usage(dict.fromkeys(results.USAGE_FIELDS, invalid)).values())


def test_usage_aliases_details_and_derived_total_have_clear_provenance():
    value = {"input_tokens": 100, "output_tokens": 50, "cache_read_input_tokens": 30,
             "cache_creation_input_tokens": 10, "output_tokens_details": {"reasoning_tokens": 20}}
    observation = results.usage_observation(value)
    assert observation["usage"]["total_tokens"] == 150
    assert observation["usage_field_provenance"]["total_tokens"] == "SUM_OF_REPORTED_INPUT_OUTPUT"
    assert sum(observation["usage"][key] for key in ("prompt_tokens", "completion_tokens")) == 150
    assert observation["usage"]["cache_write_tokens"] == 10
    value["total_tokens"] = None
    assert results.normalize_usage(value)["total_tokens"] is None
    value.update(prompt_tokens=True, input_tokens=100)
    assert results.normalize_usage(value)["prompt_tokens"] is None


def test_missing_usage_preserves_unknown_instead_of_zero():
    assert results.usage_observation(None)["usage_observation"] == "UNAVAILABLE"
    assert set(results.normalize_usage(None).values()) == {None}
    assert results.usage_observation({"cached_tokens": 0})["usage_observation"] == "INCOMPLETE"


def test_stream_accepts_terminal_usage_without_promoting_hidden_reasoning():
    value = parsed_stream([chunk(reasoning_content="hidden"), chunk("answer"), chunk(finish="stop"),
                           {"model": MODEL, "choices": [], "usage": USAGE}, "[DONE]"])
    assert value["content"] == "answer" and value["reasoning_present"]
    assert value["usage"]["cache_write_tokens"] == 10
    assert "hidden" not in json.dumps(value)


@pytest.mark.parametrize("events", [
    [chunk("answer"), "[DONE]"], [chunk("answer"), chunk(finish="stop")],
    ["[DONE]"], [chunk(reasoning_content="hidden"), chunk(finish="stop"), "[DONE]"],
    [chunk("answer"), chunk(finish="stop"), chunk("extra"), "[DONE]"],
    [chunk("answer"), chunk(finish="stop"), chunk(finish="length"), "[DONE]"],
    [chunk("answer"), chunk(finish="stop"), "[DONE]", "[DONE]"],
    [chunk("answer"), {"model": "wrong", "choices": []}, "[DONE]"],
    [chunk("answer"), chunk(finish="length"), "[DONE]"],
    [chunk("answer"), chunk(finish="stop"), {"choices": [], "usage": USAGE},
     {"choices": [], "usage": {"total_tokens": 999}}, "[DONE]"],
])
def test_partial_conflicting_and_post_terminal_streams_are_not_success(events):
    with pytest.raises(results.ModelResultError):
        parsed_stream(events)


def test_stream_tool_arguments_are_only_valid_after_full_assembly():
    call = tool(arguments='{"query":')
    call["index"] = 0
    fragments = [chunk(tool_calls=[call]), chunk(tool_calls=[{"index": 0, "function": {"arguments": '"value"}'}}]),
                 chunk(finish="tool_calls"), "[DONE]"]
    assert parsed_stream(fragments, output_kind="tool")["tool_calls"] == [tool()]
    with pytest.raises(results.ModelResultError):
        parsed_stream(fragments[:1] + [chunk(finish="tool_calls"), "[DONE]"], output_kind="tool")


def test_sse_reader_supports_multiline_and_arbitrary_transport_chunks():
    raw = b'event: completion\n: comment\ndata: {"model":"test-model",\ndata: "choices":[]}\n\ndata: [DONE]\n\n'
    expected = [{"model": MODEL, "choices": []}, "[DONE]"]
    assert list(results.sse_events(io.BytesIO(raw))) == expected
    assert list(results.sse_events([raw[:12], raw[12:31], raw[31:]])) == expected
    assert list(results.sse_events([b'data: {"choices":[]}\ndata: [DONE]\n'])) == [{"choices": []}, "[DONE]"]


@pytest.mark.parametrize("raw,options", [
    (b"data: \xff\n", {}), (b'data: {"x":1,"x":2}\n', {}),
    (b"data: {broken}\n\n", {}), (b"data: " + b"x" * 100 + b"\n", {"max_event_bytes": 50}),
    (b"data: {}\n\n" * 5, {"max_bytes": 30}),
])
def test_sse_decoder_is_bounded_and_strict(raw, options):
    with pytest.raises(results.ModelResultError):
        list(results.sse_events(io.BytesIO(raw), **options))


@pytest.fixture
def routes(monkeypatch):
    """Only synthetic HTTP responses and in-memory accounting observations."""
    # These parser/disclosure fixtures have no selected capacity group. The
    # independent relational/process suite exercises actual group admission.
    from lib import model_dispatch, model_coordinator_origin
    monkeypatch.setattr(model_dispatch, "_lookup", lambda profile: None)
    monkeypatch.setattr(model_coordinator_origin, "selected_route", lambda profile: None)
    profile = {"profile_id": "profile", "version": 7, "profile_key": "provider",
               "provider_url": "https://provider.invalid/v1", "model_id": MODEL}
    observed = {"sends": [], "usage": [], "updates": [], "settlements": [], "replays": []}
    monkeypatch.setattr(config, "get_config", lambda: SimpleNamespace(llm=config.LLMConfig(request_timeout_seconds=180)))
    monkeypatch.setattr(provider_capability_probes, "apply_parameters", lambda _profile, payload: dict(payload))
    monkeypatch.setattr(gateway, "_forward_context", lambda *_: {"actor": "actor", "credential_id": ""})
    monkeypatch.setattr(gateway.connection, "execute_query_one", lambda *_: profile)
    monkeypatch.setattr(gateway.connection, "execute", lambda sql, values: observed["updates"].append((sql, values)) or 1)
    monkeypatch.setattr(gateway, "_idempotent_replay", lambda *_: None)
    monkeypatch.setattr(gateway, "_reserve_idempotency", lambda *_: None)
    monkeypatch.setattr(gateway, "_write_usage", lambda *args, **kwargs: observed["usage"].append(args) or args[5])
    monkeypatch.setattr(gateway.model_governance_api, "reserve_quota", lambda *_: {"warnings": []})
    monkeypatch.setattr(gateway.model_governance_api, "release_quota", lambda *_: None)
    monkeypatch.setattr(gateway.model_governance_api, "settle_quota", lambda *args, **kwargs: observed["settlements"].append((args, kwargs)))
    monkeypatch.setattr(gateway.model_governance_api, "finalize_replayable_success", lambda *args: observed["replays"].append(args))

    def install(value, *, stream=False):
        class Response(io.BytesIO):
            def __enter__(self): return self
            def __exit__(self, *_): self.close()
        raw = event_bytes(value) if stream else json.dumps(value).encode()
        def send(request, **_):
            observed["sends"].append(json.loads(request.data))
            return Response(raw)
        monkeypatch.setattr(native_runtime.urllib.request, "urlopen", send)
    return profile, observed, install


@pytest.mark.parametrize("route", ["native", "gateway"])
def test_routes_keep_terminal_usage_and_never_disclose_reasoning(routes, route):
    profile, observed, install = routes
    install([chunk("answer", reasoning_content="private thought"), chunk(finish="stop"),
             {"model": MODEL, "choices": [], "usage": USAGE}, "[DONE]"], stream=True)
    delivered = []
    if route == "native":
        value = native_runtime._stream_llm(profile, [{"role": "user", "content": "question"}], delivered.append)
        assert delivered == ["answer"] and value["usage"]["cache_write_tokens"] == 10
    else:
        emitted = b"".join(gateway.stream_forward("actor", "profile", [{"role": "user", "content": "question"}]))
        assert b"answer" in emitted and b"private thought" not in emitted
        assert observed["usage"][0][5]["total_tokens"] == 150
    assert len(observed["sends"]) == 1


@pytest.mark.parametrize("route", ["native", "gateway"])
def test_routes_do_not_release_partial_stream_or_retry_it(routes, route):
    profile, observed, install = routes
    install([chunk("partial")], stream=True)
    delivered = []
    with pytest.raises((results.ModelResultError, gateway.ModelUsageError)):
        if route == "native":
            native_runtime._stream_llm(profile, [{"role": "user", "content": "question"}], delivered.append)
        else:
            delivered.extend(gateway.stream_forward("actor", "profile", [{"role": "user", "content": "question"}]))
    assert delivered == [] and len(observed["sends"]) == 1
    if route == "gateway":
        assert len(observed["usage"]) == 1
        assert observed["usage"][0][8] == "INCOMPLETE"
        assert all(value is None for value in observed["usage"][0][5].values())
        assert any(values.get("status") == "INCOMPLETE" for _, values in observed["updates"])
    else:
        assert observed["usage"] == []


def test_gateway_sanitizes_completed_nonstream_response(routes):
    _, observed, install = routes
    install(completion(reasoning_content="private thought"))
    value = gateway.forward("actor", "profile", [{"role": "user", "content": "question"}])
    assert value["choices"][0]["message"] == {"role": "assistant", "content": "answer"}
    assert "private thought" not in json.dumps(value) and len(observed["replays"]) == 1


def test_gateway_does_not_disclose_a_credential_split_across_chunks(routes):
    _, observed, install = routes
    install([chunk("safe "), chunk("-----BEGIN "), chunk("PRIVATE KEY-----"),
             chunk(finish="stop"), "[DONE]"], stream=True)
    delivered=[]
    with pytest.raises(gateway.ModelUsageError):
        delivered.extend(gateway.stream_forward("actor", "profile", [{"role":"user","content":"question"}]))
    assert delivered == [] and len(observed["sends"]) == 1
    assert len(observed["usage"]) == 1 and observed["usage"][0][8] == "FAILED"


def test_nonstream_api_rejects_stream_flag_before_any_send(routes):
    _,observed,_=routes
    with pytest.raises(gateway.ModelUsageError,match="stream_forward"):
        gateway.forward("actor","profile",[{"role":"user","content":"question"}],stream=True)
    assert observed["sends"]==[]


@pytest.mark.parametrize("stream", [False, True])
def test_completed_truncation_is_failed_business_output_with_unknown_charge(routes, stream):
    _, observed, install = routes
    install([chunk("partial"), chunk(finish="length"), "[DONE]"] if stream else completion("partial", "length"), stream=stream)
    with pytest.raises(gateway.ModelUsageError, match="OUTPUT_TRUNCATED"):
        value = gateway.stream_forward("actor", "profile", [{"role": "user", "content": "question"}]) if stream else gateway.forward("actor", "profile", [{"role": "user", "content": "question"}])
        if stream: list(value)
    assert any(values.get("status") == "FAILED" for _, values in observed["updates"])
    assert len(observed["usage"]) == 1 and observed["usage"][0][8] == "FAILED"
    if stream:
        assert all(value is None for value in observed["usage"][0][5].values())
    else:
        assert observed["usage"][0][5] == results.normalize_usage(USAGE)
    assert len(observed["sends"]) == 1


def test_replay_finalization_failure_preserves_observed_usage_once(routes, monkeypatch):
    _, observed, install = routes
    install(completion())
    def fail(*args):
        raise RuntimeError("snapshot storage unavailable")
    monkeypatch.setattr(gateway.model_governance_api, "finalize_replayable_success", fail)
    with pytest.raises(gateway.ModelUsageError):
        gateway.forward("actor", "profile", [{"role": "user", "content": "question"}])
    assert len(observed["usage"]) == 1 and observed["usage"][0][5] == results.normalize_usage(USAGE)
    assert len(observed["sends"]) == 1
    assert any(values.get("status") == "FAILED" and values.get("error") == "FINALIZATION_FAILED"
               for _, values in observed["updates"])
