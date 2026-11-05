"""Bounded connector and governed-candidate regressions; no live model calls."""
import copy
import json

import pytest

from lib import agent_source_sync as sync, enterprise_incidents as incidents
from lib import continuity_candidates as candidates
from lib.continuity_contracts import SourceRef
from lib.continuity_state import ContinuityError
from .test_v501_context_assets import store
from .test_continuity_candidates import candidate_db
from .test_continuity_handoff import fixture
from .test_continuity_work import database

ENDPOINT = 'https://www.githubstatus.com/api/v2/incidents.json'


def record(iid='fixture1'):
    return dict(id=iid, name='Synthetic incident', status='resolved', impact='none',
        started_at='2026-11-04T21:20:00Z', resolved_at='2026-11-04T21:22:00Z',
        components=[dict(id='component1', name='Synthetic service', status='operational')],
        incident_updates=[dict(id='update1', status='resolved', body='Some synthetic users experienced errors.',
            display_at='2026-11-04T21:22:00Z', created_at='2026-11-04T22:21:26Z', updated_at=None)])


def configuration(**changes):
    return dict(security_domain_id='domain', agent_id='agent', kind='STATUSPAGE', endpoint=ENDPOINT,
        paths=['/incidents/recent/1'], content_types=['application/json'], max_bytes=262144,
        reason='Collect official incident evidence for independent review', idempotency_key='configure') | changes


def response(*records):
    return dict(status=200, content_type='application/json', body=json.dumps(dict(incidents=list(records))).encode())


@pytest.mark.parametrize('change', [dict(endpoint='https://example.org/api/v2/incidents.json'),
    dict(endpoint=ENDPOINT+'?page=1'), dict(paths=['/']), dict(paths=['/incidents/recent/6']),
    dict(paths=['/incidents/recent/1', '/incidents/recent/2']), dict(credential_ref='READ_TOKEN'),
    dict(content_types=['text/plain']), dict(pinned_commit='a'*40)])
def test_configuration_cannot_expand_official_read_contract(change):
    with pytest.raises(ValueError):
        sync.SourceConfiguration.model_validate(configuration(**change))


def test_projection_preserves_unknowns_and_distinct_timestamps():
    projected = incidents.project(ENDPOINT, record())
    assert projected['declared_window_seconds'] == 120
    assert projected['updates'][0]['display_at'] < projected['updates'][0]['created_at']
    assert projected['upstream_impact_label'] == 'none'
    assert projected['root_cause'] is projected['affected_users'] is projected['internal_severity'] is None
    assert 'status' not in projected['listed_components'][0]
    assert record()['incident_updates'][0]['body'] in incidents.units(ENDPOINT, record())[1]['text']


def test_fetch_verifies_actual_response_and_stable_per_record_identity():
    source = dict(endpoint=ENDPOINT, paths=['/incidents/recent/1'], types=['application/json'], max_bytes=262144)
    calls = []
    def get(url, **kwargs):
        calls.append((url, kwargs))
        return response(record(), record('unselected2'))
    first = incidents.fetch(source, get)
    second = incidents.fetch(source, lambda *a, **kw: response(record(), record('unselected3')))
    assert len(first) == 2 and first[0]['version'] == second[0]['version']
    assert first[0]['statuspage']['response_sha256'] != second[0]['statuspage']['response_sha256']
    assert calls[0] == (ENDPOINT, dict(allowed_hosts={'www.githubstatus.com'}, headers={}, max_bytes=incidents.RESPONSE_LIMIT))
    document = first[1]
    revision = dict(source_version=document['version'], source_path=document['path'], title=document['title'])
    stored = dict(text=document['text'], statuspage=document['statuspage'])
    verified = incidents.verify_snapshot(revision, stored)
    assert verified['method'] == 'TASK_HTTP_STATUSPAGE' and verified['decision_status'] == 'HISTORICAL'
    forged = copy.deepcopy(stored); forged['statuspage']['record']['incident_updates'][0]['body'] += ' Forged'
    with pytest.raises(ContinuityError, match='provenance'):
        incidents.verify_snapshot(revision, forged)


def test_bound_factual_report_matches_bundled_schema_and_rejects_tampering():
    from pathlib import Path
    import jsonschema
    document = incidents.fetch(dict(endpoint=ENDPOINT, paths=['/incidents/recent/1'],
        types=['application/json'], max_bytes=262144), lambda *a, **kw: response(record()))[0]
    revision = dict(source_version=document['version'], source_path=document['path'], title=document['title'])
    stored = dict(text=document['text'], statuspage=document['statuspage'])
    root = Path(__file__).resolve().parents[2]
    schema_path = root/'docs/enterprise-incidents/report.schema.json'
    if not schema_path.exists(): schema_path = root/'docs/v5.0.4/enterprise-incidents/report.schema.json'
    schema = json.loads(schema_path.read_text())
    report = incidents.factual_report(revision, stored)
    jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker()).validate(report)
    assert report['source']['record_sha256'] == document['statuspage']['record_sha256']
    assert report['root_cause'] is report['internal_severity'] is report['affected_users'] is None
    forged = copy.deepcopy(stored); forged['statuspage']['record']['status'] = 'invented'
    with pytest.raises(ContinuityError): incidents.factual_report(revision, forged)


@pytest.mark.parametrize('fault', ['oversize', 'duplicate', 'bad_time', 'big_unit', 'duplicate_json'])
def test_malformed_response_never_slices_or_silently_accepts(fault):
    value = record()
    if fault == 'bad_time': value['started_at'] = '2026-11-04T21:20:00'
    if fault == 'big_unit': value['incident_updates'][0]['body'] = 'x'*4000
    result = response(value, value) if fault == 'duplicate' else response(value)
    if fault == 'oversize': result['body'] = b'x'*(incidents.RESPONSE_LIMIT+1)
    if fault == 'duplicate_json': result['body'] = b'{"incidents":[],"incidents":[]}'
    with pytest.raises((ValueError, ContinuityError)):
        incidents.fetch(dict(endpoint=ENDPOINT, paths=['/incidents/recent/1'], types=['application/json'],
            max_bytes=262144), lambda *a, **kw: result)


def test_task_import_is_pending_idempotent_historical_and_revocation_safe(store):
    db, _ = store
    source = sync.configure('owner', configuration())['source_id']
    def run(key, payload):
        job = sync.enqueue('owner', source, dict(reason='Read bounded official data', idempotency_key=key))['job_id']
        return sync.run('owner', job, get=lambda *a, **kw: payload)
    first = run('sync1', response(record(), record('other1')))
    assert first['status'] == 'SUCCEEDED' and len(first['imports']) == 2
    candidate = candidates.read_candidate('owner', first['imports'][0]['candidate_id'])
    assert candidate['status'] == 'PENDING'
    assert candidate['payload']['intake']['decision_status'] == 'HISTORICAL'
    assert candidate['payload']['intake']['responsible_principal_id'] is None
    assert db.execute('SELECT COUNT(*) FROM ENTITIES').fetchone()[0] == 0
    reference = SourceRef.model_validate(candidate['payload']['sources'][0])
    second = run('sync2', response(record(), record('other2')))
    assert {i['candidate_id'] for i in first['imports']} == {i['candidate_id'] for i in second['imports']}
    assert db.execute('SELECT COUNT(*) FROM CX_AGENT_SOURCE_REVISIONS').fetchone()[0] == 2
    changed = record(); changed['incident_updates'][0]['body'] += ' Corrected detail.'
    run('sync3', response(changed))
    assert db.execute('SELECT COUNT(*) FROM CX_AGENT_SOURCE_REVISIONS').fetchone()[0] == 4
    # Resolution still reads the original exact revision and truthful observation.
    from lib import connection
    original = connection.execute_transaction_callback(lambda tx: sync.resolve_source(tx, 'owner', 'domain', reference))
    assert original['provenance']['method'] == 'TASK_HTTP_STATUSPAGE'
    checkpoint = db.execute('SELECT CHECKPOINT_DIGEST FROM CX_AGENT_SOURCES').fetchone()[0]
    with pytest.raises(ValueError): run('bad', dict(status=200, content_type='application/json', body=b'broken'))
    assert db.execute('SELECT CHECKPOINT_DIGEST FROM CX_AGENT_SOURCES').fetchone()[0] == checkpoint
    sync.change_state('owner', source, dict(expected_version=1, status='REVOKED', reason='Source revoked', idempotency_key='revoke'))
    with pytest.raises(PermissionError):
        connection.execute_transaction_callback(lambda tx: sync.resolve_source(tx, 'owner', 'domain', reference))
