# Chuanxu Community Edition v5.0.0

[简体中文](../README_zh.md)

A database-backed AI Agent management platform. Tasks, collaboration barriers,
memory, knowledge, property graphs, permissions and audit records are persisted
as database entities. External Agents use governed registration and gateway APIs;
Portal conversations allocate local managed Agents.

This package is **AI-Agent-Infra-with-DB-Community-Edition**, **Community**, licensed under
**Apache-2.0**. Supported database keys: **oracle, pg, yashandb**. The unified Community
package selects one database per running process. OpenTenBase AgentX supports
PostgreSQL only; the three Enterprise packages remain database-specific.

## Install and initialize

Use Python 3.14+ on supported Linux with glibc 2.34+. Extract the complete archive,
including `vendor/`. From the package root:

1. Copy `config.example.json` to private `config.json`. In the unified package,
   use `config.oracle.example.json`, `config.pg.example.json` or
   `config.yashandb.example.json` instead. Keep the explicit `database.type` and
   enter the connection, session secret and optional model settings.
2. Run `bash scripts/install_offline.sh`. For installation before configuration,
   set `CX_DATABASE_DIALECT` to a supported database key. Only its native driver
   requirements and client libraries are installed.
3. Store an initial administrator password in an owner-readable file (mode
   `0600`). Run `bash scripts/install_platform.sh initialize --database DB
   --edition EDITION --version 5.0.0 --config /absolute/path/config.json
   --admin-password-file /absolute/path/password-file`, replacing `DB` with a
   supported database key and `EDITION` with `community` or `enterprise`.
4. Run `./start_web_server.sh start`. Dashboard: `/app/`; Portal: `/portal`.
   `/api/health` reports process identity; `/api/ready` checks database readiness.

`CX_CONFIG_PATH` selects an external private configuration file.
`CX_DATABASE_DIALECT` must agree with the configuration. A conflicting, missing
or unsupported selection stops startup. Changing the database requires a restart
and a separately prepared target; it does not move application data.

## Operate and extend

- [Deployment](deployment.md) and [migration](migration.md)
- [Architecture](architecture.md) and [API reference](api-reference.md)
- [Agent extensions](agent-extensions.md) and [DB4A2A](db4a2a.md)
- [Continuity operations](continuity-operations.md)
- [Security](security.md) and [release verification](release-signing.md)
- [Source IP access and local recovery](source-ip-access.md)
- [Release notes](../RELEASE_NOTES_v5.0.0.md)

Model features are verified per provider and model. Controlled integrations keep
their authorization, isolation, bounded execution and database audit checks.
Enterprise-only code and SQL are excluded from Community packages. Configure
human self-registration separately from external Agent registration.
