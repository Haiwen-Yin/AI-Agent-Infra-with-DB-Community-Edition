# Graph engineering v5.0.0

> Installed product: **Chuanxu Community Edition**; supported backends: **oracle, pg, yashandb**; edition: **Community**; license: **Apache-2.0**. Other backends and Enterprise-only capabilities discussed below describe differences; they do not extend this package's scope.

[简体中文](graph-engineering_zh.md)

## Execution model

Graph engineering coordinates Agent, Model, Skill, Tool, Database, Human,
Event and Subgraph nodes through a versioned, database-backed execution graph.
Definitions, immutable published Versions, compiled Plans, Runs, Node Runs,
Attempts, State Events, Checkpoints, Artifacts and governance events have
separate relational identities. The entity relationship graph remains a
different projection; a displayed edge does not grant execution authority.

The current product supports oracle, pg, yashandb. Single-backend packages carry one
adapter. The unified Community package selects one backend per process. The
same runtime contract uses the selected database's transactions and constraints;
vendor graph syntax stays in adapters. Oracle and YashanDB native property
graphs and PostgreSQL AGE are rebuildable projections. Authorized relational
traversal remains usable without a current native projection. PostgreSQL
historical text edge endpoints are compared as text, never blindly cast to
BIGINT.

## Capability posture

| Surface | Default and operational boundary |
|---|---|
| Runtime core and authorized inspection | Available with current permissions |
| Manifest draft import, read-only SLO and checkpoint fork | Controlled; evidence and capability checks apply |
| Offline replay and migration preflight | Bounded inspection; no remote effects or live Run movement |
| Registered MCP, A2A, OTLP and pinned framework execution | Independent controlled entry points, disabled until explicitly authorized |
| Arbitrary frameworks, remote-effect replay and online Dynamic Graph migration | Not enabled |

Inspect “Platform configuration → Graph Engineering” and the current database
capability matrix. A package profile, prompt, Agent Card or hidden control
cannot change those states. See [Agent extensions](agent-extensions.md) for
exact supported versions and actions. A2A task-state SSE subscriptions are
implemented within that bounded contract; this is not full SDK, gRPC or push
support.

## Definition to Run

1. Create a Draft with an explicit owner, purpose, nodes, edges, schemas,
   budgets and side-effect classifications.
2. Compile the exact Version. Inspect unresolved executors, invalid routes,
   incompatible schemas and budget diagnostics before publication.
3. Publish through the authorized service. Supply-chain imports always create
   a new Draft; untrusted drafts cannot be published merely because they parse.
4. Start a Run from the published Version and its matching compiled Plan.
   Admission stores Definition/Plan digests, compatibility and schema versions.
5. Inspect Node Runs, committed State, Trace, Attempts, Checkpoints and
   intervention decisions. Cancel, pause, resume or recover only within current
   authority.

Use the Dashboard Graph views or the authenticated API, rather than direct
table mutation. [API reference](api-reference.md) describes routes and
[continuity operations](continuity-operations.md) covers linked work/context.

## Worker and recovery contract

A Worker advertises supported executors, claims bounded work and receives a
short lease and fencing token. Heartbeats, checkpoints and completion must
match current authority. Stale or expired workers cannot commit. Every
executable node resolves to a built-in or database-registered declarative
executor; arbitrary code fields are rejected.

State Events are append-only. Checkpoints persist resumable state, not an
authorization snapshot that overrides revocation. Replacement processes
revalidate identity, source permissions and lease authority against the same
database. Waiting at a collaboration Barrier does not retain a Worker lease.

Exact request replay is idempotent at platform claim/completion boundaries.
This does not make arbitrary remote effects exactly-once. An
`IDEMPOTENT_EXTERNAL` attempt persists a stable logical effect key for a
compatible remote service. `NON_IDEMPOTENT` or uncertain outcomes require
external status confirmation, compensation or human resolution. Do not resend
an unobserved model/tool call automatically.

A checkpoint fork preserves source provenance and starts a distinct child.
Non-repeatable effects pause the child until the necessary decision is
recorded. Dynamic proposals create new Draft Versions and deterministic risk
assessments; they do not rewrite a published Version or move an active Run.

## Events, evaluation and evidence

Inbox/Outbox records retain delivery attempts, retry scheduling and
`DEAD_LETTER` state. Replay requires a reason and remains constrained by the
current operation contract. Evaluators support `MANUAL`, `TEST`, `DIFF`,
`LLM_JUDGE`, `SPEC_VALIDATION` and `AGGREGATE`. A result is attributed,
versioned evidence; it does not independently authorize a Tool or model call.

Run evidence exports are administrator-only at
`/api/graph-runs/{run_id}/evidence`, require a reason and a bounded limit, and
write governance evidence. Artifacts retain digests, classification, retention
and legal-hold metadata; listing metadata does not imply permission to read
content. Metrics describe measured transitions, retries, budget usage and
reliability within their recorded workload, not universal capacity guarantees.

Task Plans, Steps, Loops and Barriers retain their domain entities. A2A and
DB4A2A retain independent transports while linking stable Task Plan/Step
identities and fenced attempts. DB4A2A carries an authorized context reference,
digest, version and scope; it neither copies implicit authority nor establishes
cross-platform A2A conformance. See [DB4A2A](db4a2a.md).

## Operations

Deploy and verify the full selected baseline through migration 102. Preserve
applied SQL digests and migration history. Before restoring or upgrading,
record current runs and drain only affected writers. Use
[recovery](recovery.md) and [migration](migration.md) for the recovery boundary.
Process replacement against the existing database does not establish database
cluster HA, standby promotion or RPO/RTO.
