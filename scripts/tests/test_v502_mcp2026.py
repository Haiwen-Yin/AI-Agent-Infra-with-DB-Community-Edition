"""Independent HTTP peer exercises versioned MCP without a database or model."""
from copy import deepcopy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading

import pytest

from lib import mcp_2026 as modern, registered_protocols as protocols
from lib.agent_extension_contracts import digest


VERSION = "2026-07-28"
INPUT = {"type": "object", "properties": {"key": {"type": "string"}},
         "required": ["key"], "additionalProperties": False}
OUTPUT = {"type": ["array", "null"], "items": {"type": "string"}}
TOOL = {"name": "lookup", "inputSchema": INPUT, "outputSchema": OUTPUT,
        "annotations": {"readOnlyHint": True}}


@pytest.fixture
def peer():
    state = {"requests": [], "calls": 0, "mode": "normal", "value": ["observed"],
             "tokens": {"alice-token", "bob-token"}, "tool": deepcopy(TOOL)}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def respond(self, response, *, headers=None, status=200, sse=False):
            raw = json.dumps(response).encode() if response is not None else b""
            if sse:
                raw = b"data: " + raw + b"\n\n"
            self.send_response(status)
            self.send_header("Content-Type", "text/event-stream" if sse else "application/json")
            self.send_header("Content-Length", str(len(raw)))
            for key, value in (headers or {}).items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(raw)

        def do_POST(self):
            request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            headers = {key.lower(): value for key, value in self.headers.items()}
            state["requests"].append({"request": request, "headers": headers, "path": self.path})
            token = headers.get("authorization", "").removeprefix("Bearer ")
            if token not in state["tokens"]:
                return self.respond({"error": "denied"}, status=401)
            method, params = request["method"], request.get("params", {})
            legacy = method == "initialize" or headers.get("mcp-protocol-version") in {"2025-06-18", "2025-11-25"}
            if not legacy:
                meta = params.get("_meta", {})
                if (headers.get("mcp-protocol-version") != VERSION or meta.get("io.modelcontextprotocol/protocolVersion") != VERSION
                        or headers.get("mcp-method") != method or "mcp-session-id" in headers
                        or meta.get("io.modelcontextprotocol/clientCapabilities") != {}
                        or method == "tools/call" and headers.get("mcp-name") != params.get("name")):
                    return self.respond({"error": "header mismatch"}, status=400)
            if method == "notifications/initialized":
                return self.respond(None, status=202)
            if method == "initialize":
                result = {"protocolVersion": params["protocolVersion"], "capabilities": {"tools": {}}}
            elif method == "server/discover":
                result = {"supportedVersions": [VERSION], "capabilities": {
                    "tools": {}, "extensions": {"io.modelcontextprotocol/tasks": {}}}}
            elif method == "tools/list":
                result = {"tools": [deepcopy(state["tool"])]}
                if state["mode"] == "pages" and not params.get("cursor"):
                    result["nextCursor"] = "next"
                elif state["mode"] == "pages":
                    result["tools"][0]["name"] = "another"
                if state["mode"] == "repeated_cursor":
                    result["nextCursor"] = "same"
            elif method == "tools/call":
                state["calls"] += 1
                if state["mode"] == "disconnect":
                    self.close_connection = True
                    return
                result = {"content": [], "structuredContent": state["value"]}
            else:
                return self.respond({"error": "unknown method"}, status=404)
            if not legacy:
                result["resultType"] = "complete"
                if method in {"server/discover", "tools/list"}:
                    result.update(ttlMs=60000, cacheScope="private")
            mode = state["mode"]
            if mode == "missing_type":
                result.pop("resultType", None)
            elif mode in {"input_required", "task"}:
                result["resultType"] = mode
            elif mode == "bad_ttl":
                result["ttlMs"] = True
            elif mode == "bad_scope":
                result["cacheScope"] = "global"
            elif mode == "wrong_version":
                result["supportedVersions"] = ["1900-01-01"]
            elif mode == "result_version":
                result["_meta"] = {"io.modelcontextprotocol/protocolVersion": "1900-01-01"}
            elif mode == "missing_structured":
                result.pop("structuredContent", None)
            response = {"jsonrpc": "2.0", "id": request["id"], "result": result}
            if mode == "error":
                response = {"jsonrpc": "2.0", "id": request["id"], "error": {
                    "code": -32022, "message": "remote private text", "data": {"supported": ["1900-01-01"]}}}
            elif mode == "http_version_error":
                response = {"jsonrpc": "2.0", "id": request["id"], "error": {"code": -32022, "message": "private text"}}
                return self.respond(response, status=400)
            elif mode == "bad_id":
                response["id"] = "another-request"
            extra = ({"Mcp-Session-Id": "unexpected"} if mode == "session_header" else
                     {"MCP-Protocol-Version": "1900-01-01"} if mode == "version_header" else {})
            return self.respond(response, headers=extra, sse=mode == "sse")

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=0.01), daemon=True)
    thread.start()
    state["url"] = f"http://127.0.0.1:{server.server_port}/mcp"
    yield state
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)


def registration(peer, version=VERSION, token="alice-token"):
    return {"endpoint_id": "endpoint", "protocol_version": version, "endpoint_url": peer["url"],
            "version": 1, "current_revision": 1, "contract_digest": "endpoint-digest",
            "issuer_url": "https://issuer.example", "resource_url": "https://service.example",
            "auth_cipher": token, "timeout_seconds": 2, "max_response_bytes": 65536,
            "security_domain_id": "domain", "protocol_kind": "MCP", "status": "ACTIVE"}


@pytest.fixture(autouse=True)
def synthetic_credentials(monkeypatch):
    monkeypatch.setattr(protocols, "decrypt_section", lambda value: deepcopy(value) if isinstance(value, dict) else {"bearer_token": value})
    monkeypatch.setattr(protocols, "encrypt_section", lambda value: deepcopy(value))


def session(peer, monkeypatch, *, version=VERSION, authorize=None):
    record = registration(peer, version)
    return protocols.mcp_session(record, authorize=authorize or (lambda: record))


def test_real_modern_roundtrip_has_no_handshake_and_stable_inventory(peer, monkeypatch):
    client = session(peer, monkeypatch)
    observed = client.initialize()
    assert observed["unsupported_extensions"] == ["io.modelcontextprotocol/tasks"]
    assert observed["mrtr_supported"] is observed["subscriptions_supported"] is False
    assert protocols.remote_contracts(client)[0]["name"] == "lookup"
    value = client.rpc("tools/call", {"name": "lookup", "arguments": {"key": "x"}})
    modern.validate_schema(OUTPUT, value["structuredContent"])
    assert [x["request"]["method"] for x in peer["requests"]] == ["server/discover", "tools/list", "tools/call"]
    assert client.cache_observation == {"ttl_ms": 60000, "cache_scope": "private", "cache_reused": False}
    assert len({x["request"]["id"] for x in peer["requests"]}) == 3


@pytest.mark.parametrize("version", ["2025-06-18", "2025-11-25"])
def test_real_legacy_roundtrip_retains_initialize_and_missing_result_type(peer, monkeypatch, version):
    # The legacy output schema is an object, as its accepted implementation requires.
    peer["tool"]["outputSchema"] = {"type": "object"}
    peer["value"] = {"observed": True}
    client = session(peer, monkeypatch, version=version)
    client.initialize()
    assert protocols.remote_contracts(client)[0]["name"] == "lookup"
    assert client.rpc("tools/call", {"name": "lookup", "arguments": {"key": "x"}})["structuredContent"] == {"observed": True}
    assert [r["request"]["method"] for r in peer["requests"]] == ["initialize", "notifications/initialized", "tools/list", "tools/call"]
    assert all("_meta" not in r["request"].get("params", {}) for r in peer["requests"])


@pytest.mark.parametrize("version", ["2025-06-18", "2025-11-25"])
def test_legacy_revocation_after_handshake_denies_directory_before_send(peer, version):
    record = registration(peer, version)
    allowed, checks = [True], []
    def authorize():
        checks.append(True)
        if not allowed[0]:
            raise PermissionError("revoked original identity")
        return record
    client = protocols.mcp_session(record, authorize=authorize)
    client.initialize()
    assert len(checks) == 2
    allowed[0] = False
    with pytest.raises(PermissionError, match="revoked original identity"):
        protocols.remote_contracts(client)
    assert len(peer["requests"]) == 2


@pytest.mark.parametrize("version", ["2025-06-18", "2025-11-25"])
@pytest.mark.parametrize("field", ["auth_cipher", "issuer_url", "resource_url", "current_revision", "security_domain_id"])
def test_legacy_session_never_inherits_a_changed_identity_or_authority(peer, version, field):
    record = registration(peer, version)
    client = protocols.mcp_session(record, authorize=lambda: record)
    client.initialize()
    record[field] = "changed"
    with pytest.raises(PermissionError, match="session identity changed"):
        client.rpc("tools/list", {})
    assert len(peer["requests"]) == 2


@pytest.mark.parametrize("version", ["2025-06-18", "2025-11-25"])
def test_legacy_revocation_between_initialize_and_notification_denies_notification(peer, monkeypatch, version):
    record = registration(peer, version)
    def authorize():
        if peer["requests"]:
            raise PermissionError("revoked during handshake")
        return record
    with pytest.raises(PermissionError, match="revoked during handshake"):
        protocols.mcp_session(record, authorize=authorize).initialize()
    assert len(peer["requests"]) == 1


@pytest.mark.parametrize("mode,code", [
    ("missing_type", "MCP_RESULT_TYPE_INVALID"), ("input_required", "MCP_INPUT_REQUIRED_UNSUPPORTED"),
    ("task", "MCP_TASKS_UNSUPPORTED"), ("bad_ttl", "MCP_CACHE_POLICY_INVALID"),
    ("bad_scope", "MCP_CACHE_POLICY_INVALID"), ("wrong_version", "MCP_DISCOVERY_INVALID"),
    ("session_header", "MCP_SESSION_UNSUPPORTED"), ("version_header", "MCP_VERSION_MISMATCH"),
    ("error", "MCP_VERSION_MISMATCH"), ("bad_id", "MCP_RESPONSE_INVALID"),
    ("result_version", "MCP_VERSION_MISMATCH"), ("http_version_error", "MCP_VERSION_MISMATCH"),
])
def test_modern_response_errors_never_retry_or_accept_remote_text(peer, monkeypatch, mode, code):
    peer["mode"] = mode
    with pytest.raises(modern.MCPContractError, match=code) as error:
        session(peer, monkeypatch).initialize()
    assert str(error.value) == code and len(peer["requests"]) == 1


@pytest.mark.parametrize("method", ["subscriptions/listen", "tasks/get", "sampling/createMessage", "initialize"])
def test_unsupported_interactions_do_not_send(peer, monkeypatch, method):
    with pytest.raises(modern.MCPUnsupportedInteraction, match="MCP_METHOD_UNSUPPORTED"):
        session(peer, monkeypatch).rpc(method, {})
    assert not peer["requests"]


@pytest.mark.parametrize("changed", ["issuer_url", "resource_url", "version", "current_revision", "contract_digest", "endpoint_url"])
def test_registration_or_issuer_change_denies_before_request(peer, monkeypatch, changed):
    record = registration(peer)
    client = protocols.mcp_session(record, authorize=lambda: record)
    client.initialize()
    record[changed] = "changed"
    with pytest.raises(PermissionError, match="registration or issuer changed"):
        client.rpc("tools/list", {})
    assert len(peer["requests"]) == 1


def test_each_request_rechecks_identity_and_refetches_private_directory(peer, monkeypatch):
    record = registration(peer)
    checks = []
    def authorize():
        checks.append(True)
        if len(checks) == 4:
            raise PermissionError("revoked")
        return record
    client = protocols.mcp_session(record, authorize=authorize)
    client.initialize()
    protocols.remote_contracts(client)
    # Credentials are read afresh rather than inherited from the prior HTTP call.
    record["auth_cipher"] = "bob-token"
    protocols.remote_contracts(client)
    with pytest.raises(PermissionError, match="revoked"):
        protocols.remote_contracts(client)
    assert len(checks) == 4 and len(peer["requests"]) == 3
    assert [r["headers"]["authorization"] for r in peer["requests"]] == ["Bearer alice-token", "Bearer alice-token", "Bearer bob-token"]


def test_sse_and_paginated_inventory_use_independent_requests(peer, monkeypatch):
    client = session(peer, monkeypatch)
    peer["mode"] = "sse"
    client.initialize()
    peer["mode"] = "pages"
    assert [x["name"] for x in protocols.remote_contracts(client)] == ["another", "lookup"]
    assert len(peer["requests"]) == 3


def test_repeated_cursor_is_bounded(peer, monkeypatch):
    client = session(peer, monkeypatch)
    client.initialize()
    peer["mode"] = "repeated_cursor"
    with pytest.raises(ValueError, match="duplicates|cursor"):
        protocols.remote_contracts(client)
    assert len(peer["requests"]) == 3


@pytest.mark.parametrize("schema", [
    {"$ref": "https://private.example/schema"}, {"$ref": "#"},
    {"$dynamicRef": "#"}, {"type": "string", "pattern": "(a+)+$"},
    {"allOf": [{"type": "object"}]}, {"oneOf": [{"type": "object"}]},
    {"type": "object", "properties": {"x": {"x-mcp-header": "Authorization"}}},
    {"type": "array", "prefixItems": [{}] * 33},
    {"type": "object", "properties": {str(i): {} for i in range(129)}},
])
def test_unbounded_or_unsupported_schemas_reject_without_resolution(schema):
    with pytest.raises(ValueError, match="MCP_SCHEMA_UNSUPPORTED"):
        modern.validate_schema(schema, check_value=False)


@pytest.mark.parametrize("value", [None, ["a", "b"], []])
def test_nonobject_json_output_types_are_preserved(value):
    modern.validate_schema(OUTPUT, value)


def test_schema_limits_and_invalid_output_fail_closed():
    nested = {}
    for _ in range(14):
        nested = {"properties": {"nested": nested}}
    with pytest.raises(ValueError, match="nesting"):
        modern.validate_schema(nested, check_value=False)
    with pytest.raises(modern.MCPContractError, match="MCP_SCHEMA_VALUE_INVALID"):
        modern.validate_schema(OUTPUT, [4])
    modern.validate_schema(True, {"arbitrary": "value"})


def test_schema_value_work_is_bounded_before_validation():
    with pytest.raises(modern.MCPContractError, match="MCP_VALUE_WORK_LIMIT"):
        modern.validate_schema({"type": "array", "items": {}}, list(range(2048)))
    with pytest.raises(modern.MCPContractError, match="MCP_SCHEMA_UNSUPPORTED"):
        modern.validate_schema({"enum": list(range(65))}, check_value=False)


class Ledger:
    """Dictionary transaction double; it never opens a database connection."""
    def __init__(self, record):
        self.record = record
        self.calls, self.attempts, self.credentials, self.tools = {}, {}, {}, {}
        self.permission_version = 1
        self.active = True
        self.credential_active = True
        self.audits = []

    def query_one(self, sql, params):
        if "CX_PRINCIPALS" in sql:
            return {"status": "ACTIVE", "permission_version": self.permission_version}
        if "CX_PROTOCOL_CREDENTIALS" in sql:
            return self.credentials.get(params["call"])
        if "CX_PROTOCOL_TOOLS" in sql:
            value = self.tools.get(params["tool"])
            if value and ("STATUS='APPROVED'" not in sql or value["status"] == "APPROVED") and value["tool_digest"] == params["digest"]:
                return deepcopy(value)
            return None
        if "CX_PROTOCOL_CALLS" in sql:
            if "key" in params:
                return next((deepcopy(x) for x in self.calls.values() if x["actor_id"] == params["actor"] and x["idempotency_key"] == params["key"]), None)
            return deepcopy(self.calls.get(params["call"]))
        if "CX_PROTOCOL_ATTEMPTS" in sql:
            if "attempt" in params:
                value = self.attempts.get(params["attempt"])
                return deepcopy(value) if value and value["status"] == "SENDING" else None
            return next((deepcopy(x) for x in self.attempts.values() if x["call_id"] == params["call"]), None)
        raise AssertionError(sql)

    def execute(self, sql, params):
        if sql.startswith("INSERT INTO CX_PROTOCOL_CALLS"):
            self.calls[params["call_id"]] = {**params, "cancel_requested": False, "created_at": "now"}
        elif sql.startswith("INSERT INTO CX_PROTOCOL_CREDENTIALS"):
            self.credentials[params["call"]] = {"token_digest": params["token"], "instance_id": params["instance"], "fencing_token": params["fence"]}
        elif sql.startswith("INSERT INTO CX_PROTOCOL_ATTEMPTS"):
            self.attempts[params["attempt"]] = {"attempt_id": params["attempt"], "call_id": params["call"], "status": "SENDING"}
        elif sql.startswith("UPDATE CX_PROTOCOL_CALLS"):
            value = self.calls[params["call"]]
            value["status"] = params.get("state", "SENDING")
            if "cipher" in params:
                value.update(result_cipher=params["cipher"], result_digest=params["digest"])
        elif sql.startswith("UPDATE CX_PROTOCOL_ATTEMPTS"):
            self.attempts[params["attempt"]]["status"] = params["state"]
        elif sql.startswith("UPDATE CX_PROTOCOL_TOOLS") and "APPROVED_BY=NULL" in sql:
            for value in self.tools.values():
                if value["status"] == "APPROVED":
                    value["status"] = "REVOKED"
        elif sql.startswith("INSERT INTO CX_PROTOCOL_TOOLS"):
            self.tools[params["tool"]] = {"tool_name": params["tool"], "tool_digest": params["digest"],
                "input_schema_json": params["input_schema"], "output_schema_json": params["output_schema"],
                "status": "DISCOVERED", "read_only": params["readonly"]}
        else:
            raise AssertionError(sql)
        return 1


@pytest.fixture
def workflow(peer, monkeypatch):
    record = registration(peer)
    ledger = Ledger(record)
    contract = protocols.tool_contract(TOOL, protocol_version=VERSION)
    ledger.tools["lookup"] = {"tool_name": "lookup", "tool_digest": digest(contract),
        "input_schema_json": json.dumps(INPUT), "output_schema_json": json.dumps(OUTPUT),
        "status": "APPROVED", "read_only": 1}
    def endpoint(actor, endpoint_id, **_kwargs):
        if not ledger.active:
            raise PermissionError("endpoint revoked")
        return dict(record)
    monkeypatch.setattr(protocols, "endpoint", endpoint)
    monkeypatch.setattr(protocols.connection, "execute_transaction_callback", lambda callback: callback(ledger))
    monkeypatch.setattr(protocols.effective_capabilities, "require", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(protocols.identity_api, "_audit_tx", lambda *_args: ledger.audits.append(_args))
    def credential(*_args, **_kwargs):
        if not ledger.credential_active:
            raise PermissionError("original credential revoked")
        return {"fencing_token": 7, "security_domain_id": "domain"}
    monkeypatch.setattr(protocols.agent_gateway_api, "_authenticate_access_token_digest", credential)
    token = protocols._transport.set({"instance_id": "instance", "token_digest": "original", "fencing_token": 7})
    yield ledger
    protocols._transport.reset(token)


def invoke(ledger, key="operation"):
    return protocols.call_tool("alice", "endpoint", "lookup", ledger.tools["lookup"]["tool_digest"], {"key": "x"}, key)


@pytest.mark.parametrize("value", [["observed"], None])
def test_governed_call_uses_existing_attempt_and_replays_without_resending(peer, workflow, value):
    peer["value"] = value
    first = invoke(workflow)
    assert first["status"] == "SUCCEEDED" and first["result"]["structuredContent"] == value
    second = invoke(workflow)
    assert second["call_id"] == first["call_id"] and peer["calls"] == 1
    assert len(workflow.attempts) == 1 and len(peer["requests"]) == 3


def test_governed_disconnect_is_unobserved_and_idempotent_retry_sends_nothing(peer, workflow):
    peer["mode"] = "disconnect"
    result = invoke(workflow)
    assert result["status"] == "UNOBSERVED"
    assert invoke(workflow)["status"] == "UNOBSERVED"
    assert peer["calls"] == 1 and len(peer["requests"]) == 3


def test_missing_structured_value_cannot_masquerade_as_valid_null(peer, workflow, monkeypatch):
    peer["value"] = None
    original = protocols.post
    def missing_on_call(record, request, extra):
        if request["method"] == "tools/call":
            peer["mode"] = "missing_structured"
        return original(record, request, extra)
    monkeypatch.setattr(protocols, "post", missing_on_call)
    result = invoke(workflow)
    assert result["status"] == "UNOBSERVED"
    assert result["error_code"] == "MCP_STRUCTURED_CONTENT_MISSING" and peer["calls"] == 1


def test_conflicting_business_key_is_rejected_without_second_request(peer, workflow):
    invoke(workflow)
    with pytest.raises(ValueError, match="idempotency"):
        protocols.call_tool("alice", "endpoint", "lookup", workflow.tools["lookup"]["tool_digest"], {"key": "changed"}, "operation")
    assert peer["calls"] == 1 and len(peer["requests"]) == 3


@pytest.mark.parametrize("mode,code", [("input_required", "MCP_INPUT_REQUIRED_UNSUPPORTED"), ("task", "MCP_TASKS_UNSUPPORTED")])
def test_interim_call_results_have_explicit_unsupported_diagnostic(peer, workflow, monkeypatch, mode, code):
    original = protocols.post
    def change_only_call(record, request, extra):
        if request["method"] == "tools/call":
            peer["mode"] = mode
        return original(record, request, extra)
    monkeypatch.setattr(protocols, "post", change_only_call)
    result = invoke(workflow)
    assert result["status"] == "UNOBSERVED" and result["error_code"] == code
    assert peer["calls"] == 1


def test_rediscovery_revokes_identical_approval_and_blocks_call(peer, workflow):
    result = protocols.discover("alice", "endpoint")
    assert result["items"][0]["tool_digest"] == workflow.tools["lookup"]["tool_digest"]
    assert workflow.tools["lookup"]["status"] == "REVOKED"
    assert result["interoperability"]["cache_reused"] is False
    with pytest.raises(PermissionError, match="approval"):
        invoke(workflow)
    assert peer["calls"] == 0


@pytest.mark.parametrize("change", ["credential", "permission", "endpoint", "approval"])
def test_current_authority_is_rechecked_before_every_network_request(peer, workflow, monkeypatch, change):
    original = protocols.post
    def change_after_discovery(record, request, extra):
        result = original(record, request, extra)
        if request["method"] == "server/discover":
            if change == "credential":
                workflow.credential_active = False
            elif change == "permission":
                workflow.permission_version += 1
            elif change == "endpoint":
                workflow.active = False
            else:
                workflow.tools["lookup"]["status"] = "REVOKED"
        return result
    monkeypatch.setattr(protocols, "post", change_after_discovery)
    result = invoke(workflow)
    # Existing completion authority marks a revoked/fenced attempt UNOBSERVED;
    # absence of another send is checked independently on the peer.
    assert result["status"] == "UNOBSERVED" and peer["calls"] == 0
    assert len(peer["requests"]) == 1
