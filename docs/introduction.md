# Chuanxu Community Edition v5.0.1

[简体中文](../README_zh.md)

A database-backed AI Agent management platform. Tasks, collaboration barriers,
memory, knowledge, property graphs, permissions and audit records are persisted
as database entities. External Agents use governed registration and gateway APIs;
Portal conversations allocate local managed Agents.

Shared answers combine authorized retrieval with separate evidence assessment
and source labels. Work notes, temporal Memory, Agent asset bindings, configured
source synchronization and final-answer evaluation extend the existing
Task/Step, Work/Handoff and candidate/review entities. Their permissions, exact
revisions and explicit publication boundaries remain enforced.

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
2. Run `bash scripts/install_offline.sh --database DB`. For installation before configuration,
   set `CX_DATABASE_DIALECT` to a supported database key. Only its native driver
   requirements and client libraries are installed.
3. Have the DBA prepare the dedicated empty database/PDB, bounded Owner and
   selected backend's prerequisites. For v5.0.1 Oracle and YashanDB, SYS must
   separately prepare `SYS.CX_AGENT_ACCOUNT_STATUS` in the exact application
   PDB using the packaged `0_<database>_v5_0_1_native_identity_prerequisites.sql`.
   This also applies to existing-database upgrades; PostgreSQL does not use
   this view. Follow [native identity prerequisites](native-identity.md)
   and [minimum privileges](minimum-privileges.md) before initialization.
4. Store an initial administrator password in an owner-readable file (mode
   `0600`). Run `bash scripts/install_platform.sh initialize --database DB
   --edition EDITION --version 5.0.1 --config /absolute/path/config.json
   --admin-password-file /absolute/path/password-file`, replacing `DB` with a
   supported database key and `EDITION` with `community` or `enterprise`.
5. Run `./start_web_server.sh start`. Dashboard: `/app/`; Portal: `/portal`.
   `/api/health` reports process identity; `/api/ready` checks database readiness.

`CX_CONFIG_PATH` selects an external private configuration file.
`CX_DATABASE_DIALECT` must agree with the configuration. A conflicting, missing
or unsupported selection stops startup. Changing the database requires a restart
and a separately prepared target; it does not move application data.

### Three deployment choices in the unified Community package

Choose one row per installation. Edit the selected configuration before database
initialization; a single-backend package uses `config.example.json` and accepts
only its declared backend.

| Backend | Configuration example | Offline installation | Complete requirements |
|---|---|---|---|
| Oracle | `config.oracle.example.json` | `bash scripts/install_offline.sh --database oracle` | `requirements/oracle.txt` |
| PostgreSQL | `config.pg.example.json` | `bash scripts/install_offline.sh --database pg` | `requirements/pg.txt` |
| YashanDB | `config.yashandb.example.json` | `bash scripts/install_offline.sh --database yashandb` | `requirements/yashandb.txt` plus bundled native client |

The unified package's root `requirements.txt` contains shared dependencies only:
`pip install -r requirements.txt` alone does not install a database driver.
Bundling all three offline drivers in `vendor/` does not install all three.
Oracle/PG manual pip commands and the YashanDB native installation path are in
[deployment](deployment.md#separate-backend-installation-paths).
Use separate installation directories and virtual environments for concurrent
backends. If setting `CX_VENV_DIR`, retain it for installation, initialization
and startup. The installer rejects an environment containing another backend's
driver; switching configuration is not a dependency or data migration.

## Operate and extend

- [Deployment](deployment.md) and [migration](migration.md)
- [Architecture](architecture.md) and [API reference](api-reference.md)
- [Agent extensions](agent-extensions.md) and [DB4A2A](db4a2a.md)
- [Continuity operations](continuity-operations.md)
- [Memory evidence, working notes and retrospectives](memory-working-notes.md)
- [Agent assets, context budgets and source synchronization](agent-context-assets.md)
- [Shared answers and final-answer evaluation](answer-quality.md)
- [Security](security.md) and [release verification](release-signing.md)
- [Native Agent offboarding and account-status prerequisites](native-identity.md)
- [Source IP access and local recovery](source-ip-access.md)
- [Release notes](../RELEASE_NOTES_v5.0.1.md)

Model features are verified per provider and model. Controlled integrations keep
their authorization, isolation, bounded execution and database audit checks.
Enterprise-only code and SQL are excluded from Community packages. Configure
human self-registration separately from external Agent registration.
