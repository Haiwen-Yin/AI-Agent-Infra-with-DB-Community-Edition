"""Independent product identity must also hold in replies and MFA enrollment."""
from urllib.parse import parse_qs, unquote, urlparse

import pytest
from lib import answer_planning, native_runtime, product_identity, security_lifecycle


@pytest.fixture
def agentx(monkeypatch):
    product = {"brand_zh": "OpenTenBase AgentX", "brand_en": "OpenTenBase AgentX",
               "databases": ["pg"], "edition": "Community"}
    monkeypatch.setattr(product_identity, "identity", lambda: product)
    return product


@pytest.mark.parametrize("language", ["zh", "en"])
def test_management_overview_respects_agentx_backend_and_edition(agentx, language):
    reply = native_runtime._platform_product_markdown({}, language)
    assert "OpenTenBase AgentX" in reply and "PostgreSQL" in reply
    assert all(name not in reply for name in ("川序", "Chuanxu", "Oracle", "YashanDB"))
    assert ("社区版不包含企业专属审批和合规模块" if language == "zh"
            else "Community excludes Enterprise-only approval and compliance modules") in reply


def test_management_overview_includes_only_selected_enterprise_backend(agentx):
    agentx.update(brand_en="Chuanxu", brand_zh="川序", databases=["oracle"], edition="Enterprise")
    reply = native_runtime._platform_product_markdown({}, "en")
    assert "Chuanxu" in reply and "Oracle" in reply
    assert "PostgreSQL" not in reply and "YashanDB" not in reply
    assert "Enterprise additionally provides approval and compliance governance" in reply


def test_ambiguous_database_question_uses_current_product(agentx):
    reply = answer_planning.prepare("Oracle", "", {"mode": "KNOWLEDGE_FIRST", "allow_model_supplement": "Y"},
                                    {"items": [], "status": "AMBIGUOUS"})
    assert "OpenTenBase AgentX" in reply["knowledge_reply"]
    assert "川序" not in reply["knowledge_reply"]


def test_totp_uri_has_current_issuer_and_roundtrips_principal(agentx, monkeypatch):
    from lib import connection_crypto
    monkeypatch.setattr(security_lifecycle, "_require", lambda *_: None)
    monkeypatch.setattr(security_lifecycle.identity_api, "_principal_visible_to", lambda *_: True)
    monkeypatch.setattr(security_lifecycle.connection, "execute", lambda *_: 1)
    monkeypatch.setattr(security_lifecycle, "_audit", lambda *_: None)
    monkeypatch.setattr(connection_crypto, "encrypt_section", lambda *_: "encrypted")
    principal = "user:with/slash?and space"
    result = security_lifecycle.enroll_totp(principal, principal, "enroll personal authenticator")
    uri = urlparse(result["otpauth_uri"])
    assert unquote(uri.path) == "/OpenTenBase AgentX:" + principal
    assert parse_qs(uri.query) == {"secret": [result["secret"]], "issuer": ["OpenTenBase AgentX"]}
