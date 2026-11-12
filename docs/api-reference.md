# API reference v5.0.5

> Installed product: **Chuanxu Community Edition**; supported backends: **oracle, pg, yashandb**; edition: **Community**; license: **Apache-2.0**. Other backends and Enterprise-only capabilities discussed below describe differences; they do not extend this package's scope.

[简体中文](api-reference_zh.md)

## Authority and current schema

The canonical network application is FastAPI `web_app:app`. Read the running
service's `/openapi.json` (or `/docs`, where exposed) for exact methods,
request schemas and response schemas. Retained Dashboard/Portal routes pass
through the request-local compatibility bridge and do not all appear in the
FastAPI schema. Their implementation is in
[visualization/server.py](../scripts/visualization/server.py); canonical routes
are in [web_app.py](../scripts/web_app.py).

This package supports **oracle, pg, yashandb** and **Community** features. Presence
of an API name is not authority to invoke it. Every operation rechecks its
current Principal/instance, resource permissions, Domain and capability state.
Community physically excludes Enterprise-only implementations.

## Authentication and request conventions

Human login uses `POST /api/auth/login` with `username` and `password`.
The response and cookie establish a session; `GET /api/auth/me` reports its
current identity. Retain cookies in a private client and send the returned
`X-CSRF-Token` for authenticated mutations. Never put credentials in a URL.

`GET /api/auth/registration-policy` reports Human registration policy.
`POST /api/auth/register` submits the permitted Human application; an accepted
application is not necessarily an active login. Human registration and external
Agent Enrollment are independent controls. Logout, password reset, MFA and
federated login use their dedicated `/api/auth/*` routes.

External Agent calls exchange their issued credential/proof at
`POST /api/gateway/token` and use the scoped bearer token. Agent and instance
identity comes from authenticated context, not an arbitrary body identifier.
Use exact schema fields, content types and bounded inputs. Idempotency keys,
expected revisions, lease tokens, reasons and approval references are required
where declared by that operation.

Do not treat an HTTP success as completion of a queued job. Poll the returned
execution/task identity until a terminal or explicitly unobserved state.
Permission, conflict, validation and unavailable-capability responses must be
handled separately; repeated unauthorized calls are not retries.

## Service, identity and administration

| Route or family | Purpose |
|---|---|
| `GET /api/health`, `GET /api/ready` | Process product/version versus database/control-plane readiness |
| `GET /api/capabilities`, `GET /api/runtime/profile` | Current visible identity/edition/runtime capability projection |
| `/api/platform/capabilities`, `/api/platform/graph-capabilities`, `/api/platform/model-capabilities` | Read and reasoned revision-checked capability management |
| `/api/platform/administration`, `/api/platform/admin-enrollments` | Protected management membership and enrollment |
| `/api/platform/session-policies`, `/api/platform/containment` | Session policy and attributed containment outcomes |
| `/api/platform/upgrades` | Package admission, preflight, separated approval, rollout and Skill distribution |
| `/api/platform/native-bootstrap` | Native management identity bootstrap/status |
| `/api/principal-options`, `/api/users`, `/api/organization/*` | Current authorized identity directory and organization projections |
| `/api/security-domains`, `/api/security-domains/{domain_id}/members` | Domain creation, membership, bindings and lifecycle |
| `POST /api/agents/{agent_id}/offboard` | `agents.offboard` plus exact Agent access; platform revocation and separately audited native-login/local-connection result |

Select Principals by readable name/type; submit the immutable identifier returned
by the authorized candidate directory. Duplicate display names are not identities.
Domain membership precedes Channel membership and is not replaced by it.
For offboarding, inspect `native_identity_revocation` rather than treating HTTP
success or a disabled Principal as complete native closure. A COMPLETE result
also needs `audit_status=RECORDED`; it does not assert termination of external
existing sessions. Preconditions, request fields and recovery are in
[native identity operations](native-identity.md).

## External Agent registration and collaboration

Published platform guides already support Agent Bearer discovery:
`GET /api/agent-gateway/continuity/learning?role=AGENT`, followed by
`GET /api/agent-gateway/continuity/learning/{entity_id}?expected_digest={content_digest}`.
Both require current `knowledge.read` and a token containing that scope, without
Channel membership. Directory metadata is in `items`; exact chapter text is
top-level `content`. See [external Agent knowledge access](external-agent-knowledge.md)
for permission changes, combined scopes, optional imports and response handling.

Private Agent Memory uses `POST /api/gateway/memory` and
`GET /api/gateway/memory/{family_id}` (also `/api/agent-gateway/memory`).
Use `memory.read` / `memory.write` scopes and send `title`, `content`, optional
`memory_type`, `classification`, `reason`, and a required 8–256 character
`idempotency_key`. Owner, Agent, Domain and Channel fields are rejected: the
server binds ownership and Domain from the authenticated instance. Registration
explicitly grants only OWNED Memory read/write; activation and active Domain
membership remain required. No Channel membership is required. Creation returns
`family_id`, `version_id`, `version_number`, `lifecycle_state`; GET returns
`{"memory":{"family":...,"current":...}}`. Identical retries reuse the original
version; changed content with the same key returns 409. Quarantined content is
retained for review and excluded from ordinary reads. Shared Memory continues
through the existing candidate, independent review and promotion workflow.

Dashboard **Agent management → Business permissions** uses GET/POST
`/api/agents/{agent_id}/permissions`. Changes require `resource_action`, `effect`
(`ALLOW`, `DENY`, `RESET`), `data_scope: "OWNED"`, reason and the returned
`expected_permission_version`. Current owners with `agents.manage` can manage
private Memory. Permission administrators can also manage a visible Agent's
Knowledge access. Previous overrides remain as expired history. Effective
permissions, Domain membership and original-source authority are independent checks.

The Agent and its current active Human primary owner with read/Domain authority
can read Agent-private Memory and Knowledge. Sponsors, organization peers and
former owners gain no private access from those relationships. Knowledge uses
`/api/gateway/knowledge`; its GET envelope is `{"knowledge":...}`, not
`{"entity":...}`. Never use Knowledge to emulate Memory.

1. An authorized Human creates a scoped grant with
   `POST /api/enrollment/grants`. Read grants at the corresponding GET route.
2. The external runtime redeems the one-time grant at
   `POST /api/enrollment/redeem`, storing any one-time secret privately or
   supplying the configured public-key proof.
3. Complete credential proof and activation through `POST /api/gateway/activate`.
   Registration alone does not grant model, tool or data access.
4. Exchange the registered credential proof at `POST /api/gateway/token` for
   exact scopes. For the first instance, omit `instance_id` and submit the
   already authorized Domain/Channel binding; retain the returned instance ID
   and its token. For an existing instance, submit its exact ID and proof.
   Creation does not grant Domain or Channel membership.
5. Only when an additional instance is needed, use
   `POST /api/gateway/instances` with the current bearer token and an authorized
   binding, then exchange registered credential proof at `/api/gateway/token`
   with the new instance ID for that instance's own token. A token remains
   bound to its original instance; a body identifier cannot transfer it.
   Claim bounded delivery batches with
   `POST /api/gateway/events/claim` and acknowledge with
   `POST /api/gateway/events/{delivery_id}/ack` using the claim token.
6. Send heartbeats, observe containment and handle credential expiry/revocation.
   Recheck scope before each resource operation.

The root [SKILL.md](../SKILL.md) and
[framework Gateway guide](framework-agent-gateway.md) explain the client contract.
A returned external database endpoint is a governed native connection descriptor,
not a provider key or Schema Owner fallback.

| Route or family | Purpose |
|---|---|
| `/api/channels` and `/api/channels/{channel_id}/members` | Authorized Channel inventory, creation and membership |
| `/api/channels/{channel_id}/messages`, `/threads`, `/summary` | Attributed messages, scoped thread context and summaries |
| `/api/channels/{channel_id}/actions`, `/api/actions/{action_id}/decision` | Structured proposals and permitted decisions |
| `/api/barriers`, `/api/barriers/{barrier_id}/arrivals` | Participant snapshots, structured arrival and release |
| `/api/bridges` | Explicit cross-domain transfer policy |
| `/api/gateway/channels/{channel_id}/messages` | Agent-token-scoped Channel send |
| `/api/gateway/barriers/{barrier_id}/arrivals` | Agent-token-scoped arrival report |
| `/api/gateway/channels/{channel_id}/actions` | Agent-token-scoped structured proposal |
| `/api/gateway/containment`, `/api/gateway/containment/ack` | Current containment and cooperative cleanup receipt |

Messages that look like an Action or Barrier Arrival do not perform that operation.
Use the dedicated structured API and its exact idempotency key.

## Work, graph and continuity

| Route or family | Purpose |
|---|---|
| `/api/tasks` | Current Task Plan/Step inventory and supported operations |
| `/api/workspaces`, `/api/branches`, `/api/loops` | Governed work context and bounded iteration |
| `/api/graphs`, `/api/graph-types`, `/api/graph-versions` | Graph definition/type/version lifecycle |
| `/api/graph-runs`, `/api/graph-worker`, `/api/graph/events` | Run operations, fenced worker actions and durable events |
| `/api/graph/all`, `/api/graph/stats`, `/api/graph/search` | Authorized entity relationship projections |
| `/api/db4a2a/dispatches`, `/api/db4a2a/dispatches/{dispatch_id}/branch` | Reference-oriented dispatch and atomic child Branch |
| `/api/work-contracts`, `/api/handoffs`, `/api/context/*`, `/api/artifact-candidates`, `/api/context-publications` | Work contracts, sources, handoffs, candidates, review and publication |
| `/api/agent-extensions/*` | Controlled probes, directory, derivation, graph diagnostics and registered integrations |
| `/api/native-agents/{agent_id}/execute`, `/api/native-executions/{execution_id}` | Authorized native enqueue and execution status |

A2A/DB4A2A task associations reuse Task Plan/Step and exact execution links,
fenced attempts, cancellation and unknown-outcome reconciliation. Standard A2A
transport and database dispatch are independently validated. See
[DB4A2A](db4a2a.md), [continuity operations](continuity-operations.md),
[Graph Engineering](graph-engineering.md) and [Agent extensions](agent-extensions.md).

## Knowledge, Memory, Skills and inputs

| Route or family | Purpose |
|---|---|
| `/api/knowledge`, `/api/knowledge/inventory` | Authorized Knowledge listing/retrieval |
| `/api/knowledge/{entity_id}/access-policy` | Current company/organization/private policy and permitted updates |
| `/api/memory`, `/api/memory/inventory` | Versioned Memory lifecycle and authorized inventory |
| `/api/memory/{family_id}/versions`, `/chain`, `/candidates` | Immutable successors, provenance traversal and proposals |
| `/api/memory/snapshots`, `/api/memory/jobs` | Pinned context, bounded durable jobs and recovery |
| `/api/skills`, `/api/tools` | Authorized immutable Skill versions and tool registry |
| `/api/tools/{tool_id}/mcp-exposure` | Explicit exposure policy, not execution approval |
| `/api/platform/builtin-knowledge` | Versioned built-in publication, reindexing and withdrawal |
| `/api/gateway/knowledge/{entity_id}` | Independent Agent-authorized single Knowledge read |

Candidate creation does not publish truth. Snapshot resolution rechecks current
sources, digests, validity and authority. Logical unavailability retains history;
physical erasure is a separate retention/legal-hold workflow. Managed inputs and
derived context preserve exact source linkage.

## Memory quality, Agent assets and answer evaluation

The following routes use the `/api/agent-extensions` prefix. Migration 103
provides temporal evidence, working notes and retrospectives; 104 provides
assets, synchronization and context-budget facts; 105 provides durable final
answer runs. Verify all three actual schemas as well as their APPLIED checksums
before use. Their presence does not establish release acceptance.

| Method and suffix | Required route action; purpose |
|---|---|
| `POST /memory/time-evidence` | `workspaces.read`; read authorized exact memory-time facts |
| `POST /memory/{family_id}/restore` | `workspaces.write`; restore history as a new successor |
| `POST /memory/reconciliations`, `GET /memory/reconciliations/{proposal_id}`, `POST .../{proposal_id}/reviews` | Workspace write/read/write; propose and independently review exact memory relationships |
| `GET/POST /works/{work_id}/notes`, `GET /work-notes/{note_id}` | Workspace read/write/read; list, create and read typed Work notes |
| `POST /work-notes/{note_id}/revisions`, `POST .../{note_id}/state` | `workspaces.write`; versioned note edits and retirement |
| `POST /retrospectives`, `GET /retrospectives/{job_id}`, `POST .../{job_id}/run` | Workspace write/read/write; explicit Task-linked model job producing a pending candidate |
| `GET /directory`, `POST /directory/recommend`, `POST /directory/load` | `workspaces.read`; authorized metadata selection and exact content loading |
| `GET/POST /asset-bindings`, `GET /asset-bindings/{binding_id}` | Workspace read / `agents.operate` / workspace read; Agent asset eligibility |
| `POST /asset-bindings/{binding_id}/revisions`, `POST .../{binding_id}/state` | `agents.operate`; expected-version changes |
| `POST /asset-bindings/assemble` | `workspaces.write`; assemble currently authorized bound sources |
| `GET/POST /sources`, `GET /sources/{source_id}`, `POST .../{source_id}/state` | Workspace read / `platform.manage` / workspace read / `platform.manage`; configured HTTPS or pinned GitHub source |
| `POST /sources/{source_id}/sync`, `GET /source-sync-jobs/{job_id}`, `POST .../{job_id}/run` | `agents.operate` / workspace read / `agents.operate`; explicit fenced incremental import |
| `POST /context/budget`, `POST /context/derive`, `GET /context/derivations/{derivation_id}` | `workspaces.read`; conservative budget and source-bound derivation |
| `GET/POST /answer-evaluation/cases`, `POST /answer-evaluation/results` | `platform.manage`; versioned cases and explicitly reported results |
| `POST /answer-evaluation/rubrics`, `POST /answer-evaluation/runs`, `GET /answer-evaluation/runs/{run_id}` | `platform.manage`; frozen standards and queued final-answer evaluation |
| `POST /answer-evaluation/runs/{run_id}/execute`, `POST .../{run_id}/reviews` | `platform.manage`; explicit generation and independent Human review of the exact output digest |

Route actions are prerequisites. Services also check current Work/Domain,
ownership, Agent visibility and every underlying source; Memory restoration
needs `memory.write`, source management checks Knowledge permissions, and
reconciliation review requires an independent authorized reviewer. Never infer
these from Domain membership or a route grant alone. Writes require CSRF for a
Human session. Conflicts require re-reading the relevant current version;
idempotency keys cannot be reused for different payloads.

The time-evidence, restore and reconciliation endpoints use a `value` object
wrapper. For example, `POST /memory/{family_id}/restore` takes:

```json
{
  "value": {
    "expected_version_id": "CURRENT_VERSION_ID",
    "historical_version_id": "HISTORICAL_VERSION_ID",
    "reason": "Restore the reviewed historical content as a new version",
    "idempotency_key": "restore-request-001"
  }
}
```

Use actual IDs from an authorized read. Note, asset, source and quality models
use their typed bodies directly, without that wrapper. Note creation includes
`expected_work_version`; note/asset/source updates use `expected_version`.
Examples, limits and recovery steps are in [memory and working notes](memory-working-notes.md),
[Agent assets](agent-context-assets.md) and [answer quality](answer-quality.md).
Source import never automatically publishes Knowledge. Queuing a job never
proves generation, delivery or successful factual review.

## Models, Embedding and governance

| Route or family | Purpose |
|---|---|
| `/api/llm-provider-profiles` | Versioned provider configuration and redacted reads |
| `/api/model-gateway/completions` | Optional governed model forwarding |
| `/api/model-gateway/credentials`, `/routing`, `/quotas` | Scoped gateway admission, route policy and quotas |
| `/api/model-usage/summary`, `/api/model-evidence/coverage` | Observed usage and explicit observation gaps |
| `/api/model-finance/*`, `/api/model-evidence/*` | Attributed financial and verified imported evidence |
| `/api/wallboard`, `/api/wallboard/definitions` | Read-only management view and separately authorized definitions |
| `/api/embedding/*` | Profiles, immutable contracts, spaces, bindings and readiness |
| `/api/gateway/v1/embeddings` | Scoped model-bound Embedding generation |
| `/api/compliance/*`, `/api/approvals`, `/api/audit` | Enterprise-only policy/evidence/approval/audit-view operations |

Required model and Embedding grants are independent of Agent activation.
Provider capabilities are demonstrated per configuration revision, not inferred
from model names. Direct model traffic remains unobserved without validated
evidence. See [model usage](model-usage-and-wallboard.md) and [security](security.md).

## Portal and compatibility clients

Portal login/chat routes are retained under `/portal/api/*`; the UI is
`/portal`. Portal allocates eligible local managed Agents and releases its
own assignments. It does not register external Agents. Portal and Channel
answers share authorized retrieval and labeled general-model fallback.

Legacy Python APIs are available in `scripts/lib/`. Functions operating on
private resources require the authenticated context/actor documented by that
module; importing a function does not grant owner authority. Native stored
procedures and scheduler SQL differ by backend and are not interchangeable.
Use the selected package's deployment manifest and native grants.

API behavior must be verified against the current running package. Historical
route snapshots, older release results and a successful health endpoint do not
establish current workflow acceptance.
## Source IP policy

`GET /api/platform/ip-access`, `POST /api/platform/ip-access/preview` and
`PUT /api/platform/ip-access` require `platform.manage`; writes require CSRF.
See [policy bodies, source evaluation and recovery](source-ip-access.md).

## Model runtime and processing contracts

The v5.0.2 runtime requires migrations106–109 in addition to the predecessor
chain. PostgreSQL also requires migration110 for compatible native organization
approval entity constraints. Verify the complete103–110 tail on PostgreSQL and
103–109 on Oracle/YashanDB. Historical runtime packages do not mount these new capacity
and processing routes. Route actions remain prerequisites; every operation
also checks its original resource, credential and current policy.

| Method and path | Purpose |
|---|---|
| `GET/POST /api/model-endpoint-capacity/groups` | Management-authorized bounded resource directory or explicit registration. |
| `GET /api/model-endpoint-capacity/groups/{group_id}` | Current policy, participants, aliases and occupancy. |
| `GET /api/model-endpoint-capacity/groups/{group_id}/admissions?after_sequence=...&limit=20` | Management-authorized request metadata, with at most 50 rows. |
| `POST /api/model-endpoint-capacity/groups/{group_id}/revisions` | Expected-version capacity/deadline revision with reason and idempotency. |
| `POST /api/model-endpoint-capacity/groups/{group_id}/origins` | Register an exact requesting principal. |
| `POST /api/model-endpoint-capacity/groups/{group_id}/origins/{origin_id}/state` | Expected-version participant state change. |
| `POST /api/model-endpoint-capacity/groups/{group_id}/aliases` | Bind an endpoint alias and saved Profile revision. |
| `GET /api/model-endpoint-capacity/admissions/{admission_id}` | Read the caller's exact authorized request. |
| `GET /api/model-endpoint-capacity/admin/admissions/{admission_id}` | Management-authorized request inspection. |
| `POST /api/model-endpoint-capacity/admissions/{admission_id}/cancel` | Record queue cancellation or local cancellation after dispatch. |
| `POST /api/model-endpoint-capacity/admissions/{admission_id}/reconcile` | Record explicit operator confirmation for the exact unknown request. |
| `POST /api/model-gateway/coordinator-bindings` | Administrator enrollment of exact central capacity, participant, Gateway credential and both Profile revisions. |
| `POST /api/model-gateway/coordinator-routes` | Administrator registration of the fixed local Profile-to-coordinator route. |
| `GET /api/model-gateway/origin-requests/{receipt_id}` | Original principal reads its local remote-dispatch receipt, immutable observation and separate resolution. |
| `POST /api/model-gateway/origin-requests/{receipt_id}/reconcile` | Read exact registered central transport evidence, then recheck original local business authority and retain a separate resolution. No model send or retry. |
| `GET /api/agent-extensions/executions/{execution_id}/progress` | Read authorized original execution, processing and model observations. |
| `GET /api/agent-extensions/processing/{continuity_id}?after=...&limit=100` | Read at most 100 processing block observations without repair or generation. |
| `POST /api/agent-extensions/processing/retries` | Active Human admission of an exact bounded recovery. |
| `POST /api/agent-extensions/processing/blocks/{block_id}/reconcile` | Read original evidence or record an explicit Human resolution. |
| `POST /api/agent-extensions/processing/recoveries/{recovery_id}/dispatch` | Explicit dispatch through the original trusted adapter, with an empty object body. |

Capacity administration requires `model_gateway.manage`; request read and
cancellation require `model_gateway.forward` plus ownership. Processing reads
require `workspaces.read`; recovery decisions require `workspaces.write`, an
active Human and current exact business authority. Session mutations require
CSRF. An admission ID, correlation ID, recovery receipt or idempotency key is
never a bearer credential. Gateway replay retains the original Profile, Agent
and credential boundary and rechecks current authority before response access.

Coordinator enrollment also requires `platform.manage`. Origin receipt reads
require `workspaces.read`; explicit reconciliation requires `agents.operate`
and its original business adapter's current authority. Fixed coordinator peer
reservation, completion, observation and cancellation routes authenticate the
enrolled original `cxgw_` machine credential, not a foreign browser session.
Transport termination and Provider response completeness remain distinct;
reconciliation does not rewrite an old unknown observation or approve content.

Queue cancellation proves no send only for an unused admission. Closing an
already dispatched local connection does not prove remote termination.
Unknown requests continue occupying capacity until exact completion evidence
or an explicitly recorded operator decision. Recovery acceptance, dispatch,
Task completion and independent content approval remain separate states.

Usage fields distinguish missing from measured zero. Cache and reasoning
details are subsets of input/output totals. Timings identify client observations;
no Provider prefill/decode measurement is inferred. Metadata omits prompts,
answers, credentials and hidden reasoning text. See
[capacity](model-endpoint-capacity.md), [processing](processing-recovery.md),
[structured and tool workflows](model-workflows.md) and
[versioned MCP](mcp-versioned-interoperability.md).

## Observed-answer Human reviews

Migration 109 adds `/api/observed-answer-reviews` in v5.0.2 installations. These
Dashboard routes import typed observations of already completed answers and
record independent Human decisions. They make no generation request and do not
convert imported observations into native answer-quality runs. Original v5.0.1
observations can be registered after upgrading to v5.0.2; the v5.0.1 package is
not modified.

| Method and path | Purpose and request |
|---|---|
| `POST /api/observed-answer-reviews/sets` | Register `{packet, reason}`. The typed packet binds version/phase/target/track/generation, package/policy/report digests, and each original output, actor, Domain, Agent/Profile revision, query and observation. |
| `GET /api/observed-answer-reviews/sets/{set_id}` | Read the original packet and recorded reviews under current authority. |
| `POST /api/observed-answer-reviews/sets/{set_id}/outputs/{key}/reviews` | Submit `{output_digest, factual_correct, citations_supported, reason}` for that exact output. Both decisions require JSON booleans; the review reason must contain 3–1000 characters and be substantive. |
| `GET /api/observed-answer-reviews/sets/{set_id}/export` | Export the original immutable set/output/review and required audit facts under current authority. The export does not declare release readiness. |

All four routes require current `platform.manage`, an active Human principal and
the original authenticated Dashboard Session. POST requests also require the
session's `X-CSRF-Token`; Gateway credentials cannot replace that Session.
Each operation rechecks Domain membership, visibility of the active original
Agent, its exact healthy Profile revision, current Knowledge reader/citation
intersection and disclosed exact context sources. A stale revision or lost
authority prevents disclosure or review.

The reviewer must differ from both the registering actor and the original
responsible actor. Use the selected output's `output_digest` from its authorized
export: it binds the complete canonical typed Observation row, rather than just
the answer text. Registration and review preserve the real Session facts and
commit immutable records with required audit in one transaction. A client flag
or imported verdict cannot substitute for a Human review.

Release verification separately proves the original capture, exact package and
matrix coverage. A private native observer can retain historical review facts
after fixture cleanup; that does not authorize a later HTTP read. Import,
recorded Human review and final release acceptance remain separate facts.
