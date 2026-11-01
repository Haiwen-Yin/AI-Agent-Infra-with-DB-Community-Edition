"""Router keeps the existing authenticated dependency and server context."""
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient

from lib import observed_answer_review_http as routes, model_credentials
from .test_observed_answer_review import packet


def test_router_requires_dashboard_permission_and_csrf_before_packet_registration(monkeypatch):
    app = FastAPI(); calls = []
    def require_action(action):
        assert action == 'platform.manage'
        def authenticated(request: Request):
            if request.headers.get('X-CSRF-Token') != 'actual-csrf':
                raise HTTPException(403, 'CSRF validation failed')
            return dict(principal_id='server-human', session_digest='a'*64)
        return authenticated
    def register(actor, body):
        calls.append((actor, model_credentials._session.get(), body.packet.rows[0].observed['answer']))
        return dict(set_id='OAS_'+'a'*32, generation_requests=0)
    monkeypatch.setattr(routes.service, 'schema_enabled', lambda: True)
    monkeypatch.setattr(routes.service, 'register', register)
    routes.install(app, require_action)
    with TestClient(app) as client:
        body = dict(packet=packet(), reason='Original observation registration')
        assert client.post('/api/observed-answer-reviews/sets', json=body).status_code == 403
        response = client.post('/api/observed-answer-reviews/sets', json=body, headers={'X-CSRF-Token': 'actual-csrf'})
        assert response.status_code == 200
        assert response.json()['generation_requests'] == 0
    assert calls == [('server-human', dict(principal_id='server-human', session_digest='a'*64), 'The original captured answer.')]
    assert model_credentials._session.get() is None


def test_disabled_release_has_no_observed_review_routes(monkeypatch):
    app = FastAPI()
    monkeypatch.setattr(routes.service, 'schema_enabled', lambda: False)
    routes.install(app, lambda _: (_ for _ in ()).throw(AssertionError('No enabled API')))
    assert all('observed-answer-reviews' not in route.path for route in app.routes)
