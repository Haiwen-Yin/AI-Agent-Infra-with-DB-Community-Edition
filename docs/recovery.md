# Recovery and availability v5.0.1

> Installed product: **Chuanxu Community Edition**; supported backends: **oracle, pg, yashandb**; edition: **Community**; license: **Apache-2.0**. Other backends and Enterprise-only capabilities discussed below describe differences; they do not extend this package's scope.

[简体中文](recovery_zh.md)

## Authoritative state

The selected database stores Task Plans/Steps, Graph Versions/Plans/Runs,
Attempts, State Events, Checkpoints, leases, fencing tokens, continuity
records, delivery queues and audit/governance facts. Web, Agent, Scheduler
and Worker processes must not become the only owner of that state.

Management-channel leadership terms, node rollout, signed package staging,
Skill distribution, containment and session policies are durable facts too.
An eligible replacement can acquire a new term after the current lease
expires; the former leader cannot write with an old fence. This is application
availability against an existing database, not database-cluster HA.

## Process restart

1. Stop accepting new side effects while the database is unavailable.
2. Reconnect to the same classified target and verify identity, migration
   ledger, current permissions, source digests and capability policy.
3. Reclaim only expired work within the appropriate node/service scope.
4. Reject stale or expired fences. Exact replay of an already committed
   completion returns its existing result.
5. Reconstruct legal State from a valid Checkpoint and later State Events.
6. Resume only with current budgets, leases and authorization.

A local Web restart does not revoke leases belonging to other nodes.
Native executions require the claiming Worker, node, fence and CLAIMED state
at completion. Continuity/model requests additionally retain their original
Gateway credential and instance/context bindings; a replacement token cannot
repair a revoked original credential.

Uncertain model/tool/remote effects remain UNOBSERVED until reconciled.
Do not automatically resend a NON_IDEMPOTENT action. An external effect key
can deduplicate only when the receiving service honors that contract.

## Domain-specific recovery

| Domain | Recovery rule |
|---|---|
| Deployment | Resume the same journaled plan, target and verified action digests; never guess an unknown partial schema |
| Embedding | Retry expired fenced jobs; re-embedding uses a new Space before an authorized cutover |
| Graph | Preserve exact Version/Plan/schema digests, checkpoints, state and attempts |
| Work continuity | Retain immutable handoff, revision, context and original credential evidence |
| Protocol delivery | Retry only within the registered bounded policy; preserve cancellation, dead-letter and unknown outcomes |
| Compliance (Enterprise) | Reclaim expired evaluation leases; keep finding/exception identity and audit |
| Signed rollout/Skill | Keep the prior directory and Agent version until verified safe-point activation |

A node in DRAINING keeps bounded active work and rejects new claims. It must
not enter MIGRATING before that affected work is drained. Missing Skill
acknowledgements are drift, not permission to force-switch a running turn.
The cooperative Skill wrapper does not isolate a process that bypasses it.

Stale compliance evidence degrades posture; it does not autonomously
quarantine or restore authority. Recovery of a quarantined Agent uses the
governed remediation path and retains the triggering finding. System Agent
identities are not recovery credentials for a Human or schema Owner.

## Backup and upgrade

Before modifying an existing database, retain a coordinated, tested database
backup, private configuration, encryption key, deployment journal and exact
program archive. The operator confirms that boundary; a client flag does not
verify the backup. See [migration](migration.md).

Drain only the affected writer class. Oracle task migration retains resumable
copy/check/cutover phases rather than imposing a platform-wide write outage.
On failure, preserve the journal, prior files and database recovery facts.
Resume the verified plan or use the approved database restore procedure.

A program rollback must match the restored database/schema and supported
product/edition contract. Do not run a historical v4.1 profile against a current
schema as an assumed downgrade. Database conversion, cross-product rebranding,
credential rotations and irreversible external effects require their own
explicit recovery plan.

## Database availability

Database replication, storage durability, backup and failover are deployment
responsibilities. Choose the selected database's approved HA design and test
it in that environment. Process-replacement tests do not establish standby
promotion, cluster failover, RPO or RTO.

After a customer-managed failover, reconnect application nodes and verify
target identity, ledger, invalid objects, authorization, leases and Graph
readiness before traffic resumes. An unavailable or unrecoverable database
cannot be replaced with in-memory authority.

## Artifact and evidence integrity

Content-addressed Artifacts retain classification, retention and legal holds.
If content is unavailable, keep its digest and transition metadata and report
the missing payload; never silently substitute different bytes. Legal hold
blocks purge. Support exports contain sanitized, bounded evidence rather than
credentials or full configuration. See [release signing](release-signing.md)
and [continuity operations](continuity-operations.md).
