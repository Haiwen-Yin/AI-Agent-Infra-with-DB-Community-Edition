"""Package mutation gates bind the exact isolated release/track/database owner."""
import json
from types import SimpleNamespace

import pytest

from product_delivery import acceptance_targets
from . import release_target


def fixture_scope(tmp_path, monkeypatch, item, track="fresh", generation="original"):
    from lib import config, product_identity
    prefixes = {"original": {"fresh": ("cxv50201", "cxv50202"), "upgrade": ("cxv50203", "cxv50204")},
                "exact-r1": {"fresh": ("cxv50205", "cxv50206"), "upgrade": ("cxv50207", "cxv50208")},
                "exact-r2": {"fresh": ("cxv50209", "cxv50210"), "upgrade": ("cxv50211", "cxv50212")},
                "exact-r3": {"fresh": ("cxv50213", "cxv50214"), "upgrade": ("cxv50215", "cxv50216")},
                "exact-r4": {"fresh": ("cxv50217", "cxv50218"), "upgrade": ("cxv50219", "cxv50220")},
                "exact-r5": {"fresh": ("cxv50221", "cxv50222"), "upgrade": ("cxv50223", "cxv50224")}}
    prefix = prefixes[generation][track][item["product"] == "agentx-community"]
    name = prefix + ("com" if item["edition"] == "Community" else "ent")
    owner = name + "owner" if item["database"] == "pg" else ("AIADMIN" if item["database"] == "oracle" else "CX_AGENT_OWNER")
    host = "203.0.113.17"
    facts = dict(item, edition=item["edition"].lower(), schema="chuanxu-isolated-acceptance/v2",
                 version="5.0.2", classification="temporary", connection="direct-root-ssh",
                 track=track, target=name, owner=owner, host=host)
    cfg = SimpleNamespace(user=owner, host=host, port=5433, dbname=name,
                          dsn=host + (":1521/" if item["database"] == "oracle" else ":1688/") + name)
    manifest = dict(version="5.0.2", delivery_product=dict(key=item["product"]))
    path = tmp_path / "classification.json"
    if generation != "original":
        state = tmp_path / "runtime/v5.0.2-acceptance/generations" / generation / track / item["key"]
        state.mkdir(parents=True)
        path = state / "classification.json"
        index = next(index for index, target in enumerate(acceptance_targets()) if target["key"] == item["key"])
        facts.update(acceptance_generation=generation, acceptance_state=str(state),
                     service_port={"exact-r1":19640, "exact-r2":19680, "exact-r3":19720, "exact-r4":19760, "exact-r5":19840}[generation] + (20 if track == "upgrade" else 0) + index)
    monkeypatch.setenv("CX_RELEASE_TEST_CLASSIFICATION", str(path))
    monkeypatch.setenv("CX_RELEASE_TEST_HOST", host)
    monkeypatch.setattr(config, "get_config", lambda: SimpleNamespace(database=cfg))
    monkeypatch.setattr(product_identity, "read_manifest", lambda: manifest)
    return path, facts, cfg, manifest


@pytest.mark.parametrize("item", acceptance_targets(), ids=lambda value: value["key"])
@pytest.mark.parametrize("track", ["fresh", "upgrade"])
@pytest.mark.parametrize("generation", ["original", "exact-r1", "exact-r2", "exact-r3", "exact-r4", "exact-r5"])
def test_all_seven_targets_and_both_tracks_are_exact(tmp_path, monkeypatch, item, track, generation):
    path, facts, _, _ = fixture_scope(tmp_path, monkeypatch, item, track, generation)
    path.write_text(json.dumps(facts))
    assert release_target.classified_current_target()


@pytest.mark.parametrize("key,value", [
    ("schema", "chuanxu-isolated-acceptance/v1"), ("track", "baseline"),
    ("target", "cxv502com"), ("target", "cxv50203com"), ("target", "protected_test"),
    ("version", "5.0.1"), ("classification", "baseline"), ("connection", "direct"),
    ("owner", "postgres"), ("database", "oracle"), ("product", "agentx-community"),
    ("host", "203.0.113.18"),
])
@pytest.mark.parametrize("generation", ["original", "exact-r4", "exact-r5"])
def test_wrong_classification_never_opens_mutation_scope(tmp_path, monkeypatch, key, value, generation):
    item = next(value for value in acceptance_targets() if value["key"] == "unified-community-pg")
    path, facts, _, _ = fixture_scope(tmp_path, monkeypatch, item, generation=generation)
    facts[key] = value
    path.write_text(json.dumps(facts))
    with pytest.raises(AssertionError):
        release_target.classified_current_target()


@pytest.mark.parametrize("attribute,value", [("user", "postgres"), ("host", "203.0.113.18"), ("port", 5432), ("dbname", "cxv50203com")])
@pytest.mark.parametrize("generation", ["original", "exact-r4", "exact-r5"])
def test_runtime_config_must_match_the_classified_database(tmp_path, monkeypatch, attribute, value, generation):
    item = next(value for value in acceptance_targets() if value["key"] == "unified-community-pg")
    path, facts, cfg, _ = fixture_scope(tmp_path, monkeypatch, item, generation=generation)
    setattr(cfg, attribute, value)
    path.write_text(json.dumps(facts))
    with pytest.raises(AssertionError):
        release_target.classified_current_target()


def test_no_opt_in_and_future_versions_remain_closed(tmp_path, monkeypatch):
    monkeypatch.delenv("CX_RELEASE_TEST_CLASSIFICATION", raising=False)
    assert release_target.classified_current_target() is False
    path, facts, _, manifest = fixture_scope(tmp_path, monkeypatch, acceptance_targets()[0])
    manifest["version"] = facts["version"] = "5.0.3"
    path.write_text(json.dumps(facts))
    with pytest.raises(AssertionError, match="unreviewed release"):
        release_target.classified_current_target()


@pytest.mark.parametrize("field,value", [("acceptance_generation", "original"), ("acceptance_generation", "exact-r2"),
    ("target", "cxv50201com"), ("acceptance_state", "/unrelated"), ("service_port", 19601), ("track", "upgrade")])
@pytest.mark.parametrize("generation", ["exact-r1", "exact-r2", "exact-r3", "exact-r4", "exact-r5"])
def test_exact_generation_rejects_mixed_bindings(tmp_path, monkeypatch, field, value, generation):
    item = next(item for item in acceptance_targets() if item["key"] == "unified-community-pg")
    path, facts, _, _ = fixture_scope(tmp_path, monkeypatch, item, generation=generation)
    facts[field] = "exact-r1" if field == "acceptance_generation" and value == generation else value
    path.write_text(json.dumps(facts))
    with pytest.raises(AssertionError): release_target.classified_current_target()


@pytest.mark.parametrize("generation", ["exact-r1", "exact-r2", "exact-r3", "exact-r4", "exact-r5"])
def test_exact_generation_rejects_classification_from_old_state_tree(tmp_path, monkeypatch, generation):
    path, facts, _, _ = fixture_scope(tmp_path, monkeypatch, acceptance_targets()[0], generation=generation)
    moved = tmp_path / "old-classification.json"
    moved.write_text(json.dumps(facts))
    monkeypatch.setenv("CX_RELEASE_TEST_CLASSIFICATION", str(moved))
    with pytest.raises(AssertionError, match="state directory"): release_target.classified_current_target()


@pytest.mark.parametrize("generation", ["exact-r6", "../exact-r4", "EXACT-R4", "", None])
def test_unenumerated_generation_is_refused_before_runtime_configuration(tmp_path, monkeypatch, generation):
    from lib import config
    item = next(item for item in acceptance_targets() if item["key"] == "pg-enterprise-pg")
    path, facts, _, _ = fixture_scope(tmp_path, monkeypatch, item, generation="exact-r4")
    facts["acceptance_generation"] = generation
    path.write_text(json.dumps(facts))
    monkeypatch.setattr(config, "get_config", lambda: pytest.fail("A rejected generation cannot reach runtime configuration"))
    with pytest.raises(AssertionError, match="Unclassified acceptance generation"):
        release_target.classified_current_target()


@pytest.mark.parametrize("field,value", [
    ("target", "cxv50213ent"), ("target", "cxv50215ent"), ("target", "cxv50219ent"),
    ("target", "cxv50218ent"), ("track", "baseline"), ("track", "upgrade"),
    ("product", "agentx-community"), ("key", "agentx-community-pg"), ("edition", "community"),
    ("service_port", 19725), ("service_port", 19785), ("service_port", 19764),
    ("service_port", "19765"), ("acceptance_generation", "exact-r3"),
])
def test_exact_r4_enterprise_cannot_adopt_other_target_track_product_generation_or_port(tmp_path, monkeypatch, field, value):
    item = next(item for item in acceptance_targets() if item["key"] == "pg-enterprise-pg")
    path, facts, _, _ = fixture_scope(tmp_path, monkeypatch, item, generation="exact-r4")
    facts[field] = value
    path.write_text(json.dumps(facts))
    with pytest.raises(AssertionError):
        release_target.classified_current_target()
