"""Package-derived product identity; no database or network access."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


def package_root(module_file: str | Path) -> Path:
    """Support source, legacy overlays and nested unified adapter payloads."""
    path = Path(module_file).resolve()
    for parent in path.parents:
        if (parent / "build-manifest.json").is_file():
            return parent
    return path.parents[2]


def read_manifest(root: Path | None = None) -> dict[str, Any]:
    root = root or package_root(__file__)
    path = root / "build-manifest.json"
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError("Package identity manifest is unreadable") from exc
    if not isinstance(value, dict):
        raise ValueError("Package identity manifest must be an object")
    return value


def identity(root: Path | None = None) -> dict[str, Any]:
    manifest = read_manifest(root)
    product = manifest.get("delivery_product") or {}
    donated = product.get("brand") == "agentx"
    return {
        "product_key": product.get("key") or "legacy",
        "name_zh": product.get("name_zh") or "川序",
        "name_en": product.get("name_en") or "Chuanxu",
        "brand_key": "agentx" if donated else "chuanxu",
        "brand_zh": "OpenTenBase AgentX" if donated else "川序",
        "brand_en": "OpenTenBase AgentX" if donated else "Chuanxu",
        "version": manifest.get("version") or "5.0.1",
        "edition": manifest.get("edition") or "Community",
        "databases": product.get("databases") or [
            (manifest.get("database") or {}).get("key") or "pg"
        ],
        # AgentX uses the official OpenTenBase logo as the image mark.  The
        # product name is rendered beside it by the page shell, so the mark
        # itself stays vendor-authentic and is not a custom combined lockup.
        "logo": "/static/brand/opentenbase-mark.png" if donated else "/static/brand/chuanxu-mark.svg",
    }


def release_product(manifest: dict[str, Any]) -> dict[str, Any]:
    """Validate archive identity without importing drivers or trusting its label."""
    version = str(manifest.get("version") or "")
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError("release version must use three numeric components")
    edition = manifest.get("edition")
    if edition not in {"Community", "Enterprise"}:
        raise ValueError("release edition is unsupported")
    declared = manifest.get("delivery_product")
    database = (manifest.get("database") or {}).get("key")
    if declared is not None:
        from product_delivery import product_for
        if not isinstance(declared, dict):
            raise ValueError("release product identity is invalid")
        expected = product_for(declared.get("key"))
        if declared != json.loads(json.dumps(expected.manifest())):
            raise ValueError("release product differs from the delivery registry")
        if edition != expected.edition or manifest.get("license") != expected.license:
            raise ValueError("release edition or license differs from its product")
        if database != ("selectable" if len(expected.databases) > 1 else expected.databases[0]):
            raise ValueError("release database differs from its product")
        return {"product_key": expected.key, "databases": list(expected.databases), "edition": edition}
    if int(version.split(".")[0]) >= 5 or database not in {"oracle", "pg", "yashandb"}:
        raise ValueError("release requires a supported product and database identity")
    return {"product_key": "legacy", "databases": [database], "edition": edition}


def check_release_compatibility(manifest: dict[str, Any], *, database: str,
                                edition: str = "", current: dict[str, Any] | None = None) -> dict[str, Any]:
    """Permit supported upgrades, with independent products kept separate."""
    release = release_product(manifest)
    database = "pg" if database in {"postgresql", "pg"} else database
    if database not in release["databases"]:
        raise ValueError("upgrade package database does not match this installation")
    if edition and release["edition"].lower() != edition.lower():
        raise ValueError("upgrade package edition is incompatible with this installation")
    if current:
        installed = release_product(current)
        if installed["edition"] != release["edition"]:
            raise ValueError("upgrade cannot change the installed edition")
        if installed["product_key"] != "legacy":
            if installed["product_key"] != release["product_key"]:
                raise ValueError("upgrade cannot change the installed product")
        elif release["product_key"] == "agentx-community":
            raise ValueError("AgentX requires its independent installation; legacy Chuanxu cannot be implicitly rebranded")
    return release
