"""Exercise the actual application stack without a database admission bypass."""
from fastapi.testclient import TestClient
import pytest

import web_app
from lib import network_access as net


@pytest.fixture
def client(monkeypatch):
    net.policy_cache.invalidate()
    monkeypatch.setattr(net.policy_cache, "loader", lambda: net.Policy(1, True, "ALLOWLIST", ()))
    return TestClient(web_app.app, client=("127.0.0.2", 1234))


@pytest.mark.parametrize("path", ["/app", "/app/", "/portal", "/api/health", "/api/platform/ip-access", "/openapi.json"])
def test_real_application_has_no_admission_exceptions(client, path):
    response = client.get(path)
    assert response.status_code == 403 and response.content == net.DENIAL
    assert "X-Correlation-ID" not in response.headers  # Rejected before inner application middleware.


def test_real_recovery_retains_shell_and_login_boundary(monkeypatch):
    # The source-only facade has no database. Admit the independent capability
    # check so the real authentication dependency can reject the missing login.
    monkeypatch.setattr(web_app.platform_capabilities, "is_enabled", lambda *_: True)
    local = TestClient(web_app.app, client=("127.0.0.1", 1234))
    for path in ("/app", "/app/"):
        response = local.get(path)
        assert response.status_code == 200 and response.headers["content-type"].startswith("text/html")
    assert local.get("/api/platform/ip-access").status_code == 401
