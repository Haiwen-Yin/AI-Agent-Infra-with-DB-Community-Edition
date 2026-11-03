"""Offline original-domain Loop/TaskStep processing hooks and rollback checks."""
import json
from decimal import Decimal

import pytest

from lib import connection, graph_compat, loop_api, processing_graph as graph
from lib import processing_legacy as legacy, processing_recovery as recovery, task_plan_api
from lib.continuity_state import ContinuityConflict, ContinuityError
from .test_v502_processing_graph import ledger


def test_native_json_numbers_keep_step_receipts_identical_to_text_json(native, monkeypatch):
    original_query = native.query
    json_columns = {'tool_input', 'tool_output', 'config_json'}
    def native_json_query(sql, params):
        rows = original_query(sql, params)
        for row in rows:
            for key in json_columns & row.keys():
                if isinstance(row[key], str):
                    row[key] = json.loads(row[key], parse_int=Decimal, parse_float=Decimal)
        return rows
    monkeypatch.setattr(native, 'query', native_json_query)
    output = dict(requests=0, nested=[dict(ratio=0.25, count=42)])
    assert task_plan_api.update_step('step', status='SUCCESS', tool_output=output)
    observed = task_plan_api._row_to_dict(native.query_one('SELECT * FROM TASK_STEPS WHERE STEP_ID=:id', {'id':'step'}))
    assert observed['tool_output'] == output
    assert json.dumps(observed['tool_output']) == json.dumps(output)
    assert graph.digest(graph._json(dict(n=Decimal('0.25'), items=[Decimal(42)]))) == graph.digest(dict(n=0.25, items=[42]))
    assert budget(native)['steps_used'] == 1


@pytest.mark.parametrize('value', ['NaN', 'Infinity', '-Infinity', '9' * 400 + '.1'])
def test_nonfinite_native_json_numbers_cannot_become_processing_receipts(value):
    with pytest.raises(ValueError):
        graph._json(dict(n=Decimal(value)))


@pytest.mark.parametrize('plan_id',[122,Decimal(122),'PLAN_ORACLE_122'])
def test_native_plan_locator_is_text_at_compatibility_binding_boundary(plan_id):
    class NativeDraftTransaction:
        def query_one(self,sql,params):
            if 'FROM TASK_STEPS' in sql:
                return dict(plan_id=plan_id,current_plan_status='PENDING',description='Original task')
            if 'FROM GRAPH_COMPAT_BINDINGS' in sql:
                if type(params['plan']) is not str:
                    raise TypeError('Native VARCHAR comparison does not accept a numeric bind')
                assert params['plan']==str(plan_id)
                return None
            pytest.fail('Unexpected native draft query')
        def execute(self,sql,params):
            assert sql.startswith('UPDATE TASK_STEPS SET DESCRIPTION=')
            return 1
    assert legacy.update_step(NativeDraftTransaction(),'148',dict(description='Edited draft'))


@pytest.fixture
def native(ledger, monkeypatch):
    ledger.db.executescript("""
        CREATE TABLE GRAPH_COMPAT_BINDINGS(LEGACY_KIND TEXT,LEGACY_ID TEXT,GRAPH_ID TEXT,
            GRAPH_VERSION_ID TEXT,GRAPH_RUN_ID TEXT,STATUS TEXT,READ_ONLY TEXT);
        CREATE TABLE LOOP_RUNS(RUN_ID TEXT PRIMARY KEY,LOOP_ID TEXT,AGENT_ID TEXT,STATUS TEXT,
            ITERATION_COUNT INTEGER DEFAULT 0,TOTAL_TOKENS INTEGER DEFAULT 0,COMPLETED_AT TIMESTAMP,FINAL_RESULT TEXT);
        CREATE TABLE LOOP_META(ENTITY_ID TEXT PRIMARY KEY,GOAL_DEFINITION TEXT,STOP_CONDITIONS TEXT,EVALUATION_CONFIG TEXT,TRIGGER_CONFIG TEXT);
        CREATE TABLE LOOP_ITERATIONS(ITERATION_ID TEXT PRIMARY KEY,RUN_ID TEXT,ITERATION_ORDER INTEGER,
            PLAN_DATA TEXT,ACTIONS TEXT,OBSERVATIONS TEXT,EVALUATION_RESULT TEXT,EVALUATION_PASSED TEXT,
            ADJUSTMENT TEXT,TOKEN_USAGE INTEGER,STARTED_AT TIMESTAMP DEFAULT CURRENT_TIMESTAMP,COMPLETED_AT TIMESTAMP);
        CREATE TABLE TASK_STEPS(STEP_ID TEXT PRIMARY KEY,PLAN_ID TEXT,DESCRIPTION TEXT,TOOL_NAME TEXT,
            TOOL_INPUT TEXT,TOOL_OUTPUT TEXT,ASSIGNED_AGENT_ID TEXT,STATUS TEXT,STARTED_AT TIMESTAMP,COMPLETED_AT TIMESTAMP);
        CREATE TABLE TASK_TOOL_CALLS(CALL_ID TEXT PRIMARY KEY,PLAN_ID TEXT,STEP_ID TEXT,TOOL_NAME TEXT,
            TOOL_INPUT TEXT,TOOL_OUTPUT TEXT,STATUS TEXT,DURATION_MS INTEGER);
        ALTER TABLE GRAPH_READY_NODES ADD COLUMN RUN_ID TEXT;
        ALTER TABLE GRAPH_NODES ADD COLUMN CONFIG_JSON TEXT;
        UPDATE GRAPH_READY_NODES SET RUN_ID='run';
        UPDATE TASK_PLANS SET AGENT_ID='human' WHERE PLAN_ID='plan';
        INSERT INTO GRAPH_COMPAT_BINDINGS VALUES('LOOP_RUN','loop-run','g','version','run','ACTIVE','N');
        INSERT INTO GRAPH_COMPAT_BINDINGS VALUES('TASK_PLAN','plan','g','version','run','ACTIVE','N');
        INSERT INTO LOOP_RUNS(RUN_ID,LOOP_ID,AGENT_ID,STATUS) VALUES('loop-run','loop','human','RUNNING');
        INSERT INTO LOOP_META VALUES('loop','{}','{}','{}','{}');
        INSERT INTO GRAPH_NODES VALUES('version','loop','NONE','{"legacy_id":"loop","goal_definition":{},"stop_conditions":{},"evaluation_config":{},"trigger_config":{}}');
        INSERT INTO GRAPH_NODES VALUES('version','task:step','NONE','{"legacy_kind":"TASK_STEP","legacy_id":"step","description":"Original task","tool_name":"tool/native","assigned_agent_id":"human"}');
        INSERT INTO TASK_STEPS(STEP_ID,PLAN_ID,DESCRIPTION,TOOL_NAME,TOOL_INPUT,ASSIGNED_AGENT_ID,STATUS)
            VALUES('step','plan','Original task','tool/native','{"input":"same"}','human','PENDING');
    """)
    ledger.db.commit()
    monkeypatch.setattr(loop_api, "get_run", lambda identity: ledger.query_one("SELECT * FROM LOOP_RUNS WHERE RUN_ID=:id", {"id": identity}))
    monkeypatch.setattr(task_plan_api, "execute_query_one", ledger.query_one)
    monkeypatch.setattr(graph_compat, "sync_loop_iteration", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(graph_compat, "sync_task_step", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(recovery, "_default_authority", lambda tx, actor, target, operation:
                        (graph.authorize_target if target.target_kind == "GRAPH" else legacy.authorize_target)(tx, actor, target, operation))
    return ledger


def iteration(native, *, observations=None, token_usage=7):
    return native.run(lambda tx: legacy.record_iteration(tx, "loop-run", plan_data={"goal": "same"}, actions={"tool": "read"},
        observations=observations or {"output": "same"}, evaluation_result=None, evaluation_passed=False,
        adjustment=None, token_usage=token_usage))


def budget(native):
    return native.run(lambda tx: recovery._budget(tx, graph._root(tx, "run")["continuity_id"]))


def test_iteration_receipt_and_real_shadow_attempt_share_existing_graph_budget_after_restart(native):
    identity = iteration(native)
    current = budget(native)
    receipt = native.query_one("SELECT * FROM LOOP_ITERATIONS WHERE ITERATION_ID=:id", {"id": identity})
    attempt = native.query_one("SELECT * FROM CX_TASK_CONTINUITY_ATTEMPTS WHERE BUSINESS_KEY=:id", {"id": identity})
    assert receipt["completed_at"] and attempt["status"] == "SUCCEEDED"
    assert attempt["attempt_id"] != identity
    assert current["steps_used"] == 1 and current["tokens_used"] == 7 and current["requests_used"] == 0
    native.restart()
    assert budget(native)["budget_id"] == current["budget_id"]
    replay = native.run(lambda tx: legacy.account(tx, "LOOP", "loop-run", identity, action_kind="ITERATION", tool_name="loop.iteration", token_count=7))
    assert replay["replayed"] and budget(native)["steps_used"] == 1


def test_native_write_counters_attempt_and_budget_roll_back_together(native, monkeypatch):
    original = legacy.account

    def fail_after_account(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("injected original transaction failure")

    monkeypatch.setattr(legacy, "account", fail_after_account)
    with pytest.raises(RuntimeError, match="original transaction"):
        iteration(native)
    assert native.query_one("SELECT COUNT(*) AS count FROM LOOP_ITERATIONS", {})["count"] == 0
    assert native.query_one("SELECT * FROM LOOP_RUNS WHERE RUN_ID='loop-run'", {})["iteration_count"] == 0
    assert native.query_one("SELECT COUNT(*) AS count FROM CX_TASK_CONTINUITY_ATTEMPTS", {})["count"] == 0
    assert budget(native)["steps_used"] == budget(native)["tokens_used"] == 0


def test_replaying_receipt_cannot_substitute_token_usage(native):
    identity = iteration(native, token_usage=7)
    with pytest.raises(ContinuityConflict, match="original native iteration receipt"):
        native.run(lambda tx: legacy.account(tx, "LOOP", "loop-run", identity, action_kind="ITERATION", tool_name="loop.iteration", token_count=0))
    assert budget(native)["tokens_used"] == 7


def test_new_iteration_ids_do_not_reset_repeat_or_no_progress_counts(native):
    identities = [iteration(native) for _ in range(3)]
    assert len(set(identities)) == 3
    current = budget(native)
    assert current["steps_used"] == 3 and current["no_progress_count"] == 2
    assert native.query_one("SELECT REASON_CODE FROM CX_PROCESSING_BLOCKS", {})["reason_code"] == "REPEATED_ACTION"
    assert loop_api.get_run("loop-run")["status"] == "PAUSED"
    assert native.query_one("SELECT STATUS FROM GRAPH_RUNS WHERE RUN_ID='run'", {})["status"] == "REVIEW_REQUIRED"
    native.restart()
    with pytest.raises(ContinuityConflict, match="Explicit bounded"):
        iteration(native, observations={"changed": True})
    assert budget(native)["steps_used"] == 3


def test_loop_step_and_tool_receipts_consume_the_same_budget_without_observing_external_effects(native):
    first = iteration(native)
    task_plan_api.update_step("step", status="RUNNING")
    call = task_plan_api.log_tool_call("plan", "step", "tool/native", {"read": "same"}, {"result": "value"}, "SUCCESS", 1)
    task_plan_api.update_step("step", status="SUCCESS", tool_output={"value": 1})
    assert call != first and budget(native)["steps_used"] == 4
    assert budget(native)["tokens_used"] == 7 and budget(native)["requests_used"] == 0
    assert native.query_one("SELECT COUNT(DISTINCT BUDGET_ID) AS count FROM CX_PROCESSING_CHAINS", {})["count"] == 1
    assert native.query_one("SELECT COUNT(*) AS count FROM CX_TASK_CONTINUITY_ATTEMPTS WHERE STATUS='SUCCEEDED'", {})["count"] == 4


def test_status_cycles_have_distinct_native_event_identities_and_cannot_replay_away_usage(native):
    task_plan_api.update_step("step", status="RUNNING")
    task_plan_api.update_step("step", status="PENDING")
    task_plan_api.update_step("step", status="RUNNING")
    assert budget(native)["steps_used"] == 3
    assert native.query_one("SELECT COUNT(DISTINCT BUSINESS_KEY) AS count FROM CX_PROCESSING_TARGETS WHERE TARGET_KIND='TASK_STEP'", {})["count"] == 3


def test_tool_output_or_new_receipt_id_cannot_disguise_repeated_tool_and_arguments(native):
    identities = [task_plan_api.log_tool_call("plan", "step", "tool/native", {"read": "same"}, {"result": number}, "SUCCESS") for number in range(3)]
    assert len(set(identities)) == 3
    assert native.query_one("SELECT REASON_CODE FROM CX_PROCESSING_BLOCKS", {})["reason_code"] == "REPEATED_ACTION"
    with pytest.raises(ContinuityConflict, match="Explicit bounded"):
        task_plan_api.log_tool_call("plan", "step", "tool/native", {"other": "value"})
    assert budget(native)["steps_used"] == 3


def test_task_tool_parent_and_original_input_substitution_are_rejected_without_writes(native):
    with pytest.raises(ContinuityConflict, match="different Task Plan"):
        task_plan_api.log_tool_call("other-plan", "step", "tool/native")
    with pytest.raises(ContinuityConflict, match="original definition"):
        task_plan_api.update_step("step", status="RUNNING", tool_input={"replacement": True})
    with pytest.raises(ContinuityError, match="exact original Task Step"):
        task_plan_api.log_tool_call("plan", None, "tool/native")
    assert native.query_one("SELECT COUNT(*) AS count FROM TASK_TOOL_CALLS", {})["count"] == 0
    assert budget(native)["steps_used"] == 0


def test_nonexecuting_draft_definition_edits_preserve_existing_api(native):
    native.run(lambda tx: tx.execute("UPDATE TASK_PLANS SET STATUS='PENDING' WHERE PLAN_ID='plan'", {}))
    native.run(lambda tx: tx.execute("UPDATE GRAPH_COMPAT_BINDINGS SET GRAPH_RUN_ID=NULL WHERE LEGACY_KIND='TASK_PLAN'", {}))
    assert task_plan_api.update_step("step", description="Edited draft", tool_input={"draft": True})
    assert budget(native)["steps_used"] == 0
    assert native.query_one("SELECT DESCRIPTION FROM TASK_STEPS WHERE STEP_ID='step'", {})["description"] == "Edited draft"


@pytest.mark.parametrize("changed", ("missing", "read_only", "actor"))
def test_missing_ambiguous_or_changed_original_binding_fails_closed(native, changed):
    if changed == "missing":
        native.run(lambda tx: tx.execute("DELETE FROM GRAPH_COMPAT_BINDINGS WHERE LEGACY_KIND='LOOP_RUN'", {}))
    elif changed == "read_only":
        native.run(lambda tx: tx.execute("UPDATE GRAPH_COMPAT_BINDINGS SET READ_ONLY='Y' WHERE LEGACY_KIND='LOOP_RUN'", {}))
    else:
        native.run(lambda tx: tx.execute("UPDATE LOOP_RUNS SET AGENT_ID='agent' WHERE RUN_ID='loop-run'", {}))
    with pytest.raises((ContinuityError, PermissionError)):
        iteration(native)
    assert budget(native)["steps_used"] == 0


def test_revoked_original_authority_rolls_back_native_receipt(native):
    native.authorized = False
    with pytest.raises(PermissionError, match="revoked"):
        iteration(native)
    assert native.query_one("SELECT COUNT(*) AS count FROM LOOP_ITERATIONS", {})["count"] == 0


def test_unknown_graph_attempt_blocks_loop_step_tool_and_resume_after_restart(native):
    native.native_attempt()
    native.run(lambda tx: graph.finish(tx, "ga1", outcome="UNOBSERVED", error_code="POSSIBLE_SEND"))
    native.run(lambda tx: tx.execute("UPDATE LOOP_RUNS SET STATUS='PAUSED' WHERE RUN_ID='loop-run'", {}))
    native.run(lambda tx: tx.execute("UPDATE GRAPH_RUNS SET STATUS='PAUSED' WHERE RUN_ID='run'", {}))
    native.restart()
    for callback in (lambda: iteration(native), lambda: task_plan_api.update_step("step", status="RUNNING"),
                     lambda: task_plan_api.log_tool_call("plan", "step", "read"), lambda: loop_api.resume_run("loop-run")):
        with pytest.raises(ContinuityConflict, match="Reconcile"):
            callback()
    assert loop_api.get_run("loop-run")["status"] == "PAUSED"
    assert budget(native)["steps_used"] == 1


def test_step_diagnostic_target_requires_its_exact_original_revision_and_input(native):
    task_plan_api.log_tool_call("plan", "step", "tool/native", {"input": 1}, {"output": 2}, "SUCCESS")
    stored = native.query_one("SELECT * FROM CX_PROCESSING_TARGETS WHERE TARGET_KIND='TASK_STEP'", {})
    target = recovery._target(stored)
    native.run(lambda tx: legacy.authorize_target(tx, "human", target, "READ"))
    native.run(lambda tx: tx.execute("UPDATE TASK_STEPS SET TOOL_INPUT='{}' WHERE STEP_ID='step'", {}))
    with pytest.raises(ContinuityConflict, match="original inputs"):
        native.run(lambda tx: legacy.authorize_target(tx, "human", target, "READ"))
    with pytest.raises(ContinuityConflict, match="original inputs"):
        task_plan_api.log_tool_call("plan", "step", "replacement")


@pytest.mark.parametrize("resource", ("loop", "step"))
def test_native_definitions_must_match_their_frozen_compatibility_graph(native, resource):
    if resource == "loop":
        native.run(lambda tx: tx.execute("UPDATE LOOP_META SET EVALUATION_CONFIG=:value WHERE ENTITY_ID='loop'", {"value": '{"eval_type":"changed"}'}))
        invoke = lambda: iteration(native)
    else:
        native.run(lambda tx: tx.execute("UPDATE TASK_STEPS SET DESCRIPTION='replacement' WHERE STEP_ID='step'", {}))
        invoke = lambda: task_plan_api.update_step("step", status="RUNNING")
    with pytest.raises(ContinuityConflict, match="original compiled Graph"):
        invoke()
    assert budget(native)["steps_used"] == 0


@pytest.mark.parametrize("value", (-1, True, 1.5, 1000000001))
def test_invalid_legacy_usage_cannot_create_a_receipt(native, value):
    with pytest.raises(ContinuityError, match="bounded integer"):
        iteration(native, token_usage=value)
    assert native.query_one("SELECT COUNT(*) AS count FROM LOOP_ITERATIONS", {})["count"] == 0


@pytest.mark.parametrize("table,identity", (("LOOP_ITERATIONS", "ITERATION_ID"), ("TASK_TOOL_CALLS", "CALL_ID")))
def test_postgres_insert_uses_native_identity_and_returns_its_exact_business_key(monkeypatch, table, identity):
    monkeypatch.setattr(connection, "DATABASE_DIALECT", "postgresql")

    class NativeIdentity:
        def query_one(self, sql, values):
            assert sql.startswith("INSERT INTO " + table + "(RUN_ID)")
            assert sql.endswith(" RETURNING " + identity)
            assert identity not in values
            return {identity.lower(): 42}

        def execute(self, *_args):
            pytest.fail("PostgreSQL GENERATED ALWAYS identity cannot be replaced by a supplied UUID")

    assert legacy._insert_id(NativeIdentity(), table, identity, {"RUN_ID": "original"}) == "42"


def test_public_loop_api_receipt_commits_accounting_before_compatibility_sync(native, monkeypatch):
    called = []

    def sync(*args, **kwargs):
        assert budget(native)["steps_used"] == 1
        called.append(args)

    monkeypatch.setattr(graph_compat, "sync_loop_iteration", sync)
    identity = loop_api.record_iteration("loop-run", observations={"source": "original"}, token_usage=2)
    assert called and called[0][1]["iteration_id"] == identity
    assert budget(native)["tokens_used"] == 2


def test_budget_stop_prevents_further_evaluation_in_public_loop_engine(native, monkeypatch):
    monkeypatch.setattr(loop_api, "check_stop_conditions", lambda _run: "CONTINUE")
    monkeypatch.setattr(loop_api, "evaluate_iteration", lambda *_args: pytest.fail("Stopped loop must not evaluate or send"))
    iteration(native)
    iteration(native)
    result = loop_api.execute_loop_iteration("loop-run", "human", plan_data={"goal": "same"}, actions={"tool": "read"},
                                             observations={"output": "same"}, token_usage=7)
    assert result["run_status"] == "PAUSED" and result["evaluation"] is None


@pytest.mark.parametrize("controlled", (True, False))
def test_only_registered_capacity_endpoint_requires_an_adapter_for_legacy_llm_judge(native, monkeypatch, controlled):
    from lib import model_endpoint_capacity
    monkeypatch.setattr(loop_api, "get_config", lambda: {"llm_judge": {"enabled": True, "api_url": "http://example.invalid/v1/chat/completions"}})
    monkeypatch.setattr(model_endpoint_capacity, "selected_group", lambda _tx, profile, url: "group" if controlled else None)
    sent = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

        def read(self):
            return json.dumps({"choices": [{"message": {"content": '{"score":8,"reasoning":"observed"}'}}]}).encode()

    monkeypatch.setattr(loop_api.urllib.request, "urlopen", lambda request, **_kwargs: sent.append(request) or Response())
    result = loop_api._eval_llm_judge({}, {"observations": {"output": "value"}})
    assert bool(sent) is not controlled
    if controlled:
        assert result["error_code"] == "PROCESSING_MODEL_ADAPTER_REQUIRED" and result["blocked"]
    else:
        assert result["passed"]


def test_capacity_lookup_failure_never_falls_back_to_uncontrolled_send(native, monkeypatch):
    from lib import model_endpoint_capacity
    monkeypatch.setattr(loop_api, "get_config", lambda: {"llm_judge": {"enabled": True, "api_url": "http://example.invalid"}})

    def unavailable(*_args):
        raise PermissionError("coordinator unavailable")

    monkeypatch.setattr(model_endpoint_capacity, "selected_group", unavailable)
    monkeypatch.setattr(loop_api.urllib.request, "urlopen", lambda *_args, **_kwargs: pytest.fail("No coordinator fallback send"))
    with pytest.raises(PermissionError, match="coordinator"):
        loop_api._eval_llm_judge({}, {})


def test_legacy_completion_path_cannot_bypass_registered_provider_base_alias(native, monkeypatch):
    from lib import model_endpoint_capacity
    full_url = "http://example.invalid/v1/chat/completions"
    base_url = "http://example.invalid/v1"
    checked = []
    monkeypatch.setattr(loop_api, "get_config", lambda: {"llm_judge": {"enabled": True, "api_url": full_url}})

    def locate(_tx, profile, endpoint):
        checked.append(endpoint)
        return "group" if endpoint == base_url else None

    monkeypatch.setattr(model_endpoint_capacity, "selected_group", locate)
    monkeypatch.setattr(loop_api.urllib.request, "urlopen", lambda *_args, **_kwargs: pytest.fail("Registered base must not send"))
    result = loop_api._eval_llm_judge({}, {})
    assert result["error_code"] == "PROCESSING_MODEL_ADAPTER_REQUIRED"
    assert checked == [full_url, base_url]
