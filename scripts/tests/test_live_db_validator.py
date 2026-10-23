"""Static contracts for edition-aware live catalog validation."""

from __future__ import annotations

import importlib

import live_db_validator as validator
import pytest

from live_db_validator import (
    GOVERNANCE_TABLES,
    REGISTRATION_TABLES,
    ProbeResult,
    _catalog_index_is_unique,
)


def test_registration_is_common_but_governance_tables_are_enterprise_only():
    assert REGISTRATION_TABLES == ("AGENT_REGISTRATIONS",)
    assert "AGENT_REGISTRATIONS" not in GOVERNANCE_TABLES
    assert len(GOVERNANCE_TABLES) == 12

    community = ProbeResult(database="pg", connected=True)
    community.governance_tables_required = 0
    assert community.registration_tables_required == 1
    assert community.governance_tables_required == 0

    enterprise = ProbeResult(database="pg", connected=True)
    assert enterprise.registration_tables_required == 1
    assert enterprise.governance_tables_required == 12


def test_catalog_unique_flags_accept_yashandb_and_oracle_forms():
    for value in ("UNIQUE", "Y", "YES", "TRUE", " unique "):
        assert _catalog_index_is_unique(value) is True
    for value in (None, "N", "NO", "FALSE", "NONUNIQUE"):
        assert _catalog_index_is_unique(value) is False


@pytest.mark.parametrize("name", [
    "49_v4_4_8_security_domain_rls.sql",
    "51_v4_4_9_identity_boundary_repair.sql",
    "53_v4_4_9_pg_runtime_boundary.sql",
])
def test_pg_extra_migrations_follow_package_layout(tmp_path, monkeypatch, name):
    monkeypatch.setattr(validator, "REPO_ROOT", tmp_path)
    assert validator._migration_path("pg", name) == tmp_path / "adapters/pg/deploy" / name
    (tmp_path / "build-manifest.json").write_text("{}")
    # Even a missing packaged migration must not fall back to a source tree.
    assert validator._migration_path("pg", name) == tmp_path / "scripts/deploy" / name


def test_v501_live_contract_accepts_v500_network_policy_successor(tmp_path, monkeypatch):
    runner = importlib.import_module("migration_runner")
    names = (
        "102_v5_0_0_network_access.sql", "103_v5_0_1_memory_quality.sql",
        "104_v5_0_1_context_assets.sql", "105_v5_0_1_answer_quality.sql",
    )
    paths = {name: tmp_path / name for name in names}
    for path in paths.values():
        path.write_text("-- test migration\n")
    monkeypatch.setattr(validator, "_migration_path", lambda _db, name: paths[name])
    rows = {
        (names[0], "5.0.0"): {"status": "APPLIED", "checksum": "102-digest"},
        (names[1], "5.0.1"): {"status": "APPLIED", "checksum": "103-digest"},
        (names[2], "5.0.1"): {"status": "APPLIED", "checksum": "104-digest"},
        (names[3], "5.0.1"): {"status": "APPLIED", "checksum": "105-digest"},
    }
    monkeypatch.setattr(runner, "_step_row", lambda _c, _db, path, *, version=None: rows.get((path.name, version)))
    monkeypatch.setattr(runner, "_checksum", lambda path: path.name[:3] + "-digest")
    monkeypatch.setattr(runner, "_step_objects_complete", lambda *_a, **_kw: True)

    result = validator._capture_v501_migrations(object(), "pg", "5.0.1", names)

    assert result["passed"] is True
    assert result["steps"][names[0]]["version"] == "5.0.0"
    assert all(value["passed"] for value in result["steps"].values())


@pytest.mark.parametrize("failure", ["ledger", "checksum", "objects"])
def test_v501_live_contract_blocks_incomplete_migration(tmp_path, monkeypatch, failure):
    runner = importlib.import_module("migration_runner")
    name = "103_v5_0_1_memory_quality.sql"
    path = tmp_path / name
    path.write_text("-- test migration\n")
    monkeypatch.setattr(validator, "_migration_path", lambda _db, _name: path)
    status = "FAILED" if failure == "ledger" else "APPLIED"
    checksum = "wrong" if failure == "checksum" else "103-digest"
    monkeypatch.setattr(runner, "_step_row", lambda *_a, **_kw: {"status": status, "checksum": checksum})
    monkeypatch.setattr(runner, "_checksum", lambda _path: "103-digest")
    monkeypatch.setattr(runner, "_step_objects_complete", lambda *_a, **_kw: failure != "objects")

    result = validator._capture_v501_migrations(object(), "pg", "5.0.1", (name,))

    assert result["passed"] is False
    assert result["steps"][name]["passed"] is False
