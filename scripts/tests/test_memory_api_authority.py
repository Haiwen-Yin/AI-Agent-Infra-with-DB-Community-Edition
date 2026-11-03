"""Visualization and compatibility memory reads fail closed at the reader."""

import pytest

from lib import memory_api, memory_lifecycle


def test_principal_scoped_search_drops_denied_and_unlineaged_rows(monkeypatch):
    rows = [
        dict(family_id="MF-allowed", version_id="MV-allowed", content_digest="a", lifecycle_state="ACTIVE",
             security_domain_id="domain", owner_principal_id="owner", classification="INTERNAL"),
        dict(family_id="MF-denied", version_id="MV-denied", content_digest="b", lifecycle_state="ACTIVE",
             security_domain_id="domain", owner_principal_id="owner", classification="INTERNAL"),
    ]
    monkeypatch.setattr(memory_lifecycle, "current_memories", lambda **_: rows)
    monkeypatch.setattr(memory_lifecycle, "_require_memory_access",
                        lambda principal, value, **_: (_ for _ in ()).throw(PermissionError("denied"))
                        if value["version_id"] == "MV-denied" else None)
    monkeypatch.setattr(memory_api.connection, "execute_transaction_callback",
                        lambda callback: callback(object()))
    monkeypatch.setattr(memory_api, "require_memory_original_sources", lambda *args: None, raising=False)
    # The origin helper is imported inside search_memories; replace its module
    # implementation so this test remains a reader-contract check.
    import lib.continuity_promotions as promotions
    monkeypatch.setattr(promotions, "require_memory_original_sources", lambda *args: None)
    result = memory_api.search_memories(principal_id="reader", limit=10)
    assert [item["version_id"] for item in result] == ["MV-allowed"]


def test_principal_scoped_search_does_not_fallback_to_legacy_rows(monkeypatch):
    monkeypatch.setattr(memory_lifecycle, "current_memories",
                        lambda **_: (_ for _ in ()).throw(RuntimeError("projection unavailable")))
    monkeypatch.setattr(memory_api, "execute_query", lambda *args, **kwargs: pytest.fail("legacy fallback leaked"))
    with pytest.raises(PermissionError, match="projection"):
        memory_api.search_memories(principal_id="reader")
