"""Release verification must fail closed on absent or failed step evidence."""
import json

import pytest
from lib import deployment_orchestrator as deployment


class Cursor:
    def __init__(self, terminal, failed, missing):
        self.terminal, self.failed, self.missing = terminal, failed, missing

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, sql, params=None):
        if self.missing:
            raise RuntimeError("step ledger missing")
        assert "AI_SCHEMA_MIGRATION_STEPS" in sql
        self.value = self.failed if "STATUS='FAILED'" in sql else self.terminal

    def fetchone(self):
        return (self.value,)


class Connection:
    def __init__(self, cursor):
        self._cursor = cursor

    def cursor(self):
        return self._cursor

    def close(self):
        pass


@pytest.mark.parametrize("database", ["pg", "yashandb"])
@pytest.mark.parametrize("terminal,failed,missing,passed", [
    (1, 0, False, True), (0, 0, False, False),
    (1, 1, False, False), (1, 0, True, False),
])
def test_postflight_requires_real_step_evidence(monkeypatch, database, terminal, failed, missing, passed):
    monkeypatch.setattr(deployment, "_connect", lambda *_: Connection(Cursor(terminal, failed, missing)))
    result = deployment.postflight(database, "community", {}, "82_v4_4_14_governed_model_capabilities.sql")
    assert result["passed"] is passed


@pytest.mark.parametrize("failed_migration", [None, "104_v5_0_1_context_assets.sql"])
def test_v501_postflight_verifies_each_migration_then_reuses_prior_chain(
    monkeypatch, tmp_path, failed_migration,
):
    import migration_runner
    from lib import continuity_schema_validation

    deploy_dir = tmp_path / "scripts" / "deploy"
    deploy_dir.mkdir(parents=True)
    terminal = "105_v5_0_1_answer_quality.sql"
    (deploy_dir / terminal).write_text("-- terminal marker\n", encoding="ascii")
    (deploy_dir / "baseline_v5_0_1.json").write_text(json.dumps({
        "version": "5.0.1", "database": "pg", "required_terminal_migration": terminal,
    }), encoding="ascii")
    schema_manifests = (
        "86_v4_4_15_continuity_entities.schema.json",
        "87_v4_4_15_continuity_bindings.schema.json",
        "88_v4_4_15_execution_links.schema.json",
        "93_v4_4_15_mcp_tool_requests.schema.json",
        "94_v4_4_15_handoff_policy.schema.json",
        "95_v4_4_15_runtime_context.schema.json",
        "96_v4_4_15_runtime_credentials.schema.json",
        "97_v4_4_15_native_context_sources.schema.json",
    )
    for index, name in enumerate(schema_manifests):
        (deploy_dir / name).write_text(json.dumps({f"TABLE_{index}": {}}), encoding="ascii")

    class PostflightCursor:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, sql, _params=None):
            if "STATUS='FAILED'" in sql:
                self.value = 0
            elif "AI_SCHEMA_MIGRATION_STEPS" in sql:
                self.value = 1
            elif "pg_constraint" in sql:
                self.value = 1
            elif "CX_WORK_REVISIONS" in sql:
                self.value = 0
            else:
                raise AssertionError(f"unexpected postflight query: {sql}")

        def fetchone(self):
            return (self.value,)

    class PostflightConnection:
        def __init__(self):
            self._cursor = PostflightCursor()

        def cursor(self):
            return self._cursor

        def close(self):
            pass

    checked = []
    schema_checks = []

    def verify_objects(_cursor, _database, script, *, version=None):
        assert version in {None, "5.0.1"}
        checked.append(script.name)
        return script.name != failed_migration

    monkeypatch.setattr(deployment, "_connect", lambda *_: PostflightConnection())
    monkeypatch.setattr(migration_runner, "_step_objects_complete", verify_objects)
    monkeypatch.setattr(migration_runner, "_execution_queue_complete", lambda *_: True)
    monkeypatch.setattr(migration_runner, "_tool_mcp_exposure_complete", lambda *_: True)
    monkeypatch.setattr(migration_runner, "_mcp_native_boundary_complete", lambda *_: True)
    monkeypatch.setattr(migration_runner, "_mcp_owner_binding_complete", lambda *_: True)

    def verify_schema(_cursor, _database, facts):
        schema_checks.append(set(facts))
        return []

    monkeypatch.setattr(continuity_schema_validation, "errors", verify_schema)

    result = deployment.postflight("pg", "community", {}, terminal, tmp_path)
    states = {item["code"]: item["state"] for item in result["checks"]}
    assert [item["code"] for item in result["checks"] if item["code"] in {
        "MEMORY_QUALITY_STORAGE", "CONTEXT_ASSET_STORAGE", "ANSWER_QUALITY_STORAGE",
    }] == ["MEMORY_QUALITY_STORAGE", "CONTEXT_ASSET_STORAGE", "ANSWER_QUALITY_STORAGE"]
    assert states["MEMORY_QUALITY_STORAGE"] == "PASS"
    assert states["CONTEXT_ASSET_STORAGE"] == ("BLOCKED" if failed_migration else "PASS")
    assert states["ANSWER_QUALITY_STORAGE"] == "PASS"
    assert checked[:8] == [
        "103_v5_0_1_memory_quality.sql", "104_v5_0_1_context_assets.sql",
        "105_v5_0_1_answer_quality.sql", "102_v5_0_0_network_access.sql",
        "101_v4_5_2_task_continuity.sql", "100_v4_5_1_framework_rootfs_digest.sql",
        "99_v4_5_1_integration_bindings.sql", "98_v4_5_1_agent_extensions.sql",
    ]
    assert checked[8:] == ["94_v4_4_15_handoff_policy.sql", "86_v4_4_15_continuity_entities.sql"]
    assert any("TABLE_7" in facts for facts in schema_checks)
    assert states["SOURCE_IP_ACCESS_STORAGE"] == "PASS"
    assert states["TASK_CONTINUITY_STORAGE"] == "PASS"
    assert result["passed"] is (failed_migration is None)


def test_v415_uses_journaled_migration_execution():
    import migration_runner
    assert "4.4.15" in migration_runner.JOURNALED_MIGRATION_VERSIONS


@pytest.mark.parametrize('database',['pg','oracle','yashandb'])
def test_standalone_journal_lookup_uses_explicit_package_version(monkeypatch,database):
    import migration_runner as runner
    from pathlib import Path
    monkeypatch.setattr(runner,'MIGRATION_VERSION','4.1.0')
    class Journal:
        def execute(self,sql,params):
            selected=params[0] if isinstance(params,tuple) else params['version']
            self.row=('exact-checksum','APPLIED',1,0) if selected=='4.4.15' else None
        def fetchone(self): return self.row
    cursor=Journal()
    script=Path('94_v4_4_15_handoff_policy.sql')
    assert runner._step_row(cursor,database,script) is None
    assert runner._step_row(cursor,database,script,version='4.4.15')['status']=='APPLIED'
    assert runner.MIGRATION_VERSION=='4.1.0'


@pytest.mark.parametrize('database', ['oracle','pg','yashandb'])
@pytest.mark.parametrize('missing', ['table','column',None])
def test_newer_migrations_do_not_mask_missing_historical_queue(monkeypatch,database,missing):
    import migration_runner as runner
    from pathlib import Path
    tables={'EXECUTION_JOBS','EXECUTION_ATTEMPTS','EXECUTION_POLICIES','EXECUTION_ARTIFACTS','EXECUTION_AUDIT'}
    if missing=='table':
        tables.remove('EXECUTION_JOBS')
    monkeypatch.setattr(runner,'_schema_tables',lambda *_:tables)
    class AllColumns:
        def __ge__(self,required):
            return True
    monkeypatch.setattr(runner,'_schema_columns',lambda _cursor,_db,table:
                        set() if missing=='column' and table=='EXECUTION_AUDIT' else AllColumns())
    assert runner._step_objects_complete(None,database,Path('7_v4_0_1_migration.sql')) is (missing is None)


@pytest.mark.parametrize("error,code", [
    (RuntimeError("YAS-20001 load yacli library error [libyascli.so: cannot open shared object file]"),
     "YASHANDB_CLIENT_UNAVAILABLE"),
    (ModuleNotFoundError("No module named 'yaspy'"), "YASHANDB_CLIENT_UNAVAILABLE"),
    (RuntimeError("connection refused password=private-value"), "DATABASE_CONNECTION_FAILED"),
])
def test_yashan_preflight_distinguishes_local_client_from_server_failure(monkeypatch, error, code):
    def fail(*args):
        raise error
    monkeypatch.setattr(deployment, "_connect", fail)
    result = deployment.preflight("yashandb", {})
    assert not result["passed"]
    check = result["blocked"][0]
    assert check["detail"]["error_code"] == code
    assert ("install_yaspy.sh" in check["remediation"]) == (code == "YASHANDB_CLIENT_UNAVAILABLE")
    assert "private-value" not in str(result)
