# Security contract v5.0.1

> Installed product: **Chuanxu Community Edition**; supported backends: **oracle, pg, yashandb**; edition: **Community**; license: **Apache-2.0**. Other backends and Enterprise-only capabilities discussed below describe differences; they do not extend this package's scope.

[简体中文](security_zh.md)

## Identity and database authority

This package supports **oracle, pg, yashandb** and **Community** features. Database
records determine identity, authorization, capability state, attempts, leases
and audit. Neither model text nor a Skill, graph edge, URL, framework callback,
client-supplied Agent ID or visible button grants authority.

Human users, platform Agents, external Agents and the Schema Owner are distinct
identities. Inactive, revoked, expired, unknown or credential-mismatched identities
fail closed. Ordinary Business Agents use independent native identities and
cannot fall back to owner credentials. Configuration and private encryption keys
must remain readable only by the operating account.

PostgreSQL uses dedicated LOGIN roles, a trusted identity mapping and forced
RLS. Client-set session text cannot override a mapped role. The bounded trusted
owner policy resolves each table's actual owner; ordinary Agents are not owner
members. Oracle uses its native End User/context and data-grant boundary.
YashanDB uses its own user/object-grant enforcement and restricted projections.
Coverage must be demonstrated by native negative tests, not inferred from a
service-side filter. See [minimum privileges](minimum-privileges.md).

Normal Agent offboarding commits platform revocation before the separately
observed native login/local-connection step. Retain the identity mapping and
audited result; a disabled Principal or HTTP success alone does not prove native
closure. Oracle/YashanDB fresh deployments and existing-database upgrades need
the separately prepared narrow SYS status view, not broad dictionary grants.
New-login blocking does not terminate existing external sessions or remote
processes. See [native identity prerequisites and offboarding](native-identity.md).

## Authentication, registration and sessions

Fresh initialization requires a deployment-specific administrator password,
at least 12 characters under the existing policy. Only the Argon2id hash is
stored. There is no supported default password. Noninteractive input uses a
current-user-owned regular file with mode 0600 or stricter; plaintext must not
appear in arguments, journals, evidence or public configuration.

Human self-registration and external Agent registration are independent
policies. Closing the Human registration entrance does not close Agent
Enrollment. Enrollment requires an authorized sponsor, scoped grant, credential
proof and activation. A one-time compatibility client secret or Ed25519 proof
is exchanged for a short-lived instance token. Tokens retain exact scopes,
instance fencing and current authority; enrollment alone does not grant model,
Embedding, tool or data access.

Dashboard and Portal sessions use separate port-scoped cookies. Authenticated
mutations require session-bound CSRF tokens. Status, permission revision and
revocation are checked against the database. Browser storage, request body IDs
and stale cached permissions are not authentication.

## Organizations, Security Domains and Channels

Organizations describe responsibility and Knowledge scope. Security Domains are
collaboration authorization boundaries; Channels are conversation surfaces.
Current membership is checked for listing, message/history/thread access,
Gateway admission and work operations. Membership suspension or revocation
blocks later access without erasing retained history.

A Channel member does not automatically gain Knowledge, Memory, tool, model,
export or database-row rights. Legacy execution groups need explicit active
Domain bindings and current participant checks. A conversion draft lists
candidates for review; it is not a membership grant. Cross-domain transfers
require an explicit Bridge policy and classification checks.

Knowledge reads apply company-public, organization-subtree, hierarchy-level or
Principal-private policy consistently across list, item, graph and retrieval.
Portal and Channel retrieval use the Human/Agent authorization intersection.
Ambiguous vendor/product queries require appropriate relevance or clarification;
an unrelated product document is not a valid answer merely because it matched
a keyword.

## Models, Embedding and untrusted inputs

Provider keys remain encrypted server-side and redacted from reads. The optional
model gateway records request metadata, digests, usage provenance, cost and
latency, not prompts, generated bodies, authorization headers or hidden
reasoning. Direct traffic is unobserved without verified imported evidence.
The wallboard exposes bounded authorized read-only projections.

Health and capability evidence binds the exact Provider Profile revision.
Refusal, incomplete completion, malformed output, truncated streams and mixed
model chunks must not verify capabilities. Closing a client connection does
not establish that a remote provider stopped computation.

Embedding Contracts freeze model, dimension, metric, normalization,
preprocessing, modality and source mode. Writes/searches use the effective
Space/Binding; incompatible contracts do not share similarity calculations.
External Agents require an explicit grant and scoped Gateway token; they do not
receive provider secrets. Missing grants and explicit denials fail closed.

Uploaded documents, images, retrieved Knowledge and remote protocol output are
untrusted data. They cannot authorize tools or rewrite security policy. Managed
inputs remain bounded, scoped, revocable and source-digest checked. Content
retention in Knowledge is distinct from body-free usage/telemetry accounting.

## Work, effects and protocol boundaries

Task/Step, Graph, Loop and continuity operations validate current ownership,
Domain, expected version, source lineage, budget and policy. Attempts use
expiring leases and fencing; stale workers cannot commit after replacement.
State change and audit commit together where the operation requires atomicity.

A2A and DB4A2A share typed task identities but retain independent transports.
A reference or digest does not grant the receiver access. The original sender,
receiver, source snapshot and current policy are checked on retry as well as
creation. External outcomes that were not observed require reconciliation;
blind retries cannot establish exactly-once side effects.

MCP discovery is not execution approval. Only the exact approved read-only
tool contract may execute through the governed path. Rediscovery invalidates
prior approval until reviewed. Remote endpoints need registered protocol,
version, domain, dedicated credentials, bounds and current authorization.
Telemetry sends committed metadata without prompt/output bodies.

Fixed framework execution requires a digest-locked dependency set and verified
immutable root filesystem. Arbitrary frameworks, effect replay, live Graph
migration and global autonomous repair remain closed. See
[Agent extensions](agent-extensions.md) for the supported protocol scope.

## Host isolation and operations

Control-plane startup does not prove that a host can safely run untrusted
Agents. The runtime target must pass UID/GID, namespaces, cgroup v2, seccomp,
read-only-root, capabilities, mounts and egress checks. Agent state cannot
override template minimum isolation. Shared workers must not reuse credentials,
workspaces, conversation state or database sessions across Agents.

Containment revokes instance tokens and reports each action's outcome. Remote
process termination requires an actual infrastructure adapter result; a
cooperative acknowledgement alone is not proof of OS termination. Draining
work for maintenance is separate from incident containment.

Bootstrap Deployment Agent executes only the local checksum-bound manifest.
LLM output never selects SQL, privileges or deployment transitions. Existing
data upgrades require an explicit database recovery boundary. Encryption keys,
configuration and private journals must be preserved during program replacement.
Database replication, backups and standby failover remain operator duties.

## Enterprise boundary

Community packages physically omit Enterprise approval, compliance, audit-view
and other exclusive modules while retaining mandatory audit writing.
Enterprise adds classified resource policy, separated approval, compliance
evidence, retention/legal hold and scoped evidence export.

The Compliance Agent proposes and records remediation; it does not inherit
platform management authority. Platform management conversation is advisory:
typed commands still require risk policy, current permission and applicable
human approval. High-impact decisions cannot derive authority from model output.

Use [release verification](release-signing.md), [recovery](recovery.md) and
[runtime isolation](runtime-isolation.md) for the operational checks. A release
test does not constitute an independent security audit or universal isolation,
capacity or customer-specific compliance certification.
## Source IP admission

Every product provides IPv4/IPv6 allowlist or denylist configuration in Platform
configuration. The policy covers all web entry points, returns a generic denial
and preserves direct `127.0.0.1` recovery with normal authentication. See
[configuration, proxy trust and recovery](source-ip-access.md).
