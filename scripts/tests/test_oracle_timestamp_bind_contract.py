"""Oracle UTC-naive TIMESTAMP binding retains exact revision precision."""
from __future__ import annotations

import ast
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import threading

import pytest

from lib import package_layout


ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def adapter():
    if 'oracle' not in package_layout.databases(ROOT):
        pytest.skip('Oracle adapter only')
    path = package_layout.adapter_file(ROOT, 'oracle', 'connection.py')
    selected = {'_timestamp_input_type_handler', 'get_connection',
                'get_end_user_connection', '_get_agent_mode_end_user_connection'}
    tree = ast.parse(path.read_text(encoding='utf-8'))
    nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in selected]
    connection = SimpleNamespace(cursor=Mock(), close=Mock())
    connection.cursor.return_value.__enter__ = Mock(return_value=connection.cursor.return_value)
    connection.cursor.return_value.__exit__ = Mock(return_value=False)
    pool = SimpleNamespace(acquire=Mock(return_value=connection), release=Mock())
    config = SimpleNamespace(agent=SimpleNamespace(mode='admin'),
        database=SimpleNamespace(user='OWNER', dsn='isolated.invalid/SERVICE'))
    driver = SimpleNamespace(DB_TYPE_TIMESTAMP=object(), connect=Mock(return_value=connection), Error=RuntimeError)
    namespace = dict(datetime=datetime, contextmanager=contextmanager, oracledb=driver,
        get_pool=lambda: pool, get_config=lambda: config, get_current_agent_id=lambda: None,
        apply_agent_context=Mock(), clear_agent_context=Mock(), _logger=Mock(),
        _end_user_lock=threading.Lock(), _end_user_connections={}, threading=threading,
        _revoked_end_users=set(), _end_user_generations={},
        _get_end_user_password=lambda _: 'synthetic-test-only',
        _agent_id_to_end_user_name=lambda value: value.upper(),
        _load_agent_eu_creds=lambda: dict(username='AGENT', password='synthetic-test-only', dsn=config.database.dsn))
    module = ast.Module(body=[ast.ImportFrom(module='__future__', names=[ast.alias(name='annotations')], level=0), *nodes], type_ignores=[])
    ast.fix_missing_locations(module)
    exec(compile(module, str(path), 'exec'), namespace)
    return SimpleNamespace(**namespace), connection, pool, driver


def test_utc_naive_datetime_binds_timestamp_without_altering_its_value(adapter):
    api, _, _, driver = adapter
    cursor = SimpleNamespace(var=Mock(return_value=object()))
    instant = datetime(2030, 6, 1, 12, 1, 2, 345678)
    result = api._timestamp_input_type_handler(cursor, instant, 7)
    assert result is cursor.var.return_value
    cursor.var.assert_called_once_with(driver.DB_TYPE_TIMESTAMP, arraysize=7)
    assert instant.microsecond == 345678 and instant.tzinfo is None


@pytest.mark.parametrize('value', [datetime(2030, 6, 1, tzinfo=timezone.utc), date(2030, 6, 1), '2030-06-01', None, 1])
def test_other_bind_semantics_remain_driver_owned(adapter, value):
    api, _, _, _ = adapter
    cursor = SimpleNamespace(var=Mock())
    assert api._timestamp_input_type_handler(cursor, value, 1) is None
    cursor.var.assert_not_called()


@pytest.mark.parametrize('path', ['owner', 'independent', 'agent-mode'])
def test_every_oracle_connection_path_installs_timestamp_handler(adapter, path):
    api, conn, pool, _ = adapter
    if path == 'owner':
        with api.get_connection() as selected:
            assert selected is conn
            assert conn.inputtypehandler is api._timestamp_input_type_handler
        pool.release.assert_called_once_with(conn)
    else:
        selected = (api.get_end_user_connection('agent') if path == 'independent'
                    else api._get_agent_mode_end_user_connection('agent'))
        assert selected is conn
        assert conn.inputtypehandler is api._timestamp_input_type_handler
