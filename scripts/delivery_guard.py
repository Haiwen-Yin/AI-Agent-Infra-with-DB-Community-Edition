"""Product identity and payload checks shared by v5 builds and extracted packages."""
from __future__ import annotations

import json
from pathlib import Path

from product_delivery import PRODUCTS, product_for, acceptance_targets
from package_guard import verify_manifest


def validate_product(root: Path) -> list[str]:
    errors = []
    try:
        manifest = json.loads((root / "build-manifest.json").read_text(encoding="utf-8"))
        declared = manifest["delivery_product"]
        product = product_for(declared["key"])
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return [f"invalid product manifest: {type(exc).__name__}"]
    expected = json.loads(json.dumps(product.manifest()))
    if declared != expected:
        errors.append("product identity differs from the authoritative delivery registry")
    if root.name != product.package:
        errors.append("package directory differs from the product name")
    if manifest.get("edition") != product.edition or manifest.get("license") != product.license:
        errors.append("product edition or license differs from its registry entry")
    if product.key == "unified-community":
        adapter_root = root / "scripts/database_adapters"
        present = {path.name for path in adapter_root.iterdir() if path.is_dir()} if adapter_root.is_dir() else set()
        if present != set(product.databases):
            errors.append("unified adapter payload does not match the declared database set")
        for database in product.databases:
            for name in ("config", "connection", "agent_api", "graph_adapter"):
                if not (adapter_root / database / (name + ".py")).is_file():
                    errors.append(f"missing {database} adapter: {name}")
            if not (root / "requirements" / (database + ".txt")).is_file():
                errors.append(f"missing selected-driver requirements: {database}")
        shared_requirements = root / "requirements.txt"
        if shared_requirements.is_file():
            import re
            if any(re.match(r"^\s*(?:oracledb|psycopg2[-_]binary|yaspy)(?:\s|[<=>!~\[]|$)", line, re.I)
                   for line in shared_requirements.read_text().splitlines()):
                errors.append("unified common requirements must not install database drivers")
    from shared.lib.database_selection import requirements_for_database
    for database in product.databases:
        try:
            requirements_for_database(root, database)
        except (OSError, ValueError) as exc:
            errors.append(f"invalid {database} dependency profile: {exc}")
    if product.brand == "agentx":
        if manifest.get("brand") != {"zh": product.name_zh, "en": product.name_en}:
            errors.append("AgentX brand identity is inconsistent")
        brand = root / "scripts/visualization/static/brand"
        if set(manifest.get("assets", {})) != {"opentenbase-mark.png"} or not (brand / "opentenbase-mark.png").is_file():
            errors.append("AgentX requires the official OpenTenBase emblem")
        if any(brand.glob("chuanxu-*")) or (brand / "agentx-wordmark.svg").exists():
            errors.append("AgentX contains a different product's brand mark")
        if (root / "scripts/database_adapters").exists() or (root / "vendor/yaspy").exists():
            errors.append("PG-only product contains an unrelated adapter or native driver")
        if any((root / "scripts" / name).exists() for name in ("deploy_oracle.py", "deploy_yashandb.py", "install_yaspy.sh")):
            errors.append("PG-only product contains unrelated database deployment tools")
    for database in product.databases:
        deploy = root / "scripts/deploy"
        if (deploy / database).is_dir():
            deploy = deploy / database
        files = list(deploy.glob("baseline_v*.json"))
        try:
            baseline = json.loads(files[0].read_text()) if len(files) == 1 else {}
            if baseline.get("database") != database or baseline.get("version") != manifest.get("version"):
                errors.append(f"invalid baseline for {database}")
            if not (deploy / baseline.get("required_terminal_migration", "missing")).is_file():
                errors.append(f"missing terminal migration for {database}")
        except (OSError, ValueError, TypeError):
            errors.append(f"unreadable baseline for {database}")
    for name in ("README.md", "README_zh.md", "SKILL.md", "docs/deployment.md", "docs/deployment_zh.md"):
        if not (root / name).is_file():
            errors.append(f"missing product documentation: {name}")
    errors.extend(verify_manifest(root))
    return errors


def validate_delivery(root: Path, *, selected: tuple[str, ...] = ()) -> list[str]:
    products = tuple(product_for(key) for key in selected) if selected else PRODUCTS
    errors = []
    for product in products:
        package = root / product.package
        if not package.is_dir():
            errors.append(f"missing product: {product.package}")
        else:
            errors.extend(f"{product.key}: {item}" for item in validate_product(package))
    if not selected:
        actual = {path.name for path in root.iterdir() if path.is_dir() and (path / "build-manifest.json").is_file()}
        if actual != {item.package for item in products}:
            errors.append("delivery contains an unexpected product package")
        matrix = root / "acceptance-matrix.json"
        try:
            if json.loads(matrix.read_text()) != list(acceptance_targets()):
                errors.append("acceptance matrix must contain exactly the seven registered targets")
        except (OSError, ValueError):
            errors.append("missing or unreadable acceptance matrix")
    return errors
