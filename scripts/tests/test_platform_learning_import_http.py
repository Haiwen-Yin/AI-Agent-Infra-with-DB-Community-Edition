"""Actual import route, permission dependency and CSRF with isolated data."""
from contextlib import nullcontext
import hashlib
import json

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
import pytest

from lib import product_knowledge as knowledge
from .test_product_knowledge import publication, lifecycle
from .test_platform_learning_delivery import external


@pytest.fixture
def http(external, monkeypatch):
    import web_app
    root, db, product, bundle = external
    app = FastAPI()
    route = next(route for route in web_app.app.routes
                 if getattr(route, 'path', '') == '/api/platform/learning/import')
    app.add_api_route(route.path, route.endpoint, methods=['POST'])
    state = dict(authenticated=True, allowed=True)
    def session():
        if not state['authenticated']:
            raise HTTPException(401, 'Authentication required')
        return dict(principal_id='admin', csrf_digest=hashlib.sha256(b'test-csrf').hexdigest())
    app.dependency_overrides[web_app.principal] = session
    monkeypatch.setattr(web_app, '_schema_owner_context', nullcontext)
    monkeypatch.setattr(knowledge.product_identity, 'package_root', lambda *_: root)
    monkeypatch.setattr(knowledge.identity_api, 'effective_access',
                        lambda *_: {'decision': 'ALLOW' if state['allowed'] else 'DENY'})
    monkeypatch.setattr(knowledge.connection, 'DATABASE_DIALECT', 'postgresql')
    return TestClient(app), state, db, bundle


def test_import_route_requires_session_csrf_and_current_management_authority(http):
    client, state, db, bundle = http
    body = {'bundle_json': json.dumps(bundle)}
    state['authenticated'] = False
    assert client.post('/api/platform/learning/import', json=body).status_code == 401
    state['authenticated'] = True
    assert client.post('/api/platform/learning/import', json=body).status_code == 403
    state['allowed'] = False
    assert client.post('/api/platform/learning/import', json=body, headers={'X-CSRF-Token': 'test-csrf'}).status_code == 403
    assert db.execute('SELECT COUNT(*) FROM CX_PLATFORM_KNOWLEDGE').fetchone()[0] == 0
    state['allowed'] = True
    result = client.post('/api/platform/learning/import', json=body, headers={'X-CSRF-Token': 'test-csrf'})
    assert result.status_code == 200 and result.json()['status'] == 'PUBLISHED'
    assert db.execute('SELECT COUNT(*) FROM ENTITIES').fetchone()[0] == 1


@pytest.mark.parametrize('body', [{'bundle_json': 'not json'}, {'bundle_json': '{}'},
                                  {'bundle_json': '{}', 'actor': 'outsider'}])
def test_import_route_rejects_invalid_files_and_actor_override(http, body):
    client, _, db, _ = http
    result = client.post('/api/platform/learning/import', json=body, headers={'X-CSRF-Token': 'test-csrf'})
    assert result.status_code == 422
    assert db.execute('SELECT COUNT(*) FROM CX_PLATFORM_KNOWLEDGE').fetchone()[0] == 0


def test_import_route_sanitizes_driver_failure(http, monkeypatch):
    client, _, _, bundle = http
    def fail(*_, **__):
        raise RuntimeError('Private database connection material')
    monkeypatch.setattr(knowledge, 'import_learning', fail)
    result = client.post('/api/platform/learning/import', json={'bundle_json': json.dumps(bundle)},
                         headers={'X-CSRF-Token': 'test-csrf'})
    assert result.status_code == 503 and 'Private' not in result.text
