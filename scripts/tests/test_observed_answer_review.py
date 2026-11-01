"""Offline relational review contracts. No fixture is real Human acceptance."""
from copy import deepcopy
from dataclasses import replace
import json
import socket
import sqlite3

import pytest

from lib import observed_answer_review as review, model_credentials


def packet():
    return dict(schema=review.PACKET_SCHEMA, version='5.0.2', phase='candidate', target='unified-community-pg',
        track='fresh', generation='original', policy_sha256='a'*64,
        package_manifests={'unified-community': 'b'*64}, report=dict(path='private/report.json', sha256='c'*64),
        rows=[dict(key='case-portal-1', case_id='case', entry='PORTAL', repetition=1, binding_digest='d'*64,
            case_sha256='e'*64, original_output=dict(path='private/outputs/case.json', sha256='f'*64),
            original_actor_id='owner', security_domain_id='domain', agent_id='agent', profile_id='profile',
            profile_version=3, query='What did the original source say?',
            observed=dict(status='COMPLETED', answer='The original captured answer.', citations=[], context_sources=[]))])


@pytest.fixture
def database(monkeypatch):
    monkeypatch.setattr(socket, 'create_connection', lambda *a, **k: pytest.fail('Offline review cannot connect'))
    db = sqlite3.connect(':memory:')
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    db.executescript('''
        CREATE TABLE CX_PRINCIPALS(PRINCIPAL_ID TEXT PRIMARY KEY,PRINCIPAL_TYPE TEXT,STATUS TEXT);
        INSERT INTO CX_PRINCIPALS VALUES('owner','HUMAN','ACTIVE'),('reviewer','HUMAN','ACTIVE'),
            ('other','HUMAN','ACTIVE'),('agent','AGENT','ACTIVE');
        CREATE TABLE CX_WEB_SESSIONS(SESSION_DIGEST TEXT PRIMARY KEY);
        INSERT INTO CX_WEB_SESSIONS VALUES('aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa');
        CREATE TABLE CX_SECURITY_DOMAINS(SECURITY_DOMAIN_ID TEXT PRIMARY KEY,STATUS TEXT);
        INSERT INTO CX_SECURITY_DOMAINS VALUES('domain','ACTIVE');
        CREATE TABLE CX_DOMAIN_MEMBERS(SECURITY_DOMAIN_ID TEXT,PRINCIPAL_ID TEXT,STATUS TEXT,MEMBERSHIP_TIER TEXT,VALID_UNTIL TIMESTAMP);
        INSERT INTO CX_DOMAIN_MEMBERS VALUES('domain','owner','ACTIVE','OWNER',NULL),
            ('domain','reviewer','ACTIVE','ADMIN',NULL),('domain','other','ACTIVE','ADMIN',NULL);
        CREATE TABLE CX_NATIVE_AGENTS(AGENT_ID TEXT PRIMARY KEY,LLM_PROFILE_ID TEXT,STATUS TEXT);
        INSERT INTO CX_NATIVE_AGENTS VALUES('agent','profile','ACTIVE');
        CREATE TABLE CX_LLM_PROVIDER_PROFILES(PROFILE_ID TEXT PRIMARY KEY,VERSION INTEGER,STATUS TEXT,HEALTH_STATE TEXT);
        INSERT INTO CX_LLM_PROVIDER_PROFILES VALUES('profile',3,'ACTIVE','HEALTHY');
        CREATE TABLE CX_SECURITY_EVENTS(EVENT_ID TEXT PRIMARY KEY,PRINCIPAL_ID TEXT,ACTION_NAME TEXT,
            RESOURCE_TYPE TEXT,RESOURCE_ID TEXT,OUTCOME TEXT,REASON TEXT,CREATED_AT TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
    ''')
    for statement in review.schema_statements('pg'):
        db.execute(statement)
    for table in review.TABLES:
        for action in ('UPDATE', 'DELETE'):
            db.execute(f"CREATE TRIGGER deny_{table}_{action} BEFORE {action} ON {table} BEGIN SELECT RAISE(ABORT,'immutable'); END")
    class Tx:
        def execute(self, sql, params):
            return db.execute(sql.replace(' FOR UPDATE', ''), params).rowcount
        def query(self, sql, params):
            return [{key.lower(): value[key] for key in value.keys()} for value in db.execute(sql.replace(' FOR UPDATE', ''), params)]
        def query_one(self, sql, params):
            values = self.query(sql, params)
            return values[0] if values else None
    def transaction(callback):
        try:
            value = callback(Tx()); db.commit(); return value
        except BaseException:
            db.rollback(); raise
    monkeypatch.setattr(review.connection, 'execute_transaction_callback', transaction)
    monkeypatch.setattr(review.identity_api, 'effective_access', lambda *a, **k: {'decision': 'ALLOW'})
    monkeypatch.setattr(review.identity_api, '_agent_visible_to', lambda *a: True)
    monkeypatch.setattr(review.knowledge_grounding, 'require_reader', lambda *a, **k: None)
    monkeypatch.setattr(review, 'encrypt_section', lambda value: 'encrypted:' + json.dumps(value))
    monkeypatch.setattr(review, 'decrypt_section', lambda value: json.loads(value.removeprefix('encrypted:')))
    def credential(actor, **kwargs):
        return model_credentials.CredentialBinding(actor, 'WEB', 'a'*64, auth_method='PASSWORD:DASHBOARD',
            permission_version=1, mfa_level='NONE', node_id='test', created_at='2026-10-29T00:00:00+00:00')
    monkeypatch.setattr(model_credentials, 'capture', credential)
    monkeypatch.setattr(model_credentials, 'recheck', lambda tx, value: value.credential_digest)
    def audit(tx, actor, action, kind, resource, outcome, reason):
        tx.execute('INSERT INTO CX_SECURITY_EVENTS(EVENT_ID,PRINCIPAL_ID,ACTION_NAME,RESOURCE_TYPE,RESOURCE_ID,OUTCOME,REASON) VALUES(:id,:actor,:action,:kind,:resource,:outcome,:reason)',
            dict(id=review.identifier('SE'), actor=actor, action=action, kind=kind, resource=resource, outcome=outcome, reason=reason))
    monkeypatch.setattr(review.identity_api, '_audit_tx', audit)
    db.commit()
    yield db, transaction
    db.close()


def registered():
    return review.register('owner', dict(packet=packet(), reason='Import original synthetic offline observation'))['set_id']


def decision(value=None, **changes):
    item = dict(output_digest=review.digest(packet()['rows'][0]), factual_correct=True,
        citations_supported=True, reason='Compared the exact original answer and authorized evidence.')
    item.update(value or {}); item.update(changes); return item


def test_observation_registration_and_exact_independent_review_are_native_facts(database):
    db, transaction = database
    set_id = registered()
    assert review.register('owner', dict(packet=packet(), reason='Same original bytes'))['replayed'] is True
    before = review.read_set('reviewer', set_id)
    assert before['reviews'] == []
    assert before['packet']['rows'][0]['observed']['answer'] == packet()['rows'][0]['observed']['answer']
    actual = review.review('reviewer', set_id, 'case-portal-1', decision())
    exported = transaction(lambda tx: review.export_native(tx, set_id))
    assert actual['generation_requests'] == exported['generation_requests'] == 0
    assert exported['reviews'][0]['review_id'] == actual['review_id']
    assert exported['reviews'][0]['output_digest'] == review.digest(packet()['rows'][0])
    assert exported['audits'][0]['resource_id'] == actual['review_id']
    assert exported['audits'][0]['principal_id'] == 'reviewer'
    assert exported['reviewer_principals'] == {'reviewer': {'principal_type': 'HUMAN'}}
    assert exported['set']['session_digest'] == 'a'*64
    assert db.execute('SELECT COUNT(*) FROM CX_OBS_ANSWER_ROWS').fetchone()[0] == 1


@pytest.mark.parametrize('actor', ['owner', 'agent'])
def test_self_or_agent_review_is_denied(database, actor):
    set_id = registered()
    with pytest.raises(PermissionError):
        review.review(actor, set_id, 'case-portal-1', decision())
    assert database[0].execute('SELECT COUNT(*) FROM CX_OBS_ANSWER_REVIEWS').fetchone()[0] == 0


def test_registering_actor_also_cannot_review_someone_elses_original_output(database):
    value = packet(); value['rows'][0]['original_actor_id'] = 'other'
    set_id = review.register('owner', dict(packet=value, reason='Different original responsible Human'))['set_id']
    with pytest.raises(PermissionError, match='independent'):
        review.review('owner', set_id, 'case-portal-1', decision(output_digest=review.digest(value['rows'][0])))


@pytest.mark.parametrize('change', ['stale-output', 'agent-inactive', 'profile-stale', 'domain-revoked', 'membership-revoked', 'human-inactive'])
def test_current_resource_and_original_digest_checks_remain_required(database, change):
    db, _ = database; set_id = registered(); request = decision()
    if change == 'stale-output': request['output_digest'] = '0'*64
    elif change == 'agent-inactive': db.execute("UPDATE CX_NATIVE_AGENTS SET STATUS='REVOKED'")
    elif change == 'profile-stale': db.execute('UPDATE CX_LLM_PROVIDER_PROFILES SET VERSION=4')
    elif change == 'domain-revoked': db.execute("UPDATE CX_SECURITY_DOMAINS SET STATUS='REVOKED'")
    elif change == 'membership-revoked': db.execute("UPDATE CX_DOMAIN_MEMBERS SET STATUS='REVOKED' WHERE PRINCIPAL_ID='reviewer'")
    else: db.execute("UPDATE CX_PRINCIPALS SET STATUS='DISABLED' WHERE PRINCIPAL_ID='reviewer'")
    db.commit()
    with pytest.raises((PermissionError, review.ContinuityConflict)):
        review.review('reviewer', set_id, 'case-portal-1', request)
    assert db.execute('SELECT COUNT(*) FROM CX_OBS_ANSWER_REVIEWS').fetchone()[0] == 0


@pytest.mark.parametrize('value', [None, 'AGENT', 'PORTAL'])
def test_original_dashboard_web_credential_is_required(database, monkeypatch, value):
    original = model_credentials.capture('owner')
    replacement = None if value is None else replace(original, kind='AGENT') if value == 'AGENT' else replace(original, auth_method='PASSWORD:PORTAL')
    monkeypatch.setattr(model_credentials, 'capture', lambda *a, **k: replacement)
    with pytest.raises(PermissionError): registered()
    assert database[0].execute('SELECT COUNT(*) FROM CX_OBS_ANSWER_SETS').fetchone()[0] == 0


@pytest.mark.parametrize('operation', ['register', 'review'])
def test_required_audit_failure_rolls_back_the_whole_mutation(database, monkeypatch, operation):
    db, _ = database
    set_id = registered() if operation == 'review' else None
    monkeypatch.setattr(review.identity_api, '_audit_tx', lambda *a: (_ for _ in ()).throw(RuntimeError('Required audit failed')))
    with pytest.raises(RuntimeError, match='audit'):
        registered() if operation == 'register' else review.review('reviewer', set_id, 'case-portal-1', decision())
    table = 'CX_OBS_ANSWER_SETS' if operation == 'register' else 'CX_OBS_ANSWER_REVIEWS'
    assert db.execute('SELECT COUNT(*) FROM ' + table).fetchone()[0] == 0


def test_revoked_credential_before_commit_rolls_back_review(database, monkeypatch):
    set_id = registered()
    monkeypatch.setattr(model_credentials, 'recheck', lambda *a: (_ for _ in ()).throw(PermissionError('Revoked original Session')))
    with pytest.raises(PermissionError): review.review('reviewer', set_id, 'case-portal-1', decision())
    assert database[0].execute('SELECT COUNT(*) FROM CX_OBS_ANSWER_REVIEWS').fetchone()[0] == 0


def test_negative_decision_is_preserved_and_cannot_be_replaced(database):
    db, _ = database; set_id = registered()
    review.review('reviewer', set_id, 'case-portal-1', decision(factual_correct=False))
    assert db.execute('SELECT FACTUAL_CORRECT FROM CX_OBS_ANSWER_REVIEWS').fetchone()[0] == 'N'
    with pytest.raises(sqlite3.IntegrityError): review.review('reviewer', set_id, 'case-portal-1', decision())
    for sql in ('UPDATE CX_OBS_ANSWER_REVIEWS SET FACTUAL_CORRECT=\'Y\'', 'DELETE FROM CX_OBS_ANSWER_REVIEWS'):
        with pytest.raises(sqlite3.IntegrityError, match='immutable'): db.execute(sql)


@pytest.mark.parametrize('field,value', [('factual_correct', 'true'), ('citations_supported', 1), ('reason', '  ')])
def test_asserted_truth_and_empty_reasons_are_not_human_decisions(database, field, value):
    set_id = registered()
    with pytest.raises(ValueError): review.review('reviewer', set_id, 'case-portal-1', decision(**{field: value}))


def test_disclosed_sources_are_reauthorized_before_read_and_decision(database, monkeypatch):
    value = packet(); value['rows'][0]['observed']['citations'] = [dict(entity_id='knowledge', digest='1'*64)]
    checked = []
    monkeypatch.setattr(review.knowledge_grounding, 'citation', lambda *a, **k: checked.append(a))
    set_id = review.register('owner', dict(packet=value, reason='Exact disclosed knowledge reference'))['set_id']
    assert checked[-1] == ('owner', 'agent', 'knowledge', '1'*64)
    monkeypatch.setattr(review.knowledge_grounding, 'citation', lambda *a, **k: (_ for _ in ()).throw(PermissionError('Source revoked')))
    with pytest.raises(PermissionError): review.read_set('reviewer', set_id)
    with pytest.raises(PermissionError): review.review('reviewer', set_id, 'case-portal-1', decision(output_digest=review.digest(value['rows'][0])))


def test_duplicate_rows_and_noncompleted_observations_are_rejected(database):
    for mutate in (lambda p: p['rows'].append(deepcopy(p['rows'][0])),
                   lambda p: p['rows'][0]['observed'].update(status='UNOBSERVED')):
        value = packet(); mutate(value)
        with pytest.raises(ValueError): review.register('owner', dict(packet=value, reason='Invalid packet rejected'))


def test_public_export_rechecks_current_authority_in_one_transaction(database, monkeypatch):
    set_id = registered(); _, transaction = database; calls = []
    def counted(callback):
        calls.append('transaction'); return transaction(callback)
    monkeypatch.setattr(review.connection, 'execute_transaction_callback', counted)
    value = review.export('reviewer', set_id)
    assert value['set']['set_id'] == set_id and calls == ['transaction']


def test_private_native_export_preserves_review_facts_after_public_scope_is_revoked(database):
    db, transaction = database; set_id = registered()
    review.review('reviewer', set_id, 'case-portal-1', decision())
    original = transaction(lambda tx: review.export_native(tx, set_id))
    db.execute("UPDATE CX_SECURITY_DOMAINS SET STATUS='REVOKED'"); db.commit()
    with pytest.raises(PermissionError): review.export('reviewer', set_id)
    assert transaction(lambda tx: review.export_native(tx, set_id)) == original


def test_disclosed_native_context_source_uses_current_exact_source_authority(database, monkeypatch):
    value = packet(); source = dict(family='MEMORY', entity_id='family', revision_id='version', content_digest='1'*64)
    value['rows'][0]['observed']['context_sources'] = [source]
    seen = []
    monkeypatch.setattr(review.continuity_sources, 'resolve', lambda tx, actor, domain, ref: seen.append((actor, domain, ref)))
    set_id = review.register('owner', dict(packet=value, reason='Exact original disclosed native source'))['set_id']
    assert seen[-1][0:2] == ('owner', 'domain') and seen[-1][2].model_dump(mode='json') == source
    monkeypatch.setattr(review.continuity_sources, 'resolve', lambda *a: (_ for _ in ()).throw(PermissionError('Native source revoked')))
    with pytest.raises(PermissionError): review.export('reviewer', set_id)


def test_reason_whitespace_is_normalized_once_for_immutable_review_and_atomic_audit(database):
    set_id = registered()
    review.review('reviewer', set_id, 'case-portal-1', decision(reason='  Compared the exact original evidence.  '))
    value = database[1](lambda tx: review.export_native(tx, set_id))
    assert value['reviews'][0]['reason'] == value['audits'][0]['reason'] == 'Compared the exact original evidence.'


def test_read_set_rechecks_original_session_after_rows_are_loaded(database, monkeypatch):
    set_id = registered(); seen = []; decrypt = review.decrypt_section
    monkeypatch.setattr(review, 'decrypt_section', lambda value: seen.append('decrypt') or decrypt(value))
    def expired(tx, credential):
        assert len(seen) >= 2
        raise PermissionError('The original Session expired while reading')
    monkeypatch.setattr(model_credentials, 'recheck', expired)
    with pytest.raises(PermissionError, match='expired'):
        review.read_set('reviewer', set_id)


def test_export_rechecks_session_after_the_last_native_review_query(database, monkeypatch):
    set_id = registered(); seen = []; original = review.export_native
    def queried(tx, actual):
        result = original(tx, actual); seen.append('all-native-queries'); return result
    monkeypatch.setattr(review, 'export_native', queried)
    def expired(tx, credential):
        assert seen == ['all-native-queries']
        raise PermissionError('The original Session expired during the final export queries')
    monkeypatch.setattr(model_credentials, 'recheck', expired)
    with pytest.raises(PermissionError, match='expired'):
        review.export('reviewer', set_id)


def test_existing_packet_replay_rechecks_original_session_after_authorization(database, monkeypatch):
    registered()
    monkeypatch.setattr(model_credentials, 'recheck', lambda *a: (_ for _ in ()).throw(PermissionError('Original Session expired on replay')))
    with pytest.raises(PermissionError, match='replay'):
        registered()


def test_read_set_expiry_at_the_final_reviews_query_denies_the_response(database, monkeypatch):
    set_id = registered(); transaction = database[1]; finished = []
    class ObserveFinalQuery:
        def __init__(self, tx): self.tx = tx
        def __getattr__(self, key): return getattr(self.tx, key)
        def query(self, sql, params):
            rows = self.tx.query(sql, params)
            if 'FROM CX_OBS_ANSWER_REVIEWS' in sql: finished.append('last-query')
            return rows
    monkeypatch.setattr(review.connection, 'execute_transaction_callback', lambda callback: transaction(lambda tx: callback(ObserveFinalQuery(tx))))
    def expired(tx, credential):
        assert finished == ['last-query']
        raise PermissionError('Session expired in the final reviews query')
    monkeypatch.setattr(model_credentials, 'recheck', expired)
    with pytest.raises(PermissionError, match='expired'):
        review.read_set('reviewer', set_id)
