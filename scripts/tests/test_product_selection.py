"""Selection failures must precede driver imports and keep process identity stable."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

try:
    from lib.database_selection import configured_database, requirements_for_database, resolve_database
    from lib.product_identity import identity, package_root
except ModuleNotFoundError:
    from shared.lib.database_selection import configured_database, requirements_for_database, resolve_database
    from shared.lib.product_identity import identity, package_root


def package(tmp_path, databases=("oracle", "pg", "yashandb"), brand="chuanxu"):
    manifest = {"version": "5.0.0", "edition": "Community", "delivery_product": {
        "key": "agentx-community" if brand == "agentx" else "unified-community",
        "brand": brand, "databases": list(databases), "name_zh": "OpenTenBase AgentX" if brand == "agentx" else "川序社区版",
        "name_en": "OpenTenBase AgentX" if brand == "agentx" else "Chuanxu Community Edition"}}
    (tmp_path / "build-manifest.json").write_text(json.dumps(manifest))
    return tmp_path


def test_unified_requires_explicit_backend(tmp_path):
    with pytest.raises(ValueError, match="Select database.type"):
        resolve_database(package(tmp_path))


@pytest.mark.parametrize("value", ["pg", "postgres", "postgresql"])
def test_postgres_aliases_agree(tmp_path, value):
    assert resolve_database(package(tmp_path), environment=value, config={"database": {"type": "pg"}}) == "pg"


@pytest.mark.parametrize("value", ["oracle", "yashandb"])
def test_pg_only_rejects_other_database(tmp_path, value):
    with pytest.raises(ValueError, match="not supported"):
        resolve_database(package(tmp_path, ("pg",), "agentx"), environment=value)


def test_conflicting_selectors_fail_closed(tmp_path):
    with pytest.raises(ValueError, match="Conflicting"):
        resolve_database(package(tmp_path), environment="oracle", config={"database": {"type": "pg"}})


@pytest.mark.parametrize("database,driver", [("oracle", "oracledb>=4.0.1"),
                                          ("pg", "psycopg2-binary>=2.9"),
                                          ("yashandb", "yaspy>=1.2.1")])
def test_complete_profile_contains_only_its_selected_driver(tmp_path, database, driver):
    root = package(tmp_path)
    path = root / "requirements" / (database + ".txt")
    path.parent.mkdir()
    path.write_text(driver + "\nhttpx==0.28.1\n")
    assert requirements_for_database(root, database) == path.resolve()


@pytest.mark.parametrize("content", ["httpx==0.28.1\n", "oracledb>=4.0.1\n",
                                    "psycopg2-binary>=2.9\noracledb>=4.0.1\n"])
def test_missing_or_foreign_driver_cannot_pass_profile_validation(tmp_path, content):
    root = package(tmp_path)
    path = root / "requirements/pg.txt"
    path.parent.mkdir()
    path.write_text(content)
    with pytest.raises(ValueError, match="only the selected"):
        requirements_for_database(root, "pg")


@pytest.mark.parametrize("database,driver", [("oracle", "oracledb"), ("pg", "psycopg2-binary"),
                                          ("yashandb", "yaspy")])
@pytest.mark.parametrize("marker", ["python_version < '3.0'", "python_version >= '3.0'"])
def test_database_driver_cannot_be_skipped_by_pip_marker(tmp_path, database, driver, marker):
    root = package(tmp_path)
    profile = root / "requirements" / (database + ".txt")
    profile.parent.mkdir()
    profile.write_text(f"{driver}>=1.0; {marker}\nhttpx==0.28.1\n")
    with pytest.raises(ValueError, match="must be unconditional"):
        requirements_for_database(root, database)


def test_missing_unified_profile_does_not_fall_back_to_common_dependencies(tmp_path):
    root = package(tmp_path)
    (root / "requirements.txt").write_text("httpx==0.28.1\n")
    with pytest.raises(ValueError, match="missing"):
        requirements_for_database(root, "pg")


def test_single_backend_retains_complete_root_profile(tmp_path):
    root = package(tmp_path, ("pg",))
    (root / "requirements.txt").write_text("psycopg2-binary>=2.9\nhttpx==0.28.1\n")
    assert requirements_for_database(root, "pg") == (root / "requirements.txt").resolve()


def test_cli_environment_and_configuration_selectors_must_all_agree(tmp_path, monkeypatch):
    root = package(tmp_path)
    config = root / "config.json"
    config.write_text('{"database":{"type":"pg"}}')
    monkeypatch.setenv("CX_CONFIG_PATH", str(config))
    monkeypatch.setenv("CX_DATABASE_DIALECT", "postgresql")
    assert configured_database(root, explicit_database="postgres") == "pg"
    with pytest.raises(ValueError, match="Conflicting"):
        configured_database(root, explicit_database="oracle")


def test_offline_installer_rejects_selection_conflict_before_creating_environment(tmp_path):
    root = package(tmp_path)
    shared = Path(__file__).resolve().parents[1]
    scripts = root / "scripts"
    lib = scripts / "lib"
    lib.mkdir(parents=True)
    (lib / "__init__.py").touch()
    for name in ("database_selection", "product_identity"):
        shutil.copy2(shared / "lib" / (name + ".py"), lib / (name + ".py"))
    shutil.copy2(shared / "install_offline.sh", scripts / "install_offline.sh")
    runtime_script = shared / "scripts/python_runtime.sh"
    if not runtime_script.is_file():
        runtime_script = shared / "python_runtime.sh"
    shutil.copy2(runtime_script, scripts / "python_runtime.sh")
    (root / "vendor").mkdir()
    (root / "requirements.txt").write_text("httpx==0.28.1\n")
    config = root / "config.json"
    config.write_text('{"database":{"type":"pg"}}')
    environment = dict(os.environ, PYTHON_BIN=sys.executable, CX_CONFIG_PATH=str(config),
                       CX_VENV_DIR=str(root / "must-not-be-created"))
    environment.pop("CX_DATABASE_DIALECT", None)
    result = subprocess.run(["bash", str(scripts / "install_offline.sh"), "--database", "oracle"],
                            cwd=root, env=environment, capture_output=True, text=True)
    assert result.returncode != 0
    assert "Conflicting" in result.stderr
    assert not (root / "must-not-be-created").exists()


def test_offline_installer_rejects_foreign_driver_before_pip_install(tmp_path):
    root = package(tmp_path)
    shared = Path(__file__).resolve().parents[1]
    scripts = root / "scripts"
    lib = scripts / "lib"
    lib.mkdir(parents=True)
    (lib / "__init__.py").touch()
    for name in ("database_selection", "product_identity"):
        shutil.copy2(shared / "lib" / (name + ".py"), lib / (name + ".py"))
    shutil.copy2(shared / "install_offline.sh", scripts / "install_offline.sh")
    runtime_script = shared / "scripts/python_runtime.sh"
    if not runtime_script.is_file():
        runtime_script = shared / "python_runtime.sh"
    shutil.copy2(runtime_script, scripts / "python_runtime.sh")
    (scripts / "oracledb.py").write_text("raise AssertionError('must not import foreign driver')\n")
    (root / "vendor").mkdir()
    (root / "requirements").mkdir()
    (root / "requirements/pg.txt").write_text("psycopg2-binary>=2.9\n")
    (root / "requirements.txt").write_text("httpx==0.28.1\n")
    config = root / "config.json"
    config.write_text('{"database":{"type":"pg"}}')
    venv = root / ".venv"
    # A real isolated stdlib-only venv, without pip or any installed dependencies.
    subprocess.run([sys.executable, "-m", "venv", "--without-pip", str(venv)], check=True)
    environment = dict(os.environ, PYTHON_BIN=sys.executable, CX_CONFIG_PATH=str(config),
                       CX_VENV_DIR=str(venv))
    environment.pop("CX_DATABASE_DIALECT", None)
    result = subprocess.run(["bash", str(scripts / "install_offline.sh"), "--database", "pg"],
                            cwd=root, env=environment, capture_output=True, text=True)
    assert result.returncode != 0
    assert "another database driver: oracledb" in result.stderr
    assert "must not import" not in result.stderr
    assert not (root / ".runtime").exists()


@pytest.mark.parametrize("database,driver,broken_vendor", [("oracle", "oracledb", False),
    ("pg", "psycopg2-binary", False), ("yashandb", "yaspy", False), ("yashandb", "yaspy", True)])
def test_offline_installation_routes_one_profile_with_stubbed_package_operations(tmp_path, database, driver, broken_vendor):
    root = package(tmp_path)
    shared = Path(__file__).resolve().parents[1]
    scripts = root / "scripts"
    lib = scripts / "lib"
    lib.mkdir(parents=True)
    (lib / "__init__.py").touch()
    for name in ("database_selection", "product_identity"):
        shutil.copy2(shared / "lib" / (name + ".py"), lib / (name + ".py"))
    shutil.copy2(shared / "install_offline.sh", scripts / "install_offline.sh")
    (scripts / "python_runtime.sh").write_text(
        'cx_resolve_python() { printf "%s\\n" "$PYTHON_BIN"; }\n'
        'cx_prepare_python_environment() { :; }\n')
    (scripts / "install_yaspy.sh").write_text('printf "native\\n" >>"$CX_TEST_EVENTS"\n')
    (scripts / "verify_deps.py").touch()
    (root / "vendor/yaspy").mkdir(parents=True)
    (root / "requirements").mkdir()
    for backend, dependency in (("oracle", "oracledb"), ("pg", "psycopg2-binary"), ("yashandb", "yaspy")):
        (root / "requirements" / (backend + ".txt")).write_text(dependency + ">=1.0\nhttpx==0.28.1\n")
    (root / "requirements.txt").write_text("httpx==0.28.1\n")
    config = root / "config.json"
    config.write_text(json.dumps({"database": {"type": database}}))
    interpreter = root / ".venv/bin/python"
    interpreter.parent.mkdir(parents=True)
    # Intercept all package/native operations; real Python only resolves the
    # database/profile. This checks shell routing without installing anything.
    interpreter.write_text(f"""#!{sys.executable}
import json, os, pathlib, sys
args = sys.argv[1:]
if args[:2] == ['-m', 'lib.database_selection']:
    os.execv({sys.executable!r}, [{sys.executable!r}, *args])
event = {{'args': args}}
if args[:3] == ['-m', 'pip', 'install']:
    event['requirements'] = pathlib.Path(args[args.index('-r') + 1]).read_text()
elif args and args[0] == '-':
    event['script'] = sys.stdin.read()
elif args and args[0].endswith('verify_deps.py'):
    event['profile'] = os.environ['CX_REQUIREMENTS_FILE']
elif args[:2] != ['-m', 'pip'] and args[:1] != ['-c']:
    raise SystemExit('unexpected package operation')
with open(os.environ['CX_TEST_EVENTS'], 'a') as output:
    output.write(json.dumps(event) + '\\n')
if args and args[0].endswith('verify_deps.py') and os.environ.get('CX_TEST_BROKEN_VENDOR'):
    raise SystemExit('incomplete native payload')
""")
    interpreter.chmod(0o700)
    events = root / "events.jsonl"
    environment = dict(os.environ, PYTHON_BIN=str(interpreter), CX_CONFIG_PATH=str(config),
                       CX_VENV_DIR=str(interpreter.parents[1]), CX_TEST_EVENTS=str(events))
    environment.pop("CX_DATABASE_DIALECT", None)
    if broken_vendor:
        environment["CX_TEST_BROKEN_VENDOR"] = "1"
    result = subprocess.run(["bash", str(scripts / "install_offline.sh"), "--database", database],
                            cwd=root, env=environment, capture_output=True, text=True)
    records = [json.loads(line) for line in events.read_text().splitlines() if line != "native"]
    pip = [event for event in records if event["args"][:3] == ["-m", "pip", "install"]]
    if broken_vendor:
        assert result.returncode != 0
        assert "incomplete native payload" in result.stderr
        assert not pip
        assert "native" not in events.read_text().splitlines()
        assert not (root / ".runtime").exists()
        return
    assert result.returncode == 0, result.stderr
    assert len(pip) == 1
    assert "httpx==0.28.1" in pip[0]["requirements"]
    assert (driver + ">=1.0" in pip[0]["requirements"]) == (database != "yashandb")
    assert not any(other in pip[0]["requirements"] for other in ("oracledb", "psycopg2-binary", "yaspy")
                   if other != driver)
    assert ("native" in events.read_text().splitlines()) == (database == "yashandb")
    if database == "yashandb":
        lines = events.read_text().splitlines()
        first_verification = next(index for index, line in enumerate(lines) if 'verify_deps.py' in line)
        assert first_verification < lines.index("native")
    assert all(event["profile"] == str(root / "requirements" / (database + ".txt"))
               for event in records if "profile" in event)
    assert any("importlib.import_module" in event.get("script", "") for event in records)
    assert not list((root / ".runtime/install").glob("requirements-*.txt"))


@pytest.mark.parametrize("config", [[], {"database": []}, {"database": {"type": "../../oracle"}}])
def test_invalid_selection_never_resolves(tmp_path, config):
    with pytest.raises(ValueError):
        resolve_database(package(tmp_path), config=config)


def test_agentx_identity_is_independent_and_pg_only(tmp_path):
    value = identity(package(tmp_path, ("pg",), "agentx"))
    assert value["brand_en"] == value["brand_zh"] == "OpenTenBase AgentX"
    assert value["databases"] == ["pg"]
    assert value["logo"].endswith("opentenbase-mark.png")


def test_nested_adapter_resolves_package_config_root(tmp_path):
    root = package(tmp_path)
    module = root / "scripts/database_adapters/pg/config.py"
    module.parent.mkdir(parents=True)
    module.touch()
    assert package_root(module) == root


def test_legacy_single_database_still_resolves(tmp_path):
    (tmp_path / "build-manifest.json").write_text(json.dumps({"database": {"key": "pg"}}))
    assert resolve_database(tmp_path) == "pg"


def test_duplicate_database_declaration_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="duplicate"):
        resolve_database(package(tmp_path, ("pg", "postgresql")))


def test_selected_adapter_keeps_module_identity_without_loading_other_backend(tmp_path):
    root = package(tmp_path)
    source = Path(sys.modules[resolve_database.__module__].__file__).parent
    lib = root / "scripts/lib"
    lib.mkdir(parents=True)
    (lib / "__init__.py").touch()
    for name in ("database_selection", "product_identity"):
        shutil.copy2(source / (name + ".py"), lib / (name + ".py"))
    (lib / "connection.py").write_text("from .database_selection import activate_adapter\nactivate_adapter(__name__)\n")
    for database in ("oracle", "pg", "yashandb"):
        adapter = root / "scripts/database_adapters" / database
        adapter.mkdir(parents=True)
        content = ("from dataclasses import dataclass\n@dataclass\nclass State:\n    value: str = 'pg'\n"
                   if database == "pg" else "raise AssertionError('unselected adapter imported')\n")
        (adapter / "connection.py").write_text(content)
    (root / "config.json").write_text('{"database":{"type":"pg"}}')
    code = """import json, sys
from lib import connection
from lib.database_selection import selected_database
assert connection.State().value == 'pg'
assert connection is sys.modules['lib.connection']
from pathlib import Path
Path('config.json').write_text('{"database":{"type":"oracle"}}')
assert selected_database() == 'pg'
assert not any(key in sys.modules for key in ('oracledb','yaspy'))
print('pinned, selected-only, module identity preserved')
"""
    result = subprocess.run([sys.executable, "-B", "-c", code], cwd=root,
                            env={"PYTHONPATH": str(root / "scripts")}, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert "selected-only" in result.stdout
