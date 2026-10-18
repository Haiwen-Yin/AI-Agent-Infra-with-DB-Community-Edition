# Chuanxu Community Edition architecture v5.0.0

> Installed product: **Chuanxu Community Edition**; supported backends: **oracle, pg, yashandb**; edition: **Community**; license: **Apache-2.0**. Other backends and Enterprise-only capabilities discussed below describe differences; they do not extend this package's scope.

[简体中文](architecture_zh.md)

## Product and database boundary

The delivery registry defines five packages and seven database acceptance targets.
The unified Chuanxu Community package includes Oracle, PostgreSQL and YashanDB
adapters. OpenTenBase AgentX is an independent PostgreSQL-only Community product.
The three Chuanxu Enterprise packages remain database-specific. This package
supports **oracle, pg, yashandb** under **Apache-2.0**.

Shared business services are implemented once. Configuration selects one backend
before native driver import and pins it for the process lifetime. Unsupported,
missing or contradictory selections fail before connection. Selecting another
backend requires a separate prepared target and a process restart; it is not
cross-database data migration. Package manifests drive UI, health and knowledge
identity. A label or environment variable cannot enable Enterprise-only code.

## Database entities and native adapters

The database is authoritative for Principals, organizations, Security Domains,
Channels, Task Plans, Steps, Workspaces, Branches, Loops, Graph definitions and
runs, Memory revisions, Knowledge, Skills, attempts, leases and audit. Typed
relationships, foreign keys, uniqueness, transaction checks and immutable history
carry operational meaning. JSON carries bounded content and protocol envelopes,
not a second authorization or execution model.

| Concern | Shared contract | Backend responsibility |
|---|---|---|
| Identity | Authenticated Principal and independent Agent identity | Native End User, LOGIN role or database user |
| Authorization | Current scope, membership, grants and resource policy | Enforced grants, row policy or restricted source projection |
| Search | Authorized lexical/vector candidates and current provenance | Oracle Text, PG extensions or YashanDB facilities |
| Property graph | Database entities remain truth; graph is a filtered projection | Native graph adapter and compatible SQL |
| Deployment | Checksum-bound ordered manifests and postflight | Backend SQL, prerequisites and native driver |
| Durable execution | Task/Step, attempts, fenced leases and reconciliation | Atomic updates and concurrent row locking |

Ordinary Business Agents never use the Schema Owner as a fallback. PostgreSQL
uses non-superuser control-plane ownership with forced RLS and dedicated Agent
roles. Oracle and YashanDB retain their own native identity and privilege
boundaries. See [minimum privileges](minimum-privileges.md).

## Human, Agent and collaboration planes

Dashboard and Portal sessions resolve to Human Principals; Agent Gateway requests
resolve to active registered Agents and exact instances. Permission revisions,
expiry, suspension and revocation are rechecked. Session-bound mutations require
CSRF protection. Human self-registration and external Agent enrollment have
independent policies.

A Security Domain is the collaboration authorization boundary. A Channel is an
attributable conversation surface inside that boundary. Channel membership does
not grant access to Knowledge, Memory, tools, models or database rows. Legacy
execution groups require explicit current Domain bindings and membership; graph
edges and descriptive sharing metadata are not grants.

Enrollment binds sponsor, owner, runtime, environment, domain and admission
policy. Registration, credential proof, activation, instance token scopes and
resource grants are distinct steps. Platform-hosted business Agents also need an
approved template, deployment target and verified isolation. Community and
Enterprise approval rules differ as documented in [operations](operations.md).

## Durable work and continuity

Task Plans and Steps are reused by native jobs, A2A and DB4A2A. Typed execution
links bind the transport's delivery/run identifiers to the same task identity.
Leases and fencing reject stale completion. Duplicate requests use idempotency
keys; an uncertain external send remains unobserved until reconciled, rather
than being blindly repeated.

Work contracts, responsibilities, revisions, handoffs, candidates, reviews and
publications are separate database entities. Context assemblies reference exact
authorized source snapshots and digests. Derived summaries retain constraints
and source lineage; later source revocation blocks reuse. Branch policy and
expected versions apply at handoff and execution. See
[continuity operations](continuity-operations.md) and [DB4A2A](db4a2a.md).

Graph Engineering compiles published definitions into database-backed Runs,
Nodes, Attempts, Events and Checkpoints. Barriers persist participant snapshots,
arrivals and one-winner release decisions. Waiting at a barrier does not retain a
worker lease. Loops reuse bounded budgets and the same execution controls.
Offline replay and migration preflight are diagnostics; they do not run external
effects or migrate a live graph.

## Knowledge, memory and model plane

Portal allocates eligible local managed Agents; it is independent of external
Agent registration. Portal and Channel answering share authorized Knowledge
retrieval, ambiguity handling and model preparation. Retrieval uses the
intersection of the Human's and Agent's current rights. References, partial
coverage, general-model answers and unavailable models are distinguished.
Versioned Memory, approved inputs and continuity sources reuse existing entities.

LLM Provider Profiles are versioned database records. Model names and a /v1 URL
do not establish protocol or feature support. Health checks and capability
probes bind evidence to the exact configuration revision. Refusals, incomplete
finishes, truncated streams and mixed-model chunks cannot count as successful
capability evidence. Client connection cancellation does not prove provider
compute cancellation.

The optional model gateway keeps provider credentials server-side and records
bounded usage, cost provenance and latency. Direct calls remain unobserved
unless verified evidence is imported. The wallboard projects authorized
read-only aggregates; it is not an execution or approval surface. Embedding
Profiles, immutable Contracts, Spaces and Bindings prevent incompatible vectors
from entering the same search space.

Current product facts are published through the existing built-in Knowledge
lifecycle and public Knowledge entities in one transaction. Only unchanged,
hash-matched legacy product seeds are superseded; user-edited Knowledge remains.

## Controlled integrations and isolation

MCP, A2A, telemetry, tools and framework execution reuse current authorization,
exact contracts, attempt records, bounded requests and audit. Protocol versions
and SDK versions are separate. Current supported interoperability and limitations
are in [Agent extensions](agent-extensions.md).

Fixed LangGraph execution uses isolated prepare/model/finalize stages; the
platform database retains task and recovery authority. Arbitrary user graphs,
framework checkpoints, effect replay, live graph migration and global autonomous
repair are not enabled by a new upstream release.

Control-plane compatibility does not prove host isolation. Native execution must
pass the supported host, UID/GID, namespace, cgroup, seccomp, filesystem and
egress gates. Remote Agent termination is not claimed without an observed
infrastructure adapter result. See [runtime isolation](runtime-isolation.md).

## Deployment and service boundaries

The canonical listener is FastAPI `web_app:app`. The React Dashboard is at
`/app/`; Portal and retained routes use the request-local compatibility bridge.
The bridge does not create a second identity, listener or scheduler.

Bootstrap Deployment Agent executes only package-selected SQL and records
checksums, steps, readiness and handoff. It does not turn model text into SQL or
privileges. v5.0.0 retains the complete migration chain through
`102_v5_0_0_network_access.sql`. Historical SQL filenames remain unchanged.

Process restart recovery uses database leases and recorded outcomes. Database
backup, replication, standby promotion and RPO/RTO remain deployment
responsibilities. A successful build or health request is not release acceptance:
all seven classified targets, current package hashes and applicable workflows
must be verified. See [deployment](deployment.md), [migration](migration.md) and
[recovery](recovery.md).
