#!/bin/bash
# Install yaspy driver and YashanDB client libraries
# Usage: bash scripts/install_yaspy.sh

cx_atomic_copy() {
    local source="$1" target="$2" staged
    staged="$(mktemp "$(dirname "$target")/.cx-native-XXXXXX")" || return 1
    if cp --preserve=mode "$source" "$staged" && mv -f "$staged" "$target"; then
        return 0
    fi
    rm -f "$staged"
    return 1
}

cx_link_client_library() {
    local lib="$1" base soname
    base="${lib%%.so.*}"
    soname="$(LC_ALL=C readelf -d "$lib" | awk '/\(SONAME\)/ { sub(/^.*\[/, ""); sub(/\].*$/, ""); print; exit }')"
    if [[ ! "$soname" =~ ^lib[A-Za-z0-9_]+\.so(\.[0-9]+)*$ ]]; then
        echo "[install] ERROR: Missing or invalid ELF SONAME for $lib" >&2
        return 1
    fi
    ln -sfn "$lib" "$soname"
    ln -sfn "$lib" "${base}.so"
}

# Allow the linker helper to be tested without installing a Python module.
if [[ "${BASH_SOURCE[0]}" != "$0" ]]; then
    return 0
fi
set -euo pipefail
if ! command -v readelf >/dev/null 2>&1; then
    echo "[install] ERROR: readelf is required; install binutils first." >&2
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
if [ -f "$SCRIPT_DIR/python_runtime.sh" ]; then
    RUNTIME_HELPER="$SCRIPT_DIR/python_runtime.sh"
elif [ -f "$SCRIPT_DIR/../../shared/scripts/python_runtime.sh" ]; then
    RUNTIME_HELPER="$SCRIPT_DIR/../../shared/scripts/python_runtime.sh"
else
    echo "[install] ERROR: Python runtime helper is missing." >&2
    exit 1
fi
source "$RUNTIME_HELPER"
if ! PYTHON_BIN="$(cx_resolve_python "${PYTHON_BIN:-}")"; then
    echo "[install] ERROR: Python 3.14+ was not found; set PYTHON_BIN." >&2
    exit 1
fi
cx_prepare_python_environment "$PYTHON_BIN"
PYTHON_SITE=$("$PYTHON_BIN" -c "import sysconfig; print(sysconfig.get_path('platlib'))")
mkdir -p "$PYTHON_SITE"

echo "[install] Installing yaspy driver..."

# Install yaspy .so file
if [ -f "$PROJECT_DIR/vendor/yaspy/yaspy.cpython-314-x86_64-linux-gnu.so" ]; then
    cx_atomic_copy "$PROJECT_DIR/vendor/yaspy/yaspy.cpython-314-x86_64-linux-gnu.so" "$PYTHON_SITE/yaspy.cpython-314-x86_64-linux-gnu.so"
    echo "[install] yaspy driver installed to $PYTHON_SITE"
else
    echo "[install] ERROR: yaspy .so file not found in vendor/yaspy/"
    exit 1
fi

# Install YashanDB client libraries beside the package by default. Operators
# can override CX_YASHAN_LIB_DIR for an approved shared client location.
YASHAN_LIB_DIR="${CX_YASHAN_LIB_DIR:-$PROJECT_DIR/.runtime/yashandb-client/lib}"
mkdir -p "$YASHAN_LIB_DIR"

if [ -d "$PROJECT_DIR/vendor/yaspy/client_lib" ]; then
    for source_lib in "$PROJECT_DIR/vendor/yaspy/client_lib/"*; do
        cx_atomic_copy "$source_lib" "$YASHAN_LIB_DIR/$(basename "$source_lib")"
    done
    
    # Create symlinks for shared library versioning
    cd "$YASHAN_LIB_DIR"
    shopt -s nullglob
    for lib in *.so.*.*.*; do
        cx_link_client_library "$lib"
    done
    
    echo "[install] YashanDB client libraries installed to $YASHAN_LIB_DIR"
    
    # Keep loader configuration process-local. The Web start script applies
    # the same path on every launch, so installation never modifies ~/.bashrc.
    export LD_LIBRARY_PATH="$YASHAN_LIB_DIR${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
else
    echo "[install] ERROR: YashanDB client libraries not found in vendor/yaspy/client_lib/" >&2
    exit 1
fi

# Verify installation
if "$PYTHON_BIN" -c "import ctypes, yaspy; ctypes.CDLL('libyascli.so'); print('[install] yaspy driver and native client load verified')"; then
    :
else
    echo "[install] ERROR: yaspy import failed - check the package-local client library path" >&2
    exit 1
fi

echo "[install] Done."
