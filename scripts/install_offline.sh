#!/bin/bash
# AI Agent Infra - Offline Dependency Installer
# Installs all Python packages from local vendor/ directory (no network required)
set -euo pipefail

DATABASE_ARGS=()
while [[ $# -gt 0 ]]; do
    case "$1" in
        --database)
            if [[ $# -lt 2 || ${#DATABASE_ARGS[@]} -ne 0 ]]; then
                echo "[ERROR] specify --database once: oracle, pg or yashandb" >&2
                exit 2
            fi
            DATABASE_ARGS=(--database "$2")
            shift 2
            ;;
        -h|--help)
            echo "Usage: bash scripts/install_offline.sh [--database oracle|pg|yashandb]"
            echo "Selection must agree with CX_DATABASE_DIALECT and config.json."
            echo "Use a separate installation directory or CX_VENV_DIR for each backend."
            exit 0
            ;;
        *) echo "[ERROR] unknown option: $1" >&2; exit 2 ;;
    esac
done

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
VENDOR_DIR="$PROJECT_DIR/vendor"
REQ_FILE="$PROJECT_DIR/requirements.txt"
VENV_DIR="${CX_VENV_DIR:-$PROJECT_DIR/.venv}"
VENV_PYTHON="$VENV_DIR/bin/python"

if [ ! -d "$VENDOR_DIR" ]; then
    echo "[ERROR] vendor/ directory not found at $VENDOR_DIR"
    echo "        Run this script from the project root directory."
    exit 1
fi

if [ ! -f "$REQ_FILE" ]; then
    echo "[ERROR] requirements.txt not found at $REQ_FILE"
    exit 1
fi

echo "[install] Installing dependencies from vendor/ (offline mode)..."
if [[ -f "$SCRIPT_DIR/python_runtime.sh" ]]; then
    # In a generated package this installer lives under scripts/.
    RUNTIME_HELPER="$SCRIPT_DIR/python_runtime.sh"
else
    # In the unified source tree it lives beside shared/scripts/.
    RUNTIME_HELPER="$SCRIPT_DIR/scripts/python_runtime.sh"
fi
if [[ ! -f "$RUNTIME_HELPER" ]]; then
    echo "[ERROR] Python runtime helper is missing: $RUNTIME_HELPER" >&2
    exit 1
fi
source "$RUNTIME_HELPER"
if [[ -z "${PYTHON_BIN:-}" && -x "$VENV_PYTHON" ]]; then
    PYTHON_BIN="$VENV_PYTHON"
fi
if ! PYTHON_BIN="$(cx_resolve_python "${PYTHON_BIN:-}")"; then
    echo "[ERROR] Python 3.14+ is required. Set PYTHON_BIN to an accessible interpreter." >&2
    exit 1
fi
cx_prepare_python_environment "$PYTHON_BIN"
export PYTHONPATH="$PROJECT_DIR/scripts${PYTHONPATH:+:$PYTHONPATH}"
DB_KEY="$("$PYTHON_BIN" -m lib.database_selection "${DATABASE_ARGS[@]}")"
REQ_FILE="$("$PYTHON_BIN" -m lib.database_selection "${DATABASE_ARGS[@]}" --requirements)"
export CX_DATABASE_DIALECT="$DB_KEY"
export CX_REQUIREMENTS_FILE="$REQ_FILE"
echo "[install] Selected database: $DB_KEY; requirements: $REQ_FILE"
if ! "$PYTHON_BIN" -m pip --version >/dev/null 2>&1; then
    echo "[ERROR] $PYTHON_BIN has no pip module. Install pip for the same interpreter before retrying." >&2
    exit 1
fi
# Homebrew and other PEP 668 Python installations deliberately reject global
# pip writes. A package-local virtual environment also keeps an offline
# deployment isolated from the operator's Python installation.
if [[ ! -x "$VENV_PYTHON" ]]; then
    "$PYTHON_BIN" -m venv "$VENV_DIR"
fi
if ! "$VENV_PYTHON" -c 'import sys; raise SystemExit(0 if sys.version_info[:2] >= (3, 14) else 1)' >/dev/null 2>&1; then
    echo "[ERROR] package virtual environment does not use Python 3.14+" >&2
    exit 1
fi
# Never silently reuse another backend's environment. No driver is imported
# and no package/native-client installation occurs before this check.
"$VENV_PYTHON" - "$DB_KEY" <<'PY'
import importlib.util
import sys
drivers = {"oracle": "oracledb", "pg": "psycopg2", "yashandb": "yaspy"}
other = [name for database, name in drivers.items()
         if database != sys.argv[1] and importlib.util.find_spec(name) is not None]
if other:
    raise SystemExit("[ERROR] virtual environment contains another database driver: "
                     + ", ".join(other) + "; select a separate CX_VENV_DIR")
PY
# Validate the complete selected wheel/native payload before installing a
# database driver or copying client libraries into the environment.
"$VENV_PYTHON" "$SCRIPT_DIR/verify_deps.py"
# YashanDB ships a CPython-native driver rather than a wheel. Install it into
# the same package-local virtual environment before checking or starting the
# Web service; no user-site or global Python path is modified.
if [[ "$DB_KEY" == "yashandb" && -d "$VENDOR_DIR/yaspy" ]]; then
    if [[ ! -f "$SCRIPT_DIR/install_yaspy.sh" ]]; then
        echo "[ERROR] YashanDB native-driver installer is missing." >&2
        exit 1
    fi
    CX_YASHAN_LIB_DIR="${CX_YASHAN_LIB_DIR:-$PROJECT_DIR/.runtime/yashandb-client/lib}" \
        PYTHON_BIN="$VENV_PYTHON" bash "$SCRIPT_DIR/install_yaspy.sh"
    export LD_LIBRARY_PATH="${CX_YASHAN_LIB_DIR:-$PROJECT_DIR/.runtime/yashandb-client/lib}${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
fi
PIP_REQ_FILE="$REQ_FILE"
TEMP_REQ_FILE=""
if [[ "$DB_KEY" == "yashandb" && -d "$VENDOR_DIR/yaspy" ]]; then
    # yaspy is shipped as a native extension, not as a pip distribution.
    mkdir -p "$PROJECT_DIR/.runtime/install"
    TEMP_REQ_FILE="$(mktemp "$PROJECT_DIR/.runtime/install/requirements-XXXXXX.txt")"
    sed -E '/^[[:space:]]*yaspy([<=>]|$)/d' "$REQ_FILE" >"$TEMP_REQ_FILE"
    PIP_REQ_FILE="$TEMP_REQ_FILE"
    trap 'rm -f "$TEMP_REQ_FILE"' EXIT
fi
"$VENV_PYTHON" -m pip install --no-index --find-links "$VENDOR_DIR" -r "$PIP_REQ_FILE"
"$VENV_PYTHON" - "$DB_KEY" <<'PY'
import importlib
import sys
importlib.import_module({"oracle": "oracledb", "pg": "psycopg2", "yashandb": "yaspy"}[sys.argv[1]])
print("[install] Selected database driver loads successfully.")
PY
echo "[install] Done. Rechecking selected offline dependency set..."
"$VENV_PYTHON" "$SCRIPT_DIR/verify_deps.py"
