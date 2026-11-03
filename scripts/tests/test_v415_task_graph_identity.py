"""Task completion keeps the identity that owns its compatibility Graph worker."""
from lib import task_plan_api, graph_compat
import pytest


@pytest.mark.parametrize('dialect', ['oracle', 'yashandb', 'postgresql'])
def test_step_reads_observed_times_without_unsupported_pg_assignment_column(monkeypatch, dialect):
    monkeypatch.setattr(task_plan_api, 'DATABASE_DIALECT', dialect)
    calls = []
    def query(sql, params):
        calls.append(sql)
        assert ('NULL AS ASSIGNED_AGENT_ID' in sql) == (dialect == 'postgresql')
        assert 'TO_CHAR(STARTED_AT,' in sql and 'TO_CHAR(COMPLETED_AT,' in sql
        return [dict(step_id='S1', started_at='2026-11-02 16:00:00', completed_at=None)]
    monkeypatch.setattr(task_plan_api, 'execute_query', query)
    assert task_plan_api.get_plan_steps('P1')[0]['started_at'] == '2026-11-02 16:00:00'
    assert len(calls) == 1


def test_legacy_step_read_does_not_invent_execution_times_from_creation(monkeypatch):
    calls = []
    def query(sql, params):
        calls.append(sql)
        if len(calls) == 1:
            raise ValueError('Legacy schema lacks timestamp columns')
        assert 'NULL AS STARTED_AT' in sql and 'NULL AS COMPLETED_AT' in sql
        assert 'CREATED_AT' not in sql
        return [dict(step_id='S1', started_at=None, completed_at=None)]
    monkeypatch.setattr(task_plan_api, 'execute_query', query)
    assert task_plan_api.get_plan_steps('P1')[0]['completed_at'] is None


@pytest.mark.parametrize("dialect", ["oracle", "yashandb", "postgresql"])
@pytest.mark.parametrize("actual", [None, "RUNNING", "PENDING"])
def test_step_insert_locks_parent_and_rejects_stale_status(monkeypatch, dialect, actual):
    from lib import connection
    statements = []
    class Transaction:
        def query_one(self, sql, params):
            if sql.lstrip().startswith("INSERT"):
                assert statements == ["lock"]
                assert "RETURNING STEP_ID" in sql
                statements.append("insert")
                return {"step_id": 42}
            assert "FOR UPDATE" in sql
            statements.append("lock")
            return {"status": actual} if actual else None
        def execute(self, sql, params):
            assert statements == ["lock"]
            statements.append("insert")
            assert params["step_id"].startswith("STEP_")
    monkeypatch.setattr(task_plan_api, "DATABASE_DIALECT", dialect)
    monkeypatch.setattr(connection, "execute_transaction_callback", lambda callback: callback(Transaction()))
    monkeypatch.setattr(task_plan_api, "get_plan", lambda _: None)
    if actual == "PENDING":
        step = task_plan_api.add_step("P1", "PENDING", "test", 1)
        assert step == "42" if dialect == "postgresql" else step.startswith("STEP_")
        assert statements == ["lock", "insert"]
    else:
        with pytest.raises(ValueError):
            task_plan_api.add_step("P1", "PENDING", "test", 1)
        assert statements == ["lock"]


@pytest.mark.parametrize("dialect", ["oracle", "yashandb", "postgresql"])
def test_get_plan_reads_real_completion_time_where_available(monkeypatch, dialect):
    monkeypatch.setattr(task_plan_api, "DATABASE_DIALECT", dialect)
    queries = []
    def query(sql, params):
        queries.append(sql)
        return {"plan_id": "P1", "completed_at": None}
    monkeypatch.setattr(task_plan_api, "execute_query_one", query)
    assert task_plan_api.get_plan("P1")["completed_at"] is None
    assert ("TO_CHAR(COMPLETED_AT," in queries[0]) is (dialect != "postgresql")


@pytest.mark.parametrize("dialect", ["oracle", "yashandb", "postgresql"])
@pytest.mark.parametrize("status", ["SUCCESS", "FAILED", "CANCELLED"])
def test_plan_terminal_transition_finishes_graph_and_keeps_supported_timestamp(monkeypatch, dialect, status):
    from lib import connection
    statements = []
    class Transaction:
        def query_one(self, *args):
            return {"status": "RUNNING"}
        def execute(self, sql, params=None):
            statements.append(sql)
            return 1
    monkeypatch.setattr(task_plan_api, "DATABASE_DIALECT", dialect)
    monkeypatch.setattr(connection, "execute_transaction_callback", lambda callback: callback(Transaction()))
    monkeypatch.setattr(task_plan_api, "get_plan", lambda _: {"agent_id": "OWNER", "status": status})
    calls = []
    monkeypatch.setattr(graph_compat, "finish_legacy_run", lambda *args, **kw: calls.append((args, kw)))
    assert task_plan_api.update_plan("P1", status=status)
    assert calls[0][0][:3] == ("TASK_PLAN", "P1", "OWNER")
    assert calls[0][1]["success"] is (status == "SUCCESS")
    parent_update = next(sql for sql in statements if sql.startswith("UPDATE TASK_PLANS"))
    assert ("COMPLETED_AT" in parent_update) is (dialect != "postgresql")


def test_step_completion_uses_parent_agent_and_preserves_output(monkeypatch):
    from lib import processing_legacy
    # This historical global-SQL contract predates processing transactions.
    monkeypatch.setattr(processing_legacy, "enabled", lambda: False)
    monkeypatch.setattr(task_plan_api, "execute", lambda *_: 1)
    queries = []
    def query(sql, params):
        queries.append(sql)
        return {"step_id": "S1", "plan_id": "P1", "status": "SUCCESS",
                "graph_actor_id": "PLAN_AGENT", "tool_output": '{"result":42}'}
    monkeypatch.setattr(task_plan_api, "execute_query_one", query)
    calls = []
    monkeypatch.setattr(graph_compat, "sync_task_step", lambda *args: calls.append(args))
    assert task_plan_api.update_step("S1", status="SUCCESS", tool_output={"result": 42})
    assert calls[0][2] == "PLAN_AGENT"
    assert calls[0][3] == {"result": 42}
    assert "JOIN TASK_PLANS" in queries[0]


def test_graph_completion_false_is_not_reported_as_task_success(monkeypatch):
    from lib import connection
    class Transaction:
        def query_one(self, *args):
            return {"status": "RUNNING"}
        def execute(self, *args):
            return 1
    monkeypatch.setattr(connection, 'execute_transaction_callback', lambda fn: fn(Transaction()))
    monkeypatch.setattr(task_plan_api, 'get_plan', lambda _: {'agent_id': 'OWNER'})
    monkeypatch.setattr(graph_compat, 'finish_legacy_run', lambda *args, **kw: False)
    with pytest.raises(RuntimeError, match='Graph completion is pending'):
        task_plan_api.update_plan('P1', status='SUCCESS')
