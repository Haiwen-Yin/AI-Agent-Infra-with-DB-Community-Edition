"""Atomic usage/details/quota tests using a relational unit fixture."""
import sqlite3
import time

import pytest

from lib import edition_features, model_usage_api as usage, model_governance_api as governance
from lib.model_endpoint_schema import schema_statements
from .test_v502_model_capacity import Transaction


@pytest.fixture
def ledger(monkeypatch):
    db = sqlite3.connect(":memory:")
    db.row_factory = lambda cursor, values: {col[0].lower(): value for col, value in zip(cursor.description, values)}
    db.execute("PRAGMA foreign_keys=ON")
    db.executescript("""
        CREATE TABLE CX_MODEL_REQUESTS(REQUEST_ID TEXT PRIMARY KEY,ACTOR_PRINCIPAL_ID TEXT,AGENT_ID TEXT);
        CREATE TABLE CX_MODEL_USAGE(USAGE_ID TEXT PRIMARY KEY,REQUEST_ID TEXT UNIQUE REFERENCES CX_MODEL_REQUESTS(REQUEST_ID),
            ACTOR_PRINCIPAL_ID TEXT,AGENT_ID TEXT,PROVIDER_KEY TEXT,MODEL_ID TEXT,PROMPT_TOKENS INTEGER,COMPLETION_TOKENS INTEGER,
            CACHED_TOKENS INTEGER,REASONING_TOKENS INTEGER,TOTAL_TOKENS INTEGER,USAGE_PROVENANCE TEXT,COST TEXT,CURRENCY TEXT,
            PRICING_VERSION TEXT,STATUS TEXT,LATENCY_MS INTEGER,IDEMPOTENCY_KEY TEXT);
        CREATE TABLE CX_MODEL_QUOTA_POLICIES(POLICY_ID TEXT PRIMARY KEY,METRIC TEXT,CURRENCY TEXT,INCOMPLETE_POLICY TEXT);
        CREATE TABLE CX_MODEL_QUOTA_RESERVATIONS(RESERVATION_ID TEXT PRIMARY KEY,REQUEST_ID TEXT,POLICY_ID TEXT,
            RESERVED_VALUE TEXT,STATUS TEXT,SETTLED_VALUE TEXT,UPDATED_AT TIMESTAMP);
        INSERT INTO CX_MODEL_REQUESTS VALUES('request','owner','agent');
        INSERT INTO CX_MODEL_QUOTA_POLICIES VALUES('tokens','TOKEN',NULL,'CHARGE_RESERVED'),('cost','COST','CNY','CHARGE_RESERVED');
        INSERT INTO CX_MODEL_QUOTA_RESERVATIONS VALUES('token-reservation','request','tokens','1000','RESERVED',NULL,NULL);
        INSERT INTO CX_MODEL_QUOTA_RESERVATIONS VALUES('cost-reservation','request','cost','2','RESERVED',NULL,NULL);
    """)
    db.execute(schema_statements("pg")[-1])
    db.commit()
    def transaction(callback):
        db.execute("BEGIN IMMEDIATE")
        try:
            value = callback(Transaction(db))
            db.commit()
            return value
        except BaseException:
            db.rollback()
            raise
    monkeypatch.setattr(usage.connection, "execute_transaction_callback", transaction)
    monkeypatch.setattr(edition_features, "MODEL_RUNTIME_CONTEXT_ENABLED", True)
    monkeypatch.setattr(usage, "_price", lambda *args: {"cost": "0.01", "currency": "CNY", "pricing_version": "price1"})
    yield db
    db.close()


def write(counts=None, **kwargs):
    return usage._write_usage("request", "owner", "agent", "provider", "model",
        counts if counts is not None else {"prompt_tokens": 10, "completion_tokens": 4, "total_tokens": 14, "cache_write_tokens": 2},
        "PROVIDER_REPORTED", time.monotonic(), "SUCCEEDED", **kwargs)


def test_usage_detail_and_quota_commit_once_for_exact_request(ledger):
    first = write()
    repeated = write()
    assert repeated == first
    assert first["cache_write_tokens"] == 2 and first["detail_provenance"] == "PROVIDER_REPORTED"
    assert ledger.execute("SELECT COUNT(*) AS n FROM CX_MODEL_USAGE").fetchone()["n"] == 1
    assert ledger.execute("SELECT COUNT(*) AS n FROM CX_MODEL_USAGE_DETAILS").fetchone()["n"] == 1
    reservations = ledger.execute("SELECT STATUS,SETTLED_VALUE FROM CX_MODEL_QUOTA_RESERVATIONS ORDER BY RESERVATION_ID").fetchall()
    assert reservations == [{"status": "SETTLED", "settled_value": "0.010000"}, {"status": "SETTLED", "settled_value": "14.000000"}]


def test_different_observation_for_same_request_cannot_double_settle(ledger):
    first = write()
    with pytest.raises(usage.ModelUsageConflict):
        write({"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15})
    assert ledger.execute("SELECT TOTAL_TOKENS FROM CX_MODEL_USAGE").fetchone()["total_tokens"] == first["total_tokens"]


def test_details_and_usage_roll_back_when_quota_settlement_fails(ledger, monkeypatch):
    original = governance.settle_quota
    def fail(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("Quota audit failure after update")
    monkeypatch.setattr(governance, "settle_quota", fail)
    with pytest.raises(RuntimeError):
        write()
    assert ledger.execute("SELECT COUNT(*) AS n FROM CX_MODEL_USAGE").fetchone()["n"] == 0
    assert ledger.execute("SELECT COUNT(*) AS n FROM CX_MODEL_USAGE_DETAILS").fetchone()["n"] == 0
    assert all(row["status"] == "RESERVED" for row in ledger.execute("SELECT STATUS FROM CX_MODEL_QUOTA_RESERVATIONS"))


def test_usage_cannot_be_attributed_to_another_requester(ledger):
    ledger.execute("UPDATE CX_MODEL_REQUESTS SET ACTOR_PRINCIPAL_ID='other'")
    ledger.commit()
    with pytest.raises(PermissionError):
        write()
    assert ledger.execute("SELECT COUNT(*) AS n FROM CX_MODEL_USAGE").fetchone()["n"] == 0


def test_derived_total_and_partial_unknown_remain_distinct(ledger):
    result = write({"prompt_tokens": 10, "completion_tokens": 4}, field_provenance={"total_tokens": "SUM_OF_REPORTED_INPUT_OUTPUT"})
    assert result["total_tokens"] == 14 and result["detail_provenance"] == "DERIVED_TOTAL"


@pytest.mark.parametrize("counts,provenance,total", [({}, "INCOMPLETE", None), ({"prompt_tokens": 0}, "PARTIAL", None),
                                                     ({"total_tokens": 12}, "PARTIAL", 12),
                                                     ({"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}, "PROVIDER_REPORTED", 0)])
def test_missing_counts_are_never_settled_as_zero(ledger, counts, provenance, total):
    result = write(counts, priceable=False)
    assert result["detail_provenance"] == provenance and result["total_tokens"] == total and result["cost"] is None
    token = ledger.execute("SELECT STATUS,SETTLED_VALUE FROM CX_MODEL_QUOTA_RESERVATIONS WHERE RESERVATION_ID='token-reservation'").fetchone()
    assert token == ({"status": "SETTLED", "settled_value": f"{total:.6f}"} if total is not None
                     else {"status": "SETTLED_INCOMPLETE", "settled_value": "1000"})
    assert ledger.execute("SELECT STATUS FROM CX_MODEL_QUOTA_RESERVATIONS WHERE RESERVATION_ID='cost-reservation'").fetchone()["status"] == "SETTLED_INCOMPLETE"


def test_explicit_release_policy_remains_an_operator_decision(ledger):
    ledger.execute("UPDATE CX_MODEL_QUOTA_POLICIES SET INCOMPLETE_POLICY='RELEASE'")
    ledger.commit()
    write({}, priceable=False)
    assert all(row["status"] == "RELEASED" for row in ledger.execute("SELECT STATUS FROM CX_MODEL_QUOTA_RESERVATIONS"))


def test_completed_refusal_keeps_provider_usage_and_settles_once(ledger):
    from lib.model_results import ModelResultError
    failure = ModelResultError("PROVIDER_REFUSAL", request_complete=True,
                               usage={"prompt_tokens": 10, "completion_tokens": 4, "total_tokens": 14})
    profile = {"profile_id": "provider", "model_id": "model"}
    for _ in range(2):
        usage._failed_usage("request", "owner", "agent", profile, time.monotonic(), "key", failure)
    record = ledger.execute("SELECT STATUS,TOTAL_TOKENS FROM CX_MODEL_USAGE").fetchall()
    assert record == [{"status": "FAILED", "total_tokens": 14}]
    assert all(row["status"] == "SETTLED" for row in ledger.execute("SELECT STATUS FROM CX_MODEL_QUOTA_RESERVATIONS"))


def test_unknown_send_retains_incomplete_accounting_and_original_reservation(ledger):
    usage._failed_usage("request", "owner", "agent", {"profile_id": "provider", "model_id": "model"},
                        time.monotonic(), "key", TimeoutError("unknown remote outcome"))
    record = ledger.execute("SELECT STATUS,TOTAL_TOKENS,COST FROM CX_MODEL_USAGE").fetchone()
    assert record == {"status": "INCOMPLETE", "total_tokens": None, "cost": None}
    assert all(row["status"] == "SETTLED_INCOMPLETE" for row in ledger.execute("SELECT STATUS FROM CX_MODEL_QUOTA_RESERVATIONS"))


def test_known_no_send_releases_quota_without_invented_usage(ledger, monkeypatch):
    from lib.model_dispatch import ModelNotDispatched
    monkeypatch.setattr(usage.connection, "execute", lambda statement, params: ledger.execute(statement, params).rowcount)
    usage._failed_usage("request", "owner", "agent", {"profile_id": "provider", "model_id": "model"},
                        time.monotonic(), "key", ModelNotDispatched("MODEL_DISPATCH_DENIED", "No provider send"))
    assert ledger.execute("SELECT COUNT(*) AS n FROM CX_MODEL_USAGE").fetchone()["n"] == 0
    assert all(row["status"] == "RELEASED" for row in ledger.execute("SELECT STATUS FROM CX_MODEL_QUOTA_RESERVATIONS"))
