# Shared model capacity and request observations

> Installed product: **Chuanxu Community Edition**; supported backends: **oracle, pg, yashandb**; edition: **Community**; license: **Apache-2.0**. Other backends and Enterprise-only capabilities discussed below describe differences; they do not extend this package's scope.

An explicitly registered model resource has one database coordinator, versioned
capacity policy, authenticated participants, Profile bindings and provider URL
aliases. Capacity defaults to one. Register every address for the same inference
resource in that group. A new Profile pointing to a registered address also
requires admission; changing its name does not bypass the queue.

Use **Platform configuration → LLM Provider Profiles → Shared model capacity**
to register a resource and its requesting principals, bind saved Profiles, inspect
requests, or record a policy revision. Refresh only reads persisted state.
These controls require current model Gateway management authority. Read-only
sessions cannot change them. They require the v5.0.2 runtime contract and
migration 106, not merely a newer browser bundle.

## Coordination boundary

All participating processes must use the same authoritative coordinator. Route
other installations through its model Gateway and register their authenticated
identities. Locks in separate databases do not create a global queue. Calls
outside supported observed routes remain unobserved. Unsupported legacy direct
and unsaved draft probes reject registered resources before sending; use a saved,
authenticated Profile route instead.

For separate databases, an administrator first registers the participant and a
saved upstream Profile on the coordinator, then creates an enrollment with
`POST /api/model-gateway/coordinator-bindings`. It fixes the capacity group and
policy revision, participant/installation identity, original Gateway credential,
upstream Profile revision and originating Profile revision. On the originating
installation, save that Profile with the enrolled Gateway credential and the
fixed URL `/api/model-gateway/coordinator/{binding_id}`, then register it with
`POST /api/model-gateway/coordinator-routes`. Profile or policy changes require
an explicitly selected matching enrollment; changing the URL cannot silently
restore a direct route. Keep machine credentials in encrypted configuration.

The originating installation authorizes its own business source. It reserves
central capacity, rechecks the original credential, source and Worker fence in
one local transaction, and sends a short-lived proof for that exact payload and
reservation. The coordinator authenticates the enrolled installation and checks
its own capacity and upstream authority. Neither database claims to authorize
the other database's private source records. There are no caller-supplied
callback URLs or automatic direct fallback.

Native and Channel Workers, Portal answers, managed-input uses, evaluations,
retrospectives, exact-contract probes and Gateway forwarding retain their original
business request and credential. Dispatch rechecks the Profile, principal,
credential, resource access, source disclosure and Worker lease/fencing.
A replacement credential cannot repair a revoked original one. Background
Workers cancel unused queued admissions and fail without sending instead of
holding a business lease while waiting for capacity.

## Completion and cancellation

Queued and unused reserved requests can be cancelled without a provider send.
Closing a client connection after dispatch is a local cancellation; it does not
prove remote generation stopped. Uncertain sends continue to occupy capacity.
Expired dispatch leases never automatically free that slot or authorize a retry.
Socket, stream-idle, queue and overall deadlines have separate meanings.

A trusted complete response can free transport capacity even when its business
output is refused, truncated or rejected. An operator can separately resolve an
unknown request after verifying that exact original request ended. Resolution
binds the admission, attempt, fence and current version. The HTTP operation
records **operator confirmation**; it cannot claim independently observed remote
termination. Failed and unknown evidence remains in history. This workflow
does not issue idle-generation probes.

For a remote originating request, read
`GET /api/model-gateway/origin-requests/{receipt_id}`. An explicit
`POST /api/model-gateway/origin-requests/{receipt_id}/reconcile` supplies the
expected version, reason and idempotency key. This operation only reads the
fixed coordinator with the original enrolled credential, then rechecks local
business authority before saving a separate immutable resolution. A central
request that remains unresolved leaves the local request unknown. Local Human
confirmation cannot release central occupancy. Operator-confirmed transport
termination does not establish a complete Provider response or business
success; original unknown usage remains unknown. Task recovery requires this
exact transport evidence and its own explicit authorized retry decision.

## Timing and usage

Execution progress reads the same admission and source-attempt identities as
model metadata. It separates client-observed queue duration, dispatch-to-first-
answer-content, local provider-request duration and total request duration.
Non-streaming first-content time is unavailable. Provider prefill/decode
measurements remain unavailable without endpoint evidence. These measurements
do not establish answer quality or remote termination.

Input/output totals, cache reads/writes and reasoning tokens retain provenance.
Cache and reasoning details are not added again to totals. Missing values remain
unavailable; a reported zero remains zero. A derived total is labelled as the
sum of reported input and output. Refused or truncated output can still carry
observed usage. Unknown sends retain incomplete observations.

Gateway usage/details and quota settlement commit together for the exact
authorized request. Repeated settlement returns the existing identity;
conflicting observations are rejected. Native dispatch metadata is an observation,
not a second charge for a Gateway request. Replay-snapshot storage failure does
not release or repeat already settled consumption. Existing pricing with no
cache-write tariff leaves cost unavailable when cache-write tokens were observed.
Later capacity reconciliation does not overwrite unknown usage.

The originating database retains a bounded immutable observation linked to its
local receipt and the coordinator's request/admission. Its counts come from
the authenticated coordinator's actual response observation. This makes remote
usage available to the original business diagnostics without charging it again
or exposing prompts, output or upstream credentials.

Metadata excludes prompts, answers, credentials and hidden reasoning text.
Business views recheck original resource authority before reading observations.
They do not claim visibility of arbitrary direct external calls.

See [the Chinese guide](model-endpoint-capacity_zh.md),
[governed model workflows](model-workflows.md) and
[continuity operations](continuity-operations.md).
