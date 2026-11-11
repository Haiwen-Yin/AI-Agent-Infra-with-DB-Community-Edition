"""Opt-in native v5.0.2 business paths on an exact classified package.

These tests use normal enrollment, native identities, domain governance and
production Task/Loop/Graph/DB4A2A APIs. No authority or processing adapter is
mocked. Fixtures and immutable audit remain in the isolated acceptance database.
"""
from contextlib import contextmanager
import json
import os
import secrets
import subprocess
import sys
from types import SimpleNamespace

import pytest

from lib import connection, identity_api, security_domain_api as domains
from lib import agent_api, agent_gateway_api, edition_features
from lib import db4a2a, graph_compat, graph_runtime, loop_api, processing_graph
from lib import processing_recovery, task_plan_api, workspace_api
from .release_target import classified_current_target

pytestmark = pytest.mark.skipif(
    os.environ.get('CX_V502_NATIVE_BUSINESS_LIVE') != '1' and os.environ.get('CX_NATIVE_BUSINESS_LIVE') != '1',
    reason='explicit exact classified native business acceptance required')


def one(sql, params=None):
    return connection.execute_query_one(sql, params or {})


def integer(sql, params=None):
    return int(next(iter(one(sql, params).values())))


@contextmanager
def native_agent(agent):
    previous = connection.get_current_agent_id()
    try:
        connection.set_agent_context(agent)
        yield
    finally:
        connection.set_agent_context(previous)


@pytest.fixture
def business(record_property):
    from lib.product_identity import read_manifest
    if os.environ.get('CX_NATIVE_BUSINESS_LIVE') == '1':
        from pathlib import Path
        from version_validation_runtime import selected
        package, target, _state, version = selected()
        assert version == '5.0.5' and read_manifest()['version'] == version
        assert target['classification'] == 'temporary'
        assert Path(connection.__file__).resolve().is_relative_to(package/'scripts')
    else:
        assert classified_current_target()
        assert read_manifest()['version'] == '5.0.2'
    assert processing_recovery.schema_enabled(), 'Never disable current processing for native acceptance'
    assert connection.get_current_agent_id() is None
    humans = connection.execute_query("SELECT PRINCIPAL_ID FROM CX_PRINCIPALS WHERE PRINCIPAL_TYPE='HUMAN' AND STATUS='ACTIVE'")
    actor = next((str(value['principal_id']) for value in humans if all(
        identity_api.effective_access(str(value['principal_id']), action)['decision'] == 'ALLOW'
        for action in ('agents.enroll', 'agents.offboard', 'domains.manage', 'users.permissions.manage', 'agents.operate'))), None)
    assert actor, 'Native business fixtures require the isolated installation administrator'
    key = 'V502_B_' + secrets.token_hex(10).upper()
    domain, agent = key + '_D', key + '_A'
    reason = 'Explicit classified v5.0.2 native business fixture ' + key
    domains.create_domain(actor, domain, key, 'INTERNAL', reason, actor, reason)
    state = SimpleNamespace(actor=actor, domain=domain, agent=agent, key=key, reason=reason,
                            created=False, grants=[], runs=[])
    record_property('fixture_domain', domain)
    record_property('fixture_agent', agent)
    try:
        grant = identity_api.create_enrollment_grant(actor, actor, environment='development',
            runtime='native-business-acceptance', security_domain_id=domain, agent_name=agent,
            risk_tier='LOW', ttl_seconds=900)
        enrolled = identity_api.redeem_enrollment(grant['token'], agent,
            runtime='native-business-acceptance', environment='development')
        state.created = True
        assert enrolled['status'] == 'PENDING_ACTIVATION'
        proof = agent_gateway_api.authenticate_activation_client_secret(agent, enrolled['credential'])
        assert proof and proof['agent_id'] == agent
        baseline = dict(runtime='native-business-acceptance', purpose=reason, external_runtime_started=False)
        if edition_features.has_feature('compliance'):
            from lib import compliance_api
            compliance_api.activate_from_gateway(agent, baseline, credential_type=proof['credential_type'],
                runtime='native-business-acceptance', environment='development', security_domain_id=domain)
        else:
            identity_api.activate_community_agent(agent, domain, baseline)
        assert agent_gateway_api.authenticate_client_secret(agent, enrolled['credential'])
        snapshot = agent_api.native_identity_snapshot(agent)
        assert snapshot['mapping_state'] == snapshot['native_state'] == 'OBSERVED'
        assert snapshot['principal_status'] == 'ACTIVE' and snapshot['login_enabled'] is True
        assert snapshot['native_privileged'] is False
        domains.set_member(actor, domain, agent, 'MEMBER', reason)
        # Normal accountable ownership is required by the existing HTTP Loop
        # admission; enrollment's sponsor field does not impersonate it.
        identity_api.transfer_agent_owner(actor, agent, actor, reason)
        for action in ('workspaces.read', 'workspaces.write', 'tasks.read', 'graphs.read'):
            granted = identity_api.assign_permission_override(actor, agent, action, 'ALLOW', 'OWNED', reason)
            state.grants.append(granted['override_id'])
            assert identity_api.effective_access(agent, action, resource={'security_domain_id':domain})['decision'] == 'ALLOW'
        assert identity_api.effective_access(agent, 'platform.manage')['decision'] != 'ALLOW'
        assert not one("SELECT INSTANCE_ID FROM CX_AGENT_INSTANCES WHERE AGENT_ID=:agent AND STATUS='ACTIVE'", {'agent':agent})
        yield state
    finally:
        connection.set_agent_context(None)
        if state.created and state.runs:
            # Restore only this fixture's membership for ordinary stop APIs;
            # the preceding denial is retained before this explicit cleanup.
            domains.set_member(actor, domain, agent, 'MEMBER', reason)
        for run in state.runs:
            loop_api.stop_run(run, reason)
        if state.created:
            result = identity_api.offboard_agent(actor, agent, environment='DEVELOPMENT', reason=reason)
            native = result['native_identity_revocation']
            assert result['status'] in {'DISABLED', 'QUARANTINED', 'OWNER_TRANSFER_REQUIRED'}
            assert native['status'] == 'COMPLETE' and native['audit_status'] == 'RECORDED'
            assert native['new_connections_blocked'] is True
        domains.set_domain_status(actor, domain, 'REVOKED', reason)


def reference(state):
    # Fixture preparation uses the existing management API. Oracle's native
    # Agent identity has a read-only workspace-context grant; direct INSERT is
    # not part of the DB4A2A dispatch contract exercised below. The receiver's
    # actual native read still has to succeed, both here and during dispatch.
    assert connection.get_current_agent_id() is None
    assert identity_api.effective_access(state.actor, 'workspaces.write',
        resource={'security_domain_id':state.domain})['decision'] == 'ALLOW'
    workspace = workspace_api.create_workspace(name=state.key, isolation_mode='ISOLATED')
    assert workspace_api.update_workspace(workspace, current_agent_id=state.agent)
    context = workspace_api.save_context(workspace, state.agent, 'CHECKPOINT',
        {'fixture':state.key, 'fact':'The approved sample contains exactly 23 blue cubes.'}, visibility='PRIVATE')
    with native_agent(state.agent):
        table = 'CX_AGENT_CONTEXT_READ' if connection.DATABASE_DIALECT == 'yashandb' else 'WORKSPACE_CONTEXT'
        assert one('SELECT CONTEXT_ID FROM ' + table + ' WHERE CONTEXT_ID=:context', {'context':context})
    current = one('SELECT CONTEXT_DATA FROM WORKSPACE_CONTEXT WHERE CONTEXT_ID=:context', {'context':context})
    envelope = db4a2a.build_dispatch(task_id=state.key,
        context=db4a2a.ContextReference(str(context), db4a2a.context_snapshot(current['context_data']), 1,
                                     'workspace:' + str(workspace)), branch_policy='CHILD_BRANCH_WRITE')
    return db4a2a.persist_dispatch(state.actor, state.agent, envelope)


def dispatch_budget(dispatch):
    return one("SELECT b.* FROM CX_PROCESSING_BUDGETS b JOIN CX_PROCESSING_CHAINS c ON c.BUDGET_ID=b.BUDGET_ID "
        "JOIN CX_TASK_CONTINUITY_LINKS l ON l.CONTINUITY_ID=c.CONTINUITY_ID WHERE l.LINK_KIND='DB4A2A' AND l.LINK_ID=:dispatch",
        {'dispatch':dispatch['dispatch_id']})


def child_process(code, value):
    # It starts a new interpreter using only the selected package's scripts.
    # The inherited encrypted config and explicit native client environment
    # remain unchanged. Reads never start a service or issue a model request.
    env = os.environ.copy()
    env.pop('PYTEST_CURRENT_TEST', None)
    guard = "import urllib.request\ndef _deny(*args,**kwargs): raise AssertionError('Native restart observation denies HTTP')\nurllib.request.OpenerDirector.open=_deny\n"
    run = subprocess.run([sys.executable, '-B', '-c', guard + code], input=json.dumps(value),
        text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, timeout=60)
    assert run.returncode == 0, run.stderr[-2000:]
    return json.loads(run.stdout)


def test_native_db4a2a_branch_task_attempt_and_budget_commit_once_across_processes(business, record_property):
    state = business
    dispatch = reference(state)
    before = dispatch_budget(dispatch)
    assert before and int(before['requests_used']) == 0
    result = db4a2a.create_dispatch_branch(state.actor, dispatch['dispatch_id'], state.key, state.reason)
    assert result['branch_id'] and result['idempotent'] is False
    after = dispatch_budget(dispatch)
    assert after['budget_id'] == before['budget_id']
    assert int(after['steps_used']) == int(before['steps_used']) + 1
    assert int(after['requests_used']) == 0
    actions = connection.execute_query('SELECT a.ATTEMPT_ID,a.STEP_COUNT,t.STATUS FROM CX_PROCESSING_ACTIONS a '
        'JOIN CX_TASK_CONTINUITY_ATTEMPTS t ON t.ATTEMPT_ID=a.ATTEMPT_ID WHERE a.BUDGET_ID=:budget', {'budget':after['budget_id']})
    assert len(actions) == 1 and actions[0]['status'] == 'SUCCEEDED' and int(actions[0]['step_count']) == 1
    replay = child_process("""import json,sys
from lib import db4a2a,connection
v=json.load(sys.stdin)
r=db4a2a.create_dispatch_branch(v['actor'],v['dispatch'],'new label after restart','Explicit replay after interpreter restart')
print(json.dumps(r,default=str))
""", {'actor':state.actor,'dispatch':dispatch['dispatch_id']})
    assert replay['idempotent'] is True and str(replay['branch_id']) == str(result['branch_id'])
    assert dispatch_budget(dispatch) == after
    record_property('dispatch_id', dispatch['dispatch_id'])
    record_property('processing_budget_id', after['budget_id'])
    record_property('native_branch_id', result['branch_id'])


def test_native_db4a2a_domain_revocation_denies_effect_without_budget_reset(business):
    state = business
    dispatch = reference(state)
    before = dispatch_budget(dispatch)
    domains.set_member(state.actor, state.domain, state.actor, 'OWNER', state.reason, status='REVOKED')
    with pytest.raises(PermissionError):
        db4a2a.create_dispatch_branch(state.actor, dispatch['dispatch_id'], state.key, state.reason)
    assert dispatch_budget(dispatch) == before
    assert one('SELECT CHILD_BRANCH_ID FROM CX_DB4A2A_DISPATCHES WHERE DISPATCH_ID=:dispatch',
               {'dispatch':dispatch['dispatch_id']})['child_branch_id'] is None


def test_native_pg_context_self_read_does_not_open_other_rows_or_writes(business):
    if connection.DATABASE_DIALECT not in {'pg','postgres','postgresql'} or os.environ.get('CX_NATIVE_BUSINESS_LIVE') != '1':
        pytest.skip('v5.0.5 PostgreSQL native self-read migration')
    from psycopg2.errors import InsufficientPrivilege
    state = business
    workspace = workspace_api.create_workspace(name=state.key, isolation_mode='ISOLATED')
    own = workspace_api.save_context(workspace, state.agent, 'CHECKPOINT', {'fact':state.key}, visibility='PRIVATE')
    other = one('SELECT AGENT_ID FROM AGENT_REGISTRY WHERE AGENT_ID<>:agent ORDER BY AGENT_ID FETCH FIRST 1 ROWS ONLY', {'agent':state.agent})
    assert other, 'A second registered identity is required for the cross-owner control'
    unowned = workspace_api.save_context(workspace, other['agent_id'], 'CHECKPOINT', {'fact':'other'}, visibility='SHARED')
    with native_agent(state.agent):
        assert one('SELECT CONTEXT_ID FROM WORKSPACE_CONTEXT WHERE CONTEXT_ID=:id', {'id':own})
        assert not one('SELECT CONTEXT_ID FROM WORKSPACE_CONTEXT WHERE CONTEXT_ID=:id', {'id':unowned})
        try:
            changed = connection.execute('UPDATE WORKSPACE_CONTEXT SET CONTEXT_DATA=CONTEXT_DATA WHERE CONTEXT_ID=:id', {'id':own})
        except InsufficientPrivilege:
            pass
        else:
            assert changed == 0
        with connection.get_connection_for_agent() as native:
            with native.cursor() as cursor:
                cursor.execute("SELECT set_config('app.current_agent_id', 'forged-agent', true)")
                cursor.execute('SELECT CONTEXT_ID FROM WORKSPACE_CONTEXT WHERE CONTEXT_ID=%s', (own,))
                assert cursor.fetchone() is None
            native.rollback()


def new_loop(state):
    loop = loop_api.create_loop(state.key, {'success_criteria':'Stop after the approved local work.'},
        {'max_iterations':2, 'max_tokens':4096, 'max_duration_seconds':300},
        {'eval_type':'MANUAL'}, owned_by_agent=state.agent)
    run = loop_api.start_run_for_actor(loop, state.actor, processing_domain_id=state.domain)
    state.runs.append(run)
    binding = graph_compat.get_binding('LOOP_RUN', str(run))
    assert binding and binding['graph_run_id']
    return loop, run, str(binding['graph_run_id'])


def graph_budget(run):
    return one("SELECT l.CANONICAL_TASK_ID,l.SECURITY_DOMAIN_ID,l.CONTINUITY_ID,c.BUDGET_ID,b.REQUESTS_USED,b.STEPS_USED,b.TOKENS_USED "
        "FROM CX_TASK_CONTINUITY_LINKS l JOIN CX_PROCESSING_CHAINS c ON c.CONTINUITY_ID=l.CONTINUITY_ID "
        "JOIN CX_PROCESSING_BUDGETS b ON b.BUDGET_ID=c.BUDGET_ID WHERE l.LINK_KIND='GRAPH' AND l.LINK_ID=:run", {'run':run})


def test_native_loop_graph_restart_reads_preserve_original_task_domain_and_budget(business, record_property):
    state = business
    _loop, run, graph = new_loop(state)
    frozen = graph_budget(graph)
    assert frozen and frozen['security_domain_id'] == state.domain
    plan = one('SELECT AGENT_ID FROM TASK_PLANS WHERE PLAN_ID=:plan', {'plan':frozen['canonical_task_id']})
    assert plan['agent_id'] == state.agent
    digest = child_process("""import hashlib,json,sys
from lib import connection,graph_runtime
v=json.load(sys.stdin)
run=graph_runtime.get_run(v['run'])
row=connection.execute_query_one('SELECT b.* FROM CX_PROCESSING_BUDGETS b WHERE b.BUDGET_ID=:budget',{'budget':v['budget']})
print(json.dumps({'run_id':run['run_id'],'budget_id':row['budget_id'],'requests_used':int(row['requests_used'])}))
""", {'run':graph,'budget':frozen['budget_id']})
    assert digest['run_id'] == graph and digest['budget_id'] == frozen['budget_id']
    assert graph_budget(graph) == frozen
    assert loop_api.pause_run(run)
    paused = graph_budget(graph)
    assert loop_api.resume_run(run)
    assert graph_budget(graph) == paused
    record_property('loop_run_id', run)
    record_property('graph_run_id', graph)
    record_property('canonical_task_id', frozen['canonical_task_id'])


def test_native_loop_revoked_original_domain_denies_resume_without_new_task_or_budget(business):
    state = business
    _loop, run, graph = new_loop(state)
    assert loop_api.pause_run(run)
    frozen = graph_budget(graph)
    domains.set_member(state.actor, state.domain, state.agent, 'MEMBER', state.reason, status='REVOKED')
    with pytest.raises(PermissionError):
        loop_api.resume_run(run)
    assert loop_api.get_run(run)['status'] == 'PAUSED'
    assert graph_budget(graph) == frozen


def test_native_child_loop_keeps_original_canonical_task_domain_and_one_budget(business):
    state = business
    parent_loop, parent_run, parent_graph = new_loop(state)
    original = graph_budget(parent_graph)
    child_loop = loop_api.create_loop(state.key + '_CHILD', {'success_criteria':'Read the original Task only.'},
        {'max_iterations':1, 'max_tokens':1024, 'max_duration_seconds':120}, {'eval_type':'MANUAL'},
        owned_by_agent=state.agent, parent_loop_id=parent_loop)
    child = loop_api.start_run(child_loop, state.agent, processing_domain_id=state.domain,
        canonical_task_id=str(original['canonical_task_id']), processing_parent_run_id=parent_graph)
    state.runs.insert(0, child)
    binding = graph_compat.get_binding('LOOP_RUN', str(child))
    shared = graph_budget(binding['graph_run_id'])
    assert shared['budget_id'] == original['budget_id']
    assert str(shared['canonical_task_id']) == str(original['canonical_task_id'])
    assert shared['security_domain_id'] == original['security_domain_id'] == state.domain
    assert one('SELECT RUN_ID FROM LOOP_RUNS WHERE RUN_ID=:run', {'run':parent_run})


def test_native_observed_review109_immutable_tables_deny_direct_agent_sql(business, record_property):
    from lib import observed_answer_review as reviews
    state = business
    assert reviews.schema_enabled()
    counts = {table: integer('SELECT COUNT(*) AS CNT FROM ' + table) for table in reviews.TABLES}
    for table in reviews.TABLES:
        # Statement triggers must reject even an empty UPDATE/DELETE. The
        # owner reads above independently establish that each table exists.
        for statement in ('UPDATE ' + table + ' SET SET_ID=SET_ID WHERE 1=0',
                          'DELETE FROM ' + table + ' WHERE 1=0'):
            with pytest.raises(Exception):
                connection.execute(statement)
    with native_agent(state.agent):
        with connection.get_connection_for_agent() as session:
            with session.cursor() as cursor:
                cursor.execute('SELECT 1' + connection.scalar_select_suffix())
                assert cursor.fetchone()[0] == 1
        for table in reviews.TABLES:
            for statement in ('SELECT * FROM ' + table + ' WHERE 1=0',
                              'UPDATE ' + table + ' SET SET_ID=SET_ID WHERE 1=0',
                              'DELETE FROM ' + table + ' WHERE 1=0',
                              'INSERT INTO ' + table + " (SET_ID) SELECT 'DENIED109'" + connection.scalar_select_suffix() + ' WHERE 1=0'):
                with pytest.raises(Exception):
                    with connection.get_connection_for_agent() as session:
                        with session.cursor() as cursor:
                            cursor.execute(statement)
    assert {table: integer('SELECT COUNT(*) AS CNT FROM ' + table) for table in reviews.TABLES} == counts
    record_property('review109_scope', 'NATIVE_IMMUTABILITY_AND_AGENT_SQL_DENIAL_ONLY; NO_HUMAN_DECISION')


def test_native_observed_review109_synthetic_origin_independent_session_and_atomic_audit(business, monkeypatch, record_property):
    # This one-row, deliberately non-matrix import is synthetic API contract
    # evidence. It cannot stand in for Portal/Channel generation, real64 output
    # provenance, or an actual independent Human acceptance decision.
    from pathlib import Path
    from lib import observed_answer_review as reviews, model_credentials, native_agent_api
    from lib import provider_capability_probes as probes, memory_lifecycle as memory
    state = business
    assert reviews.schema_enabled()
    profile_id = os.environ['CX_V502_REVIEW109_PROFILE_ID']
    profile_version = int(os.environ['CX_V502_REVIEW109_PROFILE_VERSION'])
    profile_digest = os.environ['CX_V502_REVIEW109_PROFILE_PARAMETER_SHA256']
    health_reference = json.loads(os.environ['CX_V502_REVIEW109_HEALTH_EVIDENCE'])
    assert profile_id == 'LLM_V502_ACCEPTANCE'
    profile = one('SELECT PROFILE_ID,VERSION,STATUS,HEALTH_STATE,PROVIDER_URL,MODEL_ID FROM CX_LLM_PROVIDER_PROFILES '
        'WHERE PROFILE_ID=:id', {'id':profile_id})
    assert profile and profile['status'] == 'ACTIVE' and profile['health_state'] == 'HEALTHY', \
        'Complete the real saved-Profile health prerequisite separately; this native test never sends a probe'
    assert int(profile['version']) == profile_version
    assert profile['provider_url'] == 'http://<DB_HOST>:12345/v1' and profile['model_id'] == 'qwopus3.6-35b-a3b-coder-mtp'
    assert reviews.digest(probes.request_parameters(profile_id, profile_version)) == profile_digest
    assert one("SELECT EVENT_ID FROM CX_SECURITY_EVENTS WHERE ACTION_NAME='LLM_PROFILE_PROBE' "
        "AND RESOURCE_TYPE='LLM_PROFILE' AND RESOURCE_ID=:id AND OUTCOME='ALLOW'", {'id':profile_id}), \
        'Retain the real saved-Profile native probe audit; never manufacture healthy metadata'
    record_property('review109_health_prerequisite', json.dumps(health_reference, sort_keys=True))
    record_property('review109_health_scope', 'CURRENT_NATIVE_PROFILE_REVISION_PARAMETERS_AND_PROBE_AUDIT; HTTP_ORIGIN_VERIFIED_SEPARATELY')

    @contextmanager
    def session(username, password, actor):
        authenticated = identity_api.authenticate_local(username, password)
        assert authenticated and authenticated['principal_id'] == actor
        created = identity_api.create_session(actor, str(authenticated['user_id']), state.key, ttl_seconds=900)
        try:
            resolved = identity_api.resolve_session(created['session_id'], touch=False, expected_scope='DASHBOARD')
            assert resolved and resolved['principal_id'] == actor
            with model_credentials.server_session(resolved):
                yield created, resolved
        finally:
            identity_api.revoke_session(created['session_id'], state.reason)

    # Protected bootstrap administrators intentionally have no primary
    # organization membership. Use the same scoped assignment API as normal
    # registration, and check its prerequisite before creating any invitation.
    from lib import organization_api
    options = organization_api.list_options(state.actor, limit=500)
    assert isinstance(options, list) and len(options) < 500
    roots = [item for item in options if item.get('status') == 'ACTIVE' and not item.get('parent_id')]
    assert len(roots) == 1 and roots[0].get('organization_id'), \
        'Prepare one existing assignable ACTIVE root organization through normal governance before this test'
    organization_id = roots[0]['organization_id']
    username, password = 'v502_obs109_' + secrets.token_hex(10), secrets.token_urlsafe(32)
    invitation = identity_api.issue_human_registration_token(state.actor, 900, state.reason)
    registered = identity_api.register_human(username, password, display_name='Synthetic native109 test identity',
        email=username + '@example.invalid', registration_token=invitation['token'])
    if registered['status'] == 'PENDING':
        registered = identity_api.approve_registration(registered['request_id'], state.actor, state.reason, organization_id)
    assert registered['status'] == 'ACTIVE' and registered['principal_id'] != state.actor
    human, created_agent, granted = registered['principal_id'], None, []
    quality_count = integer('SELECT COUNT(*) AS CNT FROM CX_ANSWER_QUALITY_RUNS')
    try:
        for action in ('platform.manage', 'agents.manage', 'agents.read.all', 'workspaces.read', 'knowledge.read', 'memory.read'):
            identity_api.assign_permission_override(state.actor, human, action, 'ALLOW', 'ALL', state.reason)
            granted.append(action)
        identity_api.set_entry_access(state.actor, human, True, state.reason)
        domains.set_member(state.actor, state.domain, human, 'MEMBER', state.reason)
        request = native_agent_api.create_request(state.actor, agent_name=state.key + '_OBS109', owner_principal_id=state.actor,
            template_key='general-restricted', provider_profile_id=profile_id, target_id='DT_LOCAL_MANAGED',
            isolation_level='DOMAIN_ISOLATED', classification='INTERNAL', purpose=state.reason, reason=state.reason)
        with session(username, password, human):
            approved = native_agent_api.decide_request(human, request['request_id'], 'APPROVE', state.reason)
        created_agent = approved['agent_id']
        assert created_agent
        agent_api.register_agent(created_agent, state.key + '_OBS109', agent_type='test')
        snapshot = agent_api.native_identity_snapshot(created_agent)
        assert snapshot['mapping_state'] == snapshot['native_state'] == 'OBSERVED'
        assert snapshot['login_enabled'] is True and snapshot['native_privileged'] is False
        native_agent_api.activate_agent(state.actor, created_agent, profile_id, state.reason)
        domains.set_member(state.actor, state.domain, created_agent, 'MEMBER', state.reason)
        identity_api.assign_permission_override(state.actor, created_agent, 'knowledge.read', 'ALLOW', 'OWNED', state.reason)
        source = memory.create_family(dict(title='Synthetic native109 contract fact', body='The synthetic sample contains exactly 23 blue cubes.',
            memory_type='FACT', memory_scope='AGENT_MEMORY', owner_principal_id=human,
            security_domain_id=state.domain, classification='INTERNAL', reason=state.reason), actor=state.actor)
        source_row = one('SELECT CONTENT_DIGEST FROM CX_MEMORY_VERSIONS WHERE VERSION_ID=:id', {'id':source['version_id']})
        observation = dict(key='SYNTHETIC_NATIVE109_ONLY', case_id='SYNTHETIC_NATIVE109_ONLY', entry='PORTAL', repetition=1,
            binding_digest=reviews.digest(state.key), case_sha256=reviews.digest({'synthetic':state.key}),
            original_output=dict(path='synthetic-native-contract-only/' + state.key + '.json', sha256=reviews.digest(state.reason)),
            original_actor_id=state.actor, security_domain_id=state.domain, agent_id=created_agent,
            profile_id=profile_id, profile_version=profile_version, query='Synthetic native109 API contract test only.',
            observed=dict(status='COMPLETED', answer='[SYNTHETIC_NATIVE_CONTRACT_TEST_ONLY] 23 blue cubes.', citations=[],
                synthetic_test_only=True, generation_kind='SYNTHETIC_NATIVE_CONTRACT_TEST_ONLY', context_sources=[dict(family='MEMORY',
                    entity_id=source['family_id'], revision_id=source['version_id'], content_digest=source_row['content_digest'])]))
        packet = dict(schema=reviews.PACKET_SCHEMA, version='5.0.2', phase='candidate',
            target=json.loads(Path(os.environ['CX_RELEASE_TEST_CLASSIFICATION']).read_text())['key'],
            track=json.loads(Path(os.environ['CX_RELEASE_TEST_CLASSIFICATION']).read_text())['track'], generation='SYNTHETIC_TEST_ONLY',
            policy_sha256=os.environ['CX_V502_ACCEPTANCE_POLICY_SHA256'], package_manifests={},
            report=dict(path='synthetic-native-contract-only/no-real64-report.json', sha256=reviews.digest(state.key)), rows=[observation])
        decision = dict(output_digest=reviews.digest(observation), factual_correct=True, citations_supported=True,
            reason='Synthetic API assertion only; this is not a formal Human acceptance decision.')
        with session('admin', Path(os.environ['CX_V502_REVIEW109_ADMIN_PASSWORD_FILE']).read_text().strip(), state.actor):
            imported = reviews.register(state.actor, dict(packet=packet, reason=state.reason))
            set_id = imported['set_id']
            assert imported['generation_requests'] == 0
            with pytest.raises(PermissionError):
                reviews.review(state.actor, set_id, observation['key'], decision)
        assert integer('SELECT COUNT(*) AS CNT FROM CX_ANSWER_QUALITY_RUNS') == quality_count

        # Inject only the required audit write failure. Every production
        # authorization, credential, source read and native adapter is real.
        original_transaction = connection.execute_transaction_callback
        failures = []
        class AuditFailure(RuntimeError):
            pass
        class RejectReviewAudit:
            def __init__(self, tx): self.tx = tx
            def __getattr__(self, name): return getattr(self.tx, name)
            def execute(self, sql, params):
                if 'INSERT INTO CX_SECURITY_EVENTS' in sql and params.get('action_name') == 'OBSERVED_ANSWER_REVIEWED':
                    assert self.tx.query_one('SELECT REVIEW_ID FROM CX_OBS_ANSWER_REVIEWS WHERE SET_ID=:id', {'id':set_id})
                    failures.append('required-audit-write-failed-after-real-review-insert')
                    raise AuditFailure('Intentional native109 required-audit fault injection')
                return self.tx.execute(sql, params)
        with session(username, password, human) as (created, resolved):
            with monkeypatch.context() as fault:
                fault.setattr(connection, 'execute_transaction_callback',
                    lambda callback: original_transaction(lambda tx: callback(RejectReviewAudit(tx))))
                with pytest.raises(AuditFailure):
                    reviews.review(human, set_id, observation['key'], decision)
            assert failures == ['required-audit-write-failed-after-real-review-insert']
            assert integer('SELECT COUNT(*) AS CNT FROM CX_OBS_ANSWER_REVIEWS WHERE SET_ID=:id', {'id':set_id}) == 0
            assert not one('SELECT EVENT_ID FROM CX_SECURITY_EVENTS WHERE PRINCIPAL_ID=:actor AND ACTION_NAME=:action',
                {'actor':human, 'action':'OBSERVED_ANSWER_REVIEWED'})
            recorded = reviews.review(human, set_id, observation['key'], decision)
            exported = reviews.export(human, set_id)
            assert recorded['generation_requests'] == exported['generation_requests'] == 0
            assert len(exported['reviews']) == len(exported['audits']) == 1 and exported['release_ready'] is False
            actual, audit = exported['reviews'][0], exported['audits'][0]
            assert actual['reviewer_id'] == audit['principal_id'] == human
            assert actual['output_digest'] == decision['output_digest']
            assert actual['review_id'] == audit['resource_id'] and actual['reason'] == audit['reason'] == decision['reason']
            assert actual['session_digest'] == resolved['session_digest'] != exported['set']['session_digest']
            assert integer('SELECT COUNT(*) AS CNT FROM CX_ANSWER_QUALITY_RUNS') == quality_count
            for table in reviews.TABLES:
                with pytest.raises(Exception):
                    connection.execute('UPDATE ' + table + ' SET SET_ID=SET_ID WHERE SET_ID=:id', {'id':set_id})
                with pytest.raises(Exception):
                    connection.execute('DELETE FROM ' + table + ' WHERE SET_ID=:id', {'id':set_id})
            domains.set_member(state.actor, state.domain, human, 'MEMBER', state.reason, status='REVOKED')
            with pytest.raises(PermissionError):
                reviews.read_set(human, set_id)
            domains.set_member(state.actor, state.domain, human, 'MEMBER', state.reason)
            memory.mark_unavailable(source['family_id'], actor=state.actor, reason=state.reason, expected_version_id=source['version_id'])
            with pytest.raises(PermissionError):
                reviews.export(human, set_id)
            identity_api.revoke_session(created['session_id'], state.reason)
            with pytest.raises(PermissionError):
                reviews.read_set(human, set_id)
        record_property('review109_set_id', set_id)
        record_property('review109_scope', 'SYNTHETIC_NATIVE_CONTRACT_TEST_ONLY; NOT_REAL64; NOT_FORMAL_HUMAN_REVIEW')
        record_property('review109_generations', 0)
    finally:
        if created_agent:
            retired = identity_api.offboard_agent(state.actor, created_agent, environment='DEVELOPMENT', reason=state.reason)
            assert retired['native_identity_revocation']['status'] == 'COMPLETE'
        for action in granted:
            identity_api.assign_permission_override(state.actor, human, action, 'DENY', 'NONE', state.reason)
        identity_api.set_entry_access(state.actor, human, False, state.reason)
        identity_api.revoke_principal_sessions(human, state.reason)
        domains.set_member(state.actor, state.domain, human, 'MEMBER', state.reason, status='REVOKED')
