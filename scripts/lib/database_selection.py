"""Explicit backend selection and lazy adapter activation for unified packages."""

from __future__ import annotations

import importlib.util
import json
import os
from functools import lru_cache
from pathlib import Path
import sys

from .product_identity import package_root, read_manifest


_ALIASES = {"pg": "pg", "postgres": "pg", "postgresql": "pg",
            "oracle": "oracle", "yashandb": "yashandb"}
_MODULES = frozenset({"config", "connection", "agent_api", "graph_adapter"})


def normalize_database(value: object) -> str:
    key = str(value or "").strip().lower()
    if key not in _ALIASES:
        raise ValueError("Database type must be oracle, pg or yashandb")
    return _ALIASES[key]


def supported_databases(root: Path) -> tuple[str, ...]:
    manifest = read_manifest(root)
    declared = (manifest.get("delivery_product") or {}).get("databases")
    if declared is None:
        declared = [(manifest.get("database") or {}).get("key")]
    if not isinstance(declared, (list, tuple)) or not declared:
        raise ValueError("Package does not declare supported databases")
    result = tuple(normalize_database(key) for key in declared)
    if len(set(result)) != len(result):
        raise ValueError("Package declares duplicate database types")
    return result


def resolve_database(root: Path, *, environment: str = "", config: dict | None = None) -> str:
    """Resolve without importing a driver; reject all conflicting selectors."""
    supported = supported_databases(root)
    value = config if config is not None else {}
    if not isinstance(value, dict) or not isinstance(value.get("database", {}), dict):
        raise ValueError("Database configuration must be an object")
    database = value.get("database") or {}
    explicit = [environment, database.get("type"), database.get("dialect"), value.get("database_type")]
    selected = {normalize_database(item) for item in explicit if item}
    if len(selected) > 1:
        raise ValueError("Conflicting database selectors; update configuration and restart")
    if not selected:
        if len(supported) != 1:
            raise ValueError("Select database.type in config.json: oracle, pg or yashandb")
        selected = {supported[0]}
    result = selected.pop()
    if result not in supported:
        raise ValueError("The selected database is not supported by this product")
    return result


@lru_cache(maxsize=1)
def selected_database() -> str:
    """Pin selection for this process; changing a backend requires restart."""
    root = package_root(__file__)
    path = Path(os.environ.get("CX_CONFIG_PATH") or root / "config.json")
    try:
        raw = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    except (OSError, ValueError) as exc:
        raise ValueError("Database selection configuration is unreadable") from exc
    if isinstance(raw, dict) and isinstance(raw.get("database"), dict) and raw["database"].get("_encrypted"):
        from .connection_crypto import decrypt_section
        try:
            decoded = decrypt_section(raw["database"]["_encrypted"])
            raw = dict(raw, database={**raw["database"], **decoded})
        except Exception as exc:
            raise ValueError("Database selection configuration cannot be decrypted") from exc
    return resolve_database(root, environment=os.environ.get("CX_DATABASE_DIALECT", ""), config=raw)


def activate_adapter(module_name: str) -> None:
    """Load under the existing lib.* name to preserve imports and patchability."""
    name = module_name.rsplit(".", 1)[-1]
    if name not in _MODULES:
        raise ImportError("Unregistered database adapter module")
    root = package_root(__file__)
    database = selected_database()
    source = root / "scripts" / "database_adapters" / database / (name + ".py")
    if not source.is_file() or not source.resolve().is_relative_to(root.resolve()):
        raise ImportError("Selected database adapter payload is missing or invalid")
    spec = importlib.util.spec_from_file_location(module_name, source)
    if spec is None or spec.loader is None:
        raise ImportError("Selected database adapter cannot be loaded")
    previous = sys.modules.get(module_name)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        if previous is None:
            sys.modules.pop(module_name, None)
        else:
            sys.modules[module_name] = previous
        raise


if __name__ == "__main__":
    try:
        key = selected_database()
        if "--requirements" in sys.argv:
            root = package_root(__file__)
            selected = root / "requirements" / (key + ".txt")
            print(selected if selected.is_file() else root / "requirements.txt")
        else:
            print("postgresql" if key == "pg" and "--dialect" in sys.argv else key)
    except ValueError as exc:
        raise SystemExit(str(exc)) from None
