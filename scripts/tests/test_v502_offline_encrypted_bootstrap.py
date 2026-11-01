"""Encrypted selector is verified before an empty venv installs any payload."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from lib.connection_crypto import encrypt_section


def fixture(tmp_path, database="oracle", *, mismatched_runtime=False):
    shared = Path(__file__).resolve().parents[1]
    root, scripts = tmp_path, tmp_path / "scripts"
    lib = scripts / "lib"
    lib.mkdir(parents=True)
    (lib / "__init__.py").touch()
    for name in ("database_selection", "product_identity", "connection_crypto"):
        shutil.copy2(shared / "lib" / (name + ".py"), lib / (name + ".py"))
    shutil.copy2(shared / "install_offline.sh", scripts / "install_offline.sh")
    helper = shared / "scripts/python_runtime.sh"
    if not helper.exists():
        helper = shared / "python_runtime.sh"
    shutil.copy2(helper, scripts / "python_runtime.sh")
    (root / "vendor").mkdir()
    (root / "requirements").mkdir()
    (root / "requirements.txt").write_text("cryptography>=44\n")
    driver = {"oracle": "oracledb", "pg": "psycopg2-binary", "yashandb": "yaspy"}[database]
    (root / "requirements" / (database + ".txt")).write_text(driver + ">=1\ncryptography>=44\n")
    (root / "build-manifest.json").write_text(json.dumps(dict(version="5.0.2", edition="Community",
        delivery_product=dict(key="unified-community", databases=["oracle", "pg", "yashandb"]))))
    key = b"synthetic-offline-bootstrap-key!"
    config = root / "encrypted.json"
    config.write_text(json.dumps(dict(database=dict(type=database,
        _encrypted=encrypt_section(dict(type=database, user="synthetic-only"), master_key=key)))))
    config.chmod(0o600)
    venv = root / "empty-environment"
    subprocess.run([sys.executable, "-m", "venv", "--without-pip", str(venv)], check=True)
    interpreter = venv / "bin/python"
    before = subprocess.run([str(interpreter), "-c", "import cryptography"], capture_output=True)
    assert before.returncode != 0
    # Real selection/decryption precedes a deliberately failing payload gate.
    # Its sentinel proves the installer used the bootstrap interpreter rather
    # than crashing in the empty venv or reaching pip/native installation.
    (scripts / "verify_deps.py").write_text(
        "import os,sys,pathlib\n"
        "from lib.database_selection import configured_database\n"
        "assert configured_database(pathlib.Path(__file__).parents[1]) == os.environ['CX_DATABASE_DIALECT']\n"
        "pathlib.Path(os.environ['CX_TEST_GATE']).write_text(sys.executable)\n"
        "raise SystemExit('INTENTIONAL_PAYLOAD_GATE_FAILURE')\n")
    environment = {key: value for key, value in os.environ.items() if not key.startswith(("CX_", "AIAGENT_", "MEMORY_SERVER_"))}
    import base64
    environment.update(PYTHON_BIN=sys.executable, CX_CONFIG_PATH=str(config), CX_VENV_DIR=str(venv),
        MASTER_DB_KEY=base64.b64encode(key).decode(), CX_TEST_GATE=str(root / "gate-observed"))
    if mismatched_runtime:
        # A real second interpreter process with altered reported ABI, while
        # still delegating ordinary selection/runtime discovery to CPython.
        shim = root / "bootstrap-python"
        shim.write_text(f"#!{sys.executable}\nimport os,sys\n"
            "if len(sys.argv)>2 and sys.argv[1]=='-c' and 'sysconfig.get_config_var' in sys.argv[2]:\n"
            " print('[[3, 15], \"cpython\", \"cp315\", \"x86_64\"]')\n"
            "else:\n"
            f" os.execv({sys.executable!r}, [{sys.executable!r}, *sys.argv[1:]])\n")
        shim.chmod(0o700)
        environment["PYTHON_BIN"] = str(shim)
    return root, scripts, environment, config.read_bytes()


@pytest.mark.parametrize("database", ["oracle", "pg", "yashandb"])
def test_bootstrap_decrypts_before_strict_gate_and_no_driver_is_installed(tmp_path, database):
    root, scripts, env, original = fixture(tmp_path, database)
    result = subprocess.run(["bash", str(scripts / "install_offline.sh"), "--database", database],
        cwd=root, env=env, text=True, capture_output=True)
    assert result.returncode != 0 and "INTENTIONAL_PAYLOAD_GATE_FAILURE" in result.stderr
    assert "ModuleNotFoundError" not in result.stderr
    assert Path((root / "gate-observed").read_text()).resolve() == Path(sys.executable).resolve()
    assert (root / "encrypted.json").read_bytes() == original
    assert not (root / ".runtime").exists()
    assert "Processing " not in result.stdout and "Successfully installed" not in result.stdout


def test_different_runtime_or_abi_cannot_use_bootstrap_wheel_compatibility(tmp_path):
    root, scripts, env, original = fixture(tmp_path, mismatched_runtime=True)
    result = subprocess.run(["bash", str(scripts / "install_offline.sh"), "--database", "oracle"],
        cwd=root, env=env, text=True, capture_output=True)
    assert result.returncode != 0 and "same Python version, ABI and architecture" in result.stderr
    assert not (root / "gate-observed").exists()
    assert (root / "encrypted.json").read_bytes() == original
