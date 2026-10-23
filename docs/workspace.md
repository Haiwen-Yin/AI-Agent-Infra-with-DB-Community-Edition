# Workspace and context continuity v5.0.1

> Installed product: **Chuanxu Community Edition**; supported backends: **oracle, pg, yashandb**; edition: **Community**; license: **Apache-2.0**. Other backends and Enterprise-only capabilities discussed below describe differences; they do not extend this package's scope.

[简体中文](workspace_zh.md)

## Database entities and authorization

Workspaces, workspace contexts, sessions, branches and linked tasks are existing
database entities. They retain stable identifiers, source relationships and
history; JSON holds bounded content rather than permissions or a second task
engine. This product supports **oracle, pg, yashandb**.

Use authenticated Dashboard/Gateway operations with current resource permission.
Direct Python helpers in `scripts/lib/workspace_api.py` are internal primitives,
not an authorization boundary. Native Agent logins retain their backend's
independent policies. A Workspace's `SHARED` or `ISOLATED` metadata does not
grant access to Knowledge, Memory, Channels, models or another principal's data.

PostgreSQL uses native JSONB and generated numeric identifiers where defined;
Oracle and YashanDB use their selected native schema and adapter. Oracle JSON
Relational Duality views, when present, are adapter-specific projections, not a
portable write API. Do not copy Oracle JSON/SQL syntax into another backend.

## Workspace lifecycle

| State | Meaning | Intended next states |
|---|---|---|
| `ACTIVE` | Current working context | `PAUSED`, `COMPLETED`, `ABANDONED` |
| `PAUSED` | Work is suspended | `ACTIVE`, `COMPLETED`, `ABANDONED` |
| `COMPLETED` | Work has finished | Retain the result and history |
| `ABANDONED` | Work has been discontinued | Retain the reason and history |

`WORKSPACES` records owner, name, type, isolation metadata, current Agent and
session, summary and timestamps. `WORKSPACE_TASKS` links Task Plans without
duplicating their execution state. `GET /api/workspaces` is the authorized
Dashboard inventory; use `view=summary` for its bounded summary representation.
Do not infer write support merely from a read endpoint.

## Context types and content

`WORKSPACE_CONTEXT` retains parent, workspace, Agent, session and Branch
relationships separately from `CONTEXT_DATA`.

| Type | Content purpose |
|---|---|
| `SNAPSHOT` | Working state at a recorded instant |
| `CHECKPOINT` | Intermediate progress and outstanding actions |
| `HANDOFF` | Transfer reason, current state and recipient instructions |
| `SUMMARY` | Bounded account of the session's outcomes |
| `RECOVERY` | Recovery point, prior interruption and resume instructions |

A recommended content shape is:

```json
{
  "_version": 1,
  "summary": "Validation is incomplete",
  "pending_actions": ["Verify the remaining task"],
  "observed_at": "2026-10-17T00:00:00Z"
}
```

The example is illustrative, not execution evidence or a grant. Keep content
bounded, version its schema and use ISO-8601 timestamps. Content cannot contain
credentials. The service sanitizes secret-like fields, but callers must still
avoid placing secrets into arbitrary prose.

## Handoff and Branch relationships

The legacy `create_handoff_session()` helper creates a HANDOFF Branch, links a
new `AGENT_SESSION` to its predecessor, saves context and updates the Workspace's
current Agent/session. Its separate helper calls are not proof of an atomic
governed work transfer or recipient acceptance. New work uses the versioned
Work contract, handoff offer/acknowledgement and Context Assembly workflows in
[continuity operations](continuity-operations.md).

Those workflows preserve responsibilities, policy revisions, exact source
snapshots, digests, current authorization and immutable review/publication facts.
Concurrent capacity is explicit and bounded; coordinator ownership remains
distinct from a recipient's authority. Neither a text instruction nor a Branch
name transfers ownership. The recipient's current permissions must still allow
every source it reads.

DB4A2A sends context references and exact snapshot facts instead of copying
large prompts. The authorized child-Branch operation locks and validates its
dispatch and context, then commits the Branch, link and audit atomically.
A retry rejects changed sources. See [DB4A2A](db4a2a.md).

## Recovery and execution

`recover_workspace()` assembles available Workspace metadata, bounded context
and session history, linked active tasks and applicable scoped entities. It does
not resume a model, rerun an external operation, promote a database standby or
establish that a previous side effect failed. Inspect the original task,
attempt, lease, checkpoint and source revision before resuming.

Use recorded `RECOVERY` context to explain a chosen resume point. Expired
Worker fencing tokens cannot commit; uncertain external sends require explicit
reconciliation and are never blindly repeated. Original Gateway credential
revocation cannot be repaired by substituting a new credential for old work.
Database backups, replication and RPO/RTO remain operator duties.

## Operations and verification

1. Select an authorized Workspace and inspect its owner, state and current session.
2. Inspect the exact source context and Branch before a handoff or DB4A2A dispatch.
3. Use the governed operation with its expected revision and idempotency key.
4. Read the resulting database record and audit; a queued response is not completion.
5. Recheck access after membership, source or credential revocation.
6. Verify restart behavior and uncertain outcomes in a classified temporary target.

See [API reference](api-reference.md), [security](security.md),
[recovery](recovery.md) and [migration](migration.md). The retained historical
Workspace guide is source history, not the current multi-database contract.
