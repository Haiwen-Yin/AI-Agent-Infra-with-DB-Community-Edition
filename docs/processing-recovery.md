# Processing diagnosis and recovery

> Installed product: **Chuanxu Community Edition**; supported backends: **oracle, pg, yashandb**; edition: **Community**; license: **Apache-2.0**. Other backends and Enterprise-only capabilities discussed below describe differences; they do not extend this package's scope.

Processing diagnosis extends the existing Task continuity, Graph, Loop and
TaskStep records. Migration 107 stores typed targets, actions, budgets, blocks,
recovery receipts and resolutions. It does not introduce another scheduler.
Install the selected package's complete required migration chain before
enabling its runtime. Missing required tables stop the operation.

## What a processing view means

An authorized view reports the original Task and attempt, frozen target and
input/source revisions, observed cause, consumed budget and recovery state.
Source bodies, prompts, model answers and credential bytes are excluded.
Each read rechecks the original resource's current authority; a diagnostic
identifier or a Task anchor does not grant additional access.

The categories have separate meanings:

| Category | Examples | Meaning |
|---|---|---|
| `BLOCKED` | unmatched, request timeout, unavailable Provider, endpoint queued, exhausted budget, revoked source, waiting for a Human, failed | The recorded cause prevents the current operation from continuing. |
| `DEGRADED` | Embedding timeout, unavailable semantic retrieval, permitted textual fallback | A specific path was unavailable or changed; the authorized operation may still proceed. |
| `UNKNOWN` | possible send, expired lease, unknown external result, closed client | The available evidence does not establish the external outcome. |

Retrieval path and match state are independent fields. For example,
`EMBEDDING_TIMEOUT`, `TEXTUAL` and `EMPTY` mean that textual retrieval actually
ran without matching evidence after the semantic path timed out. An empty
result does not erase the timeout.

Reading, refreshing and restarting do not generate, reset budgets, repair
records or enable capabilities. A successful Task or transport result is a
lifecycle fact. Content approval remains with the existing candidate/version
pipeline and independent review.

## Durable limits and accounting

Trusted admission freezes the server policy and its digest on the original
budget root. The initial v5.0.2 limits are 32 requests, 128 steps, 262144
observed tokens, 3 equivalent actions and 8 actions without new durable progress.
HTTP callers cannot select the initial policy. An authorized recovery grants
only its explicit bounded allowance on the same budget root.

Actual durable events have stable action keys. Replaying the same event does
not count it again; changing its contents under that key is rejected. Equivalent
tool proposals, calls and iterations count toward repeated-action limits.
New iteration IDs, successor attempts, Graph forks and service restarts do not
create a fresh budget. A stop preserves its target, reason and counters.

Adapters using existing real Task continuity record one lifecycle step on
completion or expiry. Model-runtime attempts consume a request allowance; local source-sync
attempts do not. This allowance counter bounds work admission and is separate
from the observed Provider request ledger. Token accounting sums only matching
immutable observations from the original actor, source and real Task attempt.
Missing Provider usage stays unobserved; a counter that has no observed tokens
does not establish that the Provider used zero tokens. Graph and legacy adapters
record their own native events to avoid counting the same completion twice.

Action, native effect, budget, required diagnosis and audit changes commit in
the original transaction where the adapter owns that effect. A required audit
failure rolls the operation back. Token observations report usage; they do not
prove answer quality.

## Human decisions and APIs

The authenticated Agent-extension API mounts these routes under
`/api/agent-extensions/processing`. Deployment routing may add its existing
outer prefix. Reads require `workspaces.read`; decisions require
`workspaces.write`, an active Human and the original resource's current policy.
The parent HTTP layer retains session, CSRF and Agent-scope checks.

| Method and relative path | Operation |
|---|---|
| `GET /{continuity_id}?after=...&limit=100` | Read metadata; pages contain at most 100 block observations. |
| `POST /retries` | Admit one exact bounded retry and its receipt. |
| `POST /blocks/{block_id}/reconcile` | Read original evidence or record an explicit Human resolution. |
| `POST /recoveries/{recovery_id}/dispatch` | Ask the installed original-domain adapter to dispatch; the body is empty. |

A retry contains the exact block, expected version, full frozen target,
reason code, added request/step/token bounds, decision digest and idempotency
key. A stale target, substituted revision or different payload under the same
key is rejected. Admission preserves the original canonical Task relationship,
creates a successor continuity receipt and commits required audit atomically.
It does not itself acquire a Worker lease or send a model request.

`ACCEPTED`, queued capacity, `DISPATCHED`, completed lifecycle and content
approval remain separate. Replaying an accepted request returns its receipt.
An already completed original operation returns its existing result reference
after current authorization instead of executing again. Models and Agents
cannot authorize Human recovery decisions or change their own limits.

## Native adapter boundaries

| Adapter | Integrated behavior |
|---|---|
| Retrospective generation, governed model-turn stages, answer-quality evaluation, source sync | Real Task claims freeze accounting. Explicit recovery queues the original job against a successor on the same Task and budget. Existing runners reuse immutable original inputs, source versions and credentials. Completion, failure and expiry record usage and typed causes. |
| Native and Channel execution | Enqueue creates a real canonical Task and budget. Worker claims atomically map the native fence to a real Task attempt. Each Provider event has its own immutable NMA-to-Task mapping. Explicit recovery queues the original execution; the existing Worker rechecks its original credential, source, Profile and fence before sending. |
| Graph | Each real Graph attempt has an independent real Task attempt bound to its native run/node/attempt tuple. Children and forks share the original budget. Pure `SIDE_EFFECT_CLASS=NONE` recovery can dispatch through the original Graph runtime. |
| Loop and TaskStep | Native iteration, step and recorded tool-call changes, their Task attempts and accounting commit together. Resume checks the same budget and unknown-result gate. Running step definitions and inputs cannot be replaced. |
| Local DB4A2A branch creation | The immutable dispatch revision, exact branch request, independent Task attempt, local branch effect and shared-budget accounting commit together; replay returns the existing branch. |

Installed recovery adapters cover the original native execution, Channel,
retrospective, governed model-turn stage, evaluation and source-sync runners.
Queueing commits before a runner executes; final Provider admission records
dispatch. Repeated queue/dispatch requests return the same receipt. Missing
original credentials or changed authority block recovery. Graph recovery with
external side effects requires the matching capacity adapter and cannot use
the pure-Graph path. Other unsupported targets remain accepted with
`RECOVERY_DISPATCH_ADAPTER_REQUIRED`; no replacement identity is substituted.

Native executions without an explicit context, framework or Channel Domain use
a typed internal accounting anchor. It is excluded from Domain directories and
cannot contain members or Channels. It grants no collaboration permissions.
Where the historical Task foreign key needs a registry row, the same native ID
has an inert `DORMANT` metadata projection. It creates no external registration,
database account, role or credential, and cannot enroll or authenticate as an
external Agent. Existing registry identities remain unchanged.

Explicit recovery of a context-bound execution rereads the same authorized
assembly and sources. Its Task successor and Provider event retain the new
attempt; the original one-use context receipt remains historical evidence.
An assembly's expiry or a revoked source still prevents delivery.

The legacy Loop evaluator cannot execute against a controlled model endpoint
without a trusted model-admission adapter. It fails before sending with
`PROCESSING_MODEL_ADAPTER_REQUIRED`. Uncontrolled historical endpoints retain
their existing evaluator permissions and execution path. Legacy record APIs
account for trusted native records; they do not independently observe external
actions performed before those records are submitted. Local DB4A2A branch
creation is likewise evidence of that local effect, not remote Agent completion.

## Unknown effects and capacity

A timeout, client closure or expired local lease does not prove Provider
termination. The real Task attempt becomes `UNOBSERVED`, stale Workers remain
fenced, and the next send is blocked. No idle-generation probe is sent.

Reconciliation binds the original business key, digest, target and real attempt.
`READ_ORIGINAL` uses a trusted original reader. A local unknown record remains
unknown. The Graph reader can establish local success only from its exact
successful native attempt, completion digest and checkpoint. A failed or stale
Graph record alone is not proof of an external terminal outcome.

`OPERATOR_RESOLUTION` records an explicit authorized Human outcome as that
evidence kind. HTTP callers cannot supply `TERMINAL_RESPONSE`, a Provider proof
flag or a claimed request-complete value. A resolution does not send a retry.
If matching endpoint admission remains `UNKNOWN`, its capacity lifecycle must
be reconciled in the same transaction by the trusted processing adapter. This
also requires the current capacity-administrator permission and exact original
capacity attempt, version and fence. A failed required audit rolls back both
capacity and Task resolution.

For a registered remote coordinator, first resolve capacity at its authority,
then explicitly read the original Origin receipt through
`POST /api/model-gateway/origin-requests/{receipt_id}/reconcile`. The server
rechecks the original business source, credential, route, Profile and Worker
fence before and after the remote read. No local transaction spans HTTP.
Exact central terminal evidence creates a separate immutable Origin resolution;
the original UNKNOWN receipt and observation remain unchanged. A local Human
outcome cannot release an unresolved remote slot. Processing then reads that
resolution and may settle the original attempt as failed before an explicit
retry. Transport termination never establishes committed business success.

Native progress reports matching local and Origin observations under the same
original execution authorization. Task budgets count complete matching Origin
usage once; missing usage and unknown outcomes do not invent token values.

After an exact terminal reconciliation, completed work returns the durable
result or a bounded next decision becomes possible. The same completed request
does not require repeated idle confirmation. Retain unknown and failed evidence
alongside later resolutions.
