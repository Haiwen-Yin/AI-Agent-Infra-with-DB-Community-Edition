"""Product knowledge preserves user edits and publishes one atomic snapshot."""
import hashlib
import json
import sqlite3
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
    tx.query.side_effect = lambda sql, *_: [] if "CX_PLATFORM_KNOWLEDGE" in sql else [
        {"entity_id": 10, "title": "Historical product guide", "content": "original"},
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


@pytest.fixture
def lifecycle(publication, monkeypatch):
    root, _, _ = publication
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.executescript("""
        CREATE TABLE CX_PLATFORM_KNOWLEDGE (
            KNOWLEDGE_ID TEXT PRIMARY KEY, KNOWLEDGE_KEY TEXT, VERSION INTEGER,
            KNOWLEDGE_KIND TEXT, AUDIENCE TEXT, SCOPE_TYPE TEXT, CLASSIFICATION TEXT,
            CONTENT_JSON TEXT, CONTENT_DIGEST TEXT, SIGNATURE TEXT, SIGNATURE_STATUS TEXT,
            STATUS TEXT, VALID_FROM TEXT, CREATED_BY TEXT);
        CREATE TABLE CX_PLATFORM_KNOWLEDGE_CHUNKS (
            CHUNK_ID TEXT PRIMARY KEY, KNOWLEDGE_ID TEXT, CHUNK_NO INTEGER, CHUNK_TEXT TEXT,
            CHUNK_DIGEST TEXT, AUDIENCE TEXT, SCOPE_TYPE TEXT, CLASSIFICATION TEXT, STATUS TEXT);
        CREATE TABLE ENTITIES (
            ENTITY_ID TEXT PRIMARY KEY, ENTITY_TYPE TEXT, TITLE TEXT, CONTENT TEXT,
            SUMMARY TEXT, CATEGORY TEXT, IMPORTANCE INTEGER, STATUS TEXT, VISIBILITY TEXT,
            UPDATED_AT TEXT);
        CREATE TABLE KNOWLEDGE_META (
            ENTITY_ID TEXT PRIMARY KEY, ENTITY_TYPE TEXT, DOMAIN TEXT, TOPIC TEXT, DIFFICULTY TEXT);
    """)
    class Transaction:
        def execute(self, sql, params):
            return db.execute(sql.replace(" FOR UPDATE", "").replace("OVERRIDING SYSTEM VALUE ", ""), params)

        def query(self, sql, params):
            return [dict(row) for row in self.execute(sql, params).fetchall()]

        def query_one(self, sql, params):
            rows = self.query(sql, params)
            return rows[0] if rows else None

    def transaction(callback):
        with db:
            return callback(Transaction())
    monkeypatch.setattr(knowledge.connection, "execute_transaction_callback", transaction)
    catalog = root / "scripts/resources/legacy-product-knowledge.json"
    catalog.write_text(json.dumps({database: [] for database in ("pg", "oracle", "yashandb")}))
    yield root, db
    db.close()


@pytest.mark.parametrize("database,product_key,edition", [
    ("pg", "unified-community", "Community"),
    ("oracle", "unified-community", "Community"),
    ("yashandb", "unified-community", "Community"),
    ("pg", "agentx-community", "Community"),
    ("pg", "pg-enterprise", "Enterprise"),
    ("oracle", "oracle-enterprise", "Enterprise"),
    ("yashandb", "yashandb-enterprise", "Enterprise"),
])
def test_upgrade_replaces_active_projections_and_preserves_history(lifecycle, monkeypatch, database, product_key, edition):
    root, db = lifecycle
    product = dict(product_key=product_key, name_zh="Product", name_en="Product",
                   version="5.0.0", edition=edition, databases=[database])
    monkeypatch.setattr(knowledge.product_identity, "identity", lambda *_: dict(product))
    old = knowledge.publish("admin", database, root)
    snapshots = db.execute("SELECT CONTENT_JSON,CONTENT_DIGEST FROM CX_PLATFORM_KNOWLEDGE").fetchall()
    old_entities = [tuple(row) for row in db.execute("SELECT ENTITY_ID,TITLE,CONTENT FROM ENTITIES ORDER BY ENTITY_ID")]
    product["version"] = "5.0.1"
    current = knowledge.publish("admin", database, root)
    assert set(current["superseded"]) == set(old["knowledge_ids"])
    active = db.execute("SELECT ENTITY_ID,TITLE FROM ENTITIES WHERE STATUS='ACTIVE'").fetchall()
    assert {row["ENTITY_ID"] for row in active} == set(current["knowledge_ids"])
    assert all("v5.0.1" in row["TITLE"] for row in active)
    assert [tuple(row) for row in db.execute("SELECT ENTITY_ID,TITLE,CONTENT FROM ENTITIES WHERE STATUS='ARCHIVED' ORDER BY ENTITY_ID")] == old_entities
    assert db.execute("SELECT CONTENT_JSON,CONTENT_DIGEST FROM CX_PLATFORM_KNOWLEDGE WHERE VERSION=5000000").fetchall() == snapshots
    assert knowledge.publish("admin", database, root)["superseded"] == []
    assert db.execute("SELECT COUNT(*) FROM ENTITIES").fetchone()[0] == 8


@pytest.mark.parametrize("field,value", [("CONTENT", "user edited"), ("TITLE", "user title"),
    ("SUMMARY", "user summary"), ("VISIBILITY", "PRIVATE"), ("CATEGORY", "CUSTOM")])
def test_upgrade_preserves_modified_previous_projection(lifecycle, monkeypatch, field, value):
    root, db = lifecycle
    product = dict(product_key="agentx-community", name_zh="AgentX", name_en="AgentX",
                   version="5.0.0", edition="Community", databases=["pg"])
    monkeypatch.setattr(knowledge.product_identity, "identity", lambda *_: dict(product))
    old = knowledge.publish("admin", "pg", root)
    selected = old["knowledge_ids"][0]
    db.execute(f"UPDATE ENTITIES SET {field}=? WHERE ENTITY_ID=?", (value, selected))
    db.commit()
    product["version"] = "5.0.1"
    result = knowledge.publish("admin", "pg", root)
    assert result["preserved_modified_product"] == [selected]
    assert len(result["superseded"]) == 3
    assert db.execute("SELECT STATUS FROM ENTITIES WHERE ENTITY_ID=?", (selected,)).fetchone()[0] == "ACTIVE"


def test_invalid_history_rolls_back_new_publication(lifecycle, monkeypatch):
    root, db = lifecycle
    product = dict(product_key="agentx-community", name_zh="AgentX", name_en="AgentX",
                   version="5.0.0", edition="Community", databases=["pg"])
    monkeypatch.setattr(knowledge.product_identity, "identity", lambda *_: dict(product))
    knowledge.publish("admin", "pg", root)
    db.execute("UPDATE CX_PLATFORM_KNOWLEDGE SET CONTENT_DIGEST='tampered'")
    db.commit()
    product["version"] = "5.0.1"
    with pytest.raises(ValueError, match="verification failed"):
        knowledge.publish("admin", "pg", root)
    assert db.execute("SELECT COUNT(*) FROM CX_PLATFORM_KNOWLEDGE").fetchone()[0] == 1
    assert db.execute("SELECT COUNT(*) FROM ENTITIES WHERE STATUS='ACTIVE'").fetchone()[0] == 4


def test_entity_conflict_rolls_back_old_projection_retirement(lifecycle, monkeypatch):
    root, db = lifecycle
    product = dict(product_key="agentx-community", name_zh="AgentX", name_en="AgentX",
                   version="5.0.0", edition="Community", databases=["pg"])
    monkeypatch.setattr(knowledge.product_identity, "identity", lambda *_: dict(product))
    knowledge.publish("admin", "pg", root)
    product["version"] = "5.0.1"
    key = knowledge._entity_key(product, "pg", "overview")
    db.execute("INSERT INTO ENTITIES(ENTITY_ID,ENTITY_TYPE,TITLE,CONTENT) VALUES(?,'KNOWLEDGE','user','user')", (key,))
    db.commit()
    with pytest.raises(ValueError, match="immutable"):
        knowledge.publish("admin", "pg", root)
    assert db.execute("SELECT COUNT(*) FROM ENTITIES WHERE STATUS='ARCHIVED'").fetchone()[0] == 0
    assert db.execute("SELECT COUNT(*) FROM CX_PLATFORM_KNOWLEDGE").fetchone()[0] == 1
