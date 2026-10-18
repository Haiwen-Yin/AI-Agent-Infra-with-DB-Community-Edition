# Minimum database privileges v5.0.0

> Installed product: **Chuanxu Community Edition**; supported backends: **oracle, pg, yashandb**; edition: **Community**; license: **Apache-2.0**. Other backends and Enterprise-only capabilities discussed below describe differences; they do not extend this package's scope.

[简体中文](minimum-privileges_zh.md)

## Identity and scope

This product supports oracle, pg, yashandb. Its operator-controlled deployment Owner
creates and migrates platform objects. Human sessions, platform-native Agents
and external Agents have distinct identities; ordinary runtime requests must
not fall back to the Owner. Database authorization and host isolation remain
independent controls.

Review the selected package's prerequisite SQL before granting privileges.
Single-backend paths use `scripts/deploy/`; the unified Community package
uses `scripts/deploy/<database>/`. Configure a dedicated database/PDB, Owner
and finite tablespace/storage allocation. Do not treat a system database,
baseline or protected TEST PDB as an empty target.

## PostgreSQL

A database administrator runs `0_pg_database_prerequisites.sql` in the
dedicated application database, with `schema_owner` set to the configured
non-superuser Owner. Install the required vector/AGE extensions and inspect the
script's exact grants. The bounded Owner needs target schema/database creation,
AGE catalog/function/sequence access and per-Agent role management.

The prerequisite creates the shared runtime role as NOLOGIN, NOSUPERUSER,
NOCREATEDB, NOCREATEROLE, NOINHERIT and NOBYPASSRLS when absent. The Owner
requires CREATEROLE and ADMIN OPTION on that role; Agents do not acquire those
management privileges. Preflight must pass `PG_AGE_OWNER_PRIVILEGES` and
`PG_AGENT_ROLE_ADMIN` before initialization.

New Agent LOGIN roles are provisioned individually. Transaction-local
`createrole_self_grant='set, inherit'` gives the creating Owner management
of only the newly created role. An existing externally created role may need
an explicit DBA ADMIN OPTION grant before credential rotation. Never solve
that problem by making the Owner or an Agent SUPERUSER or BYPASSRLS.

Forced RLS and SESSION_USER binding must survive registration. Parent-table
policy does not protect directly granted leaf partitions; test parent and
partition access with independent Agent logins. Control-plane continuity
tables must remain denied after broad legacy grants are reconciled.

## Oracle

The DBA reviews `0_oracle_database_prerequisites.sql`, including
`SCHEMA_OWNER`, `APP_TABLESPACE` and `APP_QUOTA`. Use an application PDB,
AL32UTF8 and an Oracle Home with Partitioning available. The script defines
the exact required grants for schema DDL, APIs, scheduler jobs, triggers,
native graph and Oracle Text. Text setup includes CTXAPP and explicit
EXECUTE on CTXSYS.CTX_DDL; these are deployment Owner permissions.

Oracle Enterprise additionally requires supported End User, Data Role and
Data Grant facilities. Their deployment grants must be direct where stored
PL/SQL or Data Grant parsing cannot use inherited role privileges. The
consolidated prerequisite establishes `DEEP_SEC_SESSION_ROLE` with only
CREATE SESSION and the Owner's ADMIN OPTION for managed attachment.

Do not grant DBA, SELECT ANY DICTIONARY or UNLIMITED TABLESPACE as a shortcut.
Use a finite quota and exact catalog access when version/object inspection
requires it. Business End Users use their own credentials and granted
predicates; a failed End User connection must not switch to the Owner.
Optional network access for database-side embedding requires an explicit ACL
and the exact UTL_HTTP grant; it is not an unrestricted network permission.

Task Steps use the current stable task relationship established by migration
85. Do not recreate the historical status-dependent reference partitioning
from an old example or alter an already applied migration.

## YashanDB

Run `0_yashandb_database_prerequisites.sql` as database administrator in
the dedicated application PDB. The bounded Owner needs the declared schema
DDL privileges and CREATE USER/ALTER USER to provision and rotate independent
Agent logins. The prerequisite establishes the minimal session role and
Owner management grant; it does not grant DBA, SYSDBA or unrestricted data.

Migration 70 and successors bind authorized views and private-write entry
points to SESSION_USER. Legacy definer packages and base tables are not
business-Agent APIs. Current schema ownership cannot be selected by a caller
to impersonate an authorized session. Role-derived grants need inspection in
ROLE_TAB_PRIVS as well as direct grants. See the adapter's native security
guide; do not copy Oracle-only exception or authorization syntax.

## Verify and change grants

Run the current journaled deployment preflight and `verify` operation from
[deployment](deployment.md), followed by [migration](migration.md) postflight.
Inspect required structures, current invalid objects, migration digests,
credential provisioning and native negative tests. A grant inventory alone
does not demonstrate enforcement.

Remove an excessive privilege only after resolving the exact principal,
current dependencies, replacement grants and recovery route. Use a dedicated
test target for DDL/denial checks. Do not execute destructive historical test
snippets against a baseline or production schema.

The operating system needs separate deployment access for its verified
runtime adapter. Database grants cannot establish container/VM isolation or
authorize access to the Host Manager. See [runtime isolation](runtime-isolation.md).
