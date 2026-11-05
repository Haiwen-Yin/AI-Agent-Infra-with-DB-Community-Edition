"""Opt-in mutation scope: validate a classified current local database target."""
import json
import os
from pathlib import Path
from ipaddress import ip_address


def _expected_target(facts, version, product):
    short = "com" if facts["edition"] == "community" else "ent"
    if version == "5.0.2":
        track = facts.get("track")
        assert track in {"fresh", "upgrade"}, "Unclassified acceptance track"
        assert facts.get("schema") == "chuanxu-isolated-acceptance/v2"
        generation = facts.get("acceptance_generation", "original")
        assert generation in {"original", "exact-r1", "exact-r2", "exact-r3", "exact-r4", "exact-r5"}, "Unclassified acceptance generation"
        agentx = product == "agentx-community"
        prefixes = {"original": {"fresh": ("cxv50201", "cxv50202"), "upgrade": ("cxv50203", "cxv50204")},
                    "exact-r1": {"fresh": ("cxv50205", "cxv50206"), "upgrade": ("cxv50207", "cxv50208")},
                    "exact-r2": {"fresh": ("cxv50209", "cxv50210"), "upgrade": ("cxv50211", "cxv50212")},
                    "exact-r3": {"fresh": ("cxv50213", "cxv50214"), "upgrade": ("cxv50215", "cxv50216")},
                    "exact-r4": {"fresh": ("cxv50217", "cxv50218"), "upgrade": ("cxv50219", "cxv50220")},
                    "exact-r5": {"fresh": ("cxv50221", "cxv50222"), "upgrade": ("cxv50223", "cxv50224")}}
        prefix = prefixes[generation][track][agentx]
        return prefix + short
    if version == "5.0.1":
        track = facts.get("track")
        assert track in {"fresh", "upgrade"}, "Unclassified acceptance track"
        assert facts.get("schema") == "chuanxu-isolated-acceptance/v1"
        agentx = product == "agentx-community"
        prefix = ("cxv5013" if agentx else "cxv5012") if track == "upgrade" else ("cxv5011" if agentx else "cxv501")
        return prefix + short
    return ("cxv5042" if product == "agentx-community" else "cxv" + version.replace(".", "")) + short


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
    version = manifest.get("version")
    assert version in {"5.0.0", "5.0.1", "5.0.2"}, "unreviewed release test version"
    assert facts.get("classification") == "temporary" and facts.get("version") == version
    assert facts.get("connection") == "direct-root-ssh"
    for key in ("database", "product", "package"):
        assert facts[key] == supported[key]
    assert facts["edition"] == supported["edition"].lower()
    database = facts["database"]
    expected = _expected_target(facts, version, product)
    assert facts["target"] == expected
    if version == "5.0.2" and facts.get("acceptance_generation") in {"exact-r1", "exact-r2", "exact-r3", "exact-r4", "exact-r5"}:
        classification = Path(path).absolute()
        generation = facts["acceptance_generation"]
        suffix = ("runtime", "v5.0.2-acceptance", "generations", generation, facts["track"], facts["key"])
        assert classification.parent.parts[-len(suffix):] == suffix, "Wrong exact generation state directory"
        assert facts.get("acceptance_state") == str(classification.parent), "Wrong exact generation state binding"
        index = next(index for index, item in enumerate(acceptance_targets()) if item["key"] == facts["key"])
        assert facts.get("service_port") == {"exact-r1": 19640, "exact-r2": 19680, "exact-r3": 19720, "exact-r4": 19760, "exact-r5": 19840}[generation] + (20 if facts["track"] == "upgrade" else 0) + index
    cfg = get_config().database
    host = os.environ.get("CX_RELEASE_TEST_HOST", "")
    assert host and host == facts["host"], "The validating harness must bind the authorized host"
    if version in {"5.0.1", "5.0.2"}:
        # The external harness validates its private host allowlist before
        # starting pytest. Bind that exact host to the classification and
        # runtime config; private infrastructure literals are sanitized when
        # packages are built and therefore cannot be shipped as comparisons.
        assert ip_address(host).version == 4, "The validating harness must bind an IPv4 host"
        owner = expected + "owner" if database == "pg" else ("AIADMIN" if database == "oracle" else "CX_AGENT_OWNER")
        assert facts.get("owner") == owner and cfg.user.upper() == owner.upper()
    if database == "pg":
        assert cfg.host == host and int(cfg.port) == 5433
        assert cfg.dbname.lower() == expected
    else:
        assert cfg.dsn.lower() == host + (":1521/" if database == "oracle" else ":1688/") + expected
    return True
