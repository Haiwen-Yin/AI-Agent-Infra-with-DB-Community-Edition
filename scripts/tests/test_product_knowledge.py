"""Product knowledge preserves user edits and publishes one atomic snapshot."""
import hashlib
import json
from unittest.mock import Mock

import pytest
from lib import product_knowledge as knowledge


@pytest.fixture
def publication(monkeypatch, tmp_path):
    product = {"product_key": "agentx-community", "name_zh": "OpenTenBase AgentX", "name_en": "OpenTenBase AgentX",
               "version": "5.0.0", "edition": "Community", "databases": ["pg"]}
    monkeypatch.setattr(knowledge.product_identity, "identity", lambda *_: product)
    monkeypatch.setattr(knowledge.identity_api, "effective_access", lambda *_: {"decision": "ALLOW"})
    monkeypatch.setattr(knowledge.identity_api, "_audit_tx", Mock())
    catalog = tmp_path / "scripts/resources/legacy-product-knowledge.json"
    catalog.parent.mkdir(parents=True)
    catalog.write_text(json.dumps({"pg": [{"title": "Historical product guide", "hashes": [hashlib.sha256(b"original").hexdigest()]}]}))
    tx = Mock(query_one=Mock(return_value=None), query=Mock(return_value=[]), execute=Mock(return_value=1))
    runner = Mock(side_effect=lambda callback: callback(tx))
    monkeypatch.setattr(knowledge.connection, "execute_transaction_callback", runner)
    return tmp_path, tx, runner


def test_legacy_user_edit_is_preserved_and_original_superseded(publication):
    root, tx, runner = publication
    tx.query.return_value = [{"entity_id": 10, "title": "Historical product guide", "content": "original"},
                             {"entity_id": 11, "title": "Historical product guide", "content": "user revised"}]
    result = knowledge.publish("admin", "pg", root)
    assert result["superseded"] == ["10"]
    assert result["preserved_modified_legacy"] == ["11"]
    assert len(result["knowledge_ids"]) == 4
    assert all((1 << 52) <= int(key) < (1 << 53) for key in result["knowledge_ids"])
    runner.assert_called_once()
    updates = [call.args[1]["id"] for call in tx.execute.call_args_list if "UPDATE ENTITIES SET STATUS='ARCHIVED'" in call.args[0]]
    assert updates == [10]


def test_entity_failure_propagates_through_same_snapshot_transaction(publication):
    root, tx, runner = publication
    def insert(sql, *_):
        if "INSERT INTO ENTITIES(" in sql:
            raise RuntimeError("injected entity write failure")
        return 1
    tx.execute.side_effect = insert
    with pytest.raises(RuntimeError, match="injected entity write failure"):
        knowledge.publish("admin", "pg", root)
    runner.assert_called_once()
    assert any("INSERT INTO CX_PLATFORM_KNOWLEDGE(" in call.args[0] for call in tx.execute.call_args_list)
    # The exception reaches the owning transaction, allowing the DB adapter to
    # roll back the snapshot/chunks, retirement and public entities together.


def test_existing_entity_cannot_be_silently_overwritten(publication):
    root, tx, _ = publication
    def existing(sql, *_):
        return {"title": "user change", "content": "user change"} if "FROM ENTITIES" in sql else None
    tx.query_one.side_effect = existing
    with pytest.raises(ValueError, match="immutable"):
        knowledge.publish("admin", "pg", root)


def test_unauthorized_publication_does_not_open_transaction(publication, monkeypatch):
    root, _, runner = publication
    monkeypatch.setattr(knowledge.identity_api, "effective_access", lambda *_: {"decision": "DENY"})
    with pytest.raises(PermissionError):
        knowledge.publish("visitor", "pg", root)
    runner.assert_not_called()
