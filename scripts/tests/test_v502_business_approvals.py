"""Relational regressions with real Channel guards; no native/Provider claims."""
import json

import pytest

from lib import identity_api, connection, governed_approval as approvals
from lib import governed_model_turns as turns, continuity_bindings as bindings
from lib import continuity_native_sources, execution_control as worker
from lib.continuity_state import ContinuityConflict
from .test_v502_governed_model_turns import (governed, runtime, candidate_db, fixture, database,
    TRANSPORT, evidence, model, execute_tool, http)

REAL_MEMBERSHIP = identity_api._assert_channel_member
REAL_CREATE_ACTION = identity_api.create_action_card


@pytest.fixture
def ordinary(governed, monkeypatch):
    db,_=governed
    db.executescript('''
        ALTER TABLE CX_DOMAIN_MEMBERS ADD COLUMN MEMBERSHIP_ID TEXT;
        UPDATE CX_DOMAIN_MEMBERS SET MEMBERSHIP_ID=PRINCIPAL_ID;
        UPDATE CX_DOMAIN_MEMBERS SET MEMBERSHIP_TIER='MEMBER' WHERE PRINCIPAL_ID='reader';
        INSERT INTO CX_DOMAIN_MEMBERS VALUES('domain','outsider','ACTIVE','MEMBER',NULL,'outsider');
        CREATE TABLE CX_CHANNELS(CHANNEL_ID TEXT PRIMARY KEY,SECURITY_DOMAIN_ID TEXT,CLASSIFICATION TEXT,
            CHANNEL_TYPE TEXT,STATUS TEXT);
        CREATE TABLE CX_CHANNEL_MEMBERS(MEMBER_ID TEXT PRIMARY KEY,CHANNEL_ID TEXT,PRINCIPAL_ID TEXT,
            MEMBER_ROLE TEXT,STATUS TEXT,VALID_UNTIL TIMESTAMP);
        INSERT INTO CX_CHANNELS VALUES('business','domain','INTERNAL','TEAM','ACTIVE'),
            ('second','domain','INTERNAL','TEAM','ACTIVE'),
            ('CH_PLATFORM_ADMINISTRATION','domain','RESTRICTED','SYSTEM_PROTECTED','ACTIVE');
        INSERT INTO CX_CHANNEL_MEMBERS VALUES('b-agent','business','owner','MEMBER','ACTIVE',NULL),
            ('b-human','business','outsider','REVIEWER','ACTIVE',NULL),
            ('s-agent','second','owner','MEMBER','ACTIVE',NULL),
            ('s-human','second','outsider','REVIEWER','ACTIVE',NULL),
            ('p-human','CH_PLATFORM_ADMINISTRATION','reader','OPERATOR','ACTIVE',NULL),
            ('p-reviewer','CH_PLATFORM_ADMINISTRATION','outsider','REVIEWER','ACTIVE',NULL);
        ALTER TABLE CX_ACTION_CARDS ADD COLUMN VERSION INTEGER DEFAULT 1;
        ALTER TABLE CX_ACTION_CARDS ADD COLUMN REASON TEXT;
        ALTER TABLE CX_ACTION_CARDS ADD COLUMN CREATED_AT TEXT DEFAULT '2026-10-28';
        ALTER TABLE CX_ACTION_CARDS ADD COLUMN DECIDED_AT TEXT;
        ALTER TABLE TASK_PLANS ADD COLUMN RESULT_SUMMARY TEXT;
        ALTER TABLE CX_AGENT_RELATIONSHIPS ADD COLUMN RELATIONSHIP_ID TEXT;
        INSERT INTO CX_AGENT_RELATIONSHIPS VALUES('owner','reader','PRIMARY_OWNER','ACTIVE',NULL,'relationship');
    ''')
    db.commit()
    def query(statement, params=None):
        return [{key.lower():row[key] for key in row.keys()}
            for row in db.execute(statement.replace(' FOR UPDATE',''),params or {})]
    def one(statement, params=None):
        rows=query(statement,params)
        return rows[0] if rows else None
    def execute(statement, params=None):
        count=db.execute(statement.replace(' FOR UPDATE',''),params or {}).rowcount
        db.commit()
        return count
    monkeypatch.setattr(connection,'execute_query',query)
    monkeypatch.setattr(connection,'execute_query_one',one)
    monkeypatch.setattr(connection,'execute',execute)
    monkeypatch.setattr(identity_api,'_assert_channel_member',REAL_MEMBERSHIP)
    monkeypatch.setattr(identity_api,'create_action_card',REAL_CREATE_ACTION)
    monkeypatch.setattr(identity_api,'_limit_clause',lambda name='limit':'LIMIT :'+name)
    # The historical relational harness supplies synthetic action permissions;
    # actual production Channel, Domain, principal and expiry checks run below.
    denied=set()
    def effective(actor,action,**kwargs):
        return dict(decision='DENY' if action=='domains.manage' or (actor,action) in denied else 'ALLOW')
    monkeypatch.setattr(identity_api,'effective_access',effective)
    source=continuity_native_sources.capture('owner',dict(family='TASK',entity_id='501',
        security_domain_id='domain',reason='Exact synthetic Task fixture',idempotency_key='capture'))['source']
    registration=dict(security_domain_id='domain',tool_id='read-tool',source=source,resource_parameter='source_id',
        reason='Independently registered read fixture',idempotency_key='registration')
    assert one("SELECT * FROM CX_DOMAIN_MEMBERS WHERE PRINCIPAL_ID='reader'")['status']=='ACTIVE'
    action=turns.request_registration('reader',registration)
    assert identity_api.decide_action_card('outsider',action['action_id'],'APPROVE','Synthetic independent registration decision')
    registered=turns.register_read_tool('reader',registration,action['action_id'])
    contract=turns.read_registration('owner',registered['registration_id'])
    evidence(db,'exact-business',contract['input_schema'],tool_name=contract['tool_name'])
    with bindings.authenticated_transport(TRANSPORT):
        turn=turns.create_turn('owner',dict(registration_id=registered['registration_id'],task_id='501',
            profile_id='model',profile_version=1,probe_id='exact-business',question='Read the approved synthetic source.',
            reason='Synthetic business Agent turn',idempotency_key='business-turn'))['turn_id']
    registered_row=connection.execute_query_one('SELECT * FROM CX_MODEL_READ_TOOLS WHERE REGISTRATION_ID=:id',
        {'id':registered['registration_id']})
    observed=model(monkeypatch,registered_row)
    with bindings.authenticated_transport(TRANSPORT):
        assert turns.run_once('owner',turn,'worker')['status']=='WAITING_APPROVAL'
    return db,turn,observed,denied


def approve_business(state):
    db,turn,_,_=state
    with bindings.authenticated_transport(TRANSPORT):
        action=turns.request_tool_approval('owner',turn,channel_id='business')
        assert identity_api.decide_action_card('outsider',action['action_id'],'APPROVE','Synthetic independent tool decision')
        turns.admit_approved_tool('owner',turn)
    return action


def test_ordinary_agent_can_complete_a_turn_without_protected_channel_membership(ordinary,monkeypatch):
    db,turn,observed,_=ordinary
    action=approve_business(ordinary)
    assert db.execute('SELECT CHANNEL_ID FROM CX_ACTION_CARDS WHERE ACTION_ID=?',(action['action_id'],)).fetchone()[0]=='business'
    external=execute_tool(db,monkeypatch)
    assert worker.run_worker_once('worker')['status']=='SUCCEEDED'
    with bindings.authenticated_transport(TRANSPORT):
        assert turns.run_once('owner',turn,'worker')['status']=='SUCCEEDED'
    assert len(external)==1 and len(observed)==2


def test_omitted_channel_preserves_protected_default_for_unbound_turn(ordinary):
    _,turn,_,_=ordinary
    with bindings.authenticated_transport(TRANSPORT),pytest.raises(PermissionError):
        turns.request_tool_approval('owner',turn)


@pytest.mark.parametrize('mutation', ['cross_domain','inactive','agent_member','agent_domain'])
def test_invalid_business_channel_denies_approval_creation(ordinary,mutation):
    db,turn,_,_=ordinary
    if mutation=='cross_domain':db.execute("UPDATE CX_CHANNELS SET SECURITY_DOMAIN_ID='other' WHERE CHANNEL_ID='business'")
    if mutation=='inactive':db.execute("UPDATE CX_CHANNELS SET STATUS='ARCHIVED' WHERE CHANNEL_ID='business'")
    if mutation=='agent_member':db.execute("UPDATE CX_CHANNEL_MEMBERS SET STATUS='REVOKED' WHERE MEMBER_ID='b-agent'")
    if mutation=='agent_domain':db.execute("UPDATE CX_DOMAIN_MEMBERS SET STATUS='REVOKED' WHERE PRINCIPAL_ID='owner'")
    db.commit()
    with bindings.authenticated_transport(TRANSPORT),pytest.raises(PermissionError):
        turns.request_tool_approval('owner',turn,channel_id='business')
    assert db.execute("SELECT COUNT(*) FROM CX_ACTION_CARDS WHERE ACTION_TYPE='PLATFORM_MODEL_READ_TOOL_CALL'").fetchone()[0]==0


def test_bound_action_channel_is_frozen_and_repeated_request_keeps_exact_card(ordinary):
    db,turn,_,_=ordinary
    with bindings.authenticated_transport(TRANSPORT):
        first=turns.request_tool_approval('owner',turn,channel_id='business')
        assert turns.request_tool_approval('owner',turn)['action_id']==first['action_id']
        with pytest.raises(ContinuityConflict):turns.request_tool_approval('owner',turn,channel_id='second')
    assert db.execute("SELECT COUNT(*) FROM CX_ACTION_CARDS WHERE ACTION_TYPE='PLATFORM_MODEL_READ_TOOL_CALL'").fetchone()[0]==1


@pytest.mark.parametrize('mutation', ['agent_channel','human_channel','agent_domain','human_domain',
    'channel_domain','channel_status','domain_status','agent_write','human_decide','self_approval'])
def test_worker_rechecks_original_business_channel_and_both_participants(ordinary,monkeypatch,mutation):
    db,_,observed,denied=ordinary
    action=approve_business(ordinary)
    if mutation=='agent_channel':db.execute("UPDATE CX_CHANNEL_MEMBERS SET STATUS='REVOKED' WHERE MEMBER_ID='b-agent'")
    if mutation=='human_channel':db.execute("UPDATE CX_CHANNEL_MEMBERS SET STATUS='REVOKED' WHERE MEMBER_ID='b-human'")
    if mutation=='agent_domain':db.execute("UPDATE CX_DOMAIN_MEMBERS SET STATUS='REVOKED' WHERE PRINCIPAL_ID='owner'")
    if mutation=='human_domain':db.execute("UPDATE CX_DOMAIN_MEMBERS SET STATUS='REVOKED' WHERE PRINCIPAL_ID='outsider'")
    if mutation=='channel_domain':db.execute("UPDATE CX_CHANNELS SET SECURITY_DOMAIN_ID='different' WHERE CHANNEL_ID='business'")
    if mutation=='channel_status':db.execute("UPDATE CX_CHANNELS SET STATUS='ARCHIVED' WHERE CHANNEL_ID='business'")
    if mutation=='domain_status':db.execute("UPDATE CX_SECURITY_DOMAINS SET STATUS='REVOKED'")
    if mutation=='agent_write':denied.add(('owner','channels.write'))
    if mutation=='human_decide':denied.add(('outsider','channels.actions.decide'))
    if mutation=='self_approval':db.execute("UPDATE CX_ACTION_CARDS SET DECIDED_BY='owner' WHERE ACTION_ID=?",(action['action_id'],))
    db.commit()
    external=execute_tool(db,monkeypatch)
    assert worker.run_worker_once('worker')['status']=='FAILED'
    assert external==[] and len(observed)==1


@pytest.mark.parametrize('mutation',['channel','domain','member','wrong_action','wrong_payload'])
def test_create_bind_race_cannot_bind_stale_or_foreign_action(ordinary,monkeypatch,mutation):
    db,turn,_,_=ordinary
    def create(*args,**kwargs):
        action=REAL_CREATE_ACTION(*args,**kwargs)
        if mutation=='channel':db.execute("UPDATE CX_CHANNELS SET STATUS='ARCHIVED' WHERE CHANNEL_ID='business'")
        if mutation=='domain':db.execute("UPDATE CX_CHANNELS SET SECURITY_DOMAIN_ID='other' WHERE CHANNEL_ID='business'")
        if mutation=='member':db.execute("UPDATE CX_CHANNEL_MEMBERS SET STATUS='REVOKED' WHERE MEMBER_ID='b-agent'")
        if mutation=='wrong_action':db.execute("UPDATE CX_ACTION_CARDS SET ACTION_TYPE='PLATFORM_OTHER' WHERE ACTION_ID=?",(action['action_id'],))
        if mutation=='wrong_payload':db.execute("UPDATE CX_ACTION_CARDS SET PAYLOAD_JSON='{}' WHERE ACTION_ID=?",(action['action_id'],))
        db.commit()
        return action
    monkeypatch.setattr(identity_api,'create_action_card',create)
    with bindings.authenticated_transport(TRANSPORT),pytest.raises((PermissionError,ContinuityConflict)):
        turns.request_tool_approval('owner',turn,channel_id='business')
    assert db.execute('SELECT ACTION_ID FROM CX_MODEL_TOOL_CALLS WHERE TURN_ID=?',(turn,)).fetchone()[0] is None


def test_http_approval_channel_body_is_closed_and_uses_original_transport(http,ordinary):
    client,headers=http
    _,turn,_,_=ordinary
    path='/api/extensions/model-tool-turns/'+turn+'/approval-requests'
    for injected in ({'actor':'outsider'},{'security_domain_id':'other'},{'approved':True},{'channel_id':''}):
        assert client.post(path,json={'channel_id':'business',**injected},headers=headers).status_code==422
    response=client.post(path,json={'channel_id':'business'},headers=headers)
    assert response.status_code==200 and response.json()['channel_id']=='business'


def test_other_platform_actions_cannot_select_a_business_approval_channel(ordinary):
    db,_,_,_=ordinary
    action=connection.execute_query_one("SELECT ACTION_ID FROM CX_ACTION_CARDS WHERE ACTION_TYPE='PLATFORM_MODEL_READ_TOOL_REGISTER'",{})
    with pytest.raises(approvals.ApprovalRequired):
        connection.execute_transaction_callback(lambda tx:approvals.require_tx(tx,action['action_id'],
            'PLATFORM_MODEL_READ_TOOL_REGISTER',{},'tools.write',expected_channel='business'))
