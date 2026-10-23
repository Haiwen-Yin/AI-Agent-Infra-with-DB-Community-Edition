# Native Agent identity operations v5.0.1

> Installed product: **Chuanxu Community Edition**; supported backends: **oracle, pg, yashandb**; edition: **Community**; license: **Apache-2.0**. Other backends and Enterprise-only capabilities discussed below describe differences; they do not extend this package's scope.

[简体中文](native-identity_zh.md)

## Identity and retained facts

An Agent Principal, its native database account and its Gateway credentials
are different identities. Offboarding preserves the Principal, native mapping,
ownership history and audit; it does not delete an account or rotate its
password. Human administrators and platform system Agents are not business
Agent offboarding targets. Database entities remain authoritative.

PostgreSQL maps each managed Agent to a database-bound LOGIN role. Oracle uses
its managed End User; YashanDB uses the mapped local PDB user. The adapter checks
the current database, configured Owner, exact Principal and unique mapping
before changing one account. Missing, ambiguous or changed mappings do not
authorize a guessed account name or an Owner fallback.

## Oracle and YashanDB administrator prerequisite

For v5.0.1, SYS prepares a read-only status interface in the exact application
PDB before initialization, upgrade, resume or verification. This is separate
from the existing database prerequisites and application migration chain:

| Backend | Additional script | Source projected into `SYS.CX_AGENT_ACCOUNT_STATUS` |
|---|---|---|
| Oracle | `0_oracle_v5_0_1_native_identity_prerequisites.sql` | `SYS.DBA_END_USERS` |
| YashanDB | `0_yashandb_v5_0_1_native_identity_prerequisites.sql` | `SYS.DBA_USERS` |

Single-backend packages keep these files in `scripts/deploy/`; unified Community
uses `scripts/deploy/oracle/` or `scripts/deploy/yashandb/`. PostgreSQL does not
use either script or this SYS view.

1. Resolve the exact PDB and configured Schema Owner. Review the supplied
   script and set `TARGET_PDB` and `SCHEMA_OWNER` explicitly. The supplied
   `REPLACE_WITH_APPLICATION_PDB` is a placeholder, not a valid deployment
   choice. Do not infer a target from a name prefix or merely check that it is
   not `CDB$ROOT`.
2. Connect as SYS in that PDB. The script checks the administrator, exact PDB
   and existence of the selected Owner, rejecting prohibited Owner names and
   unknown conflicting objects, extra columns, a writable definition or extra
   object grants. The DBA must confirm that `SCHEMA_OWNER` matches the platform
   configuration. Investigate conflicts; the script must not use `OR REPLACE`
   or automatically revoke existing grants to make them fit.
3. The view has exactly `USERNAME, ACCOUNT_STATUS` and `WITH READ ONLY`.
   Give only the exact Owner SELECT, without grant option. Do not grant PUBLIC,
   Agents or runtime roles access, or expose the full source dictionary.
4. Run the package's read-only preflight/`verify` as the configured Owner and
   inspect `NATIVE_IDENTITY_STATUS_VIEW`. A missing, unreadable or incompatible
   interface is `BLOCKED`, not proof that an Agent account is absent.
5. Use isolated acceptance accounts to verify Owner reads, independent Agent
   denial and unchanged access for a second Agent and the Owner. A passing
   preflight is not proof of native enforcement or HTTP enrollment acceptance.

The application uses the fully qualified SYS view. It never creates it,
automatically issues GRANT, changes a historical SQL checksum or adopts a
same-named Owner view. The new administrator script does not change terminal
migration 105. Never put SYS credentials in platform configuration. See
[minimum privileges](minimum-privileges.md) and [deployment](deployment.md).

## Offboard one managed Agent

Use the authenticated offboarding workflow with `agents.offboard` permission
and access to the exact Agent. The Dashboard API is
`POST /api/agents/{agent_id}/offboard`; it uses the Dashboard session cookie and
`X-CSRF-Token`, not an ordinary Agent's native credentials. Record a meaningful
reason and the correct owner/responsible-group/environment disposition.

For example, after independently confirming this disposition applies to the
selected business Agent, submit this JSON with its exact ID in the route:

```json
{
  "owner_type": "HUMAN",
  "has_responsible_group": false,
  "environment": "DEVELOPMENT",
  "reason": "Retire this approved development Agent"
}
```

These are disposition inputs, not a way to reclassify a production Agent to
obtain a desired outcome. Use the Agent's actual recorded responsibility and
environment and inspect the returned disposition; do not copy these example
values without checking the target.

Offboarding first commits the platform status, token/credential revocation,
delivery fencing and pending audit. Where that disposition requires native
revocation, a second step rechecks the exact mapping and blocks new native
logins: PostgreSQL `NOLOGIN`, Oracle End User `ACCOUNT LOCK`, or YashanDB local
user `ACCOUNT LOCK CONTAINER=CURRENT`. It also closes only this process's
tracked connections for that Agent. Other Agents, shared roles and Owner grants
must remain unchanged. No `DROP`, password rotation or `CONTAINER=ALL` is used.

Native DDL, platform state and the final audit do not share a single atomic
transaction. In particular, Oracle/YashanDB account DDL may commit implicitly.
An HTTP success or disabled Principal alone does not establish native success;
inspect `native_identity_revocation` and its result audit.

| Result | Meaning within the reported native operation |
|---|---|
| `PENDING` | Preconditions could not establish authority to complete native revocation; retain the disabled platform state and investigate. |
| `PARTIAL` | Some work or observation/auditing failed; inspect the post-snapshot, local close failures and audit status. Do not claim complete revocation. |
| `COMPLETE` | New native logins are observed blocked, tracked local closes did not fail and the current identity checks passed. |
| `SKIPPED` | The selected disposition retains native identity; this is not proof that native login is disabled. |

For the final audited result, also require `audit_status=RECORDED`. Preserve the
operation ID, database fingerprint and before/after facts. Unknown observation
fields remain unknown, not false or zero. Retry only through the authorized
workflow after resolving the cause; do not unlock, reenroll, clear history or
broaden privileges merely to obtain a successful status.

## Existing sessions and incidents

`COMPLETE` is a limited new-login/local-cache result. It does not assert that
external existing database sessions have terminated, all business reads/writes
are blocked, other application processes closed their pools, or a remote Agent
process stopped. `existing_sessions_closed` and `business_access_blocked` remain
unknown unless separately observed. A new-login rejection and a successful
query on an older external session can both be true.

If incident containment requires terminating existing sessions or processes,
use a separately authorized DBA/infrastructure procedure for exact targets and
verify its actual result. Do not kill unrelated sessions or all platform work.
Keep retained audit and independent-canary observations. See
[security](security.md), [recovery](recovery.md) and
[migration](migration.md).
