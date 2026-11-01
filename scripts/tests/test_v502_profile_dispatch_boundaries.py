"""Profile health checks retain original credentials and exact queued authority.

All peers, credentials, transactions and provider replies are synthetic.
"""
from contextlib import contextmanager
import json
from types import SimpleNamespace

import pytest

from lib import (edition_features, model_credentials, model_dispatch,
                 model_endpoint_capacity, native_agent_api as profiles,
                 provider_capability_probes)

REAL_DISPATCH = model_dispatch.dispatch


PROFILE = {"profile_id": "profile", "version": 3, "profile_key": "synthetic",
           "provider_url": "https://provider.invalid/v1", "model_id": "synthetic-model",
           "api_key_cipher": "", "status": "ACTIVE"}
BINDING = model_credentials.CredentialBinding("admin", "WEB", "b" * 64,
    auth_method="PASSWORD:DASHBOARD", permission_version=7, mfa_level="TOTP",
    node_id="synthetic-node", created_at="2026-10-28T10:00:00")


def completion(**changes):
    result = {"model": PROFILE["model_id"],
              "choices": [{"index": 0, "message": {"role": "assistant", "content": "CX_OK"}, "finish_reason": "stop"}],
              "usage": {"prompt_tokens": 8, "completion_tokens": 2, "total_tokens": 10}}
    result.update(changes)
    return result


@pytest.fixture
def probe(monkeypatch):
    monkeypatch.setattr(edition_features, "MODEL_RUNTIME_CONTEXT_ENABLED", True)
    # This fixture models a local Profile; cross-installation enrollment and
    # routing use the separate independent-database HTTP integration suite.
    from lib import model_coordinator_origin
    monkeypatch.setattr(model_coordinator_origin, "selected_route", lambda profile: None)
    state = SimpleNamespace(current=dict(PROFILE), permission=True, revoked=False,
                            sends=[], audits=[], health=[], captures=[], rechecks=[], observations=[],
                            queued=lambda: None, reply=completion(), read_effect=lambda: None, failure=None)
    class Transaction:
        def query_one(self, *_args, **_kwargs):
            return dict(state.current)
    tx = Transaction()
    monkeypatch.setattr(profiles.connection, "execute_query_one", lambda *_: dict(state.current))
    monkeypatch.setattr(profiles.connection, "execute_transaction_callback", lambda work: work(tx))
    def execute(sql, parameters):
        assert parameters == {"id": "profile", "version": 3}
        state.health.append(sql)
        return int(state.current["version"] == 3 and state.current["status"] == "ACTIVE")
    monkeypatch.setattr(profiles.connection, "execute", execute)
    monkeypatch.setattr(profiles.identity_api, "effective_access", lambda *_: {"decision": "ALLOW" if state.permission else "DENY"})
    monkeypatch.setattr(profiles, "_audit", lambda *args: state.audits.append(args[2:]))
    monkeypatch.setattr(provider_capability_probes, "request_parameters", lambda *_: {})
    def capture(actor, **options):
        state.captures.append((actor, options))
        return BINDING
    def recheck(_tx, binding):
        assert binding is BINDING
        state.rechecks.append(binding)
        if state.revoked:
            raise PermissionError("The original Web Session is no longer current")
        return binding.credential_digest
    monkeypatch.setattr(model_credentials, "capture", capture)
    monkeypatch.setattr(model_credentials, "recheck", recheck)
    class Ticket(model_dispatch.DispatchTicket):
        def observe_result(self, result):
            state.observations.append(result)
    @contextmanager
    def dispatch(profile, payload):
        assert profile == PROFILE
        assert payload["model"] == PROFILE["model_id"] and not payload["stream"]
        context = model_dispatch._context.get()
        assert context.actor == "admin" and context.credential_digest == BINDING.credential_digest
        assert context.source_kind == "PROBE" and context.source_id == context.source_attempt_id
        assert context.lock_principals == ("admin",)
        state.queued()
        context.reauthorize(tx, {"credential_digest": BINDING.credential_digest})
        yield Ticket()
    monkeypatch.setattr(model_dispatch, "dispatch", dispatch)
    class Response:
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def read(self, *_):
            state.read_effect()
            return json.dumps(state.reply).encode()
    def send(request, **options):
        state.sends.append((request, options))
        if state.failure:
            raise state.failure
        return Response()
    monkeypatch.setattr(profiles.urllib.request, "urlopen", send)
    return state


def test_saved_health_uses_original_binding_and_observes_valid_completion(probe):
    result = profiles.probe_saved_llm_profile("admin", "profile")
    assert result["health_state"] == "HEALTHY" and result["observed_model"] == PROFILE["model_id"]
    assert probe.captures == [("admin", {"required_scope": "platform.manage"})]
    assert len(probe.rechecks) == 2 and len(probe.sends) == 1
    assert probe.observations[0]["usage"]["total_tokens"] == 10
    assert len(probe.audits) == 1 and probe.audits[0][0] == "LLM_PROFILE_PROBE"


@pytest.mark.parametrize("field,value", [("version", 4), ("status", "RETIRED"),
    ("provider_url", "https://changed.invalid/v1"), ("model_id", "other-model"),
    ("api_key_cipher", "another-cipher"), ("profile_key", "another-profile")])
def test_queued_health_never_switches_to_another_profile_revision(probe, field, value):
    probe.queued = lambda: probe.current.update({field: value})
    with pytest.raises(profiles.NativeAgentConflict, match="changed during"):
        profiles.probe_saved_llm_profile("admin", "profile")
    assert not probe.sends and not probe.observations


def test_revoked_original_session_is_not_replaced_after_queueing(probe):
    probe.queued = lambda: setattr(probe, "revoked", True)
    with pytest.raises(PermissionError, match="original Web Session"):
        profiles.probe_saved_llm_profile("admin", "profile")
    assert len(probe.captures) == 1 and len(probe.rechecks) == 2 and not probe.sends


def test_permission_revocation_after_queueing_prevents_health_send(probe):
    probe.queued = lambda: setattr(probe, "permission", False)
    with pytest.raises(PermissionError, match="platform management"):
        profiles.probe_saved_llm_profile("admin", "profile")
    assert not probe.sends


def test_changed_profile_after_response_cannot_be_marked_healthy(probe):
    probe.read_effect = lambda: probe.current.update(version=4)
    with pytest.raises(profiles.NativeAgentConflict, match="changed during"):
        profiles.probe_saved_llm_profile("admin", "profile")
    assert len(probe.sends) == 1 and not probe.audits


@pytest.mark.parametrize("finish", [None, "length", "content_filter", "tool_calls"])
def test_health_requires_complete_text_before_marking_healthy(probe, finish):
    probe.reply["choices"][0]["finish_reason"] = finish
    with pytest.raises(profiles.NativeAgentError, match="no completion"):
        profiles.probe_saved_llm_profile("admin", "profile")
    assert len(probe.sends) == 1 and not probe.observations
    assert all("HEALTHY" not in sql for sql in probe.health)


@pytest.mark.parametrize("message", [{"content": ""}, {"content": "  "}, {"reasoning_content": "hidden"}])
def test_saved_health_retains_empty_content_error_category(probe, message):
    probe.reply["choices"][0]["message"] = message
    with pytest.raises(profiles.NativeAgentError, match="no content"):
        profiles.probe_saved_llm_profile("admin", "profile")
    assert len(probe.sends) == 1 and not probe.observations


def test_health_transport_timeout_does_not_resend(probe):
    probe.failure = TimeoutError("private provider text")
    with pytest.raises(TimeoutError):
        profiles.probe_saved_llm_profile("admin", "profile")
    assert len(probe.sends) == 1 and not probe.observations


def test_saved_controlled_health_requires_an_original_authenticated_credential(probe, monkeypatch):
    monkeypatch.setattr(model_credentials, "capture", lambda *_a, **_kw: None)
    monkeypatch.setattr(model_dispatch, "dispatch", REAL_DISPATCH)
    monkeypatch.setattr(model_endpoint_capacity, "selected_group", lambda *_: "controlled")
    with pytest.raises(PermissionError, match="authenticated supported dispatch route"):
        profiles.probe_saved_llm_profile("admin", "profile")
    assert not probe.sends and not probe.rechecks


def test_health_provider_refusal_does_not_become_healthy(probe):
    probe.reply["choices"][0]["message"]["refusal"] = "private refusal details"
    with pytest.raises(profiles.NativeAgentError, match="no completion"):
        profiles.probe_saved_llm_profile("admin", "profile")
    assert len(probe.sends) == 1 and not probe.observations
    assert "private refusal" not in str(probe.audits)


def test_health_rejects_oversized_response_once(probe):
    probe.reply["choices"][0]["message"]["content"] = "x" * (1024 * 1024)
    with pytest.raises(profiles.NativeAgentError, match="too large"):
        profiles.probe_saved_llm_profile("admin", "profile")
    assert len(probe.sends) == 1 and not probe.observations


@pytest.mark.parametrize("inherited_context", [False, True])
def test_draft_controlled_alias_cannot_borrow_another_dispatch_context(monkeypatch, inherited_context):
    monkeypatch.setattr(edition_features, "MODEL_RUNTIME_CONTEXT_ENABLED", True)
    monkeypatch.setattr(profiles.connection, "execute_transaction_callback", lambda work: work(None))
    monkeypatch.setattr(model_endpoint_capacity, "selected_group", lambda *_: "controlled")
    monkeypatch.setattr(profiles, "_audit", lambda *_: None)
    sends = []
    monkeypatch.setattr(profiles.urllib.request, "urlopen", lambda *args, **kwargs: sends.append(args))
    @contextmanager
    def context():
        if inherited_context:
            with model_dispatch.authenticated_context("admin", "PROBE", "old-probe", "old-probe",
                    credential_digest="b" * 64, reauthorize=lambda *_: None, worker_key="old-worker"):
                yield
        else:
            yield
    with context(), pytest.raises(profiles.NativeAgentError, match="saved Provider Profile"):
        profiles.probe_llm_profile("admin", "draft", PROFILE["provider_url"], PROFILE["model_id"], "private-secret")
    assert not sends
