# Curator-supplied document snapshots

> Installed product: **Chuanxu Community Edition**; supported backends: **oracle, pg, yashandb**; edition: **Community**; license: **Apache-2.0**. Other backends and Enterprise-only capabilities discussed below describe differences; they do not extend this package's scope.

Use this path for explicitly reviewed local documents that cannot truthfully be
described as an HTTPS response or a fetched Git commit. It uses the existing
Document Source, exact source revisions, Knowledge candidates, independent review
and explicit promotion. Import never publishes automatically or executes content.

## Prepare complete source units

Each unit contains `path`, `title`, exact `text` (1–4000 Unicode characters),
`content_type` (`text/plain` or `text/markdown`), `origin` and optional `intake`.
Do not cut a table, code fence, condition, unit, negation or exception to meet the
limit. Submit a complete short original, or have a curator explicitly review a
self-contained excerpt and its necessary context. Larger material needs authored
units before import; there is no automatic fixed-width truncation.

`origin` records the original `locator`, exact `revision`, `parent_sha256`,
`parent_char_count`, Unicode `start`/`end` offsets, `decision_status`,
`context_reviewed: true` and a substantive `context_note`. Status is one of
`CURRENT`, `PROPOSED`, `HISTORICAL`, `REJECTED`, `SUPERSEDED`. Source text and notes
remain untrusted data. They do not authorize an operation.

The server verifies a whole original's SHA-256 and binds every submitted body and
its provenance to the immutable revision. For an excerpt it verifies the submitted
span length, bounds and provenance binding; it cannot independently verify an
unsubmitted parent or prove semantic completeness. The curator must verify the
parent bytes and context. Distinguish an AI-assisted review from a Human review.
Missing applicability can remain a pending candidate. An observation/import date
does not establish the original's effective date. An explicit curator applicability
decision must be recorded as such.

## Configure and import

With `lib.knowledge_curated.Document`, validate the units and calculate
`manifest_digest(documents)`. It covers their exact source payloads, excluding
candidate intake metadata. Configure an existing Document Source through
`POST /api/agent-extensions/sources`, with the exact endpoint
`urn:chuanxu:curated:sha256:<manifest_digest>`, the unit paths, accepted text types
and a sufficient `max_bytes` (128–262144). Keep the existing Security Domain,
active Agent and current source-owner/Agent permissions. Source configuration
requires the existing platform-management entry permission.

Submit `expected_version`, `documents`, `reason` and `idempotency_key` to
`POST /api/agent-extensions/sources/{source_id}/curated-import`. A request contains
1–50 unique paths, at most 1 MiB of JSON, and must match the configured manifest,
paths, types and combined body-byte limit. Authentication, CSRF and current source
write authority still apply. No network credential or pinned Git commit is valid
for this URN. `/sync` refuses it instead of pretending to fetch it.

Exact encrypted revisions, pending candidates, checkpoint, request receipt and
required audit commit together. An audit failure rolls back the import. A matching
idempotent replay reuses its revisions/candidates; it cannot reactivate a retired
revision or bypass a revoked Source. The response's
`CURATOR_SUPPLIED_NOT_REMOTE_FETCHED` explicitly identifies the acquisition method.

Agents use the same service at
`POST /api/agent-gateway/continuity/sources/{source_id}/curated-import`.
The MCP `continuity` tool and `python -m lib.continuity_cli call --request-file request.json`
share the typed `source_curated_import` operation. Its `request` adds `source_id`
to the import fields above. `source_read` requires only `source_id` and returns
configuration metadata without loading all source bodies. The operator configures
the Source first; this path grants no platform-management credential or new Source
configuration authority. Gateway token/instance authentication, current
`knowledge.write`, Source and Domain checks apply. Human Web Session writes retain
their CSRF guard.

## Review, publish and update

Use the existing candidate preview, revise, independent review and promotion
routes described in [guided intake](knowledge-intake.md). The proposer cannot
approve their own candidate. Complete intake and current authority remain required.
Promotion creates private Knowledge; audience metadata does not itself share it.
Sharing and context publication require their separate current authorization.

Exact source reads and candidate-projection context/individual Knowledge reads
recheck the original sources as the current reader. Revoking a Source prevents
these subsequent reads without deleting immutable published history. Previously
delivered data is not recalled. Do not infer native SQL closure, every inventory
surface, or end-to-end acceptance from this service-level behavior.

Authenticated Knowledge search and cursor inventories also recheck original
sources, including for an administrator with broad inventory rights. Counts cover
returned authorized entries; raw SQL totals are not exposed. A cursor advances
over its scanned candidate page, so source withdrawal can yield a short page with
a valid next cursor. Cursors remain bound to the current identity and filters.

New task assemblies use a `SOURCE_CONTEXT_V2` rendering policy, binding the body
and applicability envelope into the input budget and digest. Transitive summaries
retain the original decision status; summarizing a proposal does not make it
current policy. A derived item that cannot fit is omitted whole, even when partial
context is requested. Historical assemblies retain their original byte/digest
contract while still rechecking current original-source authority before use.

Reuse the same configured snapshot for unchanged bytes/provenance. A changed
manifest needs a new content-addressed Source snapshot. Retain the predecessor
SourceRef and its real decision status; use an explicit replacement candidate
where a reviewed artifact is superseded. A new import alone neither supersedes
an older policy nor rewrites an already published built-in manual snapshot.
Built-in learning uses trusted publication. A correction within the same product
version creates a separate source snapshot and preserves history and user edits;
see [guided knowledge intake](knowledge-intake.md).

Keep project development history, tenant business knowledge, public product
manuals and evaluation labels in their intended ownership/audience boundaries.
Never import credentials, private archives or gold-answer labels as facts.

## Explicit retrieval applicability

Shared Knowledge retrieval and answer preparation accept optional `applicability`
with exact `product`, exact `version`, timezone-qualified `as_of`, and allowed
`decision_statuses`. The Portal send endpoint accepts that object as
`knowledge_scope`, for example:

```json
{"product":"unified-community","version":"5.0.5","as_of":"2026-11-11T00:00:00+08:00","decision_statuses":["CURRENT"]}
```

Task context assembly accepts the same object as its optional `applicability`
field. An inapplicable optional source produces a `SOURCE_NOT_APPLICABLE`
omission receipt; an inapplicable mandatory source rejects the assembly before
persistence. Omitting the field preserves historical request digests.

Every strategy filters declared applicability before final selection. Citation
checks repeat before disclosure and publication, including original ancestors
of summaries. A body mentioning another release, higher relevance or a later
ingestion time cannot override a conflicting declaration. Versions match exact
identifiers, with an optional leading numeric `v`; ranges and product aliases
are not guessed. Validity intervals include the start and exclude the end. A
date mentioned in a question may describe an event; it is not inferred as an
effective-time filter.

Explicit question versions also constrain retrieval. Legacy sources with unknown
declarations remain usable for unscoped queries, and exact literal versions may
support a question's release. Unknowns cannot satisfy structured product, version,
effective-time or decision filters. Omitting a decision filter preserves truthful
proposal/history labels without making them current policy. Filters grant no
additional access or execution authority.
