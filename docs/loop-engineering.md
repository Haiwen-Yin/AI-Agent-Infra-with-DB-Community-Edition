# Loop engineering v5.0.1

> Installed product: **Chuanxu Community Edition**; supported backends: **oracle, pg, yashandb**; edition: **Community**; license: **Apache-2.0**. Other backends and Enterprise-only capabilities discussed below describe differences; they do not extend this package's scope.

[简体中文](loop-engineering_zh.md)

## Purpose and entities

A Loop records a goal, bounded iterations, observations, evaluation and stop
conditions. This guide describes this product's implementation; it does not
claim a universally agreed sequence of engineering methodologies or an
unverified attribution.

A Definition is an `ENTITIES` row of type `LOOP_DEFINITION`, extended by
`LOOP_META`. Runs, Iterations and Hooks have separate database records.
A Harness supplies an optional execution blueprint. A Loop can link a Context
Branch, Workspace Context and Task Plan/Step instead of creating a separate
untyped orchestration store. The selected database adapter persists the facts;
vendor-specific SQL remains in that adapter.

## Operator workflow

1. Create a Definition with goal, owner/Agent, evaluation configuration and
   explicit iteration, Token and duration limits.
2. Start a Run and record each intent, action, observation, adjustment and
   measured consumption through the authorized service.
3. Evaluate the committed iteration; inspect the result and evidence before
   deciding whether to continue.
4. Pause/resume, stop, fail or complete the Run explicitly. Inspect current
   state and stop conditions after a process restart.
5. Preserve the Run/Iteration history and any bound task outcome.

Use Dashboard `/app/loops` or authenticated loop routes from the
[API reference](api-reference.md). Python helpers in `lib.loop_api` are
service implementation APIs, not permission to run as the schema Owner from
an ordinary Agent. A Loop record does not autonomously run arbitrary code.
Tools, models, Skills and external effects retain their existing authorization
and runtime controls.

## Evaluation and hooks

Supported evaluation types are `TEST`, `DIFF`, `LLM_JUDGE`, `MANUAL`,
`SPEC_VALIDATION` and `AGGREGATE`. Keep the input observation and evaluator
configuration with the result. A model judge needs an approved, usable model;
its output is evidence for a decision, not authority to change permissions or
publish Knowledge. Test/diff evaluators consume bounded structured observations.

Hooks record lifecycle behavior such as `PRE_RUN`, `POST_ITERATION`,
`ON_STOP`, `ON_FAIL`, `ON_TIMEOUT` and `ON_START`. Hook type and handler
support are implementation-specific; declaring a hook is not proof a remote
effect ran. Check the current service result and audit.

## Reuse of existing capabilities

| Link | Behavior and boundary |
|---|---|
| Specification | `create_loop_from_spec` derives the goal from accepted criteria; inspect the derived input |
| Task Step | `bind_loop_to_step` records `TASK_LOOP_BINDING`; completion updates the bound step through the existing lifecycle |
| Branch | A bound branch supplies isolated context; merge remains a separate governed decision |
| Skill | A configured validation loop may be created during Skill acquisition |
| Collaborative Loop | Child runs aggregate observations; historical collaboration-group links do not grant Security Domain access |

The service limits collaborative nesting to two levels. Task completion types
include `MANUAL`, `LOOP` and `SPEC`; a waiting step can enter
`WAITING_LOOP`. Completion callbacks retain the original relationship and
must not infer missing work from an old success marker.

## Recovery and evidence

The database stores current state and iteration history, allowing authorized
inspection after an Agent restart. This is not a guarantee that an arbitrary
external action is retried safely or that every model conversation resumes.
Record uncertain effects and reconcile them rather than sending again.
Respect current permissions and source revocation when reconstructing context.

Use [Graph engineering](graph-engineering.md) for leased Graph execution,
[workspace operations](workspace.md) for branch/context lifecycle, and
[recovery](recovery.md) for process and database recovery boundaries. Do not
replace those durable services with an independent Loop scheduler or claim
database-cluster HA from process restart tests.
