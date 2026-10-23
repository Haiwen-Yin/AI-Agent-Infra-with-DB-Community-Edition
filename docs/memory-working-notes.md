# Memory evidence, working notes and retrospectives v5.0.1

> Installed product: **Chuanxu Community Edition**; supported backends: **oracle, pg, yashandb**; edition: **Community**; license: **Apache-2.0**. Other backends and Enterprise-only capabilities discussed below describe differences; they do not extend this package's scope.

[简体中文](memory-working-notes_zh.md)

Memory, Work contracts, task plans and reviewed candidates remain database
entities. Temporal evidence and working notes require migration 103; do not run
these services against a schema that has not passed its migration checks.

For Human HTTP calls, log into Dashboard with `POST /api/auth/login`, complete
any required MFA/setup, and retain its session cookie and returned `csrf_token`.
For the session-protected routes below, send that cookie and `X-CSRF-Token` on
every POST, including read-only POSTs such as `/memory/time-evidence`, and every
other method except GET, HEAD and OPTIONS. Renew the login when its session
expires. Independent Gateway machine endpoints use their own scoped Bearer
authentication, not this Human cookie/CSRF flow; a Gateway token does not replace
the Dashboard session required here.

Routes below use `/api/agent-extensions`; workspace read/write actions remain
subject to current Memory, Work, Task, Domain and exact-source permissions.
See [API reference](api-reference.md) for the route permission table.

## Temporal evidence and restoration

New memory versions retain event time separately from observation and ingestion
time. A missing event time stays unknown. A timestamp without an offset retains
its original text and an `UNKNOWN_OFFSET` state; it is not silently interpreted
in the server's local timezone. Applicable start/end times require an explicit
timezone. Evidence outside that interval cannot enter fresh context consumption.

An older applicable event cannot replace a newer current fact merely because it
arrives later. Reconcile its exact versions first. An explicit correction records
the corrected current version, scope and applicable start. Reconciliation records
two authorized source revisions, method, policy and the meaning of confidence;
an unavailable judgment remains unresolved. A different authorized reviewer may
approve the proposed relationship, but that approval does not activate content.
Content publication continues through the existing candidate/review/publication
chain.

Restoring memory requires the expected current version, selected historical
version, reason and idempotency key. Restoration creates a new successor and
records the historical origin. It does not rewind the family pointer to an old
version, rewrite history or lower the current classification. Current source,
domain and write authority are checked again. The new version, origin receipt,
projection event and audit either commit together or roll back together.

When creating a Memory version through its existing lifecycle, temporal fields
include `event_at`, `observed_at`, `applies_from`, `applies_until`,
`corrects_version_id` and `correction_scope`. `POST /memory/time-evidence` reads
an exact authorized source through `{ "value": { "family": "MEMORY",
"entity_id": "FAMILY_ID", "revision_id": "VERSION_ID", "content_digest":
"ACTUAL_SHA256" } }`; it is not an endpoint for rewriting recorded times.
For old versions without time facts, trustworthy creation time is labeled as
historical ingestion/observation, while event time remains `UNKNOWN`.

Use `POST /memory/reconciliations` with a `value` object containing
`security_domain_id`, exactly two `sources`, `relation_kind` (`DUPLICATE`,
`CONTRADICTION`, `REPLACEMENT`, `UNRESOLVED`), `method`, `policy_revision`,
`confidence` (optional 0–1), `confidence_meaning`, `judgment_available`, `reason`
and `idempotency_key`. Read `GET /memory/reconciliations/{proposal_id}`; a
different authorized reviewer sends `decision` (`APPROVED` or `REJECTED`) and
`reason` to `POST .../{proposal_id}/reviews`. Unavailable judgment stays
`UNRESOLVED`; approval never publishes the source content.

For restore, `POST /memory/{family_id}/restore` takes a `value` object with
`expected_version_id`, `historical_version_id`, `reason`, `idempotency_key`.
Read the current/history IDs first; a stale current version returns a conflict.
The response identifies the new `version_id` and historical `origin_version_id`.
Keep that receipt and verify current state instead of retrying with an altered
expected version. Source references in all examples need real IDs and the
service-returned 64-character lowercase SHA-256, replacing `ACTUAL_SHA256`.

## Working notes

Attach a note to an existing Work contract. Choose a type: `FINDING`,
`REJECTED_APPROACH`, `VALIDATION`, `OPEN_QUESTION` or `NEXT_ACTION`. Include a
title, body, exact evidence references and, where useful, an absolute expiry.
Creating a note checks the expected Work version. Revising it checks the expected
note version and creates immutable content/source revisions. Closing Work prevents
new notes and edits.

Handoffs reference a note as `WORKING_NOTE` with note ID, canonical positive
revision and SHA-256 content digest. The recipient must still have access to the
Work and every underlying source. Domain membership does not substitute for a
private Handoff's participant check. Expired or retired notes are unavailable to
new context reads, even if a Handoff pinned the note before expiry. Authorized
history remains readable. A note cannot be published directly across domains or
automatically enter long-term Memory, Knowledge or Skills.

In **Workspaces → Work continuity**, select Work, then open **Working notes**.
Create with `POST /works/{work_id}/notes`:

```json
{
  "expected_work_version": 1,
  "content": {
    "note_type": "VALIDATION",
    "title": "Deployment check",
    "body": "Record the observed result and remaining verification.",
    "sources": []
  },
  "reason": "Record current Work evidence",
  "idempotency_key": "note-create-001"
}
```

Use the actual Work version. Add exact source references when the note relies
on evidence; omit an expiry or provide an absolute offset-bearing `expires_at`.
Read `GET /works/{work_id}/notes` (bounded `limit`, optional `after`) and
`GET /work-notes/{note_id}?revision=1`. Revise through
`POST /work-notes/{note_id}/revisions` with `expected_version`, full `content`,
`reason`, `idempotency_key`. Retirement uses `POST .../{note_id}/state` with
`expected_version`, `status: RETIRED`, reason and key. Refresh and reconcile
concurrent versions rather than overwriting. History reads do not reactivate
expired content or reopen a closed Work.

## Explicit retrospective jobs

An authorized requester selects an existing task, trigger (`SUCCESS`, `FAILURE`,
`CORRECTION` or `FEEDBACK`), exact input sources, output family, policy revision,
healthy model Profile/version and budget. Creation adds a task step and a runtime
continuity link; it does not start a second scheduler or enable an automatic
policy.

The worker rechecks the original requester, task ownership, domain, current
source authority, Profile revision and lease/fencing immediately before use.
The default model worker also requires the Profile in the current approved
source-disclosure list. It uses the registered provider endpoint, refuses
redirects and applies the provider's verified parameter contract. Secrets are
resolved locally and are not written to the job or returned to clients.

The total request uses a conservative UTF-8 byte token bound plus reserved
output tokens. This is an estimator, not measured model token usage. Evidence is
not silently truncated; an oversized request fails before dispatch. The response
must match the selected model and contain a complete, nonempty candidate in the
frozen output family. Provider reasoning is not used as the candidate.

The result enters the existing candidate chain as `PENDING`; a separate reviewer
and explicit publication are still required. An uncertain provider send becomes
`UNOBSERVED` and is never automatically sent again. A completed job is replayed
without a second model call. These controls do not establish that an external
model forgot information already sent to an approved endpoint.

In Dashboard **Retrospective and answer evaluation → Work retrospective**,
select an existing Task, exact sources and an approved healthy Profile. The UI
requires management access to its model/policy selectors; the HTTP service also
enforces the original requester and underlying task/source permissions.
`POST /retrospectives` takes `security_domain_id`, `task_id`, `trigger`,
`target_family` (`MEMORY`, `KNOWLEDGE`, `EXPERIENCE`, `SKILL`), nonempty `sources`,
`policy_revision`, `profile_id`, `profile_version`, `token_budget` (128–32768),
`reason`, `idempotency_key`; optional `replaces` is an exact source in the output
family. Read `GET /retrospectives/{job_id}` and explicitly run
`POST /retrospectives/{job_id}/run` after approving the possible model send.

`PENDING`, `RUNNING`, `PROPOSED`, `FAILED`, `UNOBSERVED` describe the job, not
content publication. On `PROPOSED`, inspect its candidate and use independent
review/publication. On stale Profile/source, budget failure or unknown send,
retain the original job and investigate; do not delete state or blindly rerun.
