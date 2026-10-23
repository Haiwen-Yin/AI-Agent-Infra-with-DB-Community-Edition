# API reference v5.0.1

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
