# Deployment guide v5.0.1

> Installed product: **Chuanxu Community Edition**; supported backends: **oracle, pg, yashandb**; edition: **Community**; license: **Apache-2.0**. Other backends and Enterprise-only capabilities discussed below describe differences; they do not extend this package's scope.

[简体中文](deployment_zh.md)

## Product and database selection

The v5 delivery model has five packages with seven database acceptance targets. Unified
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
3. For an external private configuration, first run
   `export CX_CONFIG_PATH=/absolute/path/config.json`; otherwise retain the
   package-root `config.json`. The installer and launcher read this environment
   variable. The deployment CLI does not use it as the default for `--config`,
   so pass `--config "$CX_CONFIG_PATH"` explicitly when selecting an external file.
   Set the same exported path again in a new shell or service manager; deployment
   does not persist the selection for later launcher commands.
4. Run `bash scripts/install_offline.sh --database pg` (replace `pg` with your
   backend) to create the package's `.venv`.
   `PYTHON_BIN` selects Python and `CX_VENV_DIR` selects the environment.
   To install before configuring, set `CX_DATABASE_DIALECT=pg` or another
   supported backend. Only that backend's native requirements are selected.

`CX_DATABASE_DIALECT` must agree with configuration. Missing, unsupported or
conflicting selection is rejected before driver import. The process pins its
selected backend.

### Separate backend installation paths

The unified Community archive contains three alternatives. Run only the selected
path, from its own installation directory, and edit `config.json` before database
initialization. In a single-backend archive use `config.example.json` instead;
other backend selections are rejected.

Oracle:

```bash
install -m 600 config.oracle.example.json config.json
bash scripts/install_offline.sh --database oracle
```

PostgreSQL:

```bash
install -m 600 config.pg.example.json config.json
bash scripts/install_offline.sh --database pg
```

YashanDB:

```bash
install -m 600 config.yashandb.example.json config.json
bash scripts/install_offline.sh --database yashandb
```

Each `requirements/<database>.txt` is complete: shared packages plus only that
backend's driver. The root `requirements.txt` in the unified archive contains
shared packages only; installing it alone is not a complete deployment.
`vendor/` carries alternatives for offline use, not a request to install every
driver. The installer validates CLI, environment and configuration agreement
before changing the Python environment, and refuses a virtual environment that
already contains a different backend's driver.

Use separate installation directories for simultaneous backends. When selecting
`CX_VENV_DIR=/absolute/path/to/private-venv`, keep the same value for the offline
installer, `install_platform.sh` and `start_web_server.sh`. For a different backend,
prepare a separate environment; do not repurpose a running service's environment.

For manual Oracle/PG pip installation, first create and activate a dedicated
Python 3.14+ virtual environment. Choose exactly one command:

```bash
python -m pip install --no-index --find-links vendor -r requirements/oracle.txt
```

```bash
python -m pip install --no-index --find-links vendor -r requirements/pg.txt
```

These profile paths apply to the unified archive; single-backend archives use
their complete root `requirements.txt`. YashanDB's `yaspy` is a bundled native
extension, not a pip distribution: use `install_offline.sh --database yashandb`
to install it and the client libraries together. Do not run pip directly against
`requirements/yashandb.txt`. From a configured package, verify the selected
offline dependency set with `.venv/bin/python scripts/verify_deps.py --database pg`
(replace the interpreter and database when applicable). This verifies bundled
files; the installer separately imports the installed driver. Database readiness
still requires the initialization/verification steps below.

`server.host` controls the bind address and `server.port` the port. External
access also requires appropriate routing and firewall rules. With a reverse
proxy, configure HTTPS, trusted forwarding and `CX_PUBLIC_BASE_URL`. Do not
use an unverified forwarded address as a model gateway endpoint.

## Initialize a prepared empty target

A database administrator first prepares the dedicated empty PDB/database,
tablespaces, extensions and bounded owner privileges according to the selected
`0_*_database_prerequisites.sql`. Deployment privileges are different from
ordinary Agent privileges. Business Agents cannot fall back to owner credentials.

For a v5.0.1 Oracle or YashanDB target, the DBA also reviews and separately runs
the native-identity prerequisite in that exact application PDB:

| Backend | Additional administrator script |
|---|---|
| Oracle | `0_oracle_v5_0_1_native_identity_prerequisites.sql` |
| YashanDB | `0_yashandb_v5_0_1_native_identity_prerequisites.sql` |

These files are under `scripts/deploy/` in single-backend packages and
`scripts/deploy/<database>/` in unified Community. Set `TARGET_PDB` and
`SCHEMA_OWNER` to the exact target; connect as SYS in that PDB, not the CDB root
or a different PDB. The read-only `SYS.CX_AGENT_ACCOUNT_STATUS` view exposes only
`USERNAME, ACCOUNT_STATUS`, with SELECT for that Owner only. It does not grant
access to the full source dictionary or grant management authority to Agents.
The application never creates the view or repairs its grants automatically.
Missing, inaccessible or incompatible prerequisites block the read-only
`NATIVE_IDENTITY_STATUS_VIEW` preflight check.
See [native identity operations](native-identity.md) for verification and limits.

A single-backend package has one `scripts/deploy/baseline_v*.json`; the unified
package has one per backend under `scripts/deploy/<database>/`. v5.0.0 ends at
`102_v5_0_0_network_access.sql`. v5.0.1 extends that checksum-bound chain with
`103_v5_0_1_memory_quality.sql`, `104_v5_0_1_context_assets.sql` and
`105_v5_0_1_answer_quality.sql`; each has a backend-specific schema manifest.
Use the baseline generated for the exact package version. Historical filenames
and applied checksums are not renamed.

For v5.0.1, postflight verifies the actual time/note/retrospective, context/asset/
source and answer-quality objects as well as their APPLIED entries and script
digests. A terminal 105 ledger row cannot substitute for missing 103 or 104
structures. These services must not start against an earlier schema. Existing
data, independent Agent SQL denials and the prior Task/Step/continuity chain
remain part of verification; a successful fresh installation does not prove an
existing-database transition.

Store the initial administrator password in a private, current-user-owned
regular file with mode `0600`, then run:

```bash
export CX_CONFIG_PATH=/absolute/path/config.json
bash scripts/install_platform.sh initialize \
  --database pg --edition community --version 5.0.1 \
  --config "$CX_CONFIG_PATH" \
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
export CX_CONFIG_PATH=/absolute/path/config.json
bash scripts/install_platform.sh verify \
  --database pg --edition community --version 5.0.1 \
  --config "$CX_CONFIG_PATH"
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

The additional workflows are documented in [memory and working notes](memory-working-notes.md),
[Agent assets and source synchronization](agent-context-assets.md) and
[final-answer evaluation](answer-quality.md). Source synchronization and model
retrospectives are explicit jobs; neither deployment nor a page visit enables
automatic publication, schedules or new controlled-capability defaults.

Stop with `./start_web_server.sh stop`, or use `restart`. Preserve Task and
Worker lease records for recovery rather than deleting state to clear errors.
