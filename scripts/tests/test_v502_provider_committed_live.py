"""Opt-in exact-package Provider workflows with retained unreviewed outputs.

Real schema probes, structured candidate generation and ordinary business-Agent
tool transport are separate observations. Synthetic public echo output verifies
transport and exact invocation identity; it is not business-source retrieval.
"""
from contextlib import contextmanager
from datetime import date, datetime
from decimal import Decimal
import json
import os
from pathlib import Path
import secrets
from types import SimpleNamespace

import pytest

from lib import (connection, identity_api, agent_gateway_api, security_domain_api as domains,
    continuity_bindings as bindings, continuity_native_sources as sources, continuity_candidates as candidates,
    continuity_retrospectives as retros, model_output_contracts as contracts, model_credentials,
    governed_model_turns as turns, portal_grounding, task_plan_api, tool_registry, model_capability_api)
from lib import provider_capability_probes as probes
from lib.agent_extension_contracts import digest
from .test_v502_business_committed_live import business, one

pytestmark=pytest.mark.skipif(os.environ.get('CX_V502_PROVIDER_BUSINESS_LIVE')!='1',
    reason='explicit exact classified real-Provider acceptance required')


def observation_json(value):
    if isinstance(value,(date,datetime)):return value.isoformat()
    if isinstance(value,Decimal):return int(value) if value==int(value) else float(value)
    raise TypeError('Unsupported Provider observation type: '+type(value).__name__)


def output(state, name, value):
    from .v502_provider_guard import private_json
    state.guard.require_complete()
    requests=state.guard.records[state.observation_start:]
    assert requests and all(item['status']=='COMPLETE_RESPONSE' for item in requests)
    assert all(item['total_ms']<=state.maximum_generation_seconds*1000 for item in requests), 'Frozen generation threshold exceeded'
    value=dict(value,human_review='AWAITING_INDEPENDENT_AUTHORIZED_HUMAN_REVIEW',
        human_review_manufactured=False,fixture_domain=state.domain,fixture_agent=state.agent,
        case_name=state.case_name,profile_id=state.profile,profile_version=state.profile_version,
        profile_parameter_sha256=state.parameter_digest,
        acceptance_policy_sha256=os.environ['CX_V502_ACCEPTANCE_POLICY_SHA256'],
        http_request_ids=[item['request_id'] for item in requests])
    private_json(Path(os.environ['CX_V502_PROVIDER_OUTPUTS'])/(state.key+'_'+name+'.json'),
        json.loads(json.dumps(value,default=observation_json)))


@contextmanager
def authenticated_human(username, password, expected):
    authenticated=identity_api.authenticate_local(username,password)
    assert authenticated and authenticated['principal_id']==expected
    session=identity_api.create_session(expected,str(authenticated['user_id']),'v502-provider-business',ttl_seconds=900)
    try:
        resolved=identity_api.resolve_session(session['session_id'],touch=False,expected_scope='DASHBOARD')
        assert resolved and resolved['principal_id']==expected
        with model_credentials.server_session(resolved):yield resolved
    finally:
        identity_api.revoke_session(session['session_id'],'Explicit isolated Provider fixture cleanup')


@pytest.fixture
def provider(business, provider_observer, request):
    state=business
    state.guard=provider_observer
    state.case_name=request.node.name
    state.observation_start=len(provider_observer.records)
    state.maximum_generation_seconds=int(os.environ['CX_V502_PROVIDER_MAXIMUM_GENERATION_SECONDS'])
    assert state.maximum_generation_seconds==180
    profile_id=os.environ['CX_V502_PROVIDER_PROFILE_ID']
    profile=one('SELECT PROFILE_ID,VERSION,STATUS,HEALTH_STATE,PROVIDER_URL,MODEL_ID FROM CX_LLM_PROVIDER_PROFILES '
        'WHERE PROFILE_ID=:profile',{'profile':profile_id})
    assert profile and profile['status']=='ACTIVE' and profile['health_state']=='HEALTHY', 'Use an existing genuinely healthy saved Profile'
    assert profile['provider_url']=='http://<DB_HOST>:12345/v1' and profile['model_id']=='qwopus3.6-35b-a3b-coder-mtp'
    state.profile,state.profile_version=profile_id,int(profile['version'])
    assert state.profile_version==int(os.environ['CX_V502_PROVIDER_PROFILE_VERSION'])
    state.parameter_digest=digest(probes.request_parameters(profile_id,state.profile_version))
    assert state.parameter_digest==os.environ['CX_V502_PROVIDER_PROFILE_PARAMETER_SHA256']
    configured=portal_grounding.policy()
    changed=profile_id not in configured['disclosure_profiles']
    if changed:
        portal_grounding.set_policy(state.actor,configured['mode'],configured['allow_model_supplement']=='Y',
            [*configured['disclosure_profiles'],profile_id],configured['version'],state.reason)
    password=Path(os.environ['CX_V502_ADMIN_PASSWORD_FILE']).read_text().strip()
    try:
        with authenticated_human('admin',password,state.actor):yield state
    finally:
        if changed:
            current=portal_grounding.policy()
            portal_grounding.set_policy(state.actor,configured['mode'],configured['allow_model_supplement']=='Y',
                configured['disclosure_profiles'],current['version'],state.reason+' restore disclosure selection')


def new_source(state):
    # Prepare the synthetic Task through the existing server management API.
    # Native Agent SQL is independently restricted; fixture creation must not
    # require a new direct-write grant on the legacy orchestration tables.
    assert connection.get_current_agent_id() is None
    task=task_plan_api.create_plan(state.agent,
        'Approved synthetic training sample: exactly 23 blue cubes. Record only this sample fact; '
        'no production outcome, external validation or publication has occurred.',strategy='V502_PROVIDER_FIXTURE')
    captured=sources.capture(state.actor,dict(family='TASK',entity_id=str(task),security_domain_id=state.domain,
        reason=state.reason,idempotency_key=state.key+'_capture'))
    return str(task),captured['source']


@contextmanager
def authenticated_business_agent(state):
    identity_api.assign_permission_override(state.actor,state.agent,'actions.propose','ALLOW','OWNED',state.reason)
    assert not one("SELECT MEMBER_ID FROM CX_ADMIN_AGENT_MEMBERS WHERE AGENT_ID=:agent AND STATUS='ACTIVE'",{'agent':state.agent})
    instance=agent_gateway_api.create_instance(state.agent,security_domain_id=state.domain)
    try:
        token=agent_gateway_api.issue_access_token(state.agent,instance['instance_id'],
            ['actions.propose','workspaces.write'],ttl_seconds=900)
        context=agent_gateway_api.authenticate_access_token(token['access_token'],state.agent,instance['instance_id'],'workspaces.write')
        assert context and context['agent_id']==state.agent
        with model_credentials.server_session(None),bindings.authenticated_transport(context):yield context
    finally:
        agent_gateway_api.revoke_instance(state.agent,instance['instance_id'],state.reason)


def strict_retrospective(state, family, record_property):
    task,source=new_source(state)
    directory=retros.output_directory(state.actor,state.profile,family)
    probe=contracts.probe_exact(state.actor,state.profile,directory['output_schema'],directory['example'])
    state.guard.require_complete()
    assert probe['schema_digest']==contracts.schema_digest(directory['output_schema'])
    assert probe['parameter_digest']==state.parameter_digest and int(probe['profile_version'])==state.profile_version
    record_property('exact_schema_probe_id',probe['probe_id'])
    request=dict(security_domain_id=state.domain,task_id=task,trigger='FEEDBACK',target_family=family,sources=[source],
        policy_revision=os.environ['CX_V502_ACCEPTANCE_POLICY_SHA256'],profile_id=state.profile,
        profile_version=state.profile_version,token_budget=32768,output_mode='NATIVE_STRICT',
        output_probe_id=probe['probe_id'],reason=state.reason,idempotency_key=state.key+'_'+family)
    with authenticated_business_agent(state) as transport:
        if probe['status']!='VERIFIED':
            before=one('SELECT COUNT(*) AS CNT FROM CX_RETROSPECTIVE_JOBS WHERE CREATED_BY=:actor AND IDEMPOTENCY_KEY=:key',
                {'actor':state.agent,'key':request['idempotency_key']})['cnt']
            with pytest.raises(PermissionError):retros.create_job(state.agent,request)
            after=one('SELECT COUNT(*) AS CNT FROM CX_RETROSPECTIVE_JOBS WHERE CREATED_BY=:actor AND IDEMPOTENCY_KEY=:key',
                {'actor':state.agent,'key':request['idempotency_key']})['cnt']
            output(state,family,dict(kind='EXACT_SCHEMA_CAPABILITY',target_family=family,probe=probe,
                business_dispatch_denied=True,business_output_completed=False,source=source))
            assert before==after==0
            assert probe['status']=='UNSUPPORTED', 'A failed probe is retained as failure; it does not prove an unsupported capability'
            record_property('native_strict_business_output','UNAVAILABLE_EXACT_SCHEMA_DENIAL_VERIFIED')
            return
        created=retros.create_job(state.agent,request)
        credential=one('SELECT CREDENTIAL_KIND,INSTANCE_ID,TOKEN_DIGEST,FENCING_TOKEN,SESSION_DIGEST '
            'FROM CX_RETROSPECTIVE_OUTPUTS WHERE JOB_ID=:job',{'job':created['job_id']})
        assert credential['credential_kind']=='AGENT' and credential['session_digest'] is None
        assert credential['instance_id']==transport['instance_id'] and credential['token_digest']==transport['token_digest']
        assert int(credential['fencing_token'])==int(transport['fencing_token'])
        generated_start=len(state.guard.records)
        result=retros.run_once(state.agent,created['job_id'],state.key+'_worker')
        state.guard.require_complete()
        assert result['status']=='PROPOSED' and result['published'] is False
        generated=state.guard.records[generated_start:]
        assert len(generated)==1 and generated[0]['kind']=='MODEL', 'A retrospective has one request and no hidden repair'
        job=retros.read_job(state.agent,created['job_id'])
        assert str(job['task_id'])==task and job['security_domain_id']==state.domain and job['created_by']==state.agent
        assert job['output_mode']=='NATIVE_STRICT' and job['output_probe_id']==probe['probe_id']
        assert job['schema_digest']==probe['schema_digest'] and job['parameter_digest']==state.parameter_digest
        candidate=candidates.read_candidate(state.agent,result['candidate_id'])
        assert candidate['status']=='PENDING' and candidate['proposed_by']==state.agent
        assert candidate['payload']['content']['family']==family and candidate['payload']['sources']==[source]
        assert candidate['result_entity_id'] is None and candidate['result_revision_id'] is None
        text_field={'MEMORY':'body','KNOWLEDGE':'body','EXPERIENCE':'solution','SKILL':'instructions'}[family]
        assert candidate['payload']['content'][text_field].strip(), 'Retain a substantive generated proposal for independent review'
        assert one('SELECT COUNT(*) AS CNT FROM CX_CANDIDATE_REVIEWS WHERE CANDIDATE_ID=:candidate',
            {'candidate':result['candidate_id']})['cnt']==0
        sent=len(state.guard.records)
        replay=retros.run_once(state.agent,created['job_id'],state.key+'_worker')
        assert replay['replayed'] is True and replay['candidate_id']==result['candidate_id']
        assert len(state.guard.records)==sent
        output(state,family,dict(kind='NATIVE_STRICT_PENDING_CANDIDATE',probe=probe,task_id=task,source=source,
            job=job,candidate=candidate,business_output_completed=True))
        record_property('retrospective_job_id',created['job_id'])
        record_property('pending_candidate_id',candidate['candidate_id'])


def test_real_native_strict_memory_stops_at_pending_candidate(provider,record_property):
    strict_retrospective(provider,'MEMORY',record_property)


def test_real_native_strict_knowledge_stops_at_pending_candidate(provider,record_property):
    strict_retrospective(provider,'KNOWLEDGE',record_property)


def test_real_native_strict_experience_stops_at_pending_candidate(provider,record_property):
    strict_retrospective(provider,'EXPERIENCE',record_property)


def test_real_native_strict_skill_stops_at_pending_candidate(provider,record_property):
    strict_retrospective(provider,'SKILL',record_property)


@contextmanager
def independent_test_approver(state):
    username='v502_review_'+secrets.token_hex(10)
    password=secrets.token_urlsafe(32)
    token=identity_api.issue_human_registration_token(state.actor,900,state.reason)
    registered=identity_api.register_human(username,password,display_name='Automated isolated approval fixture',
        email=username+'@example.invalid',registration_token=token['token'])
    if registered['status']=='PENDING':
        organization=one("SELECT ORGANIZATION_ID FROM CX_ORGANIZATION_MEMBERS WHERE PRINCIPAL_ID=:actor "
            "AND MEMBERSHIP_KIND='PRIMARY' AND STATUS='ACTIVE'",{'actor':state.actor})
        assert organization, 'Normal Human approval requires the administrator primary organization'
        registered=identity_api.approve_registration(registered['request_id'],state.actor,state.reason,organization['organization_id'])
    assert registered['status']=='ACTIVE' and registered['principal_id']!=state.actor
    human=registered['principal_id']
    from lib import admin_management
    try:
        identity_api.assign_permission_override(state.actor,human,'channels.actions.decide','ALLOW','OWNED',state.reason)
        identity_api.set_entry_access(state.actor,human,True,state.reason)
        domains.set_member(state.actor,state.domain,human,'MEMBER',state.reason)
        domains.set_member(state.actor,'DEFAULT',human,'MEMBER',state.reason)
        admin_management.invite_protected_human(state.actor,human,state.reason)
        with authenticated_human(username,password,human) as session:
            with model_credentials.server_session(None):
                yield SimpleNamespace(principal_id=human,session=session)
    finally:
        identity_api.assign_permission_override(state.actor,human,'channels.actions.decide','DENY','NONE',state.reason)
        identity_api.set_entry_access(state.actor,human,False,state.reason)
        identity_api.revoke_principal_sessions(human,state.reason)
        domains.set_member(state.actor,'DEFAULT',human,'MEMBER',state.reason,status='REVOKED')
        domains.set_member(state.actor,state.domain,human,'MEMBER',state.reason,status='REVOKED')


@contextmanager
def isolated_execution_policy(state):
    original={item['capability_key']:item for item in model_capability_api.list_capabilities()['items']
        if item['capability_key'] in {'mcp_execution','governed_execution'}}
    changed=[]
    try:
        for key,item in sorted(original.items()):
            if item['state']!='GOVERNED_EXECUTOR':
                assert os.environ.get('CX_V502_ISOLATED_TOOL_POLICY')=='1', 'Explicit isolated test-only execution policy scope required'
                model_capability_api.set_state(state.actor,key,'GOVERNED_EXECUTOR',state.reason,int(item['version']),
                    evidence_ref='isolated-acceptance:'+state.key)
                changed.append(key)
        yield
    finally:
        for key in reversed(changed):
            current=next(item for item in model_capability_api.list_capabilities()['items'] if item['capability_key']==key)
            model_capability_api.set_state(state.actor,key,original[key]['state'],state.reason+' restore original capability',
                int(current['version']),evidence_ref=original[key]['evidence_ref'] or 'isolated-acceptance-restore:'+state.key)


def test_real_ordinary_business_agent_approved_echo_tool_result_final_once(provider,record_property):
    state=provider
    @contextmanager
    def approver_in_authorized_existing_organization():
        # Keep this failed case's fixture correction local so the four completed
        # strict cases retain their exact shared-code fingerprints and outputs.
        from lib import organization_api, admin_management
        options=organization_api.list_options(state.actor,limit=500)
        assert len(options)<500
        roots=[item for item in options if item.get('status')=='ACTIVE' and item.get('parent_id') is None]
        assert len(roots)==1, 'Select one existing authorized root before creating the Human fixture'
        username='v502_review_'+secrets.token_hex(10)
        password=secrets.token_urlsafe(32)
        token=identity_api.issue_human_registration_token(state.actor,900,state.reason)
        registered=identity_api.register_human(username,password,display_name='Automated isolated approval fixture',
            email=username+'@example.invalid',registration_token=token['token'])
        if registered['status']=='PENDING':
            registered=identity_api.approve_registration(registered['request_id'],state.actor,state.reason,roots[0]['organization_id'])
        assert registered['status']=='ACTIVE' and registered['principal_id']!=state.actor
        human=registered['principal_id']
        try:
            identity_api.assign_permission_override(state.actor,human,'channels.actions.decide','ALLOW','OWNED',state.reason)
            identity_api.set_entry_access(state.actor,human,True,state.reason)
            domains.set_member(state.actor,state.domain,human,'MEMBER',state.reason)
            domains.set_member(state.actor,'DEFAULT',human,'MEMBER',state.reason)
            admin_management.invite_protected_human(state.actor,human,state.reason)
            with authenticated_human(username,password,human) as session:
                with model_credentials.server_session(None):
                    yield SimpleNamespace(principal_id=human,session=session)
        finally:
            identity_api.assign_permission_override(state.actor,human,'channels.actions.decide','DENY','NONE',state.reason)
            identity_api.set_entry_access(state.actor,human,False,state.reason)
            identity_api.revoke_principal_sessions(human,state.reason)
            domains.set_member(state.actor,'DEFAULT',human,'MEMBER',state.reason,status='REVOKED')
            domains.set_member(state.actor,state.domain,human,'MEMBER',state.reason,status='REVOKED')
    task,source=new_source(state)
    state.guard.authorize_echo_entity(task)
    channel=identity_api.create_channel(state.actor,state.key,state.domain)['channel_id']
    assert agent_gateway_api.add_channel_member(state.actor,channel,state.agent,reason=state.reason)
    assert not one("SELECT MEMBER_ID FROM CX_ADMIN_AGENT_MEMBERS WHERE AGENT_ID=:agent AND STATUS='ACTIVE'",{'agent':state.agent})
    tool=None
    instance=None
    try:
        for action in ('tools.read','actions.propose'):
            identity_api.assign_permission_override(state.actor,state.agent,action,'ALLOW','OWNED',state.reason)
        spec=dict(openapi='3.0.3',info=dict(title='Synthetic echo transport only',version='1.0.0'),
            servers=[dict(url='https://postman-echo.com')],paths={'/get':{'get':dict(operationId='read_echo',
                parameters=[dict(name='entity_id',**{'in':'query'},required=True,schema={'type':'string'})],
                responses={'200':dict(description='Echoes only a synthetic locator',content={'application/json':{'schema':{
                    'type':'object','properties':{'args':{'type':'object','properties':{'entity_id':{'type':'string'}},
                        'required':['entity_id']}},'required':['args']}}})})}})
        tools=tool_registry.import_openapi(spec,state.key.lower())
        assert len(tools)==1
        tool=str(tools[0])
        tool_registry.set_mcp_exposure(state.actor,tool,expected_exposed=False,exposed=True,reason=state.reason)
        registration=dict(security_domain_id=state.domain,tool_id=tool,source=source,resource_parameter='entity_id',
            reason=state.reason,idempotency_key=state.key+'_registration')
        with approver_in_authorized_existing_organization() as approver:
            human=approver.principal_id
            assert agent_gateway_api.add_channel_member(state.actor,channel,human,role='REVIEWER',reason=state.reason)
            action=turns.request_registration(state.actor,registration)
            with model_credentials.server_session(approver.session):
                assert identity_api.decide_action_card(human,action['action_id'],'APPROVE',state.reason)
            registered=turns.register_read_tool(state.actor,registration,action['action_id'])
            directory=turns.read_registration(state.actor,registered['registration_id'])
            # A capability probe retains the actual authenticated administrator
            # Session; it never impersonates the newly enrolled Agent.
            with model_credentials.server_session(None):
                password=Path(os.environ['CX_V502_ADMIN_PASSWORD_FILE']).read_text().strip()
                with authenticated_human('admin',password,state.actor):
                    probe=contracts.probe_exact(state.actor,state.profile,directory['input_schema'],
                        {'entity_id':task},tool_name=directory['tool_name'])
            state.guard.require_complete()
            assert probe['status']=='VERIFIED'
            assert probe['schema_digest']==directory['schema_digest'] and probe['parameter_digest']==state.parameter_digest
            assert int(probe['profile_version'])==state.profile_version
            instance=agent_gateway_api.create_instance(state.agent,channel_id=channel,security_domain_id=state.domain)
            token=agent_gateway_api.issue_access_token(state.agent,instance['instance_id'],
                ['actions.propose','workspaces.write','tools.read'],ttl_seconds=900)
            context=agent_gateway_api.authenticate_access_token(token['access_token'],state.agent,instance['instance_id'],'actions.propose')
            assert context and context['agent_id']==state.agent
            with isolated_execution_policy(state),model_credentials.server_session(None),bindings.authenticated_transport(context):
                turn=turns.create_turn(state.agent,dict(registration_id=registered['registration_id'],task_id=task,
                    profile_id=state.profile,profile_version=state.profile_version,probe_id=probe['probe_id'],
                    question='Use the approved echo tool once. Report only the synthetic entity_id it actually echoes. '
                        'Do not claim it retrieved the underlying Task content or proved the training sample fact.',
                    token_budget=32768,output_budget=512,deadline_seconds=900,reason=state.reason,
                    idempotency_key=state.key+'_turn'))
                workflow_start=len(state.guard.records)
                proposed=turns.run_once(state.agent,turn['turn_id'],state.key+'_worker')
                state.guard.require_complete()
                assert proposed['status']=='WAITING_APPROVAL'
                action=turns.request_tool_approval(state.agent,turn['turn_id'],channel_id=channel)
                with pytest.raises(PermissionError):turns.admit_approved_tool(state.agent,turn['turn_id'])
                with bindings.authenticated_transport(None),model_credentials.server_session(approver.session):
                    assert identity_api.decide_action_card(human,action['action_id'],'APPROVE',state.reason)
                approval=one('SELECT CHANNEL_ID,PROPOSED_BY,DECIDED_BY,STATUS FROM CX_ACTION_CARDS WHERE ACTION_ID=:action',
                    {'action':action['action_id']})
                assert approval['channel_id']==channel and approval['proposed_by']==state.agent
                assert approval['decided_by']==human and approval['status']=='CONFIRMED'
                assert one('SELECT SECURITY_DOMAIN_ID FROM CX_CHANNELS WHERE CHANNEL_ID=:channel',
                    {'channel':channel})['security_domain_id']==state.domain
                admitted=turns.admit_approved_tool(state.agent,turn['turn_id'])
                assert not one("SELECT JOB_ID FROM EXECUTION_JOBS WHERE STATUS IN ('PENDING','RETRY') AND JOB_ID<>:job",
                    {'job':admitted['job_id']}), 'Never execute another isolated fixture job by accident'
                from lib import execution_control
                executed=execution_control.run_worker_once(state.key+'_tool_worker')
                state.guard.require_complete()
                assert executed['job_id']==admitted['job_id'] and executed['status']=='SUCCEEDED'
                final=turns.run_once(state.agent,turn['turn_id'],state.key+'_worker')
                state.guard.require_complete()
                assert final['status']=='SUCCEEDED'
                final=turns.read_turn(state.agent,turn['turn_id'])
                assert final['answer'].strip() and len(final['stages'])==2
                assert final['profile_id']==state.profile and final['profile_version']==state.profile_version
                assert final['parameter_digest']==state.parameter_digest and final['schema_digest']==probe['schema_digest']
                assert (final['max_model_requests'],final['max_tool_calls'],final['max_repairs'])==(2,1,0)
                workflow_requests=state.guard.records[workflow_start:]
                assert sum(item['kind']=='MODEL' for item in workflow_requests)==2
                assert sum(item['kind']=='SYNTHETIC_ECHO_TRANSPORT' for item in workflow_requests)==1
                assert len(workflow_requests)==3
                # A direct request has no capacity admission identity. Require
                # an identity only when this Profile selects capacity routing;
                # the observed Provider lifecycle below still counts each send.
                from lib import edition_features, model_endpoint_capacity
                selected_profile=one('SELECT PROVIDER_URL FROM CX_LLM_PROVIDER_PROFILES WHERE PROFILE_ID=:profile',
                    {'profile':state.profile})
                alias=one('SELECT GROUP_ID FROM CX_MODEL_CAP_ALIASES WHERE ALIAS_KEY=:alias',
                    {'alias':model_endpoint_capacity.alias_key(selected_profile['provider_url'])})
                capacity_binding=one('SELECT GROUP_ID FROM CX_MODEL_CAP_BINDINGS WHERE PROFILE_ID=:profile',
                    {'profile':state.profile})
                remote_route=one("SELECT ROUTE_ID FROM CX_MODEL_COORD_ROUTES WHERE PROFILE_ID=:profile "
                    "AND PROFILE_VERSION=:version AND STATUS='ACTIVE'",
                    {'profile':state.profile,'version':state.profile_version})
                controlled=edition_features.MODEL_RUNTIME_CONTEXT_ENABLED and bool(alias or capacity_binding or remote_route)
                if controlled:
                    ids=[item['model_request_id'] for item in final['stages']]
                    assert all(isinstance(value,str) and 0<len(value)<=128 for value in ids)
                    assert len(set(ids))==2
                else:
                    assert all(item['model_request_id'] is None for item in final['stages'])
                observed=len(state.guard.records)
                replay=turns.run_once(state.agent,turn['turn_id'],state.key+'_worker')
                assert replay['answer_digest']==final['answer_digest'] and len(state.guard.records)==observed
                assert one('SELECT COUNT(*) AS CNT FROM EXECUTION_ATTEMPTS WHERE JOB_ID=:job',{'job':admitted['job_id']})['cnt']==1
                job=execution_control.get_job(admitted['job_id'])
                assert job['status']=='SUCCEEDED'
                raw_result=job['result_json']
                if hasattr(raw_result,'read'):raw_result=raw_result.read()
                tool_result=json.loads(raw_result) if isinstance(raw_result,str) else raw_result
                echoed=json.loads(tool_result['body'])
                assert echoed['args']=={'entity_id':task} and tool_result['status_code']==200
                output(state,'tool',dict(kind='ORDINARY_AGENT_GOVERNED_ECHO_TRANSPORT_FINAL',probe=probe,
                    source=source,task_id=task,channel_id=channel,final=final,synthetic_echo_is_business_content_retrieval=False,
                    tool_result=tool_result,business_output_completed=True,
                    workflow_model_requests=2,workflow_http_get_requests=1,workflow_repairs=0,
                    workflow_http_request_ids=[item['request_id'] for item in workflow_requests],
                    automatic_test_approver=human,automatic_approval_is_final_answer_human_review=False))
                record_property('governed_tool_turn_id',turn['turn_id'])
                record_property('tool_worker_job_id',admitted['job_id'])
    finally:
        if instance:agent_gateway_api.revoke_instance(state.agent,instance['instance_id'],state.reason)
        if tool:tool_registry.set_mcp_exposure(state.actor,tool,expected_exposed=True,exposed=False,reason=state.reason)
        identity_api.transition_channel_lifecycle(state.actor,channel,'ARCHIVED',state.reason)
