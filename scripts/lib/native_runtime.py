"""Reference local Runtime Worker for v4.3.6.

The Worker is a control-plane reference implementation.  It executes one
database-leased unit at a time, uses a fresh in-memory message list, and never
reuses a previous Agent's credentials, workspace, or model context. Customer
Runtime Adapters may implement the same lifecycle contract externally.
"""

from __future__ import annotations

import json
import logging
import socket
import urllib.error
import urllib.request
import time
from contextvars import ContextVar
from urllib.parse import urlsplit
from typing import Any, Dict, List, Optional

from . import connection, deployment_adapters, identity_api, native_agent_api, runtime_isolation, content_security, answer_planning
from .llm_transport import request_timeout_seconds
from . import model_dispatch, model_credentials
from .continuity_state import ContinuityError
from .model_results import (ChatCompletionStream, ModelResultError, decode_json,
                            parse_completion, sse_events)

logger = logging.getLogger(__name__)
_model_observer = ContextVar("native_model_observer", default=None)


def _row(row: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    return {str(k).lower(): v for k, v in dict(row).items()} if row else None


def local_worker_id() -> str:
    return "native-worker:" + socket.gethostname()


def _parse(value: Any, fallback: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(str(value or ""))
    except (TypeError, ValueError):
        return fallback


def _llm_profile(profile_id: str) -> Optional[Dict[str, Any]]:
    if not profile_id:
        return None
    return _row(connection.execute_query_one(
        "SELECT PROFILE_ID,VERSION,PROVIDER_URL,MODEL_ID,API_KEY_CIPHER,STATUS FROM CX_LLM_PROVIDER_PROFILES "
        "WHERE PROFILE_ID=:id AND STATUS='ACTIVE'", {"id": profile_id},
    ))


def _provider_messages(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Combine leading system instructions for providers accepting one system turn.

    Preserve order and roles; never promote conversation text into system data.
    """
    leading = []
    index = 0
    while index < len(messages) and messages[index].get("role") == "system":
        leading.append(str(messages[index].get("content") or ""))
        index += 1
    if len(leading) < 2:
        return [dict(message) for message in messages]
    return [{"role": "system", "content": "\n\n".join(leading)}, *[dict(message) for message in messages[index:]]]


def _failure_code(exc: Exception) -> str:
    """Persist only bounded local error categories, never remote bodies."""
    if isinstance(exc, model_dispatch.ModelNotDispatched): return exc.code
    if isinstance(exc, ModelResultError): return 'LLM_' + exc.code
    if isinstance(exc,PermissionError): return 'AUTHORITY_DENIED'
    if isinstance(exc,runtime_isolation.IsolationError): return 'RUNTIME_ISOLATION_UNAVAILABLE'
    known={
        'LLM provider URL is invalid':'LLM_URL_INVALID',
        'LLM provider profile is incomplete':'LLM_PROFILE_INCOMPLETE',
        'LLM provider response is too large':'LLM_RESPONSE_TOO_LARGE',
        'LLM provider returned no content':'LLM_EMPTY_RESPONSE',
        'LLM provider request failed':'LLM_REQUEST_FAILED',
        'LLM provider streaming request failed':'LLM_STREAM_FAILED',
        'LLM provider stream ended before completion':'LLM_STREAM_INCOMPLETE',
        'Agent is not active':'AGENT_INACTIVE',
        'Agent has no active LLM Provider Profile':'LLM_PROFILE_UNAVAILABLE',
        'Deployment target is unavailable':'DEPLOYMENT_TARGET_UNAVAILABLE',
        'Deployment target has no verified runtime adapter':'RUNTIME_ADAPTER_UNVERIFIED',
    }
    code=known.get(str(exc),'RUNTIME_EXECUTION_FAILED')
    if code in {'LLM_REQUEST_FAILED','LLM_STREAM_FAILED'}:
        cause=exc.__cause__
        if isinstance(cause,TimeoutError) or isinstance(getattr(cause,'reason',None),TimeoutError): return 'LLM_REQUEST_TIMEOUT'
        if isinstance(cause,urllib.error.HTTPError): return 'LLM_HTTP_'+str(int(cause.code))
    return code


def _call_llm(profile: Dict[str, Any], messages: List[Dict[str, Any]], *, managed_input: bool = False,
              output_kind: str = "text", request_fields: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Call an OpenAI-compatible endpoint without logging prompt or secrets."""
    content_security.inspect_messages(messages, allow_managed_images=managed_input)
    if output_kind not in {"text", "structured", "tool"}:
        raise ValueError("Unsupported model output contract")
    fields = dict(request_fields or {})
    if set(fields) - {"response_format", "tools", "tool_choice", "max_tokens", "temperature"}:
        raise ValueError("Unsupported model request fields")
    from .agent_extension_contracts import bounded_json
    bounded_json(fields, maximum=262144)
    if "max_tokens" in fields and (type(fields["max_tokens"]) is not int or not 1 <= fields["max_tokens"] <= 32768):
        raise ValueError("Invalid model output budget")
    if "temperature" in fields and (type(fields["temperature"]) not in {int, float} or not 0 <= fields["temperature"] <= 2):
        raise ValueError("Invalid model temperature")
    messages = _provider_messages(messages)
    provider_url = str(profile.get("provider_url") or "").strip().rstrip("/")
    parsed = urlsplit(provider_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
        raise RuntimeError("LLM provider URL is invalid")
    url = provider_url + "/chat/completions"
    model = str(profile.get("model_id") or "")
    if not url or not model:
        raise RuntimeError("LLM provider profile is incomplete")
    headers = {"Content-Type": "application/json"}
    cipher = str(profile.get("api_key_cipher") or "")
    if cipher:
        from .connection_crypto import decrypt_section
        secret = str(decrypt_section(cipher).get("api_key") or "")
        if secret:
            headers["Authorization"] = "Bearer " + secret
    from .provider_capability_probes import apply_parameters
    request_payload = apply_parameters(profile, {"model": model, "messages": messages, "stream": False, **fields})
    from . import answer_context
    request_payload,input_budget=answer_context.final_payload(request_payload)
    payload = json.dumps(request_payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(url, data=payload, headers=headers, method="POST")
    with model_dispatch.dispatch(profile, request_payload) as ticket:
        try:
            with ticket.open(request, timeout=ticket.timeout_seconds(request_timeout_seconds())) as response:
                raw = ticket.read_response(response, 4 * 1024 * 1024)
                result = decode_json(raw, max_bytes=4 * 1024 * 1024)
        except ModelResultError:
            raise
        except (model_dispatch.ModelNotDispatched, ContinuityError):
            raise
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            raise RuntimeError("LLM provider request failed") from exc
        parsed = parse_completion(result, model, output_kind=output_kind, model_matches=native_agent_api._llm_model_matches)
        ticket.observe_result(parsed)
        ticket.response_complete()
        content = parsed["content"]
        try:
            content_security.enforce(content, "OUTPUT")
            if parsed.get("tool_calls"):
                content_security.enforce(json.dumps(parsed["tool_calls"], ensure_ascii=False), "OUTPUT")
        except content_security.ContentDenied as exc:
            exc.model_observation = {key: parsed[key] for key in ("model", "usage", "usage_observation", "usage_field_provenance", "request_complete")}
            raise
        return {key: parsed[key] for key in ("content", "model", "finish_reason", "request_complete", "structured", "tool_calls",
                                           "usage", "usage_observation", "usage_field_provenance")} | {"request_id": ticket.request_id} | (
                                               {'provider_input_budget':input_budget} if input_budget else {})


def _stream_llm(profile: Dict[str, Any], messages: List[Dict[str, Any]], on_delta: Any, *, request_fields=None) -> Dict[str, Any]:
    """Stream OpenAI-compatible deltas without retaining or logging prompts."""
    content_security.inspect_messages(messages)
    messages = _provider_messages(messages)
    provider_url = str(profile.get("provider_url") or "").strip().rstrip("/")
    parsed = urlsplit(provider_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
        raise RuntimeError("LLM provider URL is invalid")
    model = str(profile.get("model_id") or "")
    if not model:
        raise RuntimeError("LLM provider profile is incomplete")
    headers = {"Content-Type": "application/json", "Accept": "text/event-stream"}
    cipher = str(profile.get("api_key_cipher") or "")
    if cipher:
        from .connection_crypto import decrypt_section
        secret = str(decrypt_section(cipher).get("api_key") or "")
        if secret:
            headers["Authorization"] = "Bearer " + secret
    from .provider_capability_probes import apply_parameters
    fields=dict(request_fields or {})
    if (set(fields)-{'max_tokens'} or 'max_tokens' in fields and
            (type(fields['max_tokens']) is not int or not 1<=fields['max_tokens']<=32768)):
        raise ValueError('Unsupported streaming text request fields')
    request_payload = apply_parameters(profile, {"model": model, "messages": messages, "stream": True,
                                                "stream_options": {"include_usage": True},**fields})
    from . import answer_context
    request_payload,input_budget=answer_context.final_payload(request_payload)
    payload = json.dumps(request_payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(provider_url + "/chat/completions", data=payload, headers=headers, method="POST")
    content = ""
    pending = ""
    completed = False
    parser = ChatCompletionStream(model, model_matches=native_agent_api._llm_model_matches)
    with model_dispatch.dispatch(profile, request_payload) as ticket:
        try:
            with ticket.open(request, timeout=ticket.timeout_seconds(request_timeout_seconds(), stream=True)) as response:
                for event in sse_events(ticket.stream_response(response)):
                    ticket.check_deadline()
                    piece = parser.feed(event)
                    if parser.done:
                        break
                    if not piece:
                        continue
                    ticket.first_token()
                    if not content and _model_observer.get():
                        _model_observer.get()(time.monotonic())
                    content += piece
                    pending += piece
                parsed = parser.finish()
                ticket.observe_result(parsed)
                completed = parsed["request_complete"]
                if not completed:
                    raise RuntimeError("LLM provider stream ended before completion")
                ticket.response_complete()
                # Inspect complete output before releasing any bytes; secrets
                # can be split across arbitrary provider chunks.
                try:
                    content_security.enforce(content, "OUTPUT")
                except content_security.ContentDenied as exc:
                    exc.model_observation = {key: parsed[key] for key in ("model", "usage", "usage_observation", "usage_field_provenance", "request_complete")}
                    raise
                if pending:
                    on_delta(pending)
        except content_security.ContentDenied:
            raise
        except ModelResultError:
            raise
        except (model_dispatch.ModelNotDispatched, ContinuityError):
            raise
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            raise RuntimeError("LLM provider streaming request failed") from exc
        if not content:
            raise RuntimeError("LLM provider returned no content")
        return {key: parsed[key] for key in ("content", "model", "finish_reason", "request_complete",
                                           "usage", "usage_observation", "usage_field_provenance")} | {"request_id": ticket.request_id} | (
                                               {'provider_input_budget':input_budget} if input_budget else {})


def _set_profile_health(profile_id: str, state: str, expected_version: Optional[int] = None) -> None:
    connection.execute(
        "UPDATE CX_LLM_PROVIDER_PROFILES SET HEALTH_STATE=:state,UPDATED_AT=CURRENT_TIMESTAMP "
        "WHERE PROFILE_ID=:id AND STATUS='ACTIVE'" + (" AND VERSION=:version" if expected_version is not None else ""),
        {"state": state[:32], "id": profile_id, **({"version": expected_version} if expected_version is not None else {})},
    )


def _model_runtime_enabled():
    from . import edition_features
    return getattr(edition_features, 'MODEL_RUNTIME_CONTEXT_ENABLED', False) is True


def _runtime_execution_digest(execution, payload):
    return native_agent_api._digest({
        'execution_id': str(execution.get('execution_id') or ''),
        'agent_id': str(execution.get('agent_id') or ''), 'target_id': str(execution.get('target_id') or ''),
        'isolation_level': str(execution.get('isolation_level') or ''),
        'context_digest': str(execution.get('context_digest') or ''),
        'input_digest': native_agent_api._digest(payload)})


def _runtime_channel_source(tx, payload):
    dispatch = _channel_dispatch(payload)
    if not dispatch:
        return None
    source = _row(tx.query_one(
        'SELECT PRINCIPAL_ID,BODY_TEXT,THREAD_TYPE,THREAD_ID,REFERENCE_JSON,REDACTED_AT,MESSAGE_TYPE '
        'FROM CX_CHANNEL_MESSAGES WHERE MESSAGE_ID=:message_id AND CHANNEL_ID=:channel_id',
        {'message_id': dispatch.get('message_id'), 'channel_id': dispatch.get('channel_id')}))
    if (not source or source.get('redacted_at') is not None or source.get('message_type') != 'TEXT'
            or source.get('principal_id') != dispatch.get('requester_principal_id')
            or str(source.get('thread_id') or '') != str(dispatch.get('thread_id') or '')
            or source.get('thread_type') != dispatch.get('thread_type')):
        raise PermissionError('The original Channel message is no longer current')
    # Oracle represents an empty thread locator as NULL. Retain one digest
    # across backend round trips without changing the source's actual meaning.
    source['thread_id'] = str(source.get('thread_id') or '')
    if dispatch.get('kind') == 'BUSINESS_MENTION':
        mode_column = '"MODE"' if str(connection.DATABASE_DIALECT).lower() == 'oracle' else 'MODE'
        configured = _row(tx.query_one('SELECT POLICY_ID,' + mode_column + ',ALLOW_MODEL_SUPPLEMENT,'
            "DISCLOSURE_PROFILES_JSON,VERSION FROM CX_PORTAL_KNOWLEDGE_POLICY WHERE POLICY_ID='DEFAULT'", {}))
        if not configured:
            raise PermissionError('The original Channel knowledge policy is unavailable')
        # Native NUMBER revisions may be Decimal on YashanDB. Keep the same
        # canonical integer across backends before hashing the source policy;
        # fractional or invalid revisions must never collapse to an integer.
        from decimal import Decimal
        revision = configured.get('version')
        try:
            normalized_revision = int(revision)
        except (TypeError, ValueError, OverflowError) as exc:
            raise PermissionError('The original Channel knowledge policy revision is invalid') from exc
        if type(revision) not in (int, Decimal) or normalized_revision < 1 or revision != normalized_revision:
            raise PermissionError('The original Channel knowledge policy revision is invalid')
        configured['version'] = normalized_revision
        source['knowledge_policy'] = configured
    return native_agent_api._digest(source)


def bind_model_credential(tx, actor, execution_id, payload, *, required_scope):
    """Bind a new business execution to its actual original HTTP credential.

    Called only by trusted enqueue adapters in their insertion transaction.
    Public messages and payload fields can never supply a credential receipt.
    """
    if not _model_runtime_enabled():
        return None
    execution = _row(tx.query_one('SELECT * FROM CX_RUNTIME_EXECUTIONS WHERE EXECUTION_ID=:execution',
                                  {'execution': execution_id}))
    if not execution or _parse(execution.get('input_json'), {}) != payload:
        raise PermissionError('The original runtime input is unavailable')
    original_source = _runtime_channel_source(tx, payload)
    dispatch = _channel_dispatch(payload)
    if dispatch and dispatch.get('requester_principal_id') != actor:
        raise PermissionError('The original Channel requester differs from the authenticated identity')
    original = _row(tx.query_one('SELECT * FROM CX_RUNTIME_MODEL_CREDENTIALS WHERE EXECUTION_ID=:execution',
                                 {'execution': execution_id}))
    if original:
        if (original.get('actor_id') != actor or original.get('input_digest') != native_agent_api._digest(payload)
                or original.get('execution_digest') != _runtime_execution_digest(execution, payload)
                or original.get('source_digest') != original_source):
            raise PermissionError('The original runtime credential binding cannot be replaced')
        from . import processing_native
        processing_native.bind_execution(tx, actor, execution, payload)
        return model_credentials.binding_from_record(original)
    binding = model_credentials.capture(actor, required_scope=required_scope, tx=tx)
    if binding is None:
        # Unregistered historical resources retain their prior behavior. A
        # selected resource later refuses a Worker with no original receipt.
        from . import processing_native
        processing_native.bind_execution(tx, actor, execution, payload)
        return None
    selected_profile = _row(tx.query_one('SELECT n.LLM_PROFILE_ID,p.VERSION FROM CX_NATIVE_AGENTS n '
        'LEFT JOIN CX_LLM_PROVIDER_PROFILES p ON p.PROFILE_ID=n.LLM_PROFILE_ID WHERE n.AGENT_ID=:agent',
        {'agent': execution['agent_id']})) or {}
    values = model_credentials.binding_record(binding) | dict(execution=execution_id,
        input_digest=native_agent_api._digest(payload), execution_digest=_runtime_execution_digest(execution, payload),
        source_digest=original_source, profile_id=selected_profile.get('llm_profile_id'),
        profile_version=selected_profile.get('version'))
    tx.execute('INSERT INTO CX_RUNTIME_MODEL_CREDENTIALS(EXECUTION_ID,ACTOR_ID,CREDENTIAL_KIND,CREDENTIAL_DIGEST,'
        'REQUIRED_SCOPE,INSTANCE_ID,FENCING_TOKEN,AUTH_METHOD,PERMISSION_VERSION,MFA_LEVEL,NODE_ID,SESSION_CREATED_AT,'
        'INPUT_DIGEST,EXECUTION_DIGEST,SOURCE_DIGEST,PROFILE_ID,PROFILE_VERSION) VALUES(:execution,:actor_id,:credential_kind,:credential_digest,'
        ':required_scope,:instance_id,:fencing_token,:auth_method,:permission_version,:mfa_level,:node_id,:session_created_at,'
        ':input_digest,:execution_digest,:source_digest,:profile_id,:profile_version)', values)
    from . import processing_native
    processing_native.bind_execution(tx, actor, execution, payload)
    return binding


def _runtime_model_receipt(execution_id, *, tx=None):
    if not _model_runtime_enabled():
        return None, None
    query = tx.query_one if tx is not None else connection.execute_query_one
    receipt = _row(query('SELECT * FROM CX_RUNTIME_MODEL_CREDENTIALS WHERE EXECUTION_ID=:execution',
                         {'execution': execution_id}))
    return (receipt, model_credentials.binding_from_record(receipt)) if receipt else (None, None)


def _runtime_model_authority(tx, execution, profile, receipt, binding, target_snapshot, *,
                             context_binding=None, framework_binding=None, audience=()):
    """Current original-resource authority immediately before send/publication."""
    execution_id = str(execution['execution_id'])
    live = _row(tx.query_one('SELECT * FROM CX_RUNTIME_EXECUTIONS WHERE EXECUTION_ID=:execution '
        "AND STATUS='CLAIMED' AND WORKER_ID=:worker AND NODE_ID=:node AND FENCING_TOKEN=:fence "
        'AND LEASE_EXPIRES_AT>CURRENT_TIMESTAMP FOR UPDATE',
        {'execution': execution_id, 'worker': execution['worker_id'], 'node': execution['node_id'],
         'fence': execution['fencing_token']}))
    if not live:
        raise PermissionError('The original Runtime Worker lease was revoked, expired or fenced')
    payload = _parse(live.get('input_json'), {})
    current_receipt, current_binding = _runtime_model_receipt(execution_id, tx=tx)
    if (not current_receipt or current_binding != binding
            or current_receipt.get('input_digest') != receipt['input_digest']
            or current_receipt.get('execution_digest') != receipt['execution_digest']
            or current_receipt.get('source_digest') != receipt.get('source_digest')
            or native_agent_api._digest(payload) != receipt['input_digest']
            or _runtime_execution_digest(live, payload) != receipt['execution_digest']
            or _runtime_channel_source(tx, payload) != receipt.get('source_digest')):
        raise PermissionError('The original Runtime execution, input or source binding changed')
    model_credentials.recheck(tx, binding)
    agent = _row(tx.query_one('SELECT AGENT_ID,STATUS,LLM_PROFILE_ID,DEPLOYMENT_TARGET_ID FROM CX_NATIVE_AGENTS '
                              'WHERE AGENT_ID=:agent', {'agent': live['agent_id']})) or {}
    if (agent.get('status') != 'ACTIVE' or agent.get('deployment_target_id') != live.get('target_id')
            or agent.get('llm_profile_id') != profile.get('profile_id')
            or profile.get('profile_id') != receipt.get('profile_id')
            or int(profile.get('version') or 0) != int(receipt.get('profile_version') or 0)
            or current_receipt.get('profile_id') != receipt.get('profile_id')
            or current_receipt.get('profile_version') != receipt.get('profile_version')):
        raise PermissionError('The original Runtime Agent or Profile binding changed')
    from .portal_grounding import _recheck_profile
    _recheck_profile(tx, profile)
    target = _row(tx.query_one('SELECT TARGET_ID,TARGET_TYPE,STATUS,CONFIG_JSON FROM CX_DEPLOYMENT_TARGETS '
                               'WHERE TARGET_ID=:target', {'target': live.get('target_id')}))
    if (not target or target.get('status') != 'ACTIVE'
            or native_agent_api._digest(target) != native_agent_api._digest(target_snapshot)):
        raise PermissionError('The original Runtime isolation target changed')
    if context_binding:
        from . import continuity_runtime
        current = _row(tx.query_one('SELECT * FROM CX_RUNTIME_CONTEXT_BINDINGS WHERE EXECUTION_ID=:execution',
                                    {'execution': execution_id})) or {}
        keys = ('assembly_id', 'requested_by', 'agent_id', 'security_domain_id', 'input_digest', 'request_digest')
        if any(current.get(key) != context_binding.get(key) for key in keys) or current.get('requested_by') != binding.actor:
            raise PermissionError('The original context Runtime binding changed')
        continuity_runtime._claim(tx, execution, current)
    elif framework_binding:
        from . import framework_execution
        current = framework_execution.binding(execution_id, tx=tx) or {}
        keys = ('actor_id', 'security_domain_id', 'framework_key', 'framework_version', 'adapter_digest', 'rootfs_digest',
                'input_digest', 'profile_id', 'profile_version', 'permission_version', 'target_id')
        if any(current.get(key) != framework_binding.get(key) for key in keys) or current.get('actor_id') != binding.actor:
            raise PermissionError('The original framework Runtime binding changed')
        framework_execution.validate(tx, live, current)
    elif _channel_dispatch(payload):
        dispatch = _channel_dispatch(payload)
        if dispatch.get('requester_principal_id') != binding.actor:
            raise PermissionError('The original Channel requester changed')
        if dispatch.get('kind') == 'BUSINESS_MENTION':
            from . import business_channel_runtime
            if payload.get('knowledge_citations') and tuple(sorted(business_channel_runtime._audience(dispatch,transaction=tx))) != audience:
                raise PermissionError('The original Channel disclosure audience changed')
            business_channel_runtime.validate_response(live['agent_id'], dispatch['channel_id'], execution_id,transaction=tx)
        else:
            from . import admin_management
            if identity_api.effective_access(binding.actor, 'platform.manage').get('decision') != 'ALLOW':
                raise PermissionError('The original management Channel permission changed')
            for principal in (binding.actor, live['agent_id']):
                identity_api._assert_channel_member(principal, dispatch['channel_id'], 'channels.write')
                if dispatch.get('thread_id'):
                    identity_api._assert_thread_member(principal, dispatch['thread_id'], 'channels.write')
            membership = tx.query_one("SELECT MEMBER_ID FROM CX_ADMIN_AGENT_MEMBERS WHERE GROUP_ID=:group_id "
                "AND AGENT_ID=:agent AND STATUS='ACTIVE' AND VOTING_ENABLED='Y'",
                {'group_id': admin_management.ADMIN_GROUP_ID, 'agent': live['agent_id']})
            if not membership:
                raise PermissionError('The original management Agent admission changed')
            citations = payload.get('management_knowledge_citations') or []
            if citations:
                compliance = live['agent_id'] == native_agent_api.COMPLIANCE_ADMIN_AGENT_ID
                source = _row(tx.query_one('SELECT CONTENT_JSON,CONTENT_DIGEST,SIGNATURE_STATUS FROM CX_PLATFORM_KNOWLEDGE '
                    "WHERE KNOWLEDGE_KEY=:knowledge_key AND VERSION=:revision AND STATUS='PUBLISHED' AND AUDIENCE=:audience "
                    'AND SCOPE_TYPE=:scope_type AND (VALID_FROM IS NULL OR VALID_FROM<=CURRENT_TIMESTAMP) '
                    'AND (VALID_UNTIL IS NULL OR VALID_UNTIL>CURRENT_TIMESTAMP)',
                    {'knowledge_key': 'compliance-admin-knowledge' if compliance else 'platform-admin-knowledge',
                     'revision': 1 if compliance else native_agent_api.MANAGEMENT_KNOWLEDGE_VERSION,
                     'audience': 'COMPLIANCE_ADMIN' if compliance else 'MANAGEMENT_AGENTS',
                     'scope_type': 'COMPLIANCE_AGENT' if compliance else 'MANAGEMENT_AGENT'})) or {}
                content = _parse(source.get('content_json'), {})
                if (source.get('signature_status') != 'VERIFIED_BUILTIN'
                        or source.get('content_digest') != native_agent_api._digest(content)
                        or any(item.get('source_digest') != native_agent_api._digest(dict(content,
                               response_language=payload.get('response_language') or 'en')) for item in citations)):
                    raise PermissionError('The original management knowledge source changed')
    else:
        if (identity_api.effective_access(binding.actor, 'agents.operate').get('decision') != 'ALLOW'
                or not identity_api._agent_visible_to(binding.actor, live['agent_id'])):
            raise PermissionError('The original native execution permission changed')
    return live


def enqueue(actor: str, agent_id: str, messages: List[Dict[str, Any]], reason: str) -> Dict[str, Any]:
    if not isinstance(messages, list) or not messages or len(messages) > 100:
        raise native_agent_api.NativeAgentError("messages must contain between 1 and 100 items")
    if len(native_agent_api._json(messages).encode("utf-8")) > 256 * 1024:
        raise native_agent_api.NativeAgentError("execution input is too large")
    agent = _row(connection.execute_query_one(
        "SELECT AGENT_ID,STATUS,ACTIVATION_STATE,DEPLOYMENT_TARGET_ID,LLM_PROFILE_ID FROM CX_NATIVE_AGENTS "
        "WHERE AGENT_ID=:id", {"id": agent_id},
    ))
    if not agent:
        raise native_agent_api.NativeAgentError("native Agent is unavailable")
    if str(agent.get("status") or "").upper() != "ACTIVE":
        raise native_agent_api.NativeAgentError("native Agent is not active")
    if not identity_api._agent_visible_to(actor, agent_id):
        raise PermissionError("Agent is outside the delegated scope")
    execution_id = native_agent_api._id("EXE")
    payload = native_agent_api._json({"messages": messages})
    def reserve(tx):
        tx.execute(
            "INSERT INTO CX_RUNTIME_EXECUTIONS(EXECUTION_ID,AGENT_ID,TARGET_ID,ISOLATION_LEVEL,STATUS,INPUT_JSON,"
            "CONTEXT_DIGEST) VALUES (:id,:agent,:target,'DOMAIN_ISOLATED','PENDING',:input,:digest)",
            {"id": execution_id, "agent": agent_id, "target": agent.get("deployment_target_id"),
             "input": payload, "digest": native_agent_api._digest(payload)})
        bind_model_credential(tx, actor, execution_id, {'messages': messages}, required_scope='agents.operate')
    connection.execute_transaction_callback(reserve)
    return {"execution_id": execution_id, "agent_id": agent_id, "status": "PENDING"}


def _finish(execution_id: str, worker_id: str, node_id: str, fencing_token: int,
            status: str, output: Optional[Dict[str, Any]] = None,
            failure: str = "", observation: Optional[Dict[str, Any]] = None,
            completion_hook=None) -> None:
    sql = (
        "UPDATE CX_RUNTIME_EXECUTIONS SET STATUS=:status,OUTPUT_JSON=:output,FAILURE_REASON=:failure,"
        "COMPLETED_AT=CURRENT_TIMESTAMP,UPDATED_AT=CURRENT_TIMESTAMP WHERE EXECUTION_ID=:id "
        "AND WORKER_ID=:worker AND NODE_ID=:node AND FENCING_TOKEN=:token AND STATUS='CLAIMED' "
        "AND LEASE_EXPIRES_AT>CURRENT_TIMESTAMP")
    params = {"status": status, "output": native_agent_api._json(output) if output is not None else None,
         "failure": failure[:2000] or None, "id": execution_id, "worker": worker_id,
         "node": node_id, "token": fencing_token}
    def complete(tx):
        current = _row(tx.query_one("SELECT * FROM CX_RUNTIME_EXECUTIONS WHERE EXECUTION_ID=:execution FOR UPDATE", {"execution": execution_id}))
        if completion_hook is not None:
            completion_hook(tx)
        changed = tx.execute(sql, params)
        if changed and _model_runtime_enabled():
            from . import processing_native
            processing_native.finish(tx, current, status, failure)
        if observation is not None and changed and not tx.query_one("SELECT EXECUTION_ID FROM CX_EXECUTION_OBSERVATIONS WHERE EXECUTION_ID=:execution", {"execution": execution_id}):
            tx.execute("INSERT INTO CX_EXECUTION_OBSERVATIONS(EXECUTION_ID,FENCING_TOKEN,QUEUE_MS,PROVIDER_LATENCY_MS,FIRST_TOKEN_MS,CANCELLATION_STATE,FINISH_CODE) VALUES(:execution,:fence,:queue_ms,:provider_ms,:first_ms,'NOT_REQUESTED',:code)", {"execution": execution_id, "fence": fencing_token, "queue_ms": observation.get("queue_ms"), "provider_ms": observation.get("provider_ms"), "first_ms": observation.get("first_ms"), "code": failure[:128] or status})
        return changed
    changed = connection.execute_transaction_callback(complete) if _model_runtime_enabled() or observation is not None or completion_hook is not None else connection.execute(sql, params)
    if changed != 1 and status == "COMPLETED":
        raise PermissionError("Runtime execution authority was revoked")


def _admit_execution(execution: Dict[str, Any]) -> Dict[str, Any]:
    """Fail closed before model work when the target cannot prove isolation."""
    target = _row(connection.execute_query_one(
        "SELECT TARGET_ID,TARGET_TYPE,STATUS,CONFIG_JSON FROM CX_DEPLOYMENT_TARGETS WHERE TARGET_ID=:id",
        {"id": execution.get("target_id")},
    ))
    if not target or str(target.get("status") or "").upper() != "ACTIVE":
        raise RuntimeError("Deployment target is unavailable")
    target_type = str(target.get("target_type") or "").upper()
    if target_type == 'LOCAL_LINUX_SANDBOX':
        payload = _parse(execution.get('input_json'), {})
        if isinstance(payload.get('framework_dispatch'), dict):
            config = _parse(target.get('config_json'), {})
            config['rootfs'] = config.get('framework_rootfs')
            # Bind the database authority and immutable framework identity
            # before starting an untrusted worker.  Starting first would let a
            # stale/revoked execution consume CPU or reach the broker before
            # the profile, permission, target, or rootfs checks run.
            from . import framework_execution
            binding = framework_execution.binding(str(execution.get('execution_id') or ''))
            if not binding:
                raise PermissionError('framework execution binding is unavailable')
            # The worker is constructed only after this authoritative
            # transaction has validated the current profile, permission,
            # target, input binding, and immutable rootfs.
            def _validate_framework(tx):
                return framework_execution.validate(tx, execution, binding, verify_image=True)
            config = connection.execute_transaction_callback(_validate_framework)
            from .isolated_framework_runtime import FrameworkWorker
            worker = FrameworkWorker(execution, config)
            execution['_isolated_worker'] = worker
            observed = worker.start()
        else:
            from .isolated_channel_runtime import ChannelWorker
            config = _parse(target.get('config_json'), {})
            dispatch = payload.get('channel_dispatch') or {}
            if dispatch.get('kind') != 'BUSINESS_MENTION':
                raise PermissionError('isolated worker requires a bound business Channel mention')
            from . import business_channel_runtime
            business_channel_runtime.validate(str(execution['agent_id']), dispatch)
            worker = ChannelWorker(execution, config)
            execution['_isolated_worker'] = worker
            observed = worker.start()
    else:
        adapter = deployment_adapters.reference_adapters().get(target_type)
        if adapter is None:
            raise RuntimeError("Deployment target has no verified runtime adapter")
        observed = adapter.evidence(execution).evidence
    contract = runtime_isolation.RuntimeIsolationContract(
        isolation_level=str(execution.get("isolation_level") or ""),
        enforcement_mode=str(observed.get("enforcement_mode") or "UNVERIFIED"),
        runtime_adapter=target_type,
        runtime_identity=str(observed.get("runtime_identity") or ""),
        evidence_ref="runtime-execution:" + str(execution.get("execution_id") or ""),
        boundaries=frozenset(observed.get("boundaries") or []),
    )
    try:
        admission = runtime_isolation.validate_admission(
            contract, requested_level=str(execution.get("isolation_level") or ""),
            adapter_capabilities=observed,
        )
        evidence = {**observed, "admitted": True, "decision": "ALLOW"}
    except runtime_isolation.IsolationError:
        evidence = {**observed, "admitted": False, "decision": "DENY"}
        connection.execute(
            "UPDATE CX_RUNTIME_EXECUTIONS SET ISOLATION_EVIDENCE_JSON=:evidence,"
            "ISOLATION_EVIDENCE_REF=:ref,UPDATED_AT=CURRENT_TIMESTAMP WHERE EXECUTION_ID=:id",
            {"evidence": json.dumps(evidence, ensure_ascii=True, sort_keys=True, separators=(",", ":")),
             "ref": contract.evidence_ref, "id": execution.get("execution_id")},
        )
        raise
    connection.execute(
        "UPDATE CX_RUNTIME_EXECUTIONS SET ISOLATION_EVIDENCE_JSON=:evidence,ISOLATION_EVIDENCE_REF=:ref,"
        "ISOLATION_ADMITTED_AT=CURRENT_TIMESTAMP,UPDATED_AT=CURRENT_TIMESTAMP WHERE EXECUTION_ID=:id",
        {"evidence": json.dumps(evidence, ensure_ascii=True, sort_keys=True, separators=(",", ":")),
         "ref": contract.evidence_ref, "id": execution.get("execution_id")},
    )
    return admission


def _channel_dispatch(input_payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    dispatch = input_payload.get("channel_dispatch") if isinstance(input_payload, dict) else None
    return dispatch if isinstance(dispatch, dict) and (
        str(dispatch.get("channel_id") or "") == "CH_PLATFORM_ADMINISTRATION"
        or dispatch.get('kind') == 'BUSINESS_MENTION'
    ) else None


def _management_status_markdown(snapshot: Dict[str, Any], language: str = "zh") -> str:
    """Render a credential-free database control-plane report deterministically."""
    native = snapshot.get("native_agents") if isinstance(snapshot, dict) else {}
    runtime = snapshot.get("runtime_executions") if isinstance(snapshot, dict) else {}
    llm = snapshot.get("llm_profiles") if isinstance(snapshot, dict) else {}
    group = snapshot.get("admin_group") if isinstance(snapshot, dict) else {}
    if language == "en":
        return "\n".join([
            "## Platform runtime status", "",
            "- **Scope**: Aggregated database control-plane state; excludes hosts, connections, credentials, tokens, and user data.",
            f"- **Built-in Agents**: {int((native or {}).get('active') or 0)} active, {int((native or {}).get('non_active') or 0)} inactive.",
            f"- **Runtime executions**: {int((runtime or {}).get('pending') or 0)} pending, {int((runtime or {}).get('claimed') or 0)} running, {int((runtime or {}).get('failed') or 0)} failed.",
            f"- **LLM profiles**: {int((llm or {}).get('active') or 0)} active, {int((llm or {}).get('healthy') or 0)} healthy, {int((llm or {}).get('degraded') or 0)} degraded.",
            f"- **Admin group**: status {str((group or {}).get('status') or 'UNKNOWN')}, {int((group or {}).get('active_voting_members') or 0)} voting members, term {int((group or {}).get('current_term') or 0)}.",
            "", "> This is a read-only report. Configuration, membership, upgrade, and containment changes require governed Action Cards and approval workflows.",
        ])
    return "\n".join([
        "## 平台运行状态",
        "",
        "- **状态范围**：数据库控制平面聚合状态，不包含主机、连接、凭证、Token 或用户数据。",
        f"- **内置智能体**：活动 {int((native or {}).get('active') or 0)}，非活动 {int((native or {}).get('non_active') or 0)}。",
        f"- **运行任务**：等待 {int((runtime or {}).get('pending') or 0)}，执行中 {int((runtime or {}).get('claimed') or 0)}，失败 {int((runtime or {}).get('failed') or 0)}。",
        f"- **LLM 配置**：活动 {int((llm or {}).get('active') or 0)}，健康 {int((llm or {}).get('healthy') or 0)}，降级 {int((llm or {}).get('degraded') or 0)}。",
        f"- **Admin 协作组**：状态 {str((group or {}).get('status') or 'UNKNOWN')}，投票成员 {int((group or {}).get('active_voting_members') or 0)}，当前任期 {int((group or {}).get('current_term') or 0)}。",
        "",
        "> 该报告仅提供只读状态。配置、成员、升级和阻断操作必须通过受治理的操作卡与审批流程执行。",
    ])


def _management_template_markdown(knowledge: Dict[str, Any]) -> str:
    """Render fixed product workflow guidance; never ask the LLM to invent it."""
    language = "zh" if str(knowledge.get("response_language") or "en") == "zh" else "en"
    workflow = knowledge.get("template_workflow") or {}
    controls = knowledge.get("security_controls_" + language) or []
    lifecycle = knowledge.get("request_lifecycle_" + language) or []
    required = knowledge.get("required_request_controls_" + language) or []
    options = knowledge.get("business_template_options") or []
    if language == "zh":
        return "\n".join([
            "## 内置 Agent 模板与平台 Agent 申请", "",
            f"- **模板含义**：{workflow.get('template_meaning_zh') or '未配置'}",
            f"- **内置管理 Agent**：{workflow.get('seed_location_zh') or '未配置'}。",
            f"- **业务 Agent 申请**：{workflow.get('business_request_location_zh') or '未配置'}。",
            f"- **申请审批**：{workflow.get('approval_location_zh') or '未配置'}。",
            f"- **对象区别**：{workflow.get('compliance_distinction_zh') or '未配置'}",
            f"- **当前边界**：{knowledge.get('missing_capability_answer_zh') or ''}",
            "", "### 可选业务模板与能力倾向",
            *[f"- **{item.get('key')}**：{item.get('zh')}" for item in options],
            "", "### 申请必须填写", "- " + "、".join(required),
            "", "### 安全与合规控制", *[f"- {item}" for item in controls],
            "", "### 业务 Agent 生命周期", "- " + " -> ".join(lifecycle),
            "", f"> {knowledge.get('immutability_zh') or ''}",
            f"> {knowledge.get('external_registration_zh') or ''}",
        ])
    return "\n".join([
        "## Built-in Agent templates and platform Agent requests", "",
        f"- **Template meaning**: {workflow.get('template_meaning_en') or 'Not configured'}",
        f"- **Built-in management Agents**: {workflow.get('seed_location_en') or 'Not configured'}.",
        f"- **Business Agent request**: {workflow.get('business_request_location_en') or 'Not configured'}.",
        f"- **Request approval**: {workflow.get('approval_location_en') or 'Not configured'}.",
        f"- **Object distinction**: {workflow.get('compliance_distinction_en') or 'Not configured'}",
        f"- **Current boundary**: {knowledge.get('missing_capability_answer_en') or ''}",
        "", "### Selectable Business templates and capability tendencies",
        *[f"- **{item.get('key')}**: {item.get('en')}" for item in options],
        "", "### Required request fields", "- " + ", ".join(required),
        "", "### Security and compliance controls", *[f"- {item}" for item in controls],
        "", "### Business Agent lifecycle", "- " + " -> ".join(lifecycle),
        "", f"> {knowledge.get('immutability_en') or ''}",
        f"> {knowledge.get('external_registration_en') or ''}",
    ])


def _platform_command_help_markdown(help_payload: Dict[str, Any], language: str = "zh") -> str:
    """Render command help directly from the database registry payload."""
    item = help_payload.get("item")
    if isinstance(item, dict):
        metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        name = str(metadata.get("name_zh" if language == "zh" else "name_en") or item.get("command_key") or "")
        summary = str(metadata.get("summary_zh" if language == "zh" else "summary_en") or "")
        schema = item.get("parameter_schema") if isinstance(item.get("parameter_schema"), dict) else {}
        required = schema.get("required") if isinstance(schema.get("required"), list) else []
        return "\n".join([
            "## 平台命令帮助" if language == "zh" else "## Platform command help", "",
            f"- **{item.get('command_key')}** · {name}",
            f"- **{'格式' if language == 'zh' else 'Syntax'}**: `{item.get('example')}`",
            f"- **{'风险等级' if language == 'zh' else 'Risk'}**: {item.get('risk_level')}",
            f"- **{'执行状态' if language == 'zh' else 'Execution'}**: {item.get('execution_mode')} / {item.get('executor_state')}",
            f"- {summary}",
            f"- **{'必填参数' if language == 'zh' else 'Required parameters'}**: {', '.join(str(value) for value in required) or ('无' if language == 'zh' else 'none')}",
            f"- **{'边界' if language == 'zh' else 'Boundary'}**: " + (
                "该命令不因聊天文本或模型输出获得额外权限；需要变更时仍以操作卡和审批结果为准。"
                if language == "zh" else
                "Chat text and model output do not add authority; governed Action Cards and approvals remain authoritative."
            ),
        ])
    items = help_payload.get("items") if isinstance(help_payload.get("items"), list) else []
    rows = []
    for entry in items:
        if not isinstance(entry, dict):
            continue
        metadata = entry.get("metadata") if isinstance(entry.get("metadata"), dict) else {}
        name = str(metadata.get("name_zh" if language == "zh" else "name_en") or entry.get("command_key") or "")
        rows.append(f"- **{entry.get('command_key')}** · {name} · `{entry.get('risk_level')}` · `{entry.get('execution_mode')}`")
    return "\n".join([
        "## 平台命令帮助" if language == "zh" else "## Platform command help", "",
        *(rows or [(("- 暂无可用命令。") if language == "zh" else "- No usable commands.")]),
        "",
        "> " + (
            "输入 /platform HELP <COMMAND_KEY> 查看单个命令格式。命令发现按当前管理员权限过滤。"
            if language == "zh" else
            "Enter /platform HELP <COMMAND_KEY> for command-specific syntax. Discovery is filtered by the administrator's authority."
        ),
    ])


def _platform_command_result_markdown(command: Dict[str, Any], language: str = "zh") -> str:
    """Render a credential-free, deterministic platform command result."""
    command_key = str(command.get("command_type") or "PLATFORM_COMMAND").upper()
    status = str(command.get("status") or "UNKNOWN").upper()
    result = command.get("result") if isinstance(command.get("result"), dict) else {}
    if language == "zh":
        title = "平台命令结果"
        command_label = "命令"
        status_label = "状态"
        result_label = "结果"
        scope_labels = {
            "database_control_plane": "数据库控制平面",
        }
    else:
        title = "Platform command result"
        command_label = "Command"
        status_label = "Status"
        result_label = "Result"
        scope_labels = {
            "database_control_plane": "database control plane",
        }
    lines = [
        f"## {title}",
        "",
        f"- **{command_label}**：`{command_key}`",
        f"- **{status_label}**：`{status}`",
        "",
        f"### {result_label}",
    ]
    if result.get("status") == "ok":
        scope = str(result.get("scope") or "")
        if language == "zh":
            lines.append(f"- 检查通过，范围：{scope_labels.get(scope, scope or '数据库控制平面')}。")
        else:
            lines.append(f"- Check passed, scope: {scope_labels.get(scope, scope or 'database control plane')}.")
    def render_value(value: Any) -> str:
        if isinstance(value, dict):
            return "; ".join(f"{sub_key}={render_value(sub_value)}" for sub_key, sub_value in value.items())
        if isinstance(value, list):
            return ", ".join(render_value(item) for item in value)
        return str(value)

    action = command.get("action_card") if isinstance(command.get("action_card"), dict) else {}
    if action:
        lines.extend([
            "",
            f"### {'审批信息' if language == 'zh' else 'Approval'}",
            f"- **{'操作卡' if language == 'zh' else 'Action Card'}**：`{action.get('action_id') or action.get('id') or 'created'}`",
            f"- **{'状态' if language == 'zh' else 'Status'}**：`{action.get('status') or 'PENDING'}`",
            f"- **{'说明' if language == 'zh' else 'Boundary'}**：" + ("变更命令只创建审批卡，不会因聊天或模型输出自动执行。" if language == 'zh' else "The change command creates an approval card only; chat or model output cannot execute it automatically."),
        ])
    for key, value in result.items():
        if key in {"status", "scope"}:
            continue
        label = {
            "managed_nodes": "托管节点" if language == "zh" else "Managed nodes",
            "native_agents": "原生 Agent" if language == "zh" else "Native Agents",
            "llm_profiles": "LLM 配置" if language == "zh" else "LLM profiles",
            "embedding": "Embedding" if language == "zh" else "Embedding",
            "runtime": "运行时" if language == "zh" else "Runtime",
            "database_dialect": "数据库方言" if language == "zh" else "Database dialect",
            "checked_at": "检查时间" if language == "zh" else "Checked at",
        }.get(key, key)
        if isinstance(value, dict):
            details = render_value(value)
            lines.append(f"- **{label}**：`{details}`")
        else:
            lines.append(f"- **{label}**：`{value}`")
    return "\n".join(lines)


def _platform_product_markdown(knowledge: Dict[str, Any], language: str = "zh") -> str:
    """Render a signed platform overview without an LLM call."""
    from .product_identity import identity
    product = identity()
    databases = ", ".join({"oracle": "Oracle", "pg": "PostgreSQL", "yashandb": "YashanDB"}.get(key, key) for key in product["databases"])
    enterprise = product["edition"] == "Enterprise"
    options = knowledge.get("business_template_options") if isinstance(knowledge.get("business_template_options"), list) else []
    if language == "zh":
        return "\n".join([
            f"## {product['brand_zh']} AI Agent 管理平台", "",
            f"本产品支持 {databases}，以数据库为权威控制面，管理 Agent 身份、组织、频道、知识、记忆、图关系、任务、Skill 和审计。" + ("企业版另提供审批和合规治理。" if enterprise else "社区版不包含企业专属审批和合规模块。"),
            "", "### 当前平台能力",
            "- 可观测：Agent、运行时、关系图和审计状态可查询。",
            "- 可调度：持久任务、协作关卡和受治理执行形成闭环。",
            f"- 可运维：支持的底座为 {databases}，提供离线部署、独立身份、凭据轮换和明确故障边界。",
            "", "### Agent 与安全边界",
            "- 平台管理 Agent 只处理受保护的平台控制面；业务 Agent 必须经过申请、授权处理、部署和激活，企业版要求职责分离审批。",
            "- 聊天文本、提示词、Skill、Tool 或 URL 不会自动授予数据库或平台权限。",
            "- 高风险变更必须生成操作卡并由授权人员最终审批。",
            "", "### 可选业务模板",
            *[f"- **{item.get('key')}**：{item.get('zh')}" for item in options],
            "", "### 当前限制",
            str(knowledge.get("missing_capability_answer_zh") or "当前能力以已发布版本和实例授权为准。"),
        ])
    return "\n".join([
        f"## {product['brand_en']} AI Agent Management Platform", "",
        f"A database-governed AI Agent management platform supporting {databases}. Agent identity, organization, Channels, Knowledge, Memory, graph relationships, Tasks, Skills and audit use the database control plane. " + ("Enterprise additionally provides approval and compliance governance." if enterprise else "Community excludes Enterprise-only approval and compliance modules."),
        "", "### Current capabilities",
        "- Observable: Agent, runtime, graph, and audit state are queryable.",
        "- Schedulable: durable tasks, collaboration gates and governed execution form one lifecycle.",
        f"- Operable: {databases}, offline deployment, independent identities, credential rotation and explicit failure boundaries.",
        "", "### Agent and security boundaries",
        "- Platform management Agents handle only the protected control plane; Business Agents require request, authorized processing, deployment and activation. Enterprise requires separated approval.",
        "- Chat text, prompts, Skills, Tools, and URLs never grant database or platform authority.",
        "- High-risk changes create an Action Card and require final approval by an authorized human.",
        "", "### Selectable Business templates",
        *[f"- **{item.get('key')}**: {item.get('en')}" for item in options],
        "", "### Current boundary",
        str(knowledge.get("missing_capability_answer_en") or "Capabilities are bounded by the published release and instance authorization."),
    ])


def _write_channel_response(agent_id: str, execution_id: str, input_payload: Dict[str, Any],
                            output: Optional[Dict[str, Any]] = None, failure: str = "") -> None:
    """Return a managed runtime result to the protected Channel once only."""
    dispatch = _channel_dispatch(input_payload)
    if not dispatch:
        return
    channel_id = str(dispatch["channel_id"])
    content = str((output or {}).get("content") or "").strip()
    if not content and failure == 'RUNTIME_ISOLATION_UNAVAILABLE':
        content = (
            "当前部署目标不满足该 Agent 模板的隔离要求，尚未调用模型。请为 Agent 配置满足要求且经过验证的独立运行环境。"
            if str(input_payload.get("response_language") or "en") == "zh" else
            "The deployment target does not meet this Agent template's isolation requirements. The model was not called. Configure a verified isolated runtime that meets the template requirements."
        )
    if not content:
        content = (
            "Agent 未能完成本次请求。请检查 Agent 模型配置和审计记录后重试。"
            if str(input_payload.get("response_language") or "en") == "zh" else
            "The Agent could not complete this request. Check the Agent model configuration and the audit record before retrying."
        )
    identity_api.post_channel_agent_response(agent_id, channel_id, content, execution_id=execution_id,
                                             thread_type=str(dispatch.get("thread_type") or "CHANNEL"),
                                             thread_id=str(dispatch.get("thread_id") or ""))


def _safe_answer_metadata(value: Any) -> Dict[str, Any]:
    """Expose only bounded retrieval-policy observations, never source facts."""
    if not isinstance(value, dict):
        return {}
    strategies = {"KEYWORD", "FULLTEXT", "VECTOR", "HYBRID", "SUBJECT_CLARIFICATION"}
    channels = {"KEYWORD", "FULLTEXT", "VECTOR", "RELATIONAL", "TAG", "GRAPH"}
    statuses = {"MATCHED", "PARTIAL_MATCH", "NO_MATCH", "AMBIGUOUS", "UNAVAILABLE"}
    subjects = {"COMPANY", "DATABASE", "QUERY_TERMS", "MIXED"}
    def selected_list(key: str, permitted: set[str]) -> list[str]:
        raw = value.get(key)
        return list(dict.fromkeys(item for item in raw[:16] if isinstance(item, str) and item in permitted)) if isinstance(raw, list) else []
    requested = value.get("requested_strategy")
    status = value.get("evidence_status")
    subject = value.get("subject_type")
    degradations = []
    for item in value.get("degradations", [])[:4] if isinstance(value.get("degradations"), list) else []:
        if isinstance(item, dict) and str(item.get("channel")) in channels:
            degradations.append({"channel": str(item["channel"]), "reason": "CHANNEL_UNAVAILABLE"})
    return {
        "policy_revision": str(value.get("policy_revision") or "")[:64],
        "requested_strategy": requested if isinstance(requested, str) and requested in strategies else "UNKNOWN",
        "actual_strategies": selected_list("actual_strategies", strategies),
        "available_channels": selected_list("available_channels", channels),
        "degradations": degradations,
        "evidence_status": status if isinstance(status, str) and status in statuses else "UNAVAILABLE",
        "subject_type": subject if isinstance(subject, str) and subject in subjects else "QUERY_TERMS",
        "missing_parts_count": max(0, min(100, value.get("missing_parts_count", 0)))
            if type(value.get("missing_parts_count", 0)) is int else 0,
        "contradiction_count": max(0, min(100, value.get("contradiction_count", 0)))
            if type(value.get("contradiction_count", 0)) is int else 0,
        "rank_meaning": "RECIPROCAL_RANK_NOT_PROBABILITY",
    }


def execute_one(worker_id: str = "", node_id: str = "") -> Dict[str, Any]:
    worker_id = worker_id or local_worker_id()
    node_id = node_id or native_agent_api._text(socket.gethostname(), 128)
    native_agent_api.reconcile_expired_runtime(limit=100)
    claimed = native_agent_api.claim_runtime(worker_id, node_id, limit=1)
    if not claimed:
        return {"status": "IDLE", "worker_id": worker_id}
    execution = claimed[0]
    execution_id = str(execution.get("execution_id") or "")
    fencing_token = int(execution.get("fencing_token") or 0)
    input_payload: Dict[str, Any] = {}
    agent: Optional[Dict[str, Any]] = None
    profile: Optional[Dict[str, Any]] = None
    provider_failed = False
    provider_completed = False
    provider_unknown = False
    provider_number = 0
    context_binding = None
    publication_guard = None
    publication_principals = ()
    from .edition_features import AGENT_EXTENSIONS_ENABLED
    observation = {} if AGENT_EXTENSIONS_ENABLED else None
    if observation is not None:
        try:
            stamps = _row(connection.execute_query_one("SELECT CREATED_AT,STARTED_AT FROM CX_RUNTIME_EXECUTIONS WHERE EXECUTION_ID=:execution", {"execution": execution_id})) or {}
            if stamps.get("started_at") and stamps.get("created_at"):
                observation["queue_ms"] = max(0, round((stamps["started_at"] - stamps["created_at"]).total_seconds() * 1000))
        except Exception:
            # Metrics are diagnostic metadata; they must never turn a valid
            # leased execution into an untracked provider send.
            observation["queue_ms"] = None
    def provider_call(function, *args):
        nonlocal provider_failed, provider_completed, provider_unknown, provider_number
        nonlocal publication_guard, publication_principals
        if not connection.execute_query_one(
                "SELECT EXECUTION_ID FROM CX_RUNTIME_EXECUTIONS WHERE EXECUTION_ID=:id "
                "AND STATUS='CLAIMED' AND WORKER_ID=:worker AND NODE_ID=:node "
                "AND FENCING_TOKEN=:token AND LEASE_EXPIRES_AT>CURRENT_TIMESTAMP",
                {'id': execution_id, 'worker': worker_id, 'node': node_id, 'token': fencing_token}):
            raise PermissionError('Runtime execution lease revoked')
        business_dispatch = input_payload.get('channel_dispatch') or {}
        framework_dispatch = input_payload.get('framework_dispatch') or {}
        if business_dispatch.get('kind') == 'BUSINESS_MENTION':
            from . import business_channel_runtime
            business_channel_runtime.validate_response(str(execution['agent_id']),
                str(business_dispatch['channel_id']), execution_id)
        receipt, credential = _runtime_model_receipt(execution_id)
        framework_binding, audience = None, ()
        if credential is not None:
            if framework_dispatch:
                from . import framework_execution
                framework_binding = framework_execution.binding(execution_id)
            if business_dispatch.get('kind') == 'BUSINESS_MENTION' and input_payload.get('knowledge_citations'):
                from . import business_channel_runtime
                audience = tuple(sorted(business_channel_runtime._audience(business_dispatch)))
            target_snapshot = _row(connection.execute_query_one(
                'SELECT TARGET_ID,TARGET_TYPE,STATUS,CONFIG_JSON FROM CX_DEPLOYMENT_TARGETS WHERE TARGET_ID=:target',
                {'target': execution.get('target_id')}))
            publication_principals = tuple(sorted({credential.actor, str(execution['agent_id']), *audience}))
            def authorize_model(tx):
                from .continuity_work import _lock_actor
                from .continuity_state import ContinuityError
                from .knowledge_grounding import GroundingError
                for principal in publication_principals:
                    _lock_actor(tx, principal)
                try:
                    _runtime_model_authority(tx, execution, args[0], receipt, credential, target_snapshot,
                        context_binding=context_binding, framework_binding=framework_binding, audience=audience)
                except (native_agent_api.NativeAgentError, identity_api.IdentityError, ContinuityError, GroundingError) as exc:
                    raise PermissionError('The original Runtime business authority changed') from exc
            publication_guard = authorize_model
            try:
                connection.execute_transaction_callback(authorize_model)
            except Exception as exc:
                exc.model_not_dispatched = True
                raise
        else:
            authorize_model = None
        provider_number += 1
        source_kind = 'CHANNEL' if _channel_dispatch(input_payload) else 'NATIVE'
        source_attempt = 'NMA_' + native_agent_api._digest([execution_id, fencing_token, provider_number])
        if _model_runtime_enabled():
            from . import processing_native
            allowed = connection.execute_transaction_callback(lambda tx: processing_native.begin_call(
                tx, execution, source_attempt, source_kind, provider_number, args[1]))
            if not allowed:
                raise model_dispatch.ModelNotDispatched('PROCESSING_BLOCKED', 'The original native processing budget is exhausted')
        provider_failed = True
        provider_started = time.monotonic()
        observer = _model_observer.set(lambda received: observation.setdefault("first_ms", max(0, round((received - provider_started) * 1000))) if observation is not None else None)
        isolated = execution.get('_isolated_worker')
        # A leased background Worker must never inherit another request's
        # dispatch identity. Only its immutable original receipt can install it.
        dispatch_token = model_dispatch._context.set(None)
        try:
            def authorize_send(tx, admission):
                authorize_model(tx)
                if _model_runtime_enabled():
                    processing_native.dispatch_gate(tx, execution, source_attempt, admission)
            with model_credentials.dispatch_context(credential, source_kind, execution_id, source_attempt,
                    reauthorize=authorize_send, worker_key=worker_id,
                    allow_wait=False, lock_principals=publication_principals):
                if isolated:
                    def authorize():
                        if authorize_model is not None:
                            connection.execute_transaction_callback(authorize_model)
                            return
                        if business_dispatch.get('kind') == 'BUSINESS_MENTION':
                            from . import business_channel_runtime
                            business_channel_runtime.validate_response(str(execution['agent_id']),
                                str(input_payload['channel_dispatch']['channel_id']), execution_id)
                        elif framework_dispatch:
                            from . import framework_execution
                            binding = framework_execution.binding(execution_id)
                            if not binding:
                                raise PermissionError('framework execution binding is unavailable')
                            connection.execute_transaction_callback(lambda tx: framework_execution.validate(tx, execution, binding))
                        lease = _row(connection.execute_query_one(
                            "SELECT EXECUTION_ID FROM CX_RUNTIME_EXECUTIONS WHERE EXECUTION_ID=:id "
                            "AND STATUS='CLAIMED' AND WORKER_ID=:worker AND NODE_ID=:node "
                            "AND FENCING_TOKEN=:token AND LEASE_EXPIRES_AT>CURRENT_TIMESTAMP",
                            {'id':execution_id,'worker':worker_id,'node':node_id,'token':fencing_token}))
                        if not lease:
                            raise PermissionError('isolated execution lease revoked')
                    from . import answer_context
                    with answer_context.dispatch_budget(input_payload.get('answer_context_selection') if business_dispatch.get('kind')=='BUSINESS_MENTION' else None):
                        result = isolated.model(args[0], args[1], _call_llm, authorize)
                    if len(args) > 2:
                        args[2](result['content'])
                else:
                    from . import answer_context
                    with answer_context.dispatch_budget(input_payload.get('answer_context_selection') if business_dispatch.get('kind')=='BUSINESS_MENTION' else None):
                        result = function(*args)
        except Exception as exc:
            if isinstance(exc, model_dispatch.CapacityQueued):
                from . import model_endpoint_capacity
                queued = exc.admission
                try:
                    model_endpoint_capacity.cancel_admission(credential.actor, queued['admission_id'], dict(
                        expected_version=queued['version'], reason='Native Worker cannot wait with an active business lease',
                        idempotency_key='native-no-send:' + queued['admission_id']))
                except Exception:
                    logger.warning('Native queued admission cleanup failed; original request was not sent')
            known_no_send = getattr(exc, 'model_not_dispatched', False)
            record = None
            if _model_runtime_enabled():
                record = _row(connection.execute_query_one('SELECT ADMISSION_ID,STATUS FROM CX_MODEL_ADMISSIONS '
                    'WHERE SOURCE_KIND=:source_kind AND SOURCE_ID=:execution AND SOURCE_ATTEMPT_ID=:attempt',
                    {'source_kind': source_kind, 'execution': execution_id, 'attempt': source_attempt}))
                origin = _row(connection.execute_query_one('SELECT ORIGIN_RECEIPT_ID AS ADMISSION_ID,STATUS FROM CX_MODEL_ORIGIN_RECEIPTS '
                    'WHERE ACTOR_ID=:actor AND SOURCE_KIND=:source_kind AND SOURCE_ID=:execution AND SOURCE_ATTEMPT_ID=:attempt',
                    {'actor': receipt.get('actor_id'), 'source_kind': source_kind, 'execution': execution_id, 'attempt': source_attempt}))
                if record and origin:
                    raise RuntimeError('The original native attempt has conflicting local and remote admissions') from exc
                record = origin or record
            if record and record.get('status') in {'QUEUED', 'RESERVED', 'REJECTED', 'CANCELLED', 'EXPIRED', 'KNOWN_NO_SEND'}:
                known_no_send = True
                exc.model_not_dispatched = True
            provider_unknown = bool(record and record.get('status') in {'DISPATCHING', 'UNKNOWN'})
            provider_failed = (not known_no_send and not getattr(exc, 'model_ledger_failed', False)
                               and not isinstance(exc, (PermissionError, content_security.ContentDenied))
                               and not (record and record.get('status') == 'COMPLETED'))
            raise
        finally:
            model_dispatch._context.reset(dispatch_token)
            _model_observer.reset(observer)
            if observation is not None:
                observation["provider_ms"] = max(0, round((time.monotonic() - provider_started) * 1000))
            if _model_runtime_enabled():
                connection.execute_transaction_callback(lambda tx: processing_native.observe_call(tx, execution, source_attempt))
        provider_failed = False
        provider_completed = True
        return result

    def publish_channel(agent_id, channel_id, content, *, completed=False):
        options = dict(execution_id=execution_id, completed=completed)
        if publication_guard is not None:
            options.update(before_publish=publication_guard, lock_principals=publication_principals)
        return identity_api.update_channel_agent_response(agent_id, channel_id, content, **options)
    try:
        # Preserve the durable reply binding even when runtime admission fails,
        # so an authorized Channel sees a bounded failure instead of silence.
        input_payload = _parse(execution.get("input_json"), {})
        agent = {"agent_id": str(execution.get("agent_id") or "")}
        _admit_execution(execution)
        agent = _row(connection.execute_query_one(
            "SELECT AGENT_ID,STATUS,LLM_PROFILE_ID FROM CX_NATIVE_AGENTS WHERE AGENT_ID=:id",
            {"id": execution.get("agent_id")},
        ))
        if not agent or str(agent.get("status") or "").upper() != "ACTIVE":
            raise RuntimeError("Agent is not active")
        input_payload = _parse(execution.get("input_json"), {})
        messages = input_payload.get("messages") if isinstance(input_payload, dict) else []
        profile = _llm_profile(str(agent.get("llm_profile_id") or ""))
        status_snapshot = input_payload.get("management_status_snapshot") if isinstance(input_payload, dict) else None
        template_knowledge = input_payload.get("management_template_knowledge") if isinstance(input_payload, dict) else None
        product_overview = input_payload.get("management_product_overview") if isinstance(input_payload, dict) else None
        command_help = input_payload.get("platform_command_help") if isinstance(input_payload, dict) else None
        command_result = input_payload.get("platform_command_result") if isinstance(input_payload, dict) else None
        response_language = "zh" if str(input_payload.get("response_language") or "en") == "zh" else "en"
        if not profile and not isinstance(status_snapshot, dict) and not isinstance(template_knowledge, dict) and not isinstance(product_overview, dict) and not isinstance(command_help, dict) and not isinstance(command_result, dict):
            raise RuntimeError("Agent has no active LLM Provider Profile")
        dispatch = _channel_dispatch(input_payload)
        from . import continuity_runtime
        context_binding=continuity_runtime.binding(execution_id)
        if context_binding:
            if dispatch or any(isinstance(value,dict) for value in (status_snapshot,template_knowledge,product_overview,command_help,command_result)):
                raise PermissionError('Context-bound execution cannot change its dispatch contract')
            if not profile:
                raise RuntimeError('Agent has no active LLM Provider Profile')
            output=continuity_runtime.execute(execution,context_binding,lambda inputs:provider_call(_call_llm,profile,inputs))
        elif isinstance(input_payload.get('framework_dispatch'), dict):
            output = provider_call(_call_llm, profile, messages if isinstance(messages, list) else [])
        elif dispatch:
            channel_id = str(dispatch["channel_id"])
            identity_api.begin_channel_agent_response(
                str(agent.get("agent_id") or ""), channel_id, execution_id=execution_id,
                thread_type=str(dispatch.get("thread_type") or "CHANNEL"), thread_id=str(dispatch.get("thread_id") or ""),
            )
            if dispatch.get('kind') == 'BUSINESS_MENTION' and input_payload.get('knowledge_reply'):
                output = {'content': input_payload['knowledge_reply'], 'model': 'database-knowledge-policy'}
            elif isinstance(template_knowledge, dict):
                output = {"content": _management_template_markdown(template_knowledge), "model": "database-control-plane"}
            elif isinstance(product_overview, dict):
                output = {"content": _platform_product_markdown(product_overview, response_language), "model": "database-control-plane"}
            elif isinstance(command_help, dict):
                output = {"content": _platform_command_help_markdown(command_help, response_language), "model": "database-control-plane"}
            elif isinstance(command_result, dict):
                output = {"content": _platform_command_result_markdown(command_result, response_language), "model": "database-control-plane"}
            elif isinstance(status_snapshot, dict):
                output = {"content": _management_status_markdown(status_snapshot, response_language), "model": "database-control-plane"}
            else:
                try:
                    output = provider_call(
                        _stream_llm, profile, messages if isinstance(messages, list) else [],
                        lambda content: publish_channel(
                            str(agent.get("agent_id") or ""), channel_id,
                            answer_planning.render_reply(content, input_payload),
                        ),
                    )
                except RuntimeError as exc:
                    # Some OpenAI-compatible reasoning providers can complete an
                    # SSE response without a content delta. Preserve the same
                    # bounded prompt and safe Channel response by falling back to
                    # one non-streaming request; transport and timeout failures
                    # remain failures and are never retried here.
                    if provider_unknown or str(exc) != "LLM provider returned no content":
                        raise
                    output = provider_call(_call_llm, profile, messages if isinstance(messages, list) else [])
            output = {**output, 'content': answer_planning.render_reply(str(output.get('content') or ''), input_payload)}
            if not connection.execute_query_one(
                    "SELECT EXECUTION_ID FROM CX_RUNTIME_EXECUTIONS WHERE EXECUTION_ID=:id AND STATUS='CLAIMED' "
                    "AND WORKER_ID=:worker AND NODE_ID=:node AND FENCING_TOKEN=:token AND LEASE_EXPIRES_AT>CURRENT_TIMESTAMP",
                    {'id': execution_id, 'worker': worker_id, 'node': node_id, 'token': fencing_token}):
                raise PermissionError('Runtime execution lease revoked before response publication')
            publish_channel(
                str(agent.get("agent_id") or ""), channel_id, str(output.get("content") or ""),
                completed=True,
            )
        else:
            if not profile:
                raise RuntimeError("Agent has no active LLM Provider Profile")
            output = provider_call(_call_llm, profile, messages if isinstance(messages, list) else [])
        if provider_completed:
            _set_profile_health(str(agent.get("llm_profile_id") or ""), "HEALTHY", int(profile.get("version") or 1))
        if dispatch and dispatch.get("kind") == "BUSINESS_MENTION":
            output["answer_metadata"] = _safe_answer_metadata(input_payload.get("answer_metadata"))
        if not dispatch:
            _write_channel_response(str(agent.get("agent_id") or ""), execution_id, input_payload, output=output)
        completion_hook = None
        if publication_guard is not None:
            completion_hook = publication_guard
        if isinstance(input_payload.get('framework_dispatch'), dict):
            from . import framework_execution
            def complete_framework(tx):
                if publication_guard is not None:
                    publication_guard(tx)
                framework_execution.complete(tx, execution, output)
            completion_hook = complete_framework
        _finish(execution_id, worker_id, node_id, fencing_token, "COMPLETED", output=output, observation=observation, completion_hook=completion_hook)
        return {"status": "COMPLETED", "execution_id": execution_id}
    except Exception as exc:
        logger.info("Native execution failed: %s", type(exc).__name__)
        failure_code=_failure_code(exc)
        logger.info("Native execution failure code: %s",failure_code)
        try:
            if provider_failed:
                _set_profile_health(str((agent or {}).get("llm_profile_id") or ""), "DEGRADED", int((profile or {}).get("version") or 1))
        except Exception:
            logger.debug("Unable to update LLM health", exc_info=True)
        try:
            _write_channel_response(str((agent or {}).get("agent_id") or ""), execution_id, input_payload, failure=failure_code)
        except Exception:
            logger.debug("Unable to write Channel response", exc_info=True)
        outcome = 'UNOBSERVED' if provider_unknown else 'FAILED'
        _finish(execution_id, worker_id, node_id, fencing_token, outcome, failure=failure_code, observation=observation)
        return {"status": outcome, "execution_id": execution_id,"failure_code":failure_code}
    finally:
        isolated = execution.get('_isolated_worker')
        if isolated:
            isolated.close()


def get_execution(actor: str, execution_id: str, *, transaction=None) -> Dict[str, Any]:
    from . import continuity_runtime
    if continuity_runtime.binding(execution_id, transaction=transaction):
        return continuity_runtime.read_execution(actor,execution_id,transaction=transaction)
    query = transaction.query_one if transaction is not None else connection.execute_query_one
    row = _row(query(
        "SELECT EXECUTION_ID,AGENT_ID,TARGET_ID,ISOLATION_LEVEL,STATUS,WORKER_ID,NODE_ID,INPUT_JSON,OUTPUT_JSON,"
        "FAILURE_REASON,STARTED_AT,COMPLETED_AT,CREATED_AT,UPDATED_AT FROM CX_RUNTIME_EXECUTIONS "
        "WHERE EXECUTION_ID=:id", {"id": execution_id},
    ))
    if not row or not identity_api._agent_visible_to(actor, str(row.get("agent_id") or ""), transaction=transaction):
        raise PermissionError("Execution is unavailable")
    from . import business_channel_runtime
    business_channel_runtime.require_result_reader(actor, str(row.get('agent_id') or ''), execution_id, transaction=transaction)
    from . import framework_execution
    framework_execution.require_reader(actor, row, tx=transaction)
    row.pop("input_json", None)
    if row.get("output_json"):
        row["output"] = _parse(row.pop("output_json"), {})
    return row
