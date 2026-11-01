"""Offline v5.0.2 delivery contracts; no database/model/service is contacted."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import shutil
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
if not (ROOT / "build.py").is_file():
    pytest.skip("Build/generator fixtures run in the source checkout", allow_module_level=True)

import build
import live_db_validator as validator
import migration_runner as runner
from lib import continuity_schema_validation
from product_delivery import PRODUCTS, acceptance_targets


DATABASES = ("oracle", "pg", "yashandb")
NEW_STEPS = validator.V502_RUNTIME_MIGRATION_SCRIPTS
PHASE_STEPS = validator.V502_NATIVE_MIGRATION_SCRIPTS


def deploy(database):
    return ROOT / "adapters" / database / "deploy"


def generator():
    path = ROOT / "tools/v502_generate_runtime.py"
    sys.path.insert(0, str(path.parent))
    try:
        spec = importlib.util.spec_from_file_location("v502_delivery_generator", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(str(path.parent))


@pytest.mark.parametrize("database", DATABASES)
@pytest.mark.parametrize("edition", ("community", "enterprise"))
def test_v502_static_contract_requires_complete_historical_and_new_chain(database, edition):
    scripts = list(deploy(database).glob("*.sql"))
    assert validator.validate_v502_static_contract(database, scripts, edition)["passed"]
    for name in PHASE_STEPS:
        incomplete = [path for path in scripts if path.name != name]
        assert not validator.validate_v502_static_contract(database, incomplete, edition)["passed"]


@pytest.mark.parametrize("database", DATABASES)
@pytest.mark.parametrize("number", (106, 107, 108, 109))
def test_new_migrations_and_manifests_exactly_match_typed_schema(database, number):
    module = generator()
    filename, sql, facts = module.render(database, number)
    path = deploy(database) / filename
    assert path.read_text() == sql
    assert json.loads(path.with_suffix(".schema.json").read_text()) == facts
    assert validator.validate_v502_schema_manifest(facts) == []
    schema = __import__("lib." + module.MIGRATIONS[number][0], fromlist=["schema_statements"])
    for table, definition in facts.items():
        assert set(definition["immutable_columns"]) == set(definition["columns"]) - schema.MUTABLE.get(table, set())
        assert definition["trigger"] in sql
        assert "REVOKE" in sql and definition["grant_policy"] == "NO_NON_OWNER_GRANTS"


def test_credentials_and_int64_facts_are_in_current_native_contracts():
    for database in DATABASES:
        capacity = json.loads((deploy(database) / NEW_STEPS[0]).with_suffix(".schema.json").read_text())
        expected = "DECIMAL(19,0)" if database == "pg" else "NUMBER(19)"
        assert capacity["CX_MODEL_ADMISSIONS"]["columns"]["QUEUE_UNTIL_MS"]["type"] == expected
        assert capacity["CX_MODEL_USAGE_DETAILS"]["columns"]["CACHE_WRITE_TOKENS"]["type"] == expected
        output = json.loads((deploy(database) / NEW_STEPS[2]).with_suffix(".schema.json").read_text())
        definition = output["CX_RETROSPECTIVE_OUTPUTS"]
        assert {"CREDENTIAL_KIND", "SESSION_CREATED_AT", "SESSION_DIGEST", "TOKEN_DIGEST"} <= set(definition["immutable_columns"])


@pytest.mark.parametrize("database", DATABASES)
def test_baseline_moves_to_backend_terminal_and_requires_every_predecessor(tmp_path, database):
    target = tmp_path / database
    shutil.copytree(deploy(database), target)
    build.generate_deployment_baseline(target, "5.0.2", database)
    baselines = list(target.glob("baseline_v*.json"))
    assert [path.name for path in baselines] == ["baseline_v5_0_2.json"]
    baseline = json.loads(baselines[0].read_text())
    assert (baseline["version"], baseline["database"], baseline["required_terminal_migration"]) == (
        "5.0.2", database, validator.v502_runtime_migration_scripts(database)[-1])
    (target / PHASE_STEPS[0]).with_suffix(".schema.json").unlink()
    with pytest.raises(ValueError, match="manifest is missing"):
        build.generate_deployment_baseline(target, "5.0.2", database)


@pytest.mark.parametrize("target", acceptance_targets(), ids=lambda item: item["key"])
def test_all_seven_targets_select_backend_native_tail_without_native_connections(monkeypatch, target, tmp_path):
    def absent_config(_path):
        raise ValueError("Offline fixture has no deployed predecessor")

    def no_connection(*_args):
        pytest.fail("An offline selector must not contact a database")

    monkeypatch.setattr(runner, "_load_database_config", absent_config)
    monkeypatch.setattr(runner, "_connect_for_preflight", no_connection)
    names = runner.release_script_names("5.0.2", target["database"], tmp_path / "absent.json", target["edition"].lower())
    native_tail = validator.v502_native_migration_scripts(target["database"])
    assert names[-len(native_tail):] == list(native_tail)
    assert len(names) == len(set(names))
    assert build.deployment_terminal("5.0.2", target["database"]) == native_tail[-1]
    assert ("29_v4_3_4_agent_compliance.sql" in names) == (target["edition"] == "Enterprise")


def test_five_product_matrix_is_unchanged():
    assert len(PRODUCTS) == 5
    assert len(acceptance_targets()) == 7
    community = next(product for product in PRODUCTS if product.key == "unified-community")
    assert community.databases == DATABASES
    assert next(product for product in PRODUCTS if product.key == "agentx-community").databases == ("pg",)


@pytest.mark.parametrize("bad_step", validator.V501_MIGRATION_SCRIPTS[-3:])
@pytest.mark.parametrize("problem", ("missing", "failed", "checksum", "objects"))
def test_declared_transition_needs_each_predecessor_ledger_checksum_and_objects(monkeypatch, bad_step, problem):
    scripts = [deploy("pg") / name for name in PHASE_STEPS]
    observed = []

    def row(_cursor, _database, path, *, version):
        assert version == "5.0.1"
        observed.append(path.name)
        if path.name == bad_step and problem == "missing":
            return None
        return {"status": "FAILED" if path.name == bad_step and problem == "failed" else "APPLIED",
                "checksum": "changed" if path.name == bad_step and problem == "checksum" else runner._checksum(path)}

    monkeypatch.setattr(runner, "_step_row", row)
    monkeypatch.setattr(runner, "_step_objects_complete", lambda _c, _d, path, **_kw: not (
        path.name == bad_step and problem == "objects"))
    contract = runner._v502_predecessor_contract(None, "pg", scripts)
    assert observed == list(validator.V501_MIGRATION_SCRIPTS[-3:])
    assert not contract["passed"]
    assert not contract["steps"][bad_step]["passed"]


def test_live_capture_checks_all_seven_steps_and_does_not_fall_back_past_invalid_current_row(monkeypatch):
    observed = []

    def row(_cursor, _database, path, *, version):
        observed.append((path.name, version))
        if version == "5.0.2" and path.name == PHASE_STEPS[0]:
            return {"status": "FAILED", "checksum": runner._checksum(path)}
        if version == "5.0.2" and path.name in PHASE_STEPS[1:3]:
            return None
        return {"status": "APPLIED", "checksum": runner._checksum(path)}

    monkeypatch.setattr(runner, "_step_row", row)
    monkeypatch.setattr(runner, "_step_objects_complete", lambda *_a, **_kw: True)
    contract = validator._capture_v501_migrations(None, "pg", "5.0.2", PHASE_STEPS)
    assert set(contract["steps"]) == set(PHASE_STEPS)
    assert not contract["passed"]
    assert (PHASE_STEPS[0], "5.0.1") not in observed
    assert (PHASE_STEPS[1], "5.0.1") in observed


def test_unreadable_current_ledger_cannot_fall_back_to_historical_success(monkeypatch):
    def unreadable(*_args, **_kwargs):
        raise RuntimeError("Fixture catalog read failed")

    monkeypatch.setattr(runner, "_step_row", unreadable)
    monkeypatch.setattr(runner, "_step_objects_complete", lambda *_a, **_kw: True)
    contract = validator._capture_v501_migrations(None, "pg", "5.0.2", PHASE_STEPS)
    assert not contract["passed"]
    assert all(step["ledger_status"] == "UNREADABLE" for step in contract["steps"].values())


def test_declared_transition_preflight_blocks_missing_predecessor_proof(monkeypatch):
    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

        def execute(self, *_args):
            pass

        def fetchone(self):
            return ("fixture", "1")

    class Connection:
        def cursor(self):
            return Cursor()

    monkeypatch.setattr(runner, "MIGRATION_VERSION", "5.0.2")
    monkeypatch.setattr(runner, "MIGRATION_FROM_VERSION", "5.0.1")
    monkeypatch.setattr(runner, "_objects_complete", lambda *_args: True)
    monkeypatch.setattr(runner, "_capacity_probe", lambda *_args: {})
    monkeypatch.setattr(runner, "_v502_predecessor_contract", lambda *_args: {"passed": False})
    contract = runner._preflight(Connection(), "pg", [deploy("pg") / name for name in PHASE_STEPS], None)
    assert not contract["passed"]
    assert contract["error_type"] == "PredecessorEvidenceIncomplete"


def test_declared_transition_requires_backup_gate_before_mutation(monkeypatch, tmp_path, capsys):
    class Connection:
        def close(self):
            pass

    monkeypatch.setattr(sys, "argv", ["migration_runner.py", "--database", "pg", "--version", "5.0.2",
                                    "--from-version", "5.0.1", "--pg-config", str(tmp_path / "fixture.json")])
    monkeypatch.setattr(runner, "_load_database_config", lambda *_args: {})
    monkeypatch.setattr(runner, "_connect_for_preflight", lambda *_args: Connection())
    monkeypatch.setattr(runner, "release_script_names", lambda *_args: list(PHASE_STEPS))
    monkeypatch.setattr(runner, "_preflight", lambda *_args: {"passed": True, "scripts": []})
    monkeypatch.setattr(runner, "_apply_pg", lambda *_args: pytest.fail("Missing backup acknowledgement must block mutation"))
    assert runner.main() == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["from_version"] == "5.0.1"
    assert not payload["passed"]
    assert "backup/recovery responsibility was not confirmed" in payload["results"][0]["warnings"][0]


def minimal_facts():
    return {"CX_TEST": {
        "columns": {"ID": {"type": "VARCHAR(128)", "not_null": True, "default": None}},
        "keys": [], "checks": 0, "check_expressions": [],
        "immutable_columns": ["ID"], "trigger": "CX106_TEST",
        "trigger_function": "cx106_reject_runtime_mutation",
        "trigger_body": "BEGIN RAISE EXCEPTION 'Runtime evidence is immutable' USING ERRCODE='23000'; END",
        "grant_policy": "NO_NON_OWNER_GRANTS",
        "indexes": [{"name": "CX106_TEST_INDEX", "columns": ["ID"], "unique": False}],
    }}


class Catalog:
    """Limited native catalog fixture with independently corruptible objects."""
    def __init__(self, database, issue=None):
        self.database = database
        self.issue = issue
        self.rows = []

    def execute(self, sql, parameters):
        item = minimal_facts()["CX_TEST"]
        if "format_type" in sql:
            self.rows = [("ID", "character varying(128)", True, "'drift'" if self.issue == "default" else None)]
        elif "FROM USER_TAB_COLUMNS" in sql:
            self.rows = [("ID", "VARCHAR2", 128, "N", None, None, "'drift'" if self.issue == "default" else None)]
        elif "FROM pg_constraint" in sql or "FROM USER_CONSTRAINTS" in sql:
            self.rows = []
        elif "SELECT tgname,tgenabled" in sql:
            self.rows = [("cx106_test", "D" if self.issue == "disabled" else "O")]
        elif "SELECT TRIGGER_NAME,STATUS" in sql:
            self.rows = [("CX106_TEST", "DISABLED" if self.issue == "disabled" else "ENABLED")]
        elif "privileges" in sql or "PRIVS" in sql:
            self.rows = [("ai_agent_runtime", "SELECT")] if self.issue == "grants" else []
        elif "SELECT t.tgname,t.tgtype" in sql:
            self.rows = [("cx106_test", 18 if self.issue == "delete" else 26,
                          [] if self.issue == "columns" else ["ID"], item["trigger_function"],
                          "BEGIN RETURN NULL; END" if self.issue == "body" else item["trigger_body"],
                          self.issue == "definer", self.issue != "when", self.issue != "function_grant")]
        elif "SELECT TRIGGER_NAME,TRIGGER_TYPE" in sql:
            self.rows = [("CX106_TEST", "BEFORE STATEMENT", "UPDATE" if self.issue == "delete" else "DELETE OR UPDATE",
                          "ID IS NOT NULL" if self.issue == "when" else None,
                          "BEGIN NULL; END;" if self.issue == "body" else item["trigger_body"])]
        elif "FROM pg_index" in sql:
            self.rows = [] if self.issue == "missing_index" else [(
                "CX106_TEST_INDEX", [] if self.issue == "index_columns" else ["ID"], False,
                self.issue != "invalid_index", self.issue != "partial_index")]
        elif "FROM USER_INDEXES" in sql:
            self.rows = [] if self.issue == "missing_index" else [(
                "CX106_TEST_INDEX", "N" if self.database == "yashandb" else "NONUNIQUE",
                "UNUSABLE" if self.issue == "invalid_index" else "VALID",
                "OTHER" if self.issue == "index_columns" else "ID",
                0 if self.database == "yashandb" else 1, "ASC")]
        else:
            raise AssertionError(sql)

    def fetchall(self):
        return self.rows


@pytest.mark.parametrize("database", DATABASES)
@pytest.mark.parametrize("issue", (None, "default", "disabled", "grants", "missing_index", "index_columns", "invalid_index", "delete", "body", "when"))
def test_native_contract_detects_default_none_indexes_grants_and_trigger_drift(database, issue):
    facts = minimal_facts()
    cursor = Catalog(database, issue)
    failures = continuity_schema_validation.errors(cursor, database, facts)
    failures += runner._v502_native_boundary_errors(cursor, database, facts)
    assert bool(failures) == (issue is not None)


@pytest.mark.parametrize("issue", ("columns", "partial_index", "definer", "function_grant"))
def test_postgres_function_grants_and_full_immutable_column_guard_are_required(issue):
    assert runner._v502_native_boundary_errors(Catalog("pg", issue), "pg", minimal_facts())


@pytest.mark.parametrize("database", ("oracle", "yashandb"))
@pytest.mark.parametrize("mutation", ("position_base", "position_gap", "unique_dialect", "unique_flag", "direction"))
def test_native_index_catalog_dialects_do_not_accept_corrupt_or_foreign_facts(database, mutation):
    class IndexCatalog(Catalog):
        def execute(self, sql, parameters):
            super().execute(sql, parameters)
            if "FROM USER_INDEXES" not in sql:
                return
            name, unique, status, column, position, direction = self.rows[0]
            if mutation == "position_base":
                position = 1 if database == "yashandb" else 0
            elif mutation == "position_gap":
                position += 2
            elif mutation == "unique_dialect":
                unique = "NONUNIQUE" if database == "yashandb" else "N"
            elif mutation == "unique_flag":
                unique = "Y" if database == "yashandb" else "UNIQUE"
            elif mutation == "direction":
                direction = "DESC"
            self.rows = [(name, unique, status, column, position, direction)]

    assert runner._v502_native_boundary_errors(IndexCatalog(database), database, minimal_facts()) == [
        "CX_TEST:INDEX:CX106_TEST_INDEX"]


@pytest.mark.parametrize("field", ("default", "trigger_body", "grant_policy", "indexes", "immutable_columns"))
def test_incomplete_manifest_never_certifies_a_native_boundary(field):
    facts = deepcopy(minimal_facts())
    if field == "default":
        facts["CX_TEST"]["columns"]["ID"].pop("default")
    else:
        facts["CX_TEST"].pop(field)
    assert validator.validate_v502_schema_manifest(facts)


@pytest.mark.parametrize('database',DATABASES)
def test_observed_answer_bridge_is_an_additive_fully_immutable_denied_native_contract(database):
    name='109_v5_0_2_observed_answer_reviews.sql'
    assert NEW_STEPS==('106_v5_0_2_model_capacity.sql','107_v5_0_2_processing_recovery.sql',
        '108_v5_0_2_governed_model_turns.sql',name)
    assert PHASE_STEPS==tuple(validator.V501_MIGRATION_SCRIPTS[-3:])+NEW_STEPS
    assert name in runner.NATIVE_SCHEMA_VERIFIED_MIGRATIONS
    facts=json.loads((deploy(database)/name).with_suffix('.schema.json').read_text())
    assert set(facts)=={'CX_OBS_ANSWER_SETS','CX_OBS_ANSWER_ROWS','CX_OBS_ANSWER_REVIEWS'}
    for definition in facts.values():
        assert set(definition['immutable_columns'])==set(definition['columns'])
        assert definition['grant_policy']=='NO_NON_OWNER_GRANTS'


@pytest.mark.parametrize('database',DATABASES)
@pytest.mark.parametrize('name',NEW_STEPS)
def test_every_runtime_step_including109_requires_native_boundary_verification(monkeypatch,database,name):
    checked=[]
    monkeypatch.setattr(continuity_schema_validation,'errors',lambda *_args:[])
    def native(_cursor,observed_database,facts):
        checked.append((observed_database,set(facts)))
        return ['EXPLICIT_TEST_BOUNDARY_DENIAL']
    monkeypatch.setattr(runner,'_v502_native_boundary_errors',native)
    assert not runner._step_objects_complete(None,database,deploy(database)/name,version='5.0.2')
    assert len(checked)==1 and checked[0][0]==database


@pytest.mark.parametrize('database',DATABASES)
@pytest.mark.parametrize('fault',['missing','invalid'])
def test_baseline_cannot_skip_or_accept_invalid109_manifest(tmp_path,database,fault):
    target=tmp_path/database
    shutil.copytree(deploy(database),target)
    manifest=(target/NEW_STEPS[-1]).with_suffix('.schema.json')
    if fault=='missing':manifest.unlink()
    else:
        facts=json.loads(manifest.read_text());facts['CX_OBS_ANSWER_REVIEWS']['grant_policy']='PUBLIC_READ'
        manifest.write_text(json.dumps(facts))
    with pytest.raises(ValueError,match='manifest'):
        build.generate_deployment_baseline(target,'5.0.2',database)
