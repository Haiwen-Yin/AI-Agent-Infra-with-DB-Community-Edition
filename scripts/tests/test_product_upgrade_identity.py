"""Upgrade identity preserves product, license and selected native backend."""
import json
import pytest
from lib.product_identity import check_release_compatibility, release_product
from product_delivery import PRODUCTS, product_for


def manifest(key, version="5.0.0"):
    product = product_for(key)
    return {"schema": "ai-agent-infra-build/v1", "version": version,
            "edition": product.edition, "license": product.license,
            "delivery_product": json.loads(json.dumps(product.manifest())),
            "database": {"key": "selectable" if len(product.databases) > 1 else product.databases[0]}}


@pytest.mark.parametrize("product", PRODUCTS, ids=lambda product: product.key)
def test_same_product_upgrade_covers_exact_supported_databases(product):
    archive, installed = manifest(product.key, "5.0.1"), manifest(product.key)
    for database in product.databases:
        result = check_release_compatibility(archive, database=database, edition=product.edition, current=installed)
        assert result["product_key"] == product.key
    for database in {"oracle", "pg", "yashandb"} - set(product.databases):
        with pytest.raises(ValueError, match="database"):
            check_release_compatibility(archive, database=database, current=installed)


@pytest.mark.parametrize("installed,incoming", [("agentx-community", "unified-community"),
    ("unified-community", "agentx-community"), ("pg-enterprise", "agentx-community"),
    ("agentx-community", "pg-enterprise")])
def test_matching_pg_backend_does_not_authorize_cross_product_or_edition(installed, incoming):
    with pytest.raises(ValueError, match="product|edition"):
        check_release_compatibility(manifest(incoming), database="pg", current=manifest(installed))


@pytest.mark.parametrize("database", ["oracle", "pg", "yashandb"])
def test_previous_chuanxu_community_upgrades_to_unified_product(database):
    installed = {"version": "4.5.2", "edition": "Community", "database": {"key": database}}
    assert check_release_compatibility(manifest("unified-community"), database=database,
        edition="Community", current=installed)["product_key"] == "unified-community"
    with pytest.raises(ValueError):
        check_release_compatibility(manifest("agentx-community"), database=database, current=installed)


@pytest.mark.parametrize("change", ["database", "license", "databases", "missing", "unknown"])
def test_product_label_cannot_expand_a_signed_payload_contract(change):
    archive = manifest("agentx-community")
    if change == "database":
        archive["database"]["key"] = "oracle"
    elif change == "license":
        archive["license"] = "BSL-1.1"
    elif change == "databases":
        archive["delivery_product"]["databases"].append("oracle")
    elif change == "missing":
        del archive["delivery_product"]
    else:
        archive["delivery_product"]["key"] = "other-product"
    with pytest.raises(ValueError):
        release_product(archive)
