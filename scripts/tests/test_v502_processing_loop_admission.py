"""Legacy Loop admission keeps the exact existing Graph security boundary."""
import pytest

from lib import graph_compat, graph_definition_api, graph_runtime, loop_api
from lib import processing_graph as graph
from lib.continuity_state import ContinuityError
from .test_v502_processing_graph import ledger


def test_existing_domain_resolution_creates_no_domain_or_membership(ledger):
    before = ledger.db.total_changes
    assert graph.resolve_domain('human') == 'domain'
    assert ledger.db.total_changes == before
    assert ledger.checks[-1][1] == {'write': True}


@pytest.mark.parametrize('condition', ['missing', 'ambiguous', 'revoked_member', 'expired_member', 'revoked_domain', 'denied_action'])
def test_loop_preflight_fails_before_native_row_or_hook(ledger, monkeypatch, condition):
    selected = 'domain'
    if condition == 'missing': selected = 'not-approved'
    elif condition == 'ambiguous':
        ledger.db.executescript("INSERT INTO CX_SECURITY_DOMAINS VALUES('second','ACTIVE'); INSERT INTO CX_DOMAIN_MEMBERS VALUES('human','second','ACTIVE',NULL);")
        ledger.db.commit()
        selected = None
    elif condition == 'revoked_member':
        ledger.run(lambda tx: tx.execute("UPDATE CX_DOMAIN_MEMBERS SET STATUS='REVOKED'", {}))
    elif condition == 'expired_member':
        ledger.run(lambda tx: tx.execute("UPDATE CX_DOMAIN_MEMBERS SET VALID_UNTIL='2001-01-01'", {}))
    elif condition == 'revoked_domain':
        ledger.run(lambda tx: tx.execute("UPDATE CX_SECURITY_DOMAINS SET STATUS='REVOKED'", {}))
    elif condition == 'denied_action': ledger.authorized = False
    monkeypatch.setattr(loop_api, 'execute_insert_returning_id', lambda *_a, **_kw: pytest.fail('Denied admission wrote a Loop Run'))
    monkeypatch.setattr(loop_api, '_fire_hooks', lambda *_a, **_kw: pytest.fail('Denied admission fired ON_START'))
    with pytest.raises((PermissionError, ContinuityError)):
        loop_api.start_run('loop', 'human', processing_domain_id=selected, canonical_task_id='plan')


def test_loop_start_passes_same_explicit_domain_and_canonical_task_to_graph(ledger, monkeypatch):
    order = []
    def insert(sql, params):
        assert params['agent_id'] == 'human'
        order.append('native-row')
        return 'native-loop-run'
    def start(run, loop, actor, **kwargs):
        assert actor == 'human' and run['run_id'] == 'native-loop-run'
        assert kwargs == {'processing_domain_id': 'domain', 'canonical_task_id': 'plan', 'processing_parent_run_id': None}
        order.append('graph-admission')
        return 'graph-run'
    monkeypatch.setattr(loop_api, 'execute_insert_returning_id', insert)
    monkeypatch.setattr(loop_api, 'get_loop', lambda _: {'loop_id': 'loop', 'owned_by_agent': 'human'})
    monkeypatch.setattr(graph_compat, 'start_loop_run', start)
    monkeypatch.setattr(loop_api, '_fire_hooks', lambda *_a, **_kw: order.append('on-start'))
    assert loop_api.start_run('loop', 'human', processing_domain_id='domain', canonical_task_id='plan') == 'native-loop-run'
    assert order == ['native-row', 'graph-admission', 'on-start']


@pytest.mark.parametrize('error', [PermissionError('revoked after preflight'), ImportError('required v502 module unavailable')])
def test_failed_graph_admission_retains_failed_native_row_without_hook(ledger, monkeypatch, error):
    writes = []
    monkeypatch.setattr(loop_api, 'execute_insert_returning_id', lambda *_a, **_kw: 'native-loop-run')
    monkeypatch.setattr(loop_api, 'get_loop', lambda _: {'loop_id': 'loop'})
    monkeypatch.setattr(loop_api, 'execute', lambda sql, params: writes.append((sql, params)) or 1)
    def fail(*_args, **_kwargs): raise error
    monkeypatch.setattr(graph_compat, 'start_loop_run', fail)
    monkeypatch.setattr(loop_api, '_fire_hooks', lambda *_a, **_kw: pytest.fail('Failed admission fired ON_START'))
    with pytest.raises(type(error), match=str(error)):
        loop_api.start_run('loop', 'human', processing_domain_id='domain')
    assert len(writes) == 1 and "STATUS='FAILED'" in writes[0][0]
    assert writes[0][1] == {'id': 'native-loop-run', 'error': 'Graph processing admission failed'}


def test_loop_compatibility_forwards_domain_to_original_graph_create(ledger, monkeypatch):
    captured = {}
    binding = {'graph_id': 'graph', 'graph_version_id': 'version'}
    monkeypatch.setattr(graph_compat, 'ensure_loop_graph', lambda _: binding)
    monkeypatch.setattr(graph_compat, 'get_binding', lambda *_: None)
    monkeypatch.setattr(graph_compat, '_upsert_binding', lambda *args, **kwargs: binding)
    monkeypatch.setattr(graph_compat, '_drain_control_nodes', lambda *_: None)
    monkeypatch.setattr(graph_definition_api, 'get_version', lambda *_a, **_kw: {'plan_id': 'compiled', 'budget': {}})
    def create(*args, **kwargs):
        captured.update(args=args, kwargs=kwargs)
        return 'graph-run'
    monkeypatch.setattr(graph_runtime, 'create_run', create)
    assert graph_compat.start_loop_run({'run_id': 'legacy'}, {'loop_id': 'loop'}, 'human',
        processing_domain_id='domain', canonical_task_id='plan', processing_parent_run_id='original') == 'graph-run'
    assert captured['args'] == ('version', 'compiled', 'human')
    assert captured['kwargs']['processing_domain_id'] == 'domain'
    assert captured['kwargs']['canonical_task_id'] == 'plan'
    assert captured['kwargs']['processing_parent_run_id'] == 'original'
    assert captured['kwargs']['initial_state']['legacy_id'] == 'legacy'


@pytest.fixture
def loop_entry(ledger, monkeypatch):
    from lib import identity_api
    ledger.db.executescript("""
        CREATE TABLE CX_AGENT_RELATIONSHIPS(RELATIONSHIP_ID TEXT,AGENT_ID TEXT,PRINCIPAL_ID TEXT,
            RELATIONSHIP_ROLE TEXT,STATUS TEXT,ENDED_AT TIMESTAMP);
        CREATE TABLE TASK_STEPS(STEP_ID TEXT,PLAN_ID TEXT);
        INSERT INTO CX_DOMAIN_MEMBERS VALUES('agent','domain','ACTIVE',NULL);
        INSERT INTO CX_AGENT_RELATIONSHIPS VALUES('owner','agent','human','PRIMARY_OWNER','ACTIVE',NULL);
        INSERT INTO TASK_STEPS VALUES('step','plan');
    """)
    ledger.db.commit()
    monkeypatch.setattr(identity_api, 'effective_access', lambda *_a, **_kw: {'decision': 'ALLOW'})
    monkeypatch.setattr(loop_api, 'get_loop', lambda _: {'loop_id': 'loop', 'owned_by_agent': 'agent'})
    sent = []
    monkeypatch.setattr(loop_api, 'start_run', lambda *a, **kw: sent.append((a, kw)) or 'native-loop-run')
    return ledger, sent


def test_authenticated_start_uses_definition_agent_and_current_owner(loop_entry):
    ledger, sent = loop_entry
    assert loop_api.start_run_for_actor('loop', 'human', processing_domain_id='domain') == 'native-loop-run'
    assert sent == [(('loop', 'agent', 'MANUAL', None), {'processing_domain_id': 'domain'})]


@pytest.mark.parametrize('condition', ['spoofed_agent', 'revoked_responsibility', 'expired_owner_domain', 'wrong_domain', 'ambiguous_agent_domain', 'denied_action'])
def test_authenticated_start_rejects_changed_or_ambiguous_authority(loop_entry, monkeypatch, condition):
    from lib import identity_api
    ledger, sent = loop_entry
    kwargs = {'processing_domain_id': 'domain'}
    if condition == 'spoofed_agent': kwargs['requested_agent_id'] = 'other-agent'
    elif condition == 'revoked_responsibility':
        ledger.run(lambda tx: tx.execute("UPDATE CX_AGENT_RELATIONSHIPS SET STATUS='REVOKED'", {}))
    elif condition == 'expired_owner_domain':
        ledger.run(lambda tx: tx.execute("UPDATE CX_DOMAIN_MEMBERS SET VALID_UNTIL='2001-01-01' WHERE PRINCIPAL_ID='human'", {}))
    elif condition == 'wrong_domain': kwargs['processing_domain_id'] = 'unapproved'
    elif condition == 'ambiguous_agent_domain':
        ledger.db.executescript("INSERT INTO CX_SECURITY_DOMAINS VALUES('second','ACTIVE'); INSERT INTO CX_DOMAIN_MEMBERS VALUES('agent','second','ACTIVE',NULL);")
        ledger.db.commit()
        kwargs = {}
    elif condition == 'denied_action':
        monkeypatch.setattr(identity_api, 'effective_access', lambda *_a, **_kw: {'decision': 'DENY'})
    with pytest.raises((PermissionError, ContinuityError)):
        loop_api.start_run_for_actor('loop', 'human', **kwargs)
    assert sent == []


def test_bound_auto_start_retains_exact_parent_task_domain(loop_entry, monkeypatch):
    ledger, sent = loop_entry
    monkeypatch.setattr(graph_compat, 'get_binding', lambda kind, key: {'graph_run_id': 'run'} if (kind, key) == ('TASK_PLAN', 'plan') else None)
    writes = []
    monkeypatch.setattr(loop_api, 'execute_insert_returning_id', lambda sql, params: writes.append((sql, params)) or 'binding')
    monkeypatch.setattr(loop_api, 'execute', lambda sql, params: writes.append((sql, params)) or 1)
    assert loop_api.bind_loop_to_step('loop', 'step', auto_start='Y') == 'binding'
    assert len(writes) == 2
    assert sent == [(('loop',), {'agent_id': 'agent', 'processing_domain_id': 'domain',
                              'canonical_task_id': 'plan', 'processing_parent_run_id': 'run'})]


@pytest.mark.parametrize('condition', ['missing_step', 'missing_binding', 'unknown_send', 'revoked_agent_domain'])
def test_auto_start_fails_before_binding_when_original_task_unavailable(loop_entry, monkeypatch, condition):
    from .test_v502_processing_graph import info
    ledger, sent = loop_entry
    monkeypatch.setattr(graph_compat, 'get_binding', lambda *_: {'graph_run_id': 'run'})
    if condition == 'missing_step':
        ledger.run(lambda tx: tx.execute('DELETE FROM TASK_STEPS', {}))
    elif condition == 'missing_binding': monkeypatch.setattr(graph_compat, 'get_binding', lambda *_: None)
    elif condition == 'unknown_send':
        ledger.native_attempt()
        _attempt, link, _shadow, _target = info(ledger)
        ledger.run(lambda tx: tx.execute("UPDATE CX_TASK_CONTINUITY_ATTEMPTS SET STATUS='UNOBSERVED' WHERE CONTINUITY_ID=:chain", {'chain': link['continuity_id']}))
    elif condition == 'revoked_agent_domain':
        ledger.run(lambda tx: tx.execute("UPDATE CX_DOMAIN_MEMBERS SET STATUS='REVOKED' WHERE PRINCIPAL_ID='agent'", {}))
    monkeypatch.setattr(loop_api, 'execute_insert_returning_id', lambda *_a, **_kw: pytest.fail('Denied auto-start wrote a binding'))
    with pytest.raises((PermissionError, ContinuityError)):
        loop_api.bind_loop_to_step('loop', 'step', auto_start='Y')
    assert sent == []


def test_task_plan_binding_uses_same_governed_implementation(monkeypatch):
    from lib import task_plan_api
    captured = []
    monkeypatch.setattr(loop_api, 'bind_loop_to_step', lambda *args: captured.append(args) or 'binding')
    assert task_plan_api.bind_loop_to_step('step', 'loop', 'COMPLETION', 'Y') == 'binding'
    assert captured == [('loop', 'step', 'COMPLETION', 'Y')]


def test_child_loop_inherits_original_graph_budget_before_native_start(ledger, monkeypatch):
    captured = {}
    monkeypatch.setattr(graph_compat, 'get_binding', lambda kind, key: {'graph_run_id': 'run'} if (kind, key) == ('LOOP_RUN', 'original-loop') else None)
    monkeypatch.setattr(loop_api, 'execute_insert_returning_id', lambda *_a, **_kw: 'child-loop')
    monkeypatch.setattr(loop_api, 'get_loop', lambda _: {'loop_id': 'loop'})
    monkeypatch.setattr(loop_api, '_fire_hooks', lambda *_a, **_kw: None)
    def start(_run, _loop, _actor, **kwargs):
        captured.update(kwargs)
        ledger.run(lambda tx: tx.execute("INSERT INTO GRAPH_RUNS(RUN_ID,ACTOR_ID,GRAPH_VERSION_ID,PLAN_ID,DEFINITION_DIGEST,PLAN_DIGEST,INPUT_STATE_JSON,STATUS) "
            "VALUES('child-graph','human','version','compiled','definition','plan-digest','{}','RUNNING')", {}))
        ledger.run(lambda tx: graph.bind_run(tx, 'child-graph', domain_id=kwargs['processing_domain_id'],
            canonical_task_id=kwargs['canonical_task_id'], parent_run_id=kwargs['processing_parent_run_id']))
        return 'child-graph'
    monkeypatch.setattr(graph_compat, 'start_loop_run', start)
    assert loop_api.start_run('loop', 'human', parent_run_id='original-loop') == 'child-loop'
    assert captured == {'processing_domain_id': 'domain', 'canonical_task_id': 'plan', 'processing_parent_run_id': 'run'}
    roots = ledger.query("SELECT c.BUDGET_ID FROM CX_TASK_CONTINUITY_LINKS l JOIN CX_PROCESSING_CHAINS c "
                         "ON c.CONTINUITY_ID=l.CONTINUITY_ID WHERE l.LINK_KIND='GRAPH'", {})
    assert len(roots) == 2 and len({root['budget_id'] for root in roots}) == 1


@pytest.mark.parametrize('condition', ['missing_parent_binding', 'different_parent', 'different_domain', 'different_task'])
def test_child_loop_cannot_replace_parent_domain_task_or_budget(ledger, monkeypatch, condition):
    monkeypatch.setattr(graph_compat, 'get_binding', lambda *_: None if condition == 'missing_parent_binding' else {'graph_run_id': 'run'})
    monkeypatch.setattr(loop_api, 'execute_insert_returning_id', lambda *_a, **_kw: pytest.fail('Denied child wrote a native run'))
    kwargs = {'parent_run_id': 'original-loop'}
    if condition == 'different_parent': kwargs['processing_parent_run_id'] = 'other-parent'
    elif condition == 'different_domain': kwargs['processing_domain_id'] = 'other-domain'
    elif condition == 'different_task': kwargs['canonical_task_id'] = 'other-task'
    with pytest.raises(PermissionError):
        loop_api.start_run('loop', 'human', **kwargs)
