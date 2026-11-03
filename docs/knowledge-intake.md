# Guided knowledge intake

> Installed product: **Chuanxu Community Edition**; supported backends: **oracle, pg, yashandb**; edition: **Community**; license: **Apache-2.0**. Other backends and Enterprise-only capabilities discussed below describe differences; they do not extend this package's scope.

Knowledge intended as formal shared evidence follows the existing artifact
candidate, independent review and explicit promotion workflow. A file upload,
personal note, source-sync receipt or saved candidate is not publication.

In Work continuity, select a Knowledge candidate and supply its title, body
and exact source references (`family`, `entity_id`, `revision_id`,
`content_digest`). The intake fields describe purpose, original source and
chapter location, responsible Principal, subject, applicable product/business
and version, effective interval, classification and intended audience. Leave
unknowns empty to retain a pending candidate. Never substitute ingestion time
for an unknown effective time. Retain proposed, rejected or historical decision
status; a newer observation alone does not establish current policy.

`POST /api/knowledge-intake/preview` uses the same candidate contract and
current source/domain authorization. It returns actionable missing fields and
bounded source spans, with Unicode character offsets, exact text and digests.
Paragraphs, fenced code and contiguous table rows remain intact. Long semantic
blocks remain whole for author review; split them with their headers, units,
conditions, negations and exceptions intact. A preview performs no model call,
does not save a candidate and does not approve content. Reported duplicate or
conflict coverage is explicit; an unchecked result is not absence of conflicts.

`POST /api/artifact-candidates` saves a pending candidate. A revision preserves
prior content and applicability; its digest binds both. An independently
authorized domain administrator reviews the exact digest before explicit
promotion. Missing metadata blocks approval and promotion. Classification must
match the domain and the responsible Principal must remain an active domain
member. Current source and reviewer authority are rechecked at promotion.
Intake audience records intent; promotion retains private native visibility.
Sharing or cross-domain publication requires its own current authorization.

The equivalent Agent prefix is `/api/agent-gateway/continuity`; use the current
discovered candidate contracts. Direct `knowledge_create`/Gateway creation
retains personal private notes. A direct shared creation is rejected with
`KNOWLEDGE_INTAKE_REQUIRED` and the governed entry to use. Source synchronization
continues to create pending candidates; incomplete applicability must be
completed by an authorized revision before approval. Built-in product manuals
use the separate audited trusted package publication contract.

The typed continuity MCP/CLI entry exposes `knowledge_intake_preview` and the
existing `candidate_create`, `candidate_revise`, `candidate_review` and
`candidate_promote` operations. Platform manuals use `learning_discover` with
optional `role`/`goal`, followed by `learning_read` with the returned `entity_id`
and `content_digest` (as `expected_digest`). Discovery contains metadata only. Each content load
rechecks the current published product version and native source permission.

Built-in learning binds both the product version and a source snapshot digest.
When source documents change within a product version, an authorized
administrator publishes a new snapshot through the trusted publication path.
Original snapshots and digests remain unchanged. Only untouched old native
projections leave current retrieval; user additions remain intact. Publishing
the same snapshot is idempotent. Withdrawn or superseded snapshots cannot be
reactivated by replay. After source changes and before publication, discovery
does not return the old snapshot. Discover the new exact references after the
correction is published.

Existing knowledge is inventoried without altering content, grants or history.
Unknown provenance stays unknown. An explicit remediation plan is needed for
legacy corrections; a successful inventory is not a backfill or a review.
