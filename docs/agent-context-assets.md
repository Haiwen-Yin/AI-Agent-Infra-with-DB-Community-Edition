# Agent assets and query-aware context v5.0.1

> Installed product: **Chuanxu Community Edition**; supported backends: **oracle, pg, yashandb**; edition: **Community**; license: **Apache-2.0**. Other backends and Enterprise-only capabilities discussed below describe differences; they do not extend this package's scope.

[简体中文](agent-context-assets_zh.md)

Agent assets are eligibility bindings to existing Knowledge, Memory, Skill,
captured Graph or synchronized Source revisions. They do not copy ownership or
grant access. Migration 104 stores bindings, immutable revisions, context uses,
source configurations, synchronization jobs and budget/representation facts.
Use the selected package's complete migration chain before these operations.

## Prepare access and choose an asset

In Dashboard, open **Workspaces → Work continuity** and select a Security Domain.
The **Agent assets** area separates bindings, source synchronization and Skill
recommendation. Select an active Agent from the authorized directory. The
operator and Agent must retain current Domain and source access. A private
source does not become shared because it is attached to an Agent.

The HTTP prefix below is `/api/agent-extensions`. Human clients first log into
Dashboard with `POST /api/auth/login`, complete required MFA/setup and retain
the session cookie and returned `csrf_token`. These session-protected routes
require that cookie and `X-CSRF-Token` on every POST, including read-only
`/directory/recommend` and `/directory/load`, and on every other method except
GET, HEAD and OPTIONS. Log in again after expiry. Independent Gateway machine
endpoints use their own scoped Bearer authentication, not Human cookie/CSRF;
their token cannot replace the Dashboard session here.

`workspaces.read` protects reads;
`agents.operate` protects binding changes and sync dispatch; assembly also needs
`workspaces.write`. Configuring or changing a source requires `platform.manage`.
The service additionally checks Agent visibility, source ownership/scope and
the appropriate Knowledge/Memory/Skill permissions. A menu or route grant alone
is insufficient. Portal is not a platform-configuration entry point.

Memory metadata checks require resource-scoped `memory.read` permission and
reuse the existing Memory reader for ownership, scope and `RUNTIME_CONTEXT`
authorization; they do not impose a separate owner-or-`ALL` rule. A Human-owned
Memory can therefore remain readable by an explicitly authorized `ASSIGNED`
Agent, but that scope is not itself a Domain membership or source grant.
Operator and Agent authority are checked separately against current membership,
the exact revision/digest, current family lifecycle, expiry and applicability.
Selection reads only the title and safe metadata, never the Memory body.
Denied, blocked, expired or not-yet-applicable entries are hidden from the
binding inventory; an existing binding or prepared assembly cannot restore
withdrawn access. Other source families retain their existing ownership/scope
rules.

1. Search metadata with `GET /directory?security_domain_id=DOMAIN_ID&family=SKILL&query=QUERY`.
   Use `after` and `limit` to page; results do not contain an execution grant.
2. For query-ranked Skill candidates, use `POST /directory/recommend` with
   `security_domain_id`, `query`, optional `limit` (1–20) and `candidate_limit`
   (1–100). No suitable selection is a valid outcome.
3. Load only the chosen exact record through `POST /directory/load`, passing
   `{ "value": { "security_domain_id": "DOMAIN_ID", "family": "SKILL",
   "entity_id": "ENTITY_ID", "version": "REVISION_ID",
   "content_digest": "ACTUAL_SHA256" } }`. Replace the identifiers and digest
   with the authorized result. Loading rechecks current authority and digest.

## Bind and assemble

Create a binding with `POST /asset-bindings`:

```json
{
  "security_domain_id": "DOMAIN_ID",
  "agent_id": "AGENT_ID",
  "source": {
    "family": "KNOWLEDGE",
    "entity_id": "ENTITY_ID",
    "revision_id": "REVISION_ID",
    "content_digest": "ACTUAL_SHA256"
  },
  "purpose": "Prepare an authorized answer",
  "priority": 50,
  "resolution_policy": "PINNED",
  "reason": "Attach the reviewed reference",
  "idempotency_key": "binding-request-001"
}
```

Examples use placeholders, including `ACTUAL_SHA256`; replace them with actual
IDs and the 64-character lowercase digest returned by the service. `PINNED`
keeps the exact reference. `CURRENT` resolves the current eligible version when
used and rechecks authorization; captured `GRAPH` and `SOURCE` references must
remain pinned. An optional `valid_until` needs a future time with an offset.
Priority ranges from 0 to 100 and does not override source permissions.

Read `GET /asset-bindings?security_domain_id=DOMAIN_ID&agent_id=AGENT_ID`, then
`GET /asset-bindings/{binding_id}`. For a revision, send the binding fields plus
`expected_version` to `POST /asset-bindings/{binding_id}/revisions`. To pause,
resume or revoke a binding, send `expected_version`, `status` (`ACTIVE`, `PAUSED`
or `REVOKED`), `reason` and `idempotency_key` to `POST .../{binding_id}/state`.
A conflicting version requires a fresh read and an explicit decision; do not
silently replace the expected version and resubmit.

`POST /asset-bindings/assemble` takes `binding_ids` (1–50) and an `assembly`
request. The assembly contains `request_id`, `security_domain_id`, `purpose`,
`idempotency_key` and optional Work/Handoff, query and budget fields. For example:

```json
{
  "binding_ids": ["BINDING_ID"],
  "assembly": {
    "request_id": "assembly-001",
    "security_domain_id": "DOMAIN_ID",
    "query_text": "Which reviewed deployment steps apply?",
    "token_budget": 4096,
    "context_window": 16384,
    "output_reserve": 2048,
    "entry_limit": 20,
    "allow_partial": false,
    "purpose": "Prepare the deployment conversation",
    "idempotency_key": "assembly-request-001"
  }
}
```

Selection authorizes metadata before loading bodies, preserves exact revisions
and can omit irrelevant optional sources. `mandatory_sources` must fit without
losing required constraints. `system_text`, `tool_text` and `output_reserve`
consume the context window before the source budget. A locally initialized,
recognized tokenizer may provide the count; otherwise `UTF8_UPPER_BOUND` counts
UTF-8 bytes conservatively. It is an estimate, not measured model usage.
No tokenizer download or caller-supplied counting code is performed.

Representation (`COMPLETE`, `PARTIAL`, `OMITTED`) and delivery (`PREPARED`,
`CONFIRMED`, `UNOBSERVED`, `OMITTED`) are separate persisted facts. Preparing an
assembly does not prove that a model received it. The existing input-receipt
path must confirm the exact rendered digest and entry count. Source revocation,
expiry or changed current authority blocks later reads despite a pinned ID.
See [continuity operations](continuity-operations.md) for execution receipts.

## Configure and synchronize a source

In **Agent assets → Source synchronization**, a platform manager configures a
source; an authorized operator then queues and explicitly runs its job. Import
creates pending Knowledge candidates. A separate authorized reviewer and
explicit publication remain necessary before it becomes formal Knowledge.

`POST /sources` accepts this document-source shape:

```json
{
  "security_domain_id": "DOMAIN_ID",
  "agent_id": "AGENT_ID",
  "kind": "DOCUMENT",
  "endpoint": "https://docs.example.com/platform/deployment.html",
  "paths": ["/"],
  "content_types": ["text/html", "text/markdown", "text/plain"],
  "max_bytes": 16384,
  "max_attempts": 3,
  "reason": "Synchronize the approved documentation page",
  "idempotency_key": "source-config-001"
}
```

`DOCUMENT` fetches that exact HTTPS page; it is not a recursive wiki crawler.
For `GITHUB`, use the exact `https://github.com/OWNER/REPOSITORY` endpoint,
`pinned_commit` as a full lowercase 40-character commit SHA and approved path
prefixes such as `["docs"]`. Moving branch names, shell Git transports,
submodules and symbolic links are unsupported. The bounded tree/blob workflow
loads eligible UTF-8 text and verifies blob identity; it never executes code.

Only credential-free HTTPS URLs on port 443 and permitted public destinations
are accepted. Redirects, private/link-local/loopback destinations, binary text
and compressed response bodies are rejected. `content_types` supports plain
text, Markdown, HTML and JSON. `max_bytes` is 128–262144 (the aggregate selected
content limit for Git), with at most 50 selected Git files; `max_attempts` is
1–5. A required credential is an uppercase host-managed `credential_ref`, never
a secret in the URL or request body. Missing/revoked credentials block use.

Queue with `POST /sources/{source_id}/sync` using `reason`, `idempotency_key`
and optional existing `task_id`. Read `GET /source-sync-jobs/{job_id}`, then
explicitly run `POST /source-sync-jobs/{job_id}/run`. The job reuses Task/Step
continuity, leases and fencing; new revisions, pending candidates, imports,
checkpoint and audit commit atomically. Repeating the same completed request
does not duplicate imports. This is an explicitly invoked incremental sync,
not an automatically enabled schedule.

## Pause, investigate and recover

`GET /sources` and `GET /sources/{source_id}` return configuration/status without
credential values. `POST /sources/{source_id}/state` accepts `expected_version`,
`status`, `reason` and `idempotency_key`. `PAUSED` may return to `ACTIVE`;
`REVOKED` and `RETIRED` are permanent for that source identity. Configure a new
approved source instead of silently reviving it.

Inspect job state (`PENDING`, `RUNNING`, `SUCCEEDED`, `FAILED`, `BLOCKED`),
`attempt_count`, `error_code`, current source state and original requester.
Permission loss blocks use; a 404 does not authorize deletion or withdrawal of
previously published content. Network/content errors cannot advance the
checkpoint. Exhausted attempts, stale leases or changed configuration require
investigation before a new authorized request. Keep the original evidence and
candidate review history. Never clear the ledger or lower permissions to make
a failed sync appear successful.
