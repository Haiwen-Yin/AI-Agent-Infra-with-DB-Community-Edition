# Migration guide v5.0.1

> Installed product: **Chuanxu Community Edition**; supported backends: **oracle, pg, yashandb**; edition: **Community**; license: **Apache-2.0**. Other backends and Enterprise-only capabilities discussed below describe differences; they do not extend this package's scope.

[简体中文](migration_zh.md)

## Current contract

This package supports **oracle, pg, yashandb**. Its generated baseline manifest and
checksums define the ordered deployment contract. v5.0.0 preserves the existing
schema and adds `102_v5_0_0_network_access.sql` for source IP policy entities.
Packaging and product identity changes do not justify modifying applied SQL.
v5.0.1 adds migrations 103–105 for memory quality, context assets and final-answer
evaluation; its generated target ends at 105. This target description does not
declare completed database or release acceptance.

Single-backend baselines are at `scripts/deploy/baseline_v*.json`. In the
unified Community package, each backend has exactly one baseline under
`scripts/deploy/<database>/`. Use only the selected backend's scripts, driver
and configuration. OpenTenBase AgentX can only use the PostgreSQL chain.

| Previously released version | Terminal migration |
|---|---|
| v4.4.14 | 82 |
| v4.4.15, v4.4.16, v4.5.0 | 97 |
| v4.5.1 | 100 |
| v4.5.2 | 101 |
| v5.0.0 | 102 |

These versions were normal releases. Historical migration filenames describe
when a structure was introduced, not the target version to pass to a current
installer. Withdrawn v4.4.8 and unknown partial schemas are not assumed upgrade
sources. Preserve historical evidence and investigate before proceeding.

## Prepare an existing target

Record the current product, database/PDB, owner, running nodes, configuration,
encryption key locations and applied migration checksums. Verify compatibility
with the selected product and edition. Changing databases or moving between
editions is not an automatic data migration.

The database operator owns backup and recovery. Establish and test the relevant
database-native recovery boundary before changing existing data. The client
does not claim to verify a backup. For a noninteractive upgrade, explicit
`--confirm-database-backup` acknowledges that responsibility.

Preserve the private configuration, master encryption key and
`.runtime/deployment/` journal/key files. Never put these in a public release
or support archive. Confirm prerequisites from the selected backend and
[minimum privileges](minimum-privileges.md); an ordinary Agent must not acquire
the deployment owner's credentials.

Before upgrading an Oracle or YashanDB installation to v5.0.1, have SYS apply
the selected backend's separate `0_<database>_v5_0_1_native_identity_prerequisites.sql`
in the exact existing application PDB. It creates the narrowly projected,
read-only `SYS.CX_AGENT_ACCOUNT_STATUS` interface and grants only the exact
Owner SELECT without grant option. This administrator action is not an
application migration, is not run automatically by the installer, and does not
change historical SQL/checksums or terminal migration 105. Read-only preflight
must block a missing, inaccessible or incompatible interface; do not bypass the
check with DBA, full dictionary access or Owner credentials for Agents.
See [native identity prerequisites and revocation](native-identity.md).

## Run the journaled upgrade

Use the installed package's Python environment and work from its root:

```bash
bash scripts/install_platform.sh upgrade \
  --database pg --edition community --version 5.0.1 \
  --config /absolute/path/config.json \
  --confirm-database-backup
```

Replace the database and edition with the supported values for this package.
The installer validates the baseline, source state, ordered script digests and
object postconditions. Already applied entries are accepted only when their
checksums and required structures match. A later migration can satisfy an
earlier structure check only after its own checksum-bound entry is APPLIED.

v5.0.0 republishes current product facts through existing Knowledge entities.
Only exact, unchanged historical product seeds are archived; user edits and
unrelated Knowledge remain. Snapshot publication, public entities, retirement
and audit commit in one transaction. This is not a bulk rewrite of customer
Knowledge or a database conversion.

## Limit the affected write boundary

Drain only writers affected by a migration. Stop new claims for those jobs,
allow bounded in-flight work to finish or reach a safe point, record leases and
resume after strict postflight. Do not impose an undocumented platform-wide
write outage.

Oracle task migration 85 uses resumable copying and checks before the final
cutover. The final boundary covers Task Plan/Step writers, not unrelated
conversations or reads. Preserve its durable phases and fallback objects until
validation permits retirement. Existing task history and dependencies must be
checked, not discarded.

| Migrations | Main retained structure or boundary |
|---|---|
| 85 | Stable task/step relationships and safe status transitions |
| 86–88 | Continuity entities, bindings and typed native execution links |
| 89–93 | MCP discovery snapshots, exact tool contracts and request provenance |
| 94 | Immutable handoff-policy revisions |
| 95–96 | Worker context and original Gateway credential binding |
| 97 | Native source snapshots and source revalidation |
| 98–100 | Agent extensions, fixed-framework lock and root-filesystem digest |
| 101 | Unified A2A/DB4A2A Task Plan/Step association and fenced attempts |
| 102 | Source IP policy pointer, immutable revisions and rules; default disabled |
| 103 | Memory-time/reconciliation/restore facts, immutable working notes and explicit Task-linked retrospectives |
| 104 | Context budgets/representations, Agent asset bindings, configured source revisions and fenced sync/import checkpoints |
| 105 | Versioned answer rubrics, Task-linked runs, encrypted input/output, exact sources and independent Human reviews |

For a v5.0.1 target, verify all three added scripts and schema manifests, including
their actual tables, keys, constraints and native protection. A successful 105
ledger entry does not imply that 103/104 objects exist. Source/model jobs reuse
the existing Task continuity chain; do not introduce a second scheduler or grant
Agent SQL access to their control-plane tables. New time fields remain unknown
for historical evidence that has no reliable event time; never backfill an
invented local timestamp. See [memory evidence](memory-working-notes.md),
[Agent assets](agent-context-assets.md) and [answer quality](answer-quality.md).

PostgreSQL retains service-side stable-plan validation where the historical
status-partitioned Task Plan table has no global PLAN_ID key. This is an
explicit contract, not permission to skip verification.

## Resume and investigate failures

Inspect the returned run ID, local journal and database migration ledger before
taking action. Do not initialize an existing database, clear the ledger, edit a
checksum, skip a failed fragment or assume an interrupted statement committed.

```bash
bash scripts/install_platform.sh status \
  --database pg --edition community --version 5.0.1 \
  --config /absolute/path/config.json --run-id YOUR_RECORDED_RUN_ID
bash scripts/install_platform.sh resume \
  --database pg --edition community --version 5.0.1 \
  --config /absolute/path/config.json --run-id YOUR_RECORDED_RUN_ID
```

A resume uses the original plan and verified completed-action digests. Supply
the protected administrator password file if initialization stopped before the
administrator was committed. An already adopted administrator can be verified
without retaining plaintext. If the original plan or recovery state cannot be
verified, stop and use the database's documented recovery procedure.

## Verify and return to service

```bash
bash scripts/install_platform.sh verify \
  --database pg --edition community --version 5.0.1 \
  --config /absolute/path/config.json
```

Verify terminal migration, invalid objects, keys/constraints, native identity
denials, product identity and current capability posture. Then check health,
database readiness, login, an authorized read/write workflow, task status
transitions, cancellation/recovery and Agent enrollment where used.

Resume only the drained writers and monitor leases, attempts and errors.
Uncertain external effects require reconciliation; a restart does not authorize
a duplicate send. Retain the former program directory and database recovery
boundary for the approved rollback period.

A verified upgrade does not by itself establish customer capacity, database
cluster HA or RPO/RTO. See [recovery](recovery.md),
[continuity operations](continuity-operations.md) and [deployment](deployment.md).
