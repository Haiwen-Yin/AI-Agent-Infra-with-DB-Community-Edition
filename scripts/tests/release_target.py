"""Opt-in mutation scope: validate a classified current local database target."""
import json
import os
from pathlib import Path


def classified_current_target() -> bool:
    path = os.environ.get("CX_RELEASE_TEST_CLASSIFICATION", "")
    if not path:
        return False
    from lib.config import get_config
    from lib.product_identity import read_manifest
    from product_delivery import acceptance_targets
    facts = json.loads(Path(path).read_text())
    manifest = read_manifest()
    product = manifest.get("delivery_product", {}).get("key")
    supported = next((item for item in acceptance_targets() if item["product"] == product
                      and item["key"] == facts.get("key")), None)
    assert supported is not None, "unclassified product or test target"
    assert facts.get("classification") == "temporary" and facts.get("version") == manifest.get("version") == "5.0.0"
    assert facts.get("connection") == "direct-root-ssh"
    for key in ("database", "product", "package"):
        assert facts[key] == supported[key]
    assert facts["edition"] == supported["edition"].lower()
    database = facts["database"]
    expected = ("cxv5002" if product == "agentx-community" else "cxv500") + ("com" if facts["edition"] == "community" else "ent")
    assert facts["target"] == expected
    cfg = get_config().database
    host = os.environ.get("CX_RELEASE_TEST_HOST", "")
    assert host and host == facts["host"], "The validating harness must bind the authorized host"
    if database == "pg":
        assert cfg.host == host and int(cfg.port) == 5433
        assert cfg.dbname.lower() == expected
    else:
        assert cfg.dsn.lower() == host + (":1521/" if database == "oracle" else ":1688/") + expected
    return True
