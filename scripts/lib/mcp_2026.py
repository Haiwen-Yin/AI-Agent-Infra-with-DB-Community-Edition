"""Bounded MCP 2026-07-28 client; no handshake, subscriptions or Tasks.

No directory cache or cross-call authentication state is retained. Each request
is authorized against the original registration before credentials are loaded.
Unsupported interactions never trigger a second request automatically.
"""
from __future__ import annotations

import json
import urllib.error

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, ValidationError

from .agent_extension_contracts import bounded_json, identifier, safe_key

VERSION = "2026-07-28"
SDK_IDENTITY = "chuanxu-bounded-mcp-http/2026-07-28"
META_VERSION = "io.modelcontextprotocol/protocolVersion"
META_CAPABILITIES = "io.modelcontextprotocol/clientCapabilities"
META_CLIENT = "io.modelcontextprotocol/clientInfo"
SUPPORTED_METHODS = frozenset({"server/discover", "tools/list", "tools/call"})
SCHEMA_KEYWORDS = frozenset({
    "$schema", "title", "description", "default", "examples", "deprecated",
    "readOnly", "writeOnly", "type", "enum", "const", "properties", "required",
    "additionalProperties", "items", "prefixItems", "minItems", "maxItems",
    "minLength", "maxLength", "minimum", "maximum",
    "exclusiveMinimum", "exclusiveMaximum", "multipleOf", "minProperties",
    "maxProperties", "format",
})


class MCPContractError(ValueError):
    """A fixed diagnostic; remote text and credentials are never included."""
    def __init__(self, code):
        self.code = code
        super().__init__(code)


class MCPUnsupportedInteraction(MCPContractError):
    pass


def validate_schema(schema, value=None, *, check_value=True):
    """A deliberately small non-recursive schema subset, with no ref fetches.

    References, regexes and composition are rejected rather than delegated to
    unbounded evaluation. Boolean schemas and non-object JSON outputs are valid.
    """
    bounded_json(schema, maximum=32768, depth=12)
    visited = 0

    def inspect(item):
        nonlocal visited
        visited += 1
        if visited > 128 or not isinstance(item, (dict, bool)):
            raise MCPContractError("MCP_SCHEMA_UNSUPPORTED")
        if isinstance(item, bool):
            return
        if set(item) - SCHEMA_KEYWORDS:
            raise MCPContractError("MCP_SCHEMA_UNSUPPORTED")
        if "enum" in item and (not isinstance(item["enum"], list) or len(item["enum"]) > 64):
            raise MCPContractError("MCP_SCHEMA_UNSUPPORTED")
        for key in ("properties",):
            if key in item:
                if not isinstance(item[key], dict) or len(item[key]) > 128:
                    raise MCPContractError("MCP_SCHEMA_UNSUPPORTED")
                for nested in item[key].values():
                    inspect(nested)
        for key in ("items", "additionalProperties"):
            if key in item:
                inspect(item[key])
        if "prefixItems" in item:
            if not isinstance(item["prefixItems"], list) or len(item["prefixItems"]) > 32:
                raise MCPContractError("MCP_SCHEMA_UNSUPPORTED")
            for nested in item["prefixItems"]:
                inspect(nested)

    inspect(schema)
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError:
        raise MCPContractError("MCP_SCHEMA_INVALID") from None
    if check_value:
        bounded_json(value, maximum=262144, depth=24)
        pending, total = [value], 0
        while pending:
            item = pending.pop()
            total += 1
            if total > 2048:
                raise MCPContractError("MCP_VALUE_WORK_LIMIT")
            if isinstance(item, dict):
                pending.extend(item.values())
            elif isinstance(item, list):
                pending.extend(item)
        try:
            Draft202012Validator(schema).validate(value)
        except ValidationError:
            raise MCPContractError("MCP_SCHEMA_VALUE_INVALID") from None


def cache_policy(result):
    ttl, scope = result.get("ttlMs"), result.get("cacheScope")
    if type(ttl) is not int or ttl < 0 or scope not in {"public", "private"}:
        raise MCPContractError("MCP_CACHE_POLICY_INVALID")
    # This adapter deliberately fetches every directory; public is never treated
    # as permission to share the authenticated result across callers.
    return {"ttl_ms": ttl, "cache_scope": scope, "cache_reused": False}


class MCP2026Session:
    def __init__(self, record, post, *, authorize):
        self.record = dict(record)
        self._post, self._authorize = post, authorize
        self.discovery = None
        self.cache_observation = None

    def _fresh(self):
        current = self._authorize()
        for key in ("endpoint_id", "version", "current_revision", "protocol_version",
                    "endpoint_url", "contract_digest", "issuer_url", "resource_url"):
            if current.get(key) != self.record.get(key):
                raise PermissionError("MCP endpoint registration or issuer changed")
        if current.get("protocol_version") != VERSION:
            raise MCPContractError("MCP_VERSION_MISMATCH")
        return current

    def rpc(self, method, params):
        if method not in SUPPORTED_METHODS:
            raise MCPUnsupportedInteraction("MCP_METHOD_UNSUPPORTED")
        if not isinstance(params, dict) or "_meta" in params:
            raise MCPContractError("MCP_REQUEST_INVALID")
        request_id = identifier("MR")
        request_params = {**params, "_meta": {
            META_VERSION: VERSION, META_CAPABILITIES: {},
            META_CLIENT: {"name": "chuanxu", "version": "5.0.5"},
        }}
        extra = {"MCP-Protocol-Version": VERSION, "Mcp-Method": method,
                 "Cache-Control": "no-store"}
        if method == "tools/call":
            extra["Mcp-Name"] = safe_key(params.get("name"), maximum=256)
            if not isinstance(params.get("arguments"), dict):
                raise MCPContractError("MCP_ARGUMENTS_INVALID")
        current = self._fresh()
        try:
            result, response_headers = self._post(current, {
                "jsonrpc": "2.0", "id": request_id, "method": method,
                "params": request_params,
            }, extra)
        except urllib.error.HTTPError as exc:
            # Preserve a fixed version diagnostic from the required HTTP 400
            # response, never remote messages or an automatic version retry.
            if exc.code == 400:
                raw = exc.read(min(int(current["max_response_bytes"]), 65536) + 1)
                try:
                    failure = json.loads(raw)
                    if (len(raw) <= 65536 and isinstance(failure, dict)
                            and isinstance(failure.get("error"), dict)
                            and failure["error"].get("code") == -32022):
                        raise MCPContractError("MCP_VERSION_MISMATCH") from None
                except (json.JSONDecodeError, UnicodeDecodeError):
                    pass
            raise
        observed = {key.lower(): value for key, value in response_headers.items()}
        if "mcp-session-id" in observed:
            raise MCPContractError("MCP_SESSION_UNSUPPORTED")
        if observed.get("mcp-protocol-version", VERSION) != VERSION:
            raise MCPContractError("MCP_VERSION_MISMATCH")
        if (not isinstance(result, dict) or result.get("jsonrpc") != "2.0"
                or result.get("id") != request_id):
            raise MCPContractError("MCP_RESPONSE_INVALID")
        if "error" in result:
            error = result["error"]
            code = error.get("code") if isinstance(error, dict) else None
            raise MCPContractError("MCP_VERSION_MISMATCH" if code == -32022 else "MCP_REMOTE_ERROR")
        response = result.get("result")
        if not isinstance(response, dict):
            raise MCPContractError("MCP_RESPONSE_INVALID")
        meta = response.get("_meta", {})
        if not isinstance(meta, dict) or meta.get(META_VERSION, VERSION) != VERSION:
            raise MCPContractError("MCP_VERSION_MISMATCH")
        kind = response.get("resultType")
        if kind == "input_required":
            raise MCPUnsupportedInteraction("MCP_INPUT_REQUIRED_UNSUPPORTED")
        if kind == "task":
            raise MCPUnsupportedInteraction("MCP_TASKS_UNSUPPORTED")
        if kind != "complete":
            raise MCPContractError("MCP_RESULT_TYPE_INVALID")
        if method in {"server/discover", "tools/list"}:
            self.cache_observation = cache_policy(response)
        return response

    def initialize(self):
        """Expose the existing session interface without a legacy handshake."""
        result = self.rpc("server/discover", {})
        versions, capabilities = result.get("supportedVersions"), result.get("capabilities")
        if (not isinstance(versions, list) or len(versions) > 32
                or any(not isinstance(value, str) for value in versions)
                or VERSION not in versions or not isinstance(capabilities, dict)
                or not isinstance(capabilities.get("tools"), dict)):
            raise MCPContractError("MCP_DISCOVERY_INVALID")
        extensions = capabilities.get("extensions", {})
        if not isinstance(extensions, dict):
            raise MCPContractError("MCP_DISCOVERY_INVALID")
        self.discovery = {"protocol_version": VERSION,
                          "supported_methods": sorted(SUPPORTED_METHODS),
                          "unsupported_extensions": sorted(extensions),
                          "subscriptions_supported": False, "mrtr_supported": False,
                          "cache_reused": False}
        return self.discovery
