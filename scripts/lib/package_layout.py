"""Resolve actual adapter assets in source, single-backend and unified packages."""
from pathlib import Path
import os

from .database_selection import normalize_database, resolve_database, supported_databases


def databases(root: Path) -> tuple[str, ...]:
    if (root / "build-manifest.json").is_file():
        return supported_databases(root)
    return tuple(key for key in ("oracle", "pg", "yashandb") if (root / "adapters" / key).is_dir())


def active_database(root: Path) -> str:
    if (root / "build-manifest.json").is_file():
        return resolve_database(root, environment=os.environ.get("CX_DATABASE_DIALECT", ""))
    return normalize_database(os.environ.get("AIAGENT_SOURCE_ADAPTER") or "oracle")


def deployment_dir(root: Path, database: str) -> Path:
    key = normalize_database(database)
    if key not in databases(root):
        raise ValueError("Database assets are not available in this product")
    if (root / "adapters" / key / "deploy").is_dir():
        return root / "adapters" / key / "deploy"
    nested = root / "scripts/deploy" / key
    return nested if nested.is_dir() else root / "scripts/deploy"


def adapter_file(root: Path, database: str, name: str) -> Path:
    key = normalize_database(database)
    if key not in databases(root):
        raise ValueError("Database adapter is not available in this product")
    if name not in {"config.py", "connection.py", "agent_api.py", "graph_adapter.py"}:
        raise ValueError("Unknown adapter file")
    if (root / "adapters" / key).is_dir():
        return root / "adapters" / key / ("config_db.py" if name == "config.py" else name)
    nested = root / "scripts/database_adapters" / key / name
    return nested if nested.is_file() else root / "scripts/lib" / name
