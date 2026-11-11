"""Domain discovery and per-Agent model changes after owner Dashboard review."""

import sqlite3

import pytest

from lib import identity_api, native_agent_api, platform_agent_pool, security_domain_api


@pytest.fixture
def inventory(monkeypatch):
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.executescript("""
        CREATE TABLE CX_SECURITY_DOMAINS (SECURITY_DOMAIN_ID TEXT, DOMAIN_NAME TEXT,
            CLASSIFICATION TEXT, PURPOSE TEXT, STATUS TEXT, CREATED_AT TEXT);
        CREATE TABLE CX_DOMAIN_GOVERNANCE (SECURITY_DOMAIN_ID TEXT, OWNER_PRINCIPAL_ID TEXT,
            REASON TEXT, UPDATED_AT TEXT);
        CREATE TABLE CX_DOMAIN_MEMBERS (SECURITY_DOMAIN_ID TEXT, PRINCIPAL_ID TEXT,
            STATUS TEXT, VALID_UNTIL TEXT);
    """)
    db.executemany("INSERT INTO CX_SECURITY_DOMAINS VALUES (?,?,?,?,?,NULL)", [
        (f"SD_{i:04}", f"Domain {i:04}", "INTERNAL", "test", "ACTIVE") for i in range(305)
    ] + [("SD_LATE", "Z late project", "CONFIDENTIAL", "test", "ACTIVE"),
         ("SD_PAUSED", "Z paused", "RESTRICTED", "test", "SUSPENDED"),
         ("SD_LITERAL", "Z 100%_done!", "INTERNAL", "test", "ACTIVE"),
         ("CX_NATIVE_RUNTIME_ANCHOR", "Hidden anchor", "INTERNAL", "test", "ACTIVE")])
    db.execute("INSERT INTO CX_DOMAIN_MEMBERS VALUES ('SD_LATE','reader','ACTIVE',NULL)")
    db.execute("INSERT INTO CX_DOMAIN_MEMBERS VALUES ('SD_PAUSED','reader','ACTIVE',NULL)")
    monkeypatch.setattr(identity_api, "_require", lambda *_args: None)
    monkeypatch.setattr(identity_api, "effective_access", lambda actor, _action: {"decision": "ALLOW" if actor == "admin" else "DENY"})
    monkeypatch.setattr(security_domain_api.connection, "DATABASE_DIALECT", "pg")
    monkeypatch.setattr(security_domain_api.connection, "execute_query", lambda sql, params: [dict(row) for row in db.execute(sql, params)])
    yield db
    db.close()


def test_domain_filters_apply_before_limit_and_combine(inventory):
    assert len(security_domain_api.list_domains("admin", limit=300)) == 300
    rows = security_domain_api.list_domains("admin", limit=1, query="late", classification="CONFIDENTIAL", domain_status="ACTIVE")
    assert [r["security_domain_id"] for r in rows] == ["SD_LATE"]
    assert security_domain_api.list_domains("admin", query="SD_LATE", classification="INTERNAL") == []


def test_domain_filters_are_literal_and_parameterized(inventory):
    assert len(security_domain_api.list_domains("admin", query="100%_done!")) == 1
    assert security_domain_api.list_domains("admin", query="%' OR 1=1 --") == []


def test_filters_never_expand_nonadmin_discovery(inventory):
    assert [r["security_domain_id"] for r in security_domain_api.list_domains("reader", include_inactive=True)] == ["SD_LATE"]
    assert security_domain_api.list_domains("reader", include_inactive=True, domain_status="SUSPENDED") == []
    assert security_domain_api.list_domains("reader", query="Domain 0001") == []
    assert security_domain_api.list_domains("admin", query="anchor") == []
    assert len(security_domain_api.list_domains("admin", include_inactive=True, domain_status="SUSPENDED")) == 1


@pytest.mark.parametrize("filters", [{"query": "x" * 257}, {"domain_status": "invalid"}, {"classification": "invalid"}])
def test_invalid_domain_filters_fail(inventory, filters):
    with pytest.raises((security_domain_api.SecurityDomainError, identity_api.IdentityError)):
        security_domain_api.list_domains("admin", **filters)


class ModelTx:
    def __init__(self, state="ACTIVATION_PENDING", profile_status="ACTIVE", source="PLATFORM_CREATED"):
        self.agent = dict(agent_id="AGENT", source=source, status=state, activation_state=state, llm_profile_id="OLD")
        self.profile_status = profile_status
        self.writes = []

    def query_one(self, sql, _params):
        if "FROM CX_NATIVE_AGENTS" in sql:
            return self.agent.copy()
        if "FROM CX_LLM_PROVIDER_PROFILES" in sql:
            return dict(profile_id="NEW", status=self.profile_status) if self.profile_status else None
        raise AssertionError(sql)

    def execute(self, sql, params):
        self.writes.append((sql, params))
        self.agent["llm_profile_id"] = params["profile"]


@pytest.fixture
def model_setup(monkeypatch):
    monkeypatch.setattr(identity_api, "_require", lambda *_args: None)
    monkeypatch.setattr(identity_api, "_agent_visible_to", lambda *_args: True)
    audits = []
    monkeypatch.setattr(native_agent_api, "_audit", lambda *args: audits.append(args[2:]))
    return audits


@pytest.mark.parametrize("state", ["ACTIVE", "ACTIVATION_PENDING", "DISABLED"])
def test_model_save_preserves_state_and_audits_without_execution(monkeypatch, model_setup, state):
    tx = ModelTx(state)
    monkeypatch.setattr(native_agent_api.connection, "execute_transaction_callback", lambda work: work(tx))
    result = native_agent_api.configure_agent_model("admin", "AGENT", "NEW", "OLD", "review model")
    assert result == dict(agent_id="AGENT", status=state, activation_state=state, llm_profile_id="NEW")
    assert len(tx.writes) == 1
    assert "STATUS=" not in tx.writes[0][0] and "ACTIVATION_STATE=" not in tx.writes[0][0]
    assert model_setup[0][0] == "NATIVE_AGENT_MODEL_CONFIGURE"
    assert '"previous_profile_id":"OLD"' in model_setup[0][-1]


@pytest.mark.parametrize("profile_status,source,expected", [("RETIRED", "PLATFORM_CREATED", "OLD"), (None, "PLATFORM_CREATED", "OLD"), ("ACTIVE", "EXTERNAL_SKILL", "OLD"), ("ACTIVE", "PLATFORM_CREATED", "STALE")])
def test_rejected_model_save_leaves_binding_unchanged(monkeypatch, model_setup, profile_status, source, expected):
    tx = ModelTx(profile_status=profile_status, source=source)
    monkeypatch.setattr(native_agent_api.connection, "execute_transaction_callback", lambda work: work(tx))
    with pytest.raises(native_agent_api.NativeAgentError):
        native_agent_api.configure_agent_model("admin", "AGENT", "NEW", expected, "review model")
    assert tx.writes == [] and model_setup == []


@pytest.mark.parametrize("denied", ["platform.manage", "agents.manage", "visibility"])
def test_model_change_requires_both_permissions_and_visibility(monkeypatch, model_setup, denied):
    def require(_actor, action):
        if action == denied:
            raise PermissionError("denied")
    monkeypatch.setattr(identity_api, "_require", require)
    monkeypatch.setattr(identity_api, "_agent_visible_to", lambda *_: denied != "visibility")
    monkeypatch.setattr(native_agent_api.connection, "execute_transaction_callback", lambda _: pytest.fail("must not start a write transaction"))
    with pytest.raises(PermissionError):
        native_agent_api.configure_agent_model("reader", "AGENT", "NEW", "OLD", "review model")


@pytest.mark.parametrize("code", ["COMMAND_REASON_REQUIRED", "COMMAND_PARAMETER_REQUIRED:node_id", "UNKNOWN_PLATFORM_COMMAND"])
def test_expected_command_rejection_returns_persisted_message_and_feedback(monkeypatch, code):
    writes, audits = [], []
    monkeypatch.setattr(identity_api, "_assert_channel_member", lambda *_: {"classification": "INTERNAL"})
    monkeypatch.setattr(identity_api.connection, "execute", lambda sql, params: writes.append((sql, params)))
    monkeypatch.setattr(identity_api, "_enqueue_channel_deliveries", lambda *_: 0)
    monkeypatch.setattr(identity_api, "_audit", lambda *args: audits.append(args))
    def rejected(*_args, **_kwargs):
        raise platform_agent_pool.AgentPoolError(code)
    monkeypatch.setattr(native_agent_api, "create_channel_execution", rejected)
    result = identity_api._post_channel_message_uncached("admin", "CH_PLATFORM_ADMINISTRATION", "/platform HEALTH_READ 状态")
    assert len([sql for sql, _ in writes if sql.startswith("INSERT INTO CX_CHANNEL_MESSAGES")]) == 1
    assert result["message_id"]
    assert result["agent_dispatches"] == []
    assert result["agent_dispatch_errors"] == [{"agent_id": native_agent_api.PLATFORM_ADMIN_AGENT_ID, "reason": code}]
    assert audits[-1][-2] == "DENY"
