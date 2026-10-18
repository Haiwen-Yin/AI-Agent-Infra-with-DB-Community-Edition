# Deployment guide v5.0.0

> Installed product: **Chuanxu Community Edition**; supported backends: **oracle, pg, yashandb**; edition: **Community**; license: **Apache-2.0**. Other backends and Enterprise-only capabilities discussed below describe differences; they do not extend this package's scope.

[简体中文](deployment_zh.md)

## Product and database selection

v5.0.0 delivers five packages with seven database acceptance targets. Unified
Chuanxu Community selects Oracle, PostgreSQL or YashanDB in one package.
OpenTenBase AgentX supports PostgreSQL only. The three Enterprise packages each
support their named backend. This package supports **oracle, pg, yashandb** and is
licensed under **Apache-2.0**. Enterprise-only modules and SQL are physically
excluded from Community packages.

Tasks, Steps, Memory, Knowledge, property graphs, identities, grants and audit
remain database entities. Changing the backend is not an online switch and does
not copy application data. Prepare a separate target and restart the process.

## Prepare the environment

Use Python 3.14+ and supported Linux with glibc 2.34+. Control-plane compatibility
does not prove that the host can isolate local Agents; see
[platform compatibility](linux-platform-compatibility.md) and
[runtime isolation](runtime-isolation.md).

Keep the complete package, including offline dependencies in `vendor/`.
YashanDB requires the matching bundled native client. Database versions and
bounded owner privileges are described in [minimum privileges](minimum-privileges.md).
Oracle and YashanDB use dedicated PDBs; PostgreSQL uses a dedicated database and
non-superuser Schema Owner. Do not put host root or database SYS credentials in
the platform's runtime configuration.

## Configure and install

1. Extract into a trusted directory and work from the package root. Copy
   `config.example.json` to `config.json`. For the unified package, instead
   select `config.oracle.example.json`, `config.pg.example.json` or
   `config.yashandb.example.json`.
2. Set configuration permissions to `0600`. Enter explicit `database.type`,
   connection details, `security.secret_key`, model/Embedding settings and the
   server listener. PostgreSQL uses `host/port/dbname`; Oracle and YashanDB
   use `dsn`.
3. Run `bash scripts/install_offline.sh` to create the package's `.venv`.
   `PYTHON_BIN` selects Python and `CX_VENV_DIR` selects the environment.
   To install before configuring, set `CX_DATABASE_DIALECT=pg` or another
   supported backend. Only that backend's native requirements are selected.
4. Set `CX_CONFIG_PATH=/absolute/path/config.json` for an external private
   configuration. `CX_DATABASE_DIALECT` must agree with configuration.
   Missing, unsupported or conflicting selection is rejected before driver
   import. The process pins its selected backend.

`server.host` controls the bind address and `server.port` the port. External
access also requires appropriate routing and firewall rules. With a reverse
proxy, configure HTTPS, trusted forwarding and `CX_PUBLIC_BASE_URL`. Do not
use an unverified forwarded address as a model gateway endpoint.

## Initialize a prepared empty target

A database administrator first prepares the dedicated empty PDB/database,
tablespaces, extensions and bounded owner privileges according to the selected
`0_*_database_prerequisites.sql`. Deployment privileges are different from
ordinary Agent privileges. Business Agents cannot fall back to owner credentials.

A single-backend package has one `scripts/deploy/baseline_v*.json`; the unified
package has one per backend under `scripts/deploy/<database>/`. v5.0.0 retains
the complete checksum-bound entity schema chain through
`102_v5_0_0_network_access.sql`. Historical filenames and applied checksums
are not renamed.

Store the initial administrator password in a private, current-user-owned
regular file with mode `0600`, then run:

```bash
bash scripts/install_platform.sh initialize \
  --database pg --edition community --version 5.0.0 \
  --config /absolute/path/config.json \
  --admin-password-file /absolute/path/admin.password
```

Replace the backend and edition to match this package. Interactive initialization
can instead prompt for the password; it must meet the existing 12-character
policy. There is no universal default administrator password.

Initialization proves the target is empty, executes its manifest and migrations,
creates the Human administrator and native management identities, publishes
current product facts, checks readiness and retires the temporary deployment
identity. An LLM or external Agent is not required for schema initialization.

## Upgrade, resume and verify

An existing database must not be initialized as empty. Confirm database-side
backup/recovery responsibility before `upgrade --confirm-database-backup`.
Inspect journals and select the original `--run-id` for `resume` after an
interrupted, classified deployment. Unknown partial schemas require investigation.
Do not edit applied SQL or delete the migration ledger. See [migration](migration.md).

Private journals and keys are in `.runtime/deployment/`. Preserve configuration,
encryption keys and recovery journals before replacing a program directory.
They must not enter public archives.

```bash
bash scripts/install_platform.sh verify \
  --database pg --edition community --version 5.0.0 \
  --config /absolute/path/config.json
./start_web_server.sh start
./start_web_server.sh status
```

Dashboard is at `/app/` and Portal at `/portal`. `/api/health` reports process
identity and version; `/api/ready` checks database/control-plane readiness.
Neither alone proves release acceptance. The launcher defaults to the package's
`.runtime/web.pid`, so separate installations have separate PID files.

## Configure governance, registration and models

`CX_RUNTIME_PROFILE` defaults to `production`; it does not change database
governance records. Platform, Graph and model capability matrices remain
authoritative. Missing records or an unavailable database do not mean enabled.
Environment variables cannot expand a license or identity's authority.

Human self-registration and external Agent enrollment have independent controls.
Portal uses local managed Agents. Channel Agents require membership, activation,
a valid runtime target and data/model grants. Policy-permitted answers without
Knowledge matches use the model and show a separate source label.

Save model endpoint, model ID and any private key, then run health and individual
capability probes. Structured output, tools, images and cancellation depend on
the actual provider. MCP, A2A, framework execution, telemetry and diagnostics
retain their specific capability, authorization and isolation gates. See
[Agent extensions](agent-extensions.md) and [operations](operations.md).

Stop with `./start_web_server.sh stop`, or use `restart`. Preserve Task and
Worker lease records for recovery rather than deleting state to clear errors.
