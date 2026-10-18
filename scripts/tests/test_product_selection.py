"""Selection failures must precede driver imports and keep process identity stable."""
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

try:
    from lib.database_selection import resolve_database
    from lib.product_identity import identity, package_root
except ModuleNotFoundError:
    from shared.lib.database_selection import resolve_database
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
