"""Exact Loop/TaskStep events sharing their existing Graph processing budget.

These hooks account native durable records. They do not observe actions a
client performed before submitting a record and do not add an executor.
"""
from __future__ import annotations

import json
from . import connection, processing_graph as graph, processing_recovery as recovery, task_continuity as tasks
from .agent_extension_contracts import digest, row, identifier
from .continuity_state import ContinuityConflict, ContinuityError


def enabled():
    return recovery.schema_enabled()


def _binding(tx, kind, legacy_id):
    value = row(tx.query_one("SELECT * FROM GRAPH_COMPAT_BINDINGS WHERE LEGACY_KIND=:kind AND LEGACY_ID=:id FOR UPDATE",
                            {"kind": kind, "id": str(legacy_id)}))
    if not value or not value.get("graph_run_id") or value.get("status") != "ACTIVE" or value.get("read_only") == "Y":
        raise ContinuityError("PROCESSING_LEGACY_BINDING_REQUIRED", "An exact active native Graph compatibility binding is required")
    root = graph._root(tx, value["graph_run_id"])
    if not root:
        raise ContinuityError("PROCESSING_LEGACY_BINDING_REQUIRED", "The compatibility Graph requires its original processing budget")
    native = graph._run(tx, value["graph_run_id"])
    if value.get("graph_version_id") != native["graph_version_id"]:
        raise ContinuityConflict("STALE_TARGET", "The compatibility mapping changed its original Graph version")
    return value, root


def _resource(tx, kind, entity):
    if kind == "LOOP":
        resource = row(tx.query_one("SELECT * FROM LOOP_RUNS WHERE RUN_ID=:id FOR UPDATE", {"id": entity}))
        if not resource:
            raise PermissionError("The original Loop Run is unavailable")
        binding, root = _binding(tx, "LOOP_RUN", resource["run_id"])
        if resource["agent_id"] != root["actor_id"]:
            raise PermissionError("The Loop's original execution actor changed")
        definition = row(tx.query_one("SELECT GOAL_DEFINITION,STOP_CONDITIONS,EVALUATION_CONFIG,TRIGGER_CONFIG FROM LOOP_META WHERE ENTITY_ID=:loop_id",
                                      {"loop_id": resource["loop_id"]}))
        node = row(tx.query_one("SELECT CONFIG_JSON FROM GRAPH_NODES WHERE GRAPH_VERSION_ID=:version AND NODE_KEY='loop'",
                                {"version": binding["graph_version_id"]}))
        config = graph._json(node.get("config_json"))
        if (not definition or config.get("legacy_id") != str(resource["loop_id"]) or
                any(graph._json(definition.get(name)) != config.get(name, {}) for name in
                    ("goal_definition", "stop_conditions", "evaluation_config", "trigger_config"))):
            raise ContinuityConflict("STALE_TARGET", "The Loop definition differs from its original compiled Graph")
    elif kind == "TASK_STEP":
        resource = row(tx.query_one("SELECT s.*,p.AGENT_ID AS PLAN_AGENT_ID FROM TASK_STEPS s JOIN TASK_PLANS p "
                                    "ON p.PLAN_ID=s.PLAN_ID WHERE s.STEP_ID=:id FOR UPDATE", {"id": entity}))
        if not resource:
            raise PermissionError("The original Task Step is unavailable")
        binding, root = _binding(tx, "TASK_PLAN", resource["plan_id"])
        if resource["plan_agent_id"] != root["actor_id"]:
            raise PermissionError("The Task Step's original execution actor changed")
        node = row(tx.query_one("SELECT CONFIG_JSON FROM GRAPH_NODES WHERE GRAPH_VERSION_ID=:version AND NODE_KEY=:node_key",
                                {"version": binding["graph_version_id"], "node_key": "task:" + str(entity)}))
        config = graph._json(node.get("config_json"))
        if (config.get("legacy_kind") != "TASK_STEP" or config.get("legacy_id") != str(entity) or
                config.get("description") != str(resource.get("description") or "") or
                config.get("tool_name") != (str(resource.get("tool_name") or "").strip() or None) or
                config.get("assigned_agent_id") != resource.get("assigned_agent_id")):
            raise ContinuityConflict("STALE_TARGET", "The Task Step differs from its original compiled Graph")
    else:
        raise ValueError("Unsupported native processing resource")
    previous = [row(item) for item in tx.query("SELECT t.TARGET_REVISION,c.ORIGINAL_CONTINUITY_ID FROM CX_PROCESSING_TARGETS t "
        "JOIN CX_PROCESSING_CHAINS c ON c.CONTINUITY_ID=t.CONTINUITY_ID WHERE t.TARGET_KIND=:kind AND t.TARGET_ID=:entity",
        {"kind": kind, "entity": str(entity)})]
    if any(item["target_revision"] != _revision(resource, binding) or item["original_continuity_id"] != root["continuity_id"] for item in previous):
        raise ContinuityConflict("STALE_TARGET", "The native operation cannot replace its original inputs or processing budget")
    return resource, binding, root


def _revision(resource, binding):
    fields = {"graph_run": binding["graph_run_id"], "graph_version": binding["graph_version_id"]}
    if "step_id" in resource:
        fields.update({key: resource.get(key) for key in ("step_id", "plan_id", "description", "tool_name", "assigned_agent_id")})
        fields["tool_input"] = graph._json(resource.get("tool_input"))
    else:
        fields.update({key: resource.get(key) for key in ("run_id", "loop_id", "agent_id")})
    return digest(fields)


def _payload(tx, kind, target, resource):
    if kind == "LOOP":
        record = row(tx.query_one("SELECT * FROM LOOP_ITERATIONS WHERE ITERATION_ID=:id AND RUN_ID=:run",
                                  {"id": target.business_key, "run": target.target_id}))
        if not record:
            raise PermissionError("The original Loop iteration is unavailable")
        return {key: graph._json(record.get(key)) for key in ("plan_data", "actions", "observations")} | {"token_usage": int(record.get("token_usage") or 0)}
    if target.business_key.startswith("step:"):
        return {key: resource.get(key) for key in ("step_id", "status", "tool_name")} | {
            "tool_input": graph._json(resource.get("tool_input")), "tool_output": graph._json(resource.get("tool_output"))}
    record = row(tx.query_one("SELECT * FROM TASK_TOOL_CALLS WHERE CALL_ID=:id AND STEP_ID=:step AND PLAN_ID=:plan",
                              {"id": target.business_key, "step": target.target_id, "plan": resource["plan_id"]}))
    if not record:
        raise PermissionError("The original Task tool call is unavailable")
    return {key: record.get(key) for key in ("tool_name", "status")} | {
        "tool_input": graph._json(record.get("tool_input")), "tool_output": graph._json(record.get("tool_output"))}


def authorize_target(tx, actor, target, operation):
    target = recovery.ExactTarget.model_validate(target)
    resource, binding, root = _resource(tx, target.target_kind, target.target_id)
    frozen = row(tx.query_one("SELECT * FROM CX_PROCESSING_TARGETS WHERE CONTINUITY_ID=:chain", {"chain": root["continuity_id"]}))
    if not frozen:
        raise ContinuityError("PROCESSING_LEGACY_BINDING_REQUIRED", "The original Graph target is required")
    graph.authorize_target(tx, actor, recovery._target(frozen), operation)
    if target.target_revision != _revision(resource, binding) or target.input_digest != digest(_payload(tx, target.target_kind, target, resource)):
        raise ContinuityConflict("STALE_TARGET", "The original native Loop/Task Step facts changed")


def gate(tx, kind, entity):
    resource, binding, root = _resource(tx, kind, entity)
    graph.control_gate(tx, binding["graph_run_id"])
    return resource, binding, root


def account(tx, kind, entity, business_key, *, action_kind, tool_name, token_count=0):
    resource, binding, root = _resource(tx, kind, entity)
    budget = recovery._budget(tx, root["continuity_id"])
    proto_target = recovery.ExactTarget(continuity_id=root["continuity_id"], target_kind=kind, target_id=str(entity),
        target_revision=_revision(resource, binding), input_digest="0" * 64, business_key=str(business_key))
    payload = _payload(tx, kind, proto_target, resource)
    if kind == "LOOP" and token_count != payload["token_usage"]:
        raise ContinuityConflict("PROCESSING_USAGE_CONFLICT", "Usage must match the original native iteration receipt")
    arguments = ({key: payload[key] for key in ("tool_name", "tool_input")} if action_kind == "TOOL_CALL" else
                 {key: value for key, value in payload.items() if key != "token_usage"})
    input_digest = digest(payload)
    event = digest({"kind": kind, "entity": str(entity), "key": str(business_key), "input": input_digest})
    linked = tasks.link_protocol_task(tx, actor=root["actor_id"], security_domain_id=root["security_domain_id"], link_kind="GRAPH",
        link_id="legacy:" + event, canonical_task_id=root["canonical_task_id"], idempotency_key="legacy:" + event,
        request_digest=event, input_digest=input_digest, reason="Durable original-domain legacy event")
    target = proto_target.model_copy(update={"continuity_id": linked["continuity_id"], "input_digest": input_digest})
    existing = row(tx.query_one("SELECT * FROM CX_PROCESSING_CHAINS WHERE CONTINUITY_ID=:chain", {"chain": target.continuity_id}))
    if existing:
        return {"replayed": True, "stop": None}
    tx.execute("INSERT INTO CX_PROCESSING_CHAINS(CONTINUITY_ID,BUDGET_ID,ORIGINAL_CONTINUITY_ID) VALUES(:chain,:budget,:original)",
               {"chain": target.continuity_id, "budget": budget["budget_id"], "original": root["continuity_id"]})
    recovery._store_target(tx, target)
    attempt = tasks.claim_attempt(tx, continuity_id=target.continuity_id, worker_id="native-legacy", business_key=str(business_key), request_digest=event)
    target = target.model_copy(update={"attempt_id": attempt["attempt_id"]})
    action = recovery.record_action(tx, actor=root["actor_id"], target=target, action_key="legacy:" + event,
        action_kind=action_kind, tool_name=tool_name, arguments=arguments, request_count=0, step_count=1, token_count=token_count,
        progress_digest=digest({"kind": kind, "record": {key: value for key, value in payload.items() if key != "token_usage"}}), authority=authorize_target)
    # The native receipt is complete. A stop blocks the next operation and is
    # retained even though this recording transaction completed successfully.
    tasks.finish_attempt(tx, attempt_id=attempt["attempt_id"], worker_id="native-legacy", fencing_token=attempt["fencing_token"],
                         status="SUCCEEDED", request_digest=event)
    if action["stop"]:
        tx.execute("UPDATE GRAPH_RUNS SET STATUS='REVIEW_REQUIRED',ERROR_CODE=:reason,UPDATED_AT=CURRENT_TIMESTAMP WHERE RUN_ID=:run "
                   "AND STATUS NOT IN ('SUCCEEDED','CANCELLED')", {"reason": action["stop"]["reason_code"], "run": binding["graph_run_id"]})
    return action


def _insert_id(tx, table, identity, values):
    if connection.DATABASE_DIALECT in {"pg", "postgresql"}:
        columns = list(values)
        record = row(tx.query_one("INSERT INTO " + table + "(" + ",".join(columns) + ") VALUES(" + ",".join(":" + name for name in columns)
                                  + ") RETURNING " + identity, values))
        if not record.get(identity.lower()):
            raise ContinuityError("PROCESSING_NATIVE_ID_REQUIRED", "The database must return its native record identity")
        return str(record[identity.lower()])
    result = identifier("LI" if table == "LOOP_ITERATIONS" else "CALL")
    values = {identity: result, **values}
    tx.execute("INSERT INTO " + table + "(" + ",".join(values) + ") VALUES(" + ",".join(":" + name for name in values) + ")", values)
    return result


def record_iteration(tx, run_id, *, plan_data, actions, observations, evaluation_result, evaluation_passed, adjustment, token_usage):
    if type(token_usage) is not int or not 0 <= token_usage <= 1000000000:
        raise ContinuityError("PROCESSING_USAGE_INVALID", "Loop usage must be a bounded integer")
    resource, _, _ = gate(tx, "LOOP", run_id)
    if resource["status"] != "RUNNING":
        raise ContinuityConflict("PROCESSING_TERMINAL", "Only the current running Loop may record another iteration")
    values = {"RUN_ID": run_id, "ITERATION_ORDER": int(resource["iteration_count"]) + 1,
              "PLAN_DATA": json.dumps(plan_data) if plan_data else None, "ACTIONS": json.dumps(actions) if actions else None,
              "OBSERVATIONS": json.dumps(observations) if observations else None, "EVALUATION_RESULT": json.dumps(evaluation_result) if evaluation_result else None,
              "EVALUATION_PASSED": "Y" if evaluation_passed else "N", "ADJUSTMENT": json.dumps(adjustment) if adjustment else None, "TOKEN_USAGE": token_usage}
    iteration = _insert_id(tx, "LOOP_ITERATIONS", "ITERATION_ID", values)
    tx.execute("UPDATE LOOP_ITERATIONS SET COMPLETED_AT=CURRENT_TIMESTAMP WHERE ITERATION_ID=:iteration", {"iteration": iteration})
    tx.execute("UPDATE LOOP_RUNS SET ITERATION_COUNT=ITERATION_COUNT+1,TOTAL_TOKENS=TOTAL_TOKENS+:tokens WHERE RUN_ID=:run",
               {"tokens": token_usage, "run": run_id})
    action = account(tx, "LOOP", run_id, iteration, action_kind="ITERATION", tool_name="loop.iteration", token_count=token_usage)
    if action["stop"]:
        tx.execute("UPDATE LOOP_RUNS SET STATUS='PAUSED' WHERE RUN_ID=:run", {"run": run_id})
    elif evaluation_passed:
        tx.execute("UPDATE LOOP_RUNS SET STATUS='COMPLETED',COMPLETED_AT=CURRENT_TIMESTAMP,FINAL_RESULT='Goal achieved' WHERE RUN_ID=:run", {"run": run_id})
    return iteration


def update_step(tx, step_id, changes):
    if not changes or set(changes) - {"description", "tool_name", "tool_input", "tool_output", "status", "assigned_agent_id"}:
        raise ValueError("A native Task Step update requires explicitly allowed fields")
    draft = row(tx.query_one("SELECT s.*,p.STATUS AS CURRENT_PLAN_STATUS FROM TASK_STEPS s JOIN TASK_PLANS p "
                             "ON p.PLAN_ID=s.PLAN_ID WHERE s.STEP_ID=:step FOR UPDATE", {"step": step_id}))
    if not draft:
        return False
    binding = row(tx.query_one("SELECT * FROM GRAPH_COMPAT_BINDINGS WHERE LEGACY_KIND='TASK_PLAN' AND LEGACY_ID=:plan", {"plan": str(draft["plan_id"])}))
    design_only = (not binding.get("graph_run_id") and draft["current_plan_status"] == "PENDING" and
                   "tool_output" not in changes and changes.get("status", "PENDING") == "PENDING")
    if not design_only:
        for name in {"description", "tool_name", "tool_input", "assigned_agent_id"} & set(changes):
            original = graph._json(draft.get(name)) if name == "tool_input" else draft.get(name)
            if original != changes[name]:
                raise ContinuityConflict("STALE_TARGET", "A running Task Step cannot substitute its original definition or inputs")
        resource, _, _ = gate(tx, "TASK_STEP", step_id)
    else:
        resource = draft
    params = {"step": step_id}
    assignments = []
    for name, value in changes.items():
        params[name] = json.dumps(value) if name in {"tool_input", "tool_output"} and value is not None else value
        assignments.append(name.upper() + "=:" + name)
    if changes.get("status") == "RUNNING":
        assignments.append("STARTED_AT=CURRENT_TIMESTAMP")
    elif changes.get("status") in {"SUCCESS", "FAILED", "SKIPPED"}:
        assignments.append("COMPLETED_AT=CURRENT_TIMESTAMP")
    changed = tx.execute("UPDATE TASK_STEPS SET " + ",".join(assignments) + " WHERE STEP_ID=:step", params)
    actual_change = any((graph._json(resource.get(name)) if name in {"tool_input", "tool_output"} else resource.get(name)) != value
                        for name, value in changes.items())
    if changed and actual_change and not design_only:
        key = "step:" + str(step_id) + ":" + identifier("EV")
        account(tx, "TASK_STEP", step_id, key, action_kind="ITERATION", tool_name="task.step")
    return changed > 0


def log_tool_call(tx, *, plan_id, step_id, tool_name, tool_input, tool_output, status, duration_ms):
    if not step_id:
        raise ContinuityError("PROCESSING_TASK_STEP_REQUIRED", "A governed native tool call requires its exact original Task Step")
    resource, _, _ = gate(tx, "TASK_STEP", step_id)
    if str(resource["plan_id"]) != str(plan_id):
        raise ContinuityConflict("STALE_TARGET", "The tool call belongs to a different Task Plan")
    key = _insert_id(tx, "TASK_TOOL_CALLS", "CALL_ID", {"PLAN_ID": plan_id, "STEP_ID": step_id, "TOOL_NAME": tool_name,
        "TOOL_INPUT": json.dumps(tool_input) if tool_input is not None else None,
        "TOOL_OUTPUT": json.dumps(tool_output) if tool_output is not None else None, "STATUS": status, "DURATION_MS": duration_ms})
    account(tx, "TASK_STEP", step_id, key, action_kind="TOOL_CALL", tool_name="task.tool")
    return key


def resume_loop(tx, run_id):
    resource, binding, root = gate(tx, "LOOP", run_id)
    if resource["status"] != "PAUSED":
        return False
    run = graph._run(tx, binding["graph_run_id"])
    if run["status"] != "PAUSED":
        raise ContinuityConflict("STALE_TARGET", "The original compatibility Graph is not paused")
    tx.execute("UPDATE LOOP_RUNS SET STATUS='RUNNING' WHERE RUN_ID=:run AND STATUS='PAUSED'", {"run": run_id})
    tx.execute("UPDATE GRAPH_RUNS SET STATUS='RUNNING',UPDATED_AT=CURRENT_TIMESTAMP WHERE RUN_ID=:run AND STATUS='PAUSED'", {"run": binding["graph_run_id"]})
    tx.execute("UPDATE GRAPH_READY_NODES SET STATUS='READY',AVAILABLE_AT=CURRENT_TIMESTAMP WHERE RUN_ID=:run AND STATUS='WAITING'", {"run": binding["graph_run_id"]})
    tx.execute("UPDATE GRAPH_NODE_RUNS SET STATUS='READY',UPDATED_AT=CURRENT_TIMESTAMP WHERE RUN_ID=:run AND STATUS='WAITING'", {"run": binding["graph_run_id"]})
    from . import graph_runtime
    graph_runtime._intervention_tx(tx, binding["graph_run_id"], "RESUME", root["actor_id"], "Native Loop resume with original processing gate")
    return True
