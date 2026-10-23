"""Offline health-read semantics and query bounds for both Monitor inventories."""

from datetime import datetime, timedelta, timezone
import sqlite3

import pytest

from lib import cursor_pagination, identity_api, monitor_api


@pytest.fixture
def health_database(monkeypatch):
    """Exercise the actual aggregate SELECTs without opening a live database."""
    database = sqlite3.connect(":memory:")
    database.row_factory = sqlite3.Row
    database.executescript("""
        CREATE TABLE AGENT_REGISTRY (
            AGENT_ID TEXT PRIMARY KEY, AGENT_NAME TEXT, STATUS TEXT, LAST_ACTIVE_AT TEXT
        );
        CREATE TABLE AGENT_SESSION (AGENT_ID TEXT, SESSION_ID TEXT, IS_ACTIVE TEXT);
        CREATE TABLE TASK_PLANS (AGENT_ID TEXT, STATUS TEXT);
        CREATE TABLE LOOP_RUNS (AGENT_ID TEXT, STATUS TEXT);
    """)
    calls = []

    def query(sql, params=None):
        values = dict(params or {})
        calls.append((sql, values))
        # This adapter-neutral source test checks the aggregate SQL with SQLite;
        # the three production adapters separately validate their pagination SQL.
        sql = sql.replace("FETCH FIRST :row_limit ROWS ONLY", "LIMIT :row_limit")
        return [{key.lower(): value for key, value in dict(row).items()}
                for row in database.execute(sql, values).fetchall()]

    def query_one(sql, params=None):
        rows = query(sql, params)
        return rows[0] if rows else None

    monkeypatch.setattr(monitor_api, "execute_query", query)
    monkeypatch.setattr(monitor_api, "execute_query_one", query_one)
    yield database, calls
    database.close()


def seed_agents(database, count):
    database.executemany(
        "INSERT INTO AGENT_REGISTRY VALUES (?, ?, 'ACTIVE', NULL)",
        [(f"agent-{index:04}", f"Agent {count - index:04}") for index in range(count)],
    )


def test_legacy_inventory_batches_154_agents_and_preserves_health_fields(health_database):
    database, calls = health_database
    seed_agents(database, 154)
    database.executemany("INSERT INTO AGENT_SESSION VALUES (?, ?, ?)", [
        ("agent-0000", "session-z", "Y"),
        ("agent-0000", "session-a", "Y"),
        ("agent-0000", "session-0", "N"),
        ("agent-0001", "inactive-session", "N"),
    ])
    database.executemany("INSERT INTO TASK_PLANS VALUES (?, ?)", [
        ("agent-0000", "RUNNING"), ("agent-0000", "RUNNING"),
        ("agent-0000", "COMPLETED"), ("agent-0001", "PAUSED"),
    ])
    database.executemany("INSERT INTO LOOP_RUNS VALUES (?, ?)", [
        ("agent-0000", "RUNNING"), ("agent-0000", "COMPLETED"),
    ])

    result = monitor_api.get_agent_health()

    assert set(result) == {"agents"}
    assert len(result["agents"]) == 154
    assert len(calls) == 4, "154 Agents must not require 617 database reads"
    assert [row["agent_name"] for row in result["agents"]] == sorted(
        row["agent_name"] for row in result["agents"]
    )
    by_id = {row["agent_id"]: row for row in result["agents"]}
    assert by_id["agent-0000"] == {
        "agent_id": "agent-0000", "agent_name": "Agent 0154",
        "status": "ONLINE", "db_status": "ACTIVE",
        "current_session_id": "session-a", "active_plan_count": 2,
        "running_loop_count": 1, "last_active_at": None, "stale_seconds": None,
    }
    assert by_id["agent-0001"]["current_session_id"] is None
    assert by_id["agent-0001"]["active_plan_count"] == 0
    assert by_id["agent-0001"]["running_loop_count"] == 0
    assert all("SELECT *" not in sql for sql, _params in calls)


def test_legacy_inventory_chunks_large_id_sets_and_binds_values(health_database):
    database, calls = health_database
    seed_agents(database, 1001)
    unusual_id = "agent') OR 1=1 --"
    database.execute("INSERT INTO AGENT_REGISTRY VALUES (?, 'Unusual', 'POOL', NULL)", (unusual_id,))
    database.execute("INSERT INTO TASK_PLANS VALUES (?, 'RUNNING')", (unusual_id,))

    result = monitor_api.get_agent_health()

    assert len(result["agents"]) == 1002
    assert len(calls) == 10  # one registry read plus three reads per 500-ID batch
    related_reads = calls[1:]
    assert all(0 < len(params) <= 500 for _sql, params in related_reads)
    assert all("AGENT_ID IN (" in sql and unusual_id not in sql for sql, _params in related_reads)
    assert any(unusual_id in params.values() for _sql, params in related_reads)
    assert next(row for row in result["agents"] if row["agent_id"] == unusual_id)["active_plan_count"] == 1


def test_single_agent_health_and_missing_agent_keep_response_contract(health_database):
    database, calls = health_database
    seed_agents(database, 2)
    database.execute("INSERT INTO LOOP_RUNS VALUES ('agent-0000', 'RUNNING')")

    result = monitor_api.get_agent_health("agent-0000")

    assert result["agent_id"] == "agent-0000"
    assert result["running_loop_count"] == 1
    assert len(calls) == 4
    calls.clear()
    assert monitor_api.get_agent_health("missing") == {"error": "Agent not found: missing"}
    assert len(calls) == 1


def test_cursor_page_batches_only_visible_rows_and_keeps_scope_total_and_cursor(health_database, monkeypatch):
    database, calls = health_database
    seed_agents(database, 24)
    issued = []
    monkeypatch.setattr(cursor_pagination, "resolve", lambda *_args: {
        "position": {"agent_id": "agent-0001"}, "page_size": 20, "filter_digest": "scope-test",
    })
    monkeypatch.setattr(cursor_pagination, "issue", lambda *args: issued.append(args) or "next-cursor")
    monkeypatch.setattr(identity_api, "effective_access", lambda *_args: {"decision": "DENY"})
    monkeypatch.setattr(identity_api, "_agent_visibility_clause", lambda *_args: "p.PRINCIPAL_ID <> :principal_id")
    database.execute("CREATE TABLE CX_PRINCIPALS (PRINCIPAL_ID TEXT, PRINCIPAL_TYPE TEXT)")
    database.executemany("INSERT INTO CX_PRINCIPALS VALUES (?, 'AGENT')", [
        (f"agent-{index:04}",) for index in range(23)
    ])

    result = monitor_api.get_agent_health_cursor("agent-0000")

    assert len(calls) == 5  # page, three health aggregates, current-scope total
    assert result["count"] == 20 and result["page_size"] == 20
    assert result["total_items"] == 22  # total is scoped, not after-cursor count
    assert result["has_more"] is True and result["next_cursor"] == "next-cursor"
    assert [row["agent_id"] for row in result["items"]] == [f"agent-{index:04}" for index in range(2, 22)]
    assert issued[0][-1] == {"agent_id": "agent-0021"}
    assert ":after" in calls[0][0] and ":after" not in calls[-1][0]
    assert calls[-1][1] == {"principal_id": "agent-0000"}
    for _sql, params in calls[1:4]:
        assert len(params) == 20
        assert "agent-0022" not in params.values(), "Do not fetch health for the limit+1 sentinel"
        assert "agent-0023" not in params.values(), "Do not fetch unauthorized registry state"


def test_empty_or_failed_closed_scope_never_reads_unselected_health(health_database, monkeypatch):
    database, calls = health_database
    seed_agents(database, 1)
    monkeypatch.setattr(cursor_pagination, "resolve", lambda *_args: {
        "position": {}, "page_size": 20, "filter_digest": "scope-test",
    })
    monkeypatch.setattr(identity_api, "effective_access", lambda *_args: (_ for _ in ()).throw(RuntimeError("unavailable")))

    result = monitor_api.get_agent_health_cursor("delegated-user")

    assert result["items"] == [] and result["total_items"] == 0
    assert len(calls) == 2
    assert all("1=0" in sql for sql, _params in calls)


def test_aggregate_failure_does_not_publish_zero_health_as_success(health_database, monkeypatch):
    database, _calls = health_database
    seed_agents(database, 1)
    query = monitor_api.execute_query

    def failing_query(sql, params=None):
        if "FROM TASK_PLANS" in sql:
            raise RuntimeError("task inventory unavailable")
        return query(sql, params)

    monkeypatch.setattr(monitor_api, "execute_query", failing_query)

    with pytest.raises(RuntimeError, match="task inventory unavailable"):
        monitor_api.get_agent_health()


@pytest.mark.parametrize("db_status, age, expected", [
    ("ACTIVE", 601, "STALLED"), ("ACTIVE", 600, "ONLINE"),
    ("ACTIVE", 0, "ONLINE"), ("POOL", 700, "IDLE"),
    ("SUSPENDED", 700, "OFFLINE"), ("INACTIVE", 0, "OFFLINE"),
    ("DECOMMISSIONED", 0, "OFFLINE"), ("DORMANT", 0, "ONLINE"),
])
@pytest.mark.parametrize("aware", [False, True])
def test_naive_and_timezone_aware_health_keep_staleness_and_status(monkeypatch, db_status, age, expected, aware):
    now = datetime(2026, 10, 21, 12, tzinfo=timezone.utc)

    class FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return now.astimezone(tz) if tz else now.replace(tzinfo=None)

    last_active = now - timedelta(seconds=age)
    if not aware:
        last_active = last_active.replace(tzinfo=None)
    monkeypatch.setattr(monitor_api, "datetime", FixedDatetime)
    monkeypatch.setattr(monitor_api, "execute_query", lambda *_args: [])
    # Use the same concrete datetime class as the module's clock, just as the
    # production driver and datetime.now use the standard datetime class.
    last_active = FixedDatetime.fromisoformat(last_active.isoformat())

    row = monitor_api._agent_health_rows([{
        "agent_id": "one", "agent_name": "One", "status": db_status,
        "last_active_at": last_active,
    }])[0]

    assert row["stale_seconds"] == age
    assert row["status"] == expected
    assert row["last_active_at"] == str(last_active)


def test_text_activity_time_remains_unknown_instead_of_inventing_age(monkeypatch):
    monkeypatch.setattr(monitor_api, "execute_query", lambda *_args: [])
    result = monitor_api._agent_health_rows([{
        "agent_id": "one", "status": "ACTIVE", "last_active_at": "2026-10-21 12:00:00",
    }])[0]
    assert result["stale_seconds"] is None
    assert result["last_active_at"] == "2026-10-21 12:00:00"
