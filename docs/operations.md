# Chuanxu v5.0.1 Operations and Technical Documentation

> Installed product: **Chuanxu Community Edition**; supported backends: **oracle, pg, yashandb**; edition: **Community**; license: **Apache-2.0**. Other backends and Enterprise-only capabilities discussed below describe differences; they do not extend this package's scope.

[简体中文](operations_zh.md)

This guide covers deployment, migration, recovery, permissions, models and
acceptance for the current package. The steps and linked English guides can be
read independently. Work handover, context, candidate review and the Skill
client are covered in the [continuity operations manual](continuity-operations.md).

## Selecting people and Agents

For Channel membership, ownership transfer, branches and authorization, search
by name or username and select the intended Principal. People and Agents may
share a display name; check the type. The selector submits the immutable ID.

Add a person or Agent to the Channel's Security Domain first, then use
**Channels → Manage → Select members**. Candidates exclude inactive, expired or
existing Channel members. Channel membership never grants Domain access.
Platform management Channels accept only the required subjects and roles.

A Business Agent request may identify its Human owner by an existing username.
The approved Agent retains the request's readable name. Community permits an
authorized administrator to process their own request; Enterprise requires
another authorized administrator. The server enforces the template's minimum
isolation level.

## Deployment

Select the product first, then a supported database backend. The unified Chuanxu
Community package supports three backends; OpenTenBase AgentX supports only
PostgreSQL; Enterprise packages remain database-specific. Each process uses one
backend's SQL and driver. Oracle requires a separate PDB, never the CDB root.
YashanDB also requires a separate PDB. PostgreSQL requires a separate database
and Owner. An existing baseline, system or business database is not an empty
initialization target.

The DBA creates and opens the target, tablespaces and independent Owner, and
prepares backups, network access and extensions. Platform initialization does
not create clusters, change firewalls or replace DBA authorization.

| Database | Check before initialization |
| --- | --- |
| Oracle AI Database 26ai | AL32UTF8, Partitioning, valid Oracle Text, bounded tablespace quotas and the packaged `0_oracle_database_prerequisites.sql`. Both Community and Enterprise require the managed End User, DATA ROLE, DATA GRANT and session-role prerequisites. Thin-client settings must match database transport encryption; do not disable encryption to bypass a connection failure. |
| PostgreSQL 18 | The authorized environment currently uses 18.6. Check role management, AGE, vector and job-extension prerequisites in `0_pg_database_prerequisites.sql`. The Owner and each Agent have separate LOGIN roles; ordinary Agents cannot bypass forced RLS. |
| YashanDB 23.5.4+ | Verify the correct PDB DSN, separate user, object grants, character set, tablespaces and packaged prerequisites. Match the native client and yaspy to the server. Oracle-only syntax and error handling are not portable. |

Extract into a trusted directory and verify the supplied SHA-256. When signature
verification is required, use an independently obtained public key and the
[release verification guide](release-signing.md). Install Python 3.14+ and run
from the package root:

```bash
bash scripts/install_offline.sh
bash scripts/config_wizard.sh
```

Offline installation verifies bundled dependencies and creates this package's
`.venv`; global dependency installation is unnecessary. The wizard configures
the database, Web host and port, model and Embedding. Ports must be 1–65535.
External access also depends on proxies, firewalls and routing.

First initialization uses the deterministic Bootstrap Deployment Agent; it does
not require an external Agent or live model. This example selects PostgreSQL
Community. For other supported targets, select `oracle` / `yashandb` and
`community` / `enterprise` as appropriate:

```bash
bash scripts/install_platform.sh initialize --version 5.0.1 \
  --database pg --edition community --config config.json
bash start_web_server.sh start
```

Initialization verifies an empty target, prerequisites, ordered migrations and
the baseline manifest. It prompts for a deployment-specific administrator
password of at least 12 characters, creates the Human administrator and native
management Agent, and retires the temporary deployment identity. There is no
universal default password. Oracle/YashanDB v5.0.1 fresh deployment and upgrade
also require SYS to prepare the narrow account-status view in the exact
application PDB before preflight. A missing or incompatible view blocks
deployment; the application does not repair it. See
[native identity prerequisites](native-identity.md). After interruption, inspect the journal and resume
through the same entry point. Do not skip failed steps or treat unknown objects
as an empty target.

Restrict `config.json` and the encryption master key to the operating account
and retain them in the deployment's secret management. Preserve
`~/.ai-agent-infra/master.key`; generating a different key cannot repair existing
ciphertext. Runtime/Business Agent configuration contains only its own
credentials, never Owner fallback credentials.

After startup, check `/api/health` for process/version, `/api/ready` for database
readiness, and the management page for database governance. These are separate
checks; none alone establishes release acceptance. Reverify the deployment with:

```bash
bash scripts/install_platform.sh verify --version 5.0.1 \
  --database pg --edition community --config config.json
```

Use `CX_PUBLIC_BASE_URL=https://platform.example.com` for the public address
behind a proxy. The platform generates model relay addresses; do not substitute
an arbitrary third-party relay. Stop with the package's `start_web_server.sh
stop`, after checking the directory, port and process to avoid stopping another
installation. See [deployment](deployment.md).

## Upgrade and migration

v4.4.14 was a normal release ending at migration 82. v4.4.15, v4.4.16 and
v4.5.0 end at 97; v4.5.1 ends at 100; v4.5.2 ends at 101; v5.0.0 ends at
102. v5.0.1 adds 103–105; its target contract does not establish release acceptance.
Single-backend packages use their sole `scripts/deploy/baseline_v*.json`;
unified packages use the selected manifest under `scripts/deploy/<database>/`.
Historical template filenames do not define the deployment terminal.

Complete native backup and a recovery drill, recording the target, applied
checksums, runtime directory and processes. Never reinitialize existing data.
Run the packaged preflight, then confirm and apply the journaled sequence through
the bounded deployment entry point. Keep failed preflight logs and fix the
cause; clearing a database does not resolve a migration defect.

Migration 85 repairs Task status/Step relationships; 86–88 add relational Work
handover and native execution links; 89–93 protect dynamic MCP discovery and
dispatch provenance; 94 stores per-revision parallel handoff policies; 95–96
bind context Workers and original Gateway credentials; 97 stores native source
snapshots. Applied SQL and structure manifests retain their original checksums.
A successor may replace an old verification contract only after it is APPLIED.

Oracle Task migration uses resumable copying and verification, draining only
affected Task writers at final cutover. Do not expand this to a platform-wide
write outage. Handoff-policy backfill and context Worker upgrades similarly
drain only the affected old writers. Verify structures, historical dependencies,
permissions and readiness before restoring traffic. On failure retain the old
directory and journal and resume from the recorded phase; do not forcibly stop
all services. See [migration](migration.md).

## Recovery and isolation

The database owns runtime state, leases, fencing, Tasks, checkpoints and audit.
A restart reclaims only expired local-node leases; stale Workers cannot commit
old fences. Database unavailability stops new effects, rather than enabling an
in-memory authorization bypass. Replication, backup, standby failover and
RPO/RTO remain operator duties.

An uncertain context-model outcome records `UNOBSERVED` without automatic
resend. A replacement token cannot authorize an old request whose original
Gateway credential was revoked. Work, handoff, review and input receipts retain
history; revoked access or deleted sources block later reads without erasing
audit facts.

Control-plane startup and safe execution of untrusted Agents are separate
admission decisions. Strong isolation requires independent UID/GID, workspace,
namespaces, cgroup v2, seccomp, read-only root, minimal capabilities and a
protected Host Manager. Verify the exact image, kernel, policies and patches
with the packaged host gate. Current dependencies require glibc 2.34+ and a
supported Linux baseline; retired RHEL/Oracle Linux 8 is not supported by this
package.

Agents bypassing the managed runner do not have verified process isolation or
termination. The cooperative Skill client holds a shared process lock for each
managed turn, switches atomically at an exclusive safe point and retains old
files. It cannot constrain independent processes that bypass it. Database grants
do not establish host isolation. See [recovery](recovery.md),
[runtime isolation](runtime-isolation.md) and
[Linux compatibility](linux-platform-compatibility.md).

## Security and permissions

Humans, platform Agents, external Agents and the Schema Owner use distinct
identities. Invalid credentials cannot fall back to deployment credentials.
Knowledge uses company-public, organization-subtree, hierarchy-level and
Human/Agent-private scopes. Security Domains authorize collaboration; Channels
carry messages without widening data access. Enterprise approval, audit and
emergency controls are enforced by the server and database. See
[security](security.md) and [minimum privileges](minimum-privileges.md).

## Native Agent offboarding

Use the authorized Agent offboarding workflow, not a direct account DDL or
compatibility decommission operation. Inspect `native_identity_revocation` and
require `status=COMPLETE` with `audit_status=RECORDED` for the reported
new-login/local-connection result. Keep PENDING/PARTIAL failures for exact
reconciliation and retain identity mappings and audit. A disabled Principal,
revoked token or locked login does not prove every existing external session
or remote process has stopped. Follow [native identity operations](native-identity.md)
for permission, disposition, result and incident-containment boundaries.

## Models, MCP and A2A

Model/tool posture distinguishes `OFF`, `READ_ONLY`, `PROPOSAL_ONLY` and
`GOVERNED_EXECUTOR`. MCP continuity clients authenticate through the Gateway;
dynamic tools need explicit per-tool exposure and current invocation authority.
A2A supports bounded, controlled HTTP JSON 1.0.1 operations. Capability state
and authorization are checked separately; this is not full protocol/SDK support.
Model-generated writes, policy changes, Agent control, external contacts and
releases default to proposals.

Provider evidence records model identity, verification, tool proposals, usage,
latency, timeout, cancellation, retry and terminal state, without hidden
reasoning or full prompts. Unobserved direct traffic is not zero consumption.

A Provider Profile defines its URL, model ID and use scope. Keyless services may
use an empty API key. Health requires a valid completion from the intended
model; endpoint reachability is insufficient. Profiles still referenced by
Portal, active native Agents or pending requests cannot be retired. The optional
gateway permits direct and gateway routes to coexist, metering only observed
traffic.

Portal retrieval intersects Human and Agent access. Policy determines whether
missing Knowledge permits a general-model answer; authorized extracts can be
returned without a model. Distinguish citations, missing Knowledge and model
failure. Explicitly mention the platform management Agent by its English
display name in a Channel; Enterprise also has a separate Compliance Agent.
Commands retain their current authorization and cannot borrow a Human or Owner
identity. See [model usage](model-usage-and-wallboard.md) and
[API reference](api-reference.md).

## Graphs, organizations and DB4A2A

Graph runs, leases, checkpoints and events are database facts; the graph is an
authorized projection. DB4A2A passes context references bounded by revision,
digest and scope. Receivers still authenticate independently. This is distinct
from standard A2A interoperability.

Organizations describe responsibility and Knowledge scope; Security Domains
authorize collaboration; Channels provide communication. Recheck authority
after membership changes. Graph edges and legacy groups do not grant access.
Graph Runtime core and authorized inspection are available. Manifest drafts,
read-only SLO and checkpoint forks are controlled. Pinned frameworks, A2A and
OTLP need separate decisions and evidence. Effect replay, live dynamic Graph
migration, arbitrary frameworks and global autonomous repair remain disabled.
A prompt or Skill cannot change these states.

Principals, organizations, Domains, Tasks, Steps, executions, Work contracts,
handoffs, revisions, sources, candidates, reviews, releases and diagnostics have
typed entities and relationships. Content bodies do not replace typed state or
authority. Transactions commit state and audit consistently; keys, foreign keys
and immutable history provide concurrency control and traceability. Native
resource links use stable IDs, never mutable Task status. See
[Graph engineering](graph-engineering.md), [organization governance](organization-governance.md)
and [DB4A2A](db4a2a.md).

## Memory, assets and answer-quality operations

Verify migrations 103–105 and actual schema manifests before enabling their
v5.0.1 service paths. In Dashboard **Workspaces → Work continuity**, use the
separate asset, note and retrospective/answer-evaluation panels. Platform
configuration stays in Dashboard; a Portal session does not grant management.
Follow [memory and notes](memory-working-notes.md),
[Agent assets](agent-context-assets.md) and [answer quality](answer-quality.md)
for complete examples and permission requirements.

For an unavailable answer, inspect requested/actual retrieval strategy,
channel degradations, evidence status, current Human/Agent readers, disclosure
policy and Profile health/version. Distinguish no evidence, partial coverage,
contradictions and model failure. A generic model answer requires current
supplement permission and an independent source notice. Turning permission off
also blocks an old queued supplement before dispatch/publication.

For stale notes or assets, read Work/note/binding versions, validity and exact
source authority before editing. Never solve a version conflict by silently
substituting the latest expected version. Expiry/retirement can block current
context use while authorized history remains retained. Restore memory as a new
successor and keep its historical origin receipt.

For sync failures, inspect the configured HTTPS endpoint/pinned commit, allowed
paths/content types, total byte limit, credential reference, source state,
attempt count, error and current lease/fence. No failed fetch may advance the
checkpoint. A 404 does not authorize deleting previously published Knowledge.
For retrospective or evaluation failures, preserve the original Task link,
frozen Profile/policy/source revisions and output digest. Unknown model sends
remain `UNOBSERVED`; do not automatically resend or clear ledger/lease state.
Pending candidates require independent review and explicit publication; final
answers require distinct factual/citation review where the rubric demands it.
Keep private configuration, encrypted evidence and credentials outside public
packages and support excerpts.

## Release decision

The release validator writes the current version's release manifest at the
selected `--manifest-output` path. A release requires an explicitly successful
decision and five exact package hashes bound to seven target acceptance records.
Source, database, UI, dependency and material evidence must be current. Preserve
the stated limits: acceptance does not certify customer capacity, arbitrary
host isolation or database-cluster HA. Classify test targets as temporary; retain
baseline/system databases and protected TEST PDBs during cleanup.
