"""Opt-in native/ASGI development checks, with actual official HTTP collection.

Uses genuine dashboard login/CSRF. The independent reviewer is an enrolled AI
test identity, never a Human approval. No model or embedding request is allowed.
"""
from collections import Counter
from contextlib import contextmanager
import json
import os
from pathlib import Path
import secrets
import time
import uuid

from fastapi.testclient import TestClient
import pytest

from lib import connection, identity_api, security_domain_api as domains
from lib import agent_source_sync as sync, continuity_candidates as candidates
from lib import continuity_assembly as assembly, context_selection, embedding_api
from lib import continuity_sources, knowledge_grounding, native_runtime
from lib.continuity_contracts import SourceRef
from .test_v503_knowledge_native import native_target, independent_reviewer


class DashboardActor(tuple):
    def __repr__(self):
        return '<isolated dashboard credentials>'


@pytest.fixture
def dashboard_actor(native_target):
    """Normal registration of an isolated test operator; preserve stable admin."""
    target, provisioner = native_target
    password_path = os.environ.get('CX_DEVELOPMENT_ADMIN_PASSWORD_FILE')
    if not password_path:
        pytest.skip('Select the retained provisioner password file explicitly')
    provisioner_password = Path(password_path).read_text().strip()
    assert identity_api.authenticate_local('admin', provisioner_password)['principal_id'] == provisioner
    reason = 'Isolated v5.0.4 automated dashboard data-flow operator'
    from lib import organization_api
    roots = [item for item in organization_api.list_options(provisioner, limit=500)
             if item.get('status') == 'ACTIVE' and item.get('parent_id') is None]
    if not roots:
        # AgentX's actual stable baseline has no organization rows. Its
        # protected bootstrap operator can log in without inventing an org or
        # changing the inherited registration/entry policy in this data gate.
        access = identity_api.entry_access(provisioner)
        assert access['app_enabled'] and access['protected_system_admin']
        yield DashboardActor((target, provisioner, 'admin', provisioner_password))
        return
    assert len(roots) == 1
    username = 'v504_operator_'+secrets.token_hex(8)
    password = secrets.token_urlsafe(32)
    token = identity_api.issue_human_registration_token(provisioner, 900, reason)
    registered = identity_api.register_human(username, password, display_name='Automated development operator',
        email=username+'@example.invalid', registration_token=token['token'])
    if registered['status'] == 'PENDING':
        registered = identity_api.approve_registration(registered['request_id'], provisioner, reason, roots[0]['organization_id'])
    actor = registered['principal_id']
    assert actor != provisioner and registered['status'] == 'ACTIVE'
    identity_api.assign_user_role(provisioner, actor, 'SYSTEM_ADMIN', reason)
    try:
        identity_api.set_entry_access(provisioner, actor, True, reason)
        assert identity_api.entry_allowed(actor, 'APP')
        yield DashboardActor((target, actor, username, password))
    finally:
        identity_api.set_entry_access(provisioner, actor, False, reason)
        identity_api.revoke_principal_sessions(actor, reason)
        for role in identity_api.list_user_roles(provisioner, actor):
            if role['role_code'] == 'SYSTEM_ADMIN' and role['status'] == 'ACTIVE':
                identity_api.revoke_user_role(provisioner, actor, role['user_role_id'], reason)


@contextmanager
def preparation_measurement(monkeypatch):
    """Count actual adapter calls without replacing SQL, authorization or data."""
    counts = Counter()
    callback = connection.execute_transaction_callback
    class ObservedTransaction:
        def __init__(self, tx): self.tx = tx
        def __getattr__(self, name):
            value = getattr(self.tx, name)
            if name not in {'query', 'query_one', 'execute'}:
                return value
            def observed(*args, **kwargs):
                counts[name] += 1
                return value(*args, **kwargs)
            return observed
    def transaction(fn, *args, **kwargs):
        counts['transactions'] += 1
        return callback(lambda tx: fn(ObservedTransaction(tx)), *args, **kwargs)
    def wrapped(name, original):
        def call(*args, **kwargs):
            counts[name] += 1
            return original(*args, **kwargs)
        return call
    with monkeypatch.context() as patch:
        patch.setattr(connection, 'execute_transaction_callback', transaction)
        patch.setattr(context_selection, 'select_sources', wrapped('selection', context_selection.select_sources))
        patch.setattr(assembly, 'resolve_many', wrapped('body_batches', assembly.resolve_many))
        patch.setattr(assembly, '_source_text', wrapped('source_render', assembly._source_text))
        yield counts


def test_native_official_incident_task_session_intake_context_and_revocation(dashboard_actor, monkeypatch, record_property):
    target, actor, username, password = dashboard_actor
    import web_app
    client = TestClient(web_app.app, base_url='http://127.0.0.1:'+str(target['service_port']),
        client=('127.0.0.1', 50000))
    reason = 'v5.0.4 isolated official incident integration; independent AI review'
    domain = 'V504_INCIDENT_'+uuid.uuid4().hex.upper()
    domains.create_domain(actor, domain, 'Official incident development evidence', 'INTERNAL', reason, actor, reason)
    forbidden = Counter()
    def no_generation(*args, **kwargs):
        forbidden['generation'] += 1
        pytest.fail('This native data gate must not invoke a model or embedding')
    for module, names in ((native_runtime, ('_call_llm', '_stream_llm')),
                          (embedding_api, ('_query_embedding', 'generate_embedding'))):
        for name in names: monkeypatch.setattr(module, name, no_generation)
    measurements = []
    try:
        with independent_reviewer(actor, domain, reason) as reviewer:
            identity_api.assign_permission_override(actor, reviewer, 'agents.read', 'ALLOW', 'OWNED', reason)
            payload = dict(security_domain_id=domain, agent_id=reviewer, kind='STATUSPAGE',
                endpoint='https://www.githubstatus.com/api/v2/incidents.json',
                paths=['/incidents/recent/1'], content_types=['application/json'], max_bytes=262144,
                reason=reason, idempotency_key=uuid.uuid4().hex)
            source_root = '/api/agent-extensions/sources'
            job_root = '/api/agent-extensions/source-sync-jobs'
            assert client.post(source_root, json=payload).status_code in {401, 403}
            login = client.post('/api/auth/login', json=dict(username=username, password=password))
            assert login.status_code == 200, login.text[:200]
            headers = {'X-CSRF-Token': login.json()['csrf_token']}
            assert client.post(source_root, json=payload).status_code == 403
            created = client.post(source_root, json=payload, headers=headers)
            assert created.status_code == 200, created.text[:250]
            source = created.json()['source_id']
            job = client.post(source_root+'/'+source+'/sync', headers=headers,
                json=dict(reason=reason, idempotency_key=uuid.uuid4().hex))
            assert job.status_code == 200, job.text[:250]
            job_id = job.json()['job_id']
            run = client.post(job_root+'/'+job_id+'/run', headers=headers)
            assert run.status_code == 200, run.text[:250]
            result = run.json()
            assert result['status'] == 'SUCCEEDED' and result['imports']
            task = connection.execute_query_one('SELECT l.CANONICAL_TASK_ID AS TASK_ID FROM CX_AGENT_SYNC_JOBS j '
                'JOIN CX_TASK_CONTINUITY_LINKS l ON l.CONTINUITY_ID=j.CONTINUITY_ID WHERE j.JOB_ID=:job', dict(job=job_id))
            assert task and task['task_id']
            overview = connection.execute_query_one('SELECT REVISION_ID FROM CX_AGENT_SOURCE_REVISIONS '
                'WHERE SOURCE_ID=:source AND SOURCE_PATH LIKE :source_path', dict(source=source, source_path='%/overview.md'))
            assert overview
            imported = next(item for item in result['imports'] if item['revision_id'] == overview['revision_id'])
            pending = client.get('/api/artifact-candidates/'+imported['candidate_id']).json()
            assert pending['status'] == 'PENDING'
            assert pending['payload']['intake']['decision_status'] == 'HISTORICAL'
            assert pending['payload']['intake']['responsible_principal_id'] is None
            reference = SourceRef.model_validate(pending['payload']['sources'][0])
            exact = connection.execute_transaction_callback(lambda tx: sync.resolve_source(tx, actor, domain, reference))
            assert exact['provenance']['method'] == 'TASK_HTTP_STATUSPAGE'
            assert exact['factual_report']['source']['snapshot_sha256'] == exact['provenance']['response_sha256']
            request = dict(request_id=uuid.uuid4().hex, security_domain_id=domain,
                mandatory_sources=[reference.model_dump(mode='json')], token_budget=32000,
                purpose=reason, idempotency_key=uuid.uuid4().hex)
            with preparation_measurement(monkeypatch) as calls:
                for label, operation in (
                    ('create', lambda: assembly.assemble(actor, request)),
                    ('same_request_replay', lambda: assembly.assemble(actor, request)),
                ):
                    before = calls.copy(); started = time.monotonic()
                    prepared = operation()
                    measurements.append(dict(operation=label, elapsed_ms=round((time.monotonic()-started)*1000, 3),
                        calls=dict(calls-before)))
                    assert prepared['item_count'] == 1
                assert prepared['replayed']
            observed = client.get('/api/context/assemblies/'+prepared['assembly_id']).json()
            assert observed['budget'] and observed['representations']
            assert observed['text'] == exact['text']
            cid = imported['candidate_id']
            denied = client.post('/api/artifact-candidates/'+cid+'/review', headers=headers,
                json=dict(expected_version=1, expected_digest=pending['content_digest'], decision='APPROVED',
                    reason=reason, idempotency_key=uuid.uuid4().hex))
            assert denied.status_code in {403, 409}
            # A source Task cannot decide internal applicability or approve itself.
            revised = client.post('/api/artifact-candidates/'+cid+'/revisions', headers=headers,
                json=dict(security_domain_id=domain, expected_version=1,
                    content=pending['payload']['content'], sources=pending['payload']['sources'],
                    intake=dict(purpose='Historical external incident reference', source_locator=exact['provenance']['locator'],
                        responsible_principal_id=actor, subject='Public external service incident',
                        applicable_product='External GitHub service', applicable_version='Public incident record',
                        effective_from='2026-01-01T00:00:00Z', classification='INTERNAL',
                        audience='PRINCIPAL_PRIVATE', decision_status='HISTORICAL'),
                    reason=reason, idempotency_key=uuid.uuid4().hex))
            assert revised.status_code == 200, revised.text[:250]
            current = candidates.read_candidate(reviewer, cid)
            assert current['intake_preview']['publication_eligible']
            candidates.review_candidate(reviewer, cid, dict(expected_version=2, expected_digest=current['content_digest'],
                decision='APPROVED', reason=reason, idempotency_key=uuid.uuid4().hex))
            promoted = candidates.promote_candidate(reviewer, cid, dict(expected_version=3,
                expected_digest=current['content_digest'], reason=reason, idempotency_key=uuid.uuid4().hex))
            projection = connection.execute_query_one('SELECT NATIVE_ENTITY_ID,CONTENT_DIGEST FROM CX_CONTINUITY_ARTIFACT_REVS '
                'WHERE ARTIFACT_ID=:artifact AND REVISION_ID=:revision',
                dict(artifact=promoted['result_entity_id'], revision=promoted['result_revision_id']))
            artifact = SourceRef(family='KNOWLEDGE', entity_id=promoted['result_entity_id'],
                revision_id=promoted['result_revision_id'], content_digest=projection['content_digest'])
            loaded = connection.execute_transaction_callback(lambda tx: continuity_sources.resolve(tx, actor, domain, artifact))
            assert json.loads(loaded['text'])['body'] == exact['text']
            citation = knowledge_grounding.citation(actor, actor, str(projection['native_entity_id']))
            assert citation['source_context']['intake']['decision_status'] == 'HISTORICAL'
            revoked = client.post(source_root+'/'+source+'/state', headers=headers,
                json=dict(expected_version=1, status='REVOKED', reason=reason, idempotency_key=uuid.uuid4().hex))
            assert revoked.status_code == 200
            assert client.get('/api/context/assemblies/'+prepared['assembly_id']).status_code in {403, 409}
            with pytest.raises(PermissionError):
                connection.execute_transaction_callback(lambda tx: sync.resolve_source(tx, actor, domain, reference))
            assert not forbidden
            record_property('native_incident_flow', json.dumps(dict(target=target['key'],
                genuine_dashboard_session=True, csrf_denial=True, actual_official_http=True,
                task_id=str(task['task_id']), imported_units=len(result['imports']),
                snapshot_sha256=exact['provenance']['response_sha256'], record_sha256=exact['provenance']['record_sha256'],
                candidate_pending=True, reviewer_type='AI_TEST_IDENTITY', human_approval=False,
                historical_intake_preserved=True, exact_projection_and_citation=True, revoked_read_denied=True,
                preparation=measurements, generation_calls=0, embedding_calls=0)))
    finally:
        if client.cookies:
            client.post('/api/auth/logout', headers=headers if 'headers' in locals() else {})
        client.close()
