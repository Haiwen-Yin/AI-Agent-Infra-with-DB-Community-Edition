"""Bounded Chat Completions results and usage, without transport or DB access.

Parsing success proves a supported protocol result, not business authorization.
Errors carry safe categories and separate observed provider completion from
business validity. No exception message includes provider text or credentials.
"""
from __future__ import annotations

import json
from typing import Any, Callable, Iterable


USAGE_FIELDS = ("prompt_tokens", "completion_tokens", "total_tokens", "cached_tokens",
                "cache_write_tokens", "reasoning_tokens")
MAX_TOKEN_COUNT = 2**63 - 1


class ModelResultError(ValueError):
    def __init__(self, code: str, *, request_complete: bool = False,
                 finish_reason: str | None = None, usage: Any = None):
        super().__init__(code)
        self.code = code
        self.request_complete = bool(request_complete)
        self.finish_reason = finish_reason
        self.observation = usage_observation(usage)


def _utf8_size(value: str, *, request_complete: bool = False) -> int:
    try:
        return len(value.encode("utf-8"))
    except UnicodeError:
        raise ModelResultError("INVALID_COMPLETION", request_complete=request_complete) from None


def _no_constant(_value: str) -> None:
    raise ModelResultError("INVALID_COMPLETION")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ModelResultError("INVALID_COMPLETION")
        result[key] = value
    return result


def decode_json(raw: bytes | str, *, max_bytes: int = 4 * 1024 * 1024) -> Any:
    """Reject oversized, duplicate-key and non-finite JSON before interpretation."""
    try:
        if not isinstance(raw, (bytes, str)):
            raise ModelResultError("INVALID_COMPLETION")
        if len(raw if isinstance(raw, bytes) else raw.encode("utf-8")) > max_bytes:
            raise ModelResultError("RESPONSE_TOO_LARGE")
        return json.loads(raw, parse_constant=_no_constant, object_pairs_hook=_unique_object)
    except ModelResultError:
        raise
    except (ValueError, TypeError, UnicodeError, RecursionError, OverflowError):
        raise ModelResultError("INVALID_COMPLETION") from None


def _count(value: Any) -> int | None:
    return value if type(value) is int and 0 <= value <= MAX_TOKEN_COUNT else None


def normalize_usage(value: Any) -> dict[str, int | None]:
    """Normalize counts only; details remain subsets and unknown stays null.

    The input is the provider's usage object, not its entire response. This
    supports known field aliases, but does not infer capability or select a
    provider dialect. No cache/reasoning detail is added to input/output totals.
    """
    usage = value if isinstance(value, dict) else {}

    def first(*paths: tuple[str, ...]) -> int | None:
        for path in paths:
            current = usage
            for key in path:
                current = current.get(key) if isinstance(current, dict) else None
            if current is not None:
                # A malformed primary field is not rescued by an alias.
                return _count(current)
        return None

    result = {
        "prompt_tokens": first(("prompt_tokens",), ("input_tokens",)),
        "completion_tokens": first(("completion_tokens",), ("output_tokens",)),
        "total_tokens": first(("total_tokens",)),
        "cached_tokens": first(("cached_tokens",), ("cache_read_input_tokens",),
                               ("prompt_tokens_details", "cached_tokens"),
                               ("input_tokens_details", "cached_tokens")),
        "cache_write_tokens": first(("cache_write_tokens",), ("cache_creation_input_tokens",),
                                    ("prompt_tokens_details", "cache_write_tokens")),
        "reasoning_tokens": first(("reasoning_tokens",),
                                  ("completion_tokens_details", "reasoning_tokens"),
                                  ("output_tokens_details", "reasoning_tokens")),
    }
    if ("total_tokens" not in usage and result["prompt_tokens"] is not None
            and result["completion_tokens"] is not None):
        result["total_tokens"] = _count(result["prompt_tokens"] + result["completion_tokens"])
    return result


def usage_observation(value: Any) -> dict[str, Any]:
    counts = normalize_usage(value)
    complete = all(counts[key] is not None for key in USAGE_FIELDS[:3])
    present = any(count is not None for count in counts.values())
    provenance = {key: "PROVIDER_REPORTED" if count is not None else "UNAVAILABLE"
                  for key, count in counts.items()}
    if (counts["total_tokens"] is not None and isinstance(value, dict)
            and "total_tokens" not in value):
        provenance["total_tokens"] = "SUM_OF_REPORTED_INPUT_OUTPUT"
    return {"usage": counts,
            "usage_observation": "PROVIDER_REPORTED" if complete else ("INCOMPLETE" if present else "UNAVAILABLE"),
            "usage_field_provenance": provenance}


def _model(expected: str, observed: Any,
           matches: Callable[[str, str], bool] | None) -> str:
    if not isinstance(observed, str) or not observed or not (
            matches(expected, observed) if matches else expected == observed):
        raise ModelResultError("MODEL_MISMATCH")
    return observed


def _tools(value: Any, *, max_bytes: int, require_ids: bool) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not 1 <= len(value) <= 32:
        raise ModelResultError("TOOL_PROPOSAL_MISMATCH", request_complete=True)
    result, seen, total_bytes = [], set(), 0
    for call in value:
        if not isinstance(call, dict) or call.get("type") != "function":
            raise ModelResultError("TOOL_PROPOSAL_MISMATCH", request_complete=True)
        identifier = call.get("id")
        if require_ids and (not isinstance(identifier, str) or not identifier or len(identifier) > 256):
            raise ModelResultError("TOOL_PROPOSAL_MISMATCH", request_complete=True)
        if identifier is not None:
            if not isinstance(identifier, str) or not identifier or identifier in seen:
                raise ModelResultError("TOOL_PROPOSAL_MISMATCH", request_complete=True)
            seen.add(identifier)
        function = call.get("function")
        if (not isinstance(function, dict) or not isinstance(function.get("name"), str)
                or not function["name"] or len(function["name"]) > 256
                or not isinstance(function.get("arguments"), str)):
            raise ModelResultError("TOOL_PROPOSAL_MISMATCH", request_complete=True)
        total_bytes += sum(_utf8_size(item, request_complete=True) for item in
                           (identifier or "", function["name"], function["arguments"]))
        if total_bytes > max_bytes:
            raise ModelResultError("RESPONSE_TOO_LARGE", request_complete=True)
        try:
            arguments = decode_json(function["arguments"], max_bytes=max_bytes)
        except ModelResultError:
            raise ModelResultError("INVALID_TOOL_ARGUMENTS", request_complete=True) from None
        if not isinstance(arguments, dict):
            raise ModelResultError("INVALID_TOOL_ARGUMENTS", request_complete=True)
        clean = {"type": "function", "function": {"name": function["name"],
                                                    "arguments": function["arguments"]}}
        if identifier is not None:
            clean["id"] = identifier
        result.append(clean)
    return result


def _parse_completion(value: Any, expected_model: str, *, output_kind: str = "text",
                     model_matches: Callable[[str, str], bool] | None = None,
                     max_content_bytes: int = 4 * 1024 * 1024,
                     require_tool_ids: bool = True) -> dict[str, Any]:
    """Validate one complete choice; callers still enforce schema and authority.

    ``output_kind`` is text, structured, or tool. The probe-only caller may
    accept a missing call ID because it validates a non-executed proposal;
    executable tool workflows must retain IDs and their business bindings.
    """
    if output_kind not in {"text", "structured", "tool"}:
        raise ValueError("Unknown model output kind")
    if not isinstance(value, dict) or value.get("error"):
        raise ModelResultError("INVALID_COMPLETION")
    choices = value.get("choices")
    if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], dict):
        raise ModelResultError("INVALID_COMPLETION")
    choice = choices[0]
    if type(choice.get("index", 0)) is not int or choice.get("index", 0) != 0:
        raise ModelResultError("INVALID_COMPLETION")
    message = choice.get("message")
    if not isinstance(message, dict):
        raise ModelResultError("INVALID_COMPLETION")
    finish = choice.get("finish_reason")
    if finish is not None and not isinstance(finish, str):
        raise ModelResultError("INVALID_COMPLETION")
    known_terminal = finish in {"stop", "tool_calls", "length", "content_filter"}
    try:
        model = _model(expected_model, value.get("model"), model_matches)
    except ModelResultError as exc:
        raise ModelResultError(exc.code, request_complete=known_terminal,
                               finish_reason=finish, usage=value.get("usage")) from None
    if message.get("role", "assistant") != "assistant":
        raise ModelResultError("INVALID_COMPLETION", request_complete=known_terminal)
    if message.get("refusal"):
        raise ModelResultError("PROVIDER_REFUSAL", request_complete=known_terminal,
                               finish_reason=finish, usage=value.get("usage"))
    if finish == "length":
        raise ModelResultError("OUTPUT_TRUNCATED", request_complete=True, finish_reason=finish,
                               usage=value.get("usage"))
    if finish == "content_filter":
        raise ModelResultError("PROVIDER_REFUSAL", request_complete=True, finish_reason=finish,
                               usage=value.get("usage"))
    if finish not in ({"stop", "tool_calls"} if output_kind == "tool" else {"stop"}):
        raise ModelResultError("INCOMPLETE_COMPLETION", request_complete=known_terminal,
                               finish_reason=finish if isinstance(finish, str) else None,
                               usage=value.get("usage"))
    content = message.get("content")
    if content is None and output_kind == "tool":
        content = ""
    if not isinstance(content, str):
        raise ModelResultError("INVALID_COMPLETION", request_complete=True)
    if _utf8_size(content, request_complete=True) > max_content_bytes:
        raise ModelResultError("RESPONSE_TOO_LARGE", request_complete=True)
    tools = []
    if output_kind == "tool":
        tools = _tools(message.get("tool_calls"), max_bytes=max_content_bytes - _utf8_size(content),
                       require_ids=require_tool_ids)
    elif message.get("tool_calls"):
        raise ModelResultError("UNEXPECTED_TOOL_PROPOSAL", request_complete=True)
    elif not content.strip():
        raise ModelResultError("EMPTY_COMPLETION", request_complete=True)
    if output_kind == "structured":
        try:
            structured = decode_json(content, max_bytes=max_content_bytes)
        except ModelResultError:
            raise ModelResultError("INVALID_STRUCTURED_OUTPUT", request_complete=True) from None
    else:
        structured = None
    return {"content": content, "model": model, "finish_reason": finish,
            "kind": output_kind, "tool_calls": tools, "structured": structured,
            "request_complete": True, "reasoning_present": bool(message.get("reasoning_content")),
            **usage_observation(value.get("usage"))}


def parse_completion(value: Any, expected_model: str, *, output_kind: str = "text",
                     model_matches: Callable[[str, str], bool] | None = None,
                     max_content_bytes: int = 4 * 1024 * 1024,
                     require_tool_ids: bool = True) -> dict[str, Any]:
    """Validate a completion and retain safe accounting on rejected output."""
    try:
        return _parse_completion(value, expected_model, output_kind=output_kind,
                                 model_matches=model_matches, max_content_bytes=max_content_bytes,
                                 require_tool_ids=require_tool_ids)
    except ModelResultError as exc:
        if isinstance(value, dict):
            exc.observation = usage_observation(value.get("usage"))
        raise


def sse_events(response: Iterable[bytes], *, max_bytes: int = 8 * 1024 * 1024,
               max_event_bytes: int = 256 * 1024) -> Iterable[Any]:
    """Read bounded SSE data; support data-line events and standard multiline SSE.

    Legacy compatible servers sometimes omit blank separators. A complete JSON
    data line is accepted independently; incomplete JSON data lines are joined
    until the event separator. Non-data SSE fields never become model content.
    """
    total, pending, pending_bytes = 0, [], 0
    if callable(getattr(response, "readline", None)):
        chunks = iter(lambda: response.readline(max_event_bytes + 1), b"")
    else:
        chunks = iter(response)

    def lines():
        nonlocal total
        buffer = b""
        for chunk in chunks:
            if not isinstance(chunk, bytes):
                raise ModelResultError("INVALID_STREAM_CONTENT")
            total += len(chunk)
            if total > max_bytes:
                raise ModelResultError("STREAM_TOO_LARGE")
            buffer += chunk
            while b"\n" in buffer:
                raw, buffer = buffer.split(b"\n", 1)
                if len(raw) > max_event_bytes:
                    raise ModelResultError("STREAM_TOO_LARGE")
                yield raw
            if len(buffer) > max_event_bytes:
                raise ModelResultError("STREAM_TOO_LARGE")
        if buffer:
            yield buffer

    for raw in lines():
        try:
            line = raw.decode("utf-8").rstrip("\r\n")
        except UnicodeError:
            raise ModelResultError("INVALID_STREAM_CONTENT") from None
        if not line:
            if pending:
                yield decode_json("\n".join(pending), max_bytes=max_event_bytes)
                pending, pending_bytes = [], 0
            continue
        if not line.startswith("data:"):
            continue
        data = line[5:]
        if data.startswith(" "):
            data = data[1:]
        if data == "[DONE]" and not pending:
            yield "[DONE]"
            continue
        pending.append(data)
        pending_bytes += _utf8_size(data) + 1
        if pending_bytes > max_event_bytes:
            raise ModelResultError("STREAM_TOO_LARGE")
        try:
            json.loads("\n".join(pending))
        except (ValueError, RecursionError):
            continue
        # Re-parse through the strict decoder to reject duplicate/nonfinite JSON.
        yield decode_json("\n".join(pending), max_bytes=max_event_bytes)
        pending, pending_bytes = [], 0
    if pending:
        yield decode_json("\n".join(pending), max_bytes=max_event_bytes)


def _usage_extends(previous: Any, current: Any) -> bool:
    """Allow final supplemental fields without changing reported measurements."""
    if isinstance(previous, dict) and isinstance(current, dict):
        return all(key in current and _usage_extends(value, current[key])
                   for key, value in previous.items())
    return type(previous) is type(current) and previous == current


class ChatCompletionStream:
    """Bounded stream accumulator; never exposes hidden reasoning text."""
    def __init__(self, expected_model: str, *, output_kind: str = "text",
                 model_matches: Callable[[str, str], bool] | None = None,
                 max_content_bytes: int = 100000, require_tool_ids: bool = True):
        self.expected_model = expected_model
        self.output_kind = output_kind
        self.model_matches = model_matches
        self.max_content_bytes = max_content_bytes
        self.require_tool_ids = require_tool_ids
        self.model = None
        self.finish_reason = None
        self.done = False
        self.content = ""
        self.content_bytes = 0
        self.reasoning_present = False
        self.refusal = False
        self.usage = None
        self.usage_terminal = False
        self.calls: dict[int, dict[str, Any]] = {}

    def feed(self, event: Any) -> str:
        if self.done:
            raise ModelResultError("INVALID_STREAM_CONTENT", request_complete=True)
        if event == "[DONE]":
            self.done = True
            return ""
        if not isinstance(event, dict) or event.get("error"):
            raise ModelResultError("INVALID_COMPLETION")
        if event.get("model") is not None:
            observed = _model(self.expected_model, event["model"], self.model_matches)
            if self.model is not None and observed != self.model:
                raise ModelResultError("MODEL_MISMATCH")
            self.model = observed
        choices = event.get("choices")
        if not isinstance(choices, list) or len(choices) > 1:
            raise ModelResultError("INVALID_COMPLETION")
        if not choices:
            if event.get("usage") is None:
                raise ModelResultError("INVALID_COMPLETION")
            self._observe_usage(event["usage"], terminal=True)
            return ""
        choice = choices[0]
        if (not isinstance(choice, dict) or type(choice.get("index", 0)) is not int
                or choice.get("index", 0) != 0):
            raise ModelResultError("INVALID_COMPLETION")
        delta = choice.get("delta")
        if not isinstance(delta, dict):
            raise ModelResultError("INVALID_COMPLETION")
        if delta.get("role", "assistant") != "assistant":
            raise ModelResultError("INVALID_STREAM_CONTENT")
        if self.finish_reason is not None:
            raise ModelResultError("INVALID_STREAM_CONTENT")
        self._observe_usage(event.get("usage"), terminal=choice.get("finish_reason") is not None)
        piece = delta.get("content")
        if piece is not None and not isinstance(piece, str):
            raise ModelResultError("INVALID_STREAM_CONTENT")
        piece = piece or ""
        self.reasoning_present = self.reasoning_present or bool(delta.get("reasoning_content"))
        self.refusal = self.refusal or bool(delta.get("refusal"))
        self.content_bytes += _utf8_size(piece)
        if self.content_bytes > self.max_content_bytes:
            raise ModelResultError("RESPONSE_TOO_LARGE")
        self.content += piece
        if delta.get("tool_calls") is not None:
            if not isinstance(delta["tool_calls"], list):
                raise ModelResultError("INVALID_TOOL_ARGUMENTS")
            for call in delta["tool_calls"]:
                self._tool_delta(call)
        if choice.get("finish_reason") is not None:
            finish = choice["finish_reason"]
            if not isinstance(finish, str) or not finish:
                raise ModelResultError("INCOMPLETE_COMPLETION")
            self.finish_reason = finish
        return piece

    def _observe_usage(self, usage: Any, *, terminal: bool) -> None:
        if usage is None:
            return
        if not isinstance(usage, dict):
            raise ModelResultError("INVALID_COMPLETION")
        if self.usage is not None:
            # Some compatible providers attach cumulative counters to every
            # unfinished choice. Replace snapshots; never sum them. Once final
            # accounting is observed, only supplemental fields may be added;
            # an existing measurement cannot change or disappear.
            before, after = normalize_usage(self.usage), normalize_usage(usage)
            if (self.usage_terminal and not _usage_extends(self.usage, usage)) or any(
                    count is not None and (after[key] is None or after[key] < count)
                    for key, count in before.items()):
                raise ModelResultError("CONFLICTING_USAGE")
        self.usage = usage
        self.usage_terminal = self.usage_terminal or terminal

    def _tool_delta(self, call: Any) -> None:
        if (not isinstance(call, dict) or type(call.get("index")) is not int
                or not 0 <= call["index"] < 32):
            raise ModelResultError("INVALID_TOOL_ARGUMENTS")
        target = self.calls.setdefault(call["index"], {"type": "function", "function": {"name": "", "arguments": ""}})
        for field in ("id", "type"):
            if field in call:
                if not isinstance(call[field], str) or (field in target and target[field] != call[field]):
                    raise ModelResultError("INVALID_TOOL_ARGUMENTS")
                target[field] = call[field]
        function = call.get("function", {})
        if not isinstance(function, dict):
            raise ModelResultError("INVALID_TOOL_ARGUMENTS")
        for field in ("name", "arguments"):
            if field in function:
                if not isinstance(function[field], str):
                    raise ModelResultError("INVALID_TOOL_ARGUMENTS")
                target["function"][field] += function[field]
                self.content_bytes += _utf8_size(function[field])
                if self.content_bytes > self.max_content_bytes:
                    raise ModelResultError("RESPONSE_TOO_LARGE")

    def finish(self) -> dict[str, Any]:
        if not self.done or self.finish_reason is None:
            raise ModelResultError("STREAM_COMPLETION_MISMATCH", usage=self.usage)
        message = {"content": self.content, "reasoning_content": self.reasoning_present,
                   "refusal": self.refusal}
        if self.calls:
            if sorted(self.calls) != list(range(len(self.calls))):
                raise ModelResultError("INVALID_TOOL_ARGUMENTS", request_complete=True)
            message["tool_calls"] = [self.calls[index] for index in sorted(self.calls)]
        return parse_completion({"model": self.model, "usage": self.usage,
                                 "choices": [{"index": 0, "message": message, "finish_reason": self.finish_reason}]},
                                self.expected_model, output_kind=self.output_kind,
                                model_matches=self.model_matches, max_content_bytes=self.max_content_bytes,
                                require_tool_ids=self.require_tool_ids)
