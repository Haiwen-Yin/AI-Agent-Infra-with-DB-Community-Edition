# Official incident sources and report drafts

> Installed product: **Chuanxu Community Edition**; supported backends: **oracle, pg, yashandb**; edition: **Community**; license: **Apache-2.0**. Other backends and Enterprise-only capabilities discussed below describe differences; they do not extend this package's scope.

Choose STATUSPAGE in Agent context assets to configure the official GitHub or
Cloudflare incident feed. `/incidents/recent/N` selects 1–5 recent records, using
JSON without credentials. Create and explicitly run a synchronization Task;
periodic collection is disabled by default.

One response covers a recent API page, not complete history. Each incident has
an exact revision, a complete overview and separate complete update units.
Unchanged incidents reuse revisions. Failures do not advance the successful
checkpoint; missing records do not establish deletion or resolution. Oversized
units require explicit curation instead of arbitrary truncation.

Units become pending Knowledge candidates with HISTORICAL decision status.
Configuration and successful collection do not publish Knowledge. Guided intake
must establish purpose, responsibility, applicability, classification and audience
before independent review and explicit promotion. AI review remains AI review.

Authorized overview resolution includes a `factual_report` matching the bundled
`report.schema.json`. It binds the actual Task response digest, incident digest
and observation time. Display, creation and declared impact timestamps remain
distinct. An upstream impact label is not internal severity; a declared time
window is not internal MTTR or SLA loss. Root cause, affected users and internal
severity remain unknown, and recommendations remain unapproved.

These missing fields belong to the local factual projection; they do not imply
that the upstream API contains matching null fields or that the provider has
proved a value absent. Generated summaries require source review: the tested
model can blur that attribution. Read update stages as historical, and confirm
the final recorded status and observation time before operational use.

The adapted Chinese PagerDuty template, attribution and original license are in
`docs/enterprise-incidents/`. The open template license does not establish a
blanket redistribution license for official incident bodies. Those bodies are
not bundled as default tenant Knowledge and remain untrusted source data.

Current Source authority governs exact reads, candidate review and context use.
Revoked sources cannot be recovered through old references. The context evidence
view also hides historical identifiers of omitted sources that are no longer
readable.
