"""Native batch equivalence/rollback in an exact classified package database.

No model calls. Source/offline runs skip; only isolated v5.0.2 targets may opt in.
The probe table is created with a unique name and removed after each case.
"""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime
from decimal import Decimal
import os
import secrets
import threading

import pytest

from lib import connection
from .release_target import classified_current_target

pytestmark = pytest.mark.skipif(os.environ.get('CX_V502_NATIVE_BATCH_LIVE') != '1',
                                reason='explicit classified v5.0.2 native batch acceptance required')


@pytest.fixture
def probe():
    assert classified_current_target(), 'Native batch mutation requires the exact classified package target'
    from lib.product_identity import read_manifest
    assert read_manifest()['version'] == '5.0.2'
    table = 'CX502_B_' + secrets.token_hex(6).upper()
    pg = connection.DATABASE_DIALECT in {'pg', 'postgresql'}
    connection.execute('CREATE TABLE ' + table + '(ITEM_ID VARCHAR(40) PRIMARY KEY,BODY_TEXT ' +
        ('TEXT' if pg else 'CLOB') + ',STAMP TIMESTAMP,AMOUNT NUMERIC(32,12),OPTIONAL_VALUE VARCHAR(80))')
    statement = 'INSERT INTO ' + table + '(ITEM_ID,BODY_TEXT,STAMP,AMOUNT,OPTIONAL_VALUE) VALUES(:item_id,:body,:stamp,:amount,:optional_value)'
    try:
        yield table, statement
    finally:
        connection.execute('DROP TABLE ' + table)


def rows(count):
    return [dict(item_id=str(index), body='原生长文本' * 12000 if index == 1 else '短文本',
        stamp=None if index == 0 else datetime(2026, 10, 28, 1, 2, 3, 123456),
        amount=Decimal('1234567890.123456789'), optional_value=None) for index in range(count)]


def count(table):
    return int(connection.execute_query_one('SELECT COUNT(*) AS N FROM ' + table)['n'])


@pytest.mark.parametrize('size', [1, 100, 205])
def test_native_batch_preserves_exact_values_and_chunk_boundaries(probe, size):
    table, sql = probe
    values = rows(size)
    assert connection.execute_many(sql, values) == size
    assert count(table) == size
    exact = connection.execute_query_one('SELECT COUNT(*) AS N FROM ' + table +
        ' WHERE AMOUNT=:amount AND OPTIONAL_VALUE IS NULL', {'amount': values[0]['amount']})
    assert int(exact['n']) == size
    actual = connection.execute_query('SELECT ITEM_ID,BODY_TEXT,STAMP FROM ' + table)
    by_id = {str(item['item_id']): item for item in actual}
    for expected in values:
        item = by_id[expected['item_id']]
        assert item['body_text'] == expected['body']
        assert item['stamp'] == expected['stamp']


def test_native_later_chunk_constraint_failure_rolls_back_earlier_chunks(probe):
    table, sql = probe
    values = rows(205)
    values[101]['item_id'] = values[0]['item_id']
    with pytest.raises(Exception):
        connection.execute_many(sql, values)
    assert count(table) == 0


def test_native_following_business_failure_rolls_back_successful_batch(probe):
    table, sql = probe
    def fail(tx):
        assert tx.execute_many(sql, rows(205)) == 205
        raise RuntimeError('Synthetic business audit failed after real native batch')
    with pytest.raises(RuntimeError, match='Synthetic business audit'):
        connection.execute_transaction_callback(fail)
    assert count(table) == 0


def test_native_uncommitted_batch_is_not_visible_to_independent_reader(probe):
    table, sql = probe
    ready, release = threading.Event(), threading.Event()
    def write():
        def operation(tx):
            assert tx.execute_many(sql, rows(205)) == 205
            ready.set()
            if not release.wait(30):
                raise RuntimeError('Native batch observer did not release its transaction')
            return 205
        return connection.execute_transaction_callback(operation)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(write)
        try:
            assert ready.wait(30), 'Native batch writer did not reach its uncommitted observation point'
            assert count(table) == 0
        finally:
            release.set()
        assert future.result(timeout=30) == 205
    assert count(table) == 205


@pytest.fixture
def native_driver_calls(monkeypatch):
    original = connection.get_connection_for_agent
    calls = []
    class Cursor:
        def __init__(self, raw): self.raw = raw
        def __getattr__(self, key): return getattr(self.raw, key)
        def __enter__(self): self.raw.__enter__(); return self
        def __exit__(self, *args): return self.raw.__exit__(*args)
        def execute(self, *args, **kwargs): calls.append('execute'); return self.raw.execute(*args, **kwargs)
        def executemany(self, *args, **kwargs): calls.append('executemany'); return self.raw.executemany(*args, **kwargs)
    class Session:
        def __init__(self, raw): self.raw = raw
        def __getattr__(self, key): return getattr(self.raw, key)
        def cursor(self, *args, **kwargs): return Cursor(self.raw.cursor(*args, **kwargs))
    @contextmanager
    def observed():
        with original() as session: yield Session(session)
    monkeypatch.setattr(connection, 'get_connection_for_agent', observed)
    return calls


def test_native_batch_reduces_actual_driver_round_trips_with_identical_rows(probe, native_driver_calls, record_property):
    table, sql = probe
    calls = native_driver_calls
    values = rows(205)
    # YashanDB's independent safe fixture starts the timestamp bind typed;
    # PG/Oracle retain their original first-NULL fixture. Each serial/batch
    # comparison receives identical rows, including the all-NULL optional bind.
    if connection.DATABASE_DIALECT == 'yashandb':
        values[0]['stamp'] = values[1]['stamp']
        values[1]['body'] = '短文本'
    assert connection.execute_transaction([(sql, item) for item in values]) == 205
    baseline_calls = len(calls)
    assert baseline_calls == 205
    assert count(table) == 205
    serial_values = connection.execute_query('SELECT ITEM_ID,BODY_TEXT,STAMP,OPTIONAL_VALUE FROM ' + table + ' ORDER BY ITEM_ID')
    connection.execute('DELETE FROM ' + table)
    calls.clear()
    assert connection.execute_many(sql, values) == 205
    batch_calls = len(calls)
    assert batch_calls == 3
    assert count(table) == 205
    assert connection.execute_query('SELECT ITEM_ID,BODY_TEXT,STAMP,OPTIONAL_VALUE FROM ' + table + ' ORDER BY ITEM_ID') == serial_values
    record_property('native_serial_driver_calls', baseline_calls)
    record_property('native_batched_driver_calls', batch_calls)
    record_property('native_batch_rows', 205)
    record_property('native_fixture_large_text_excluded', connection.DATABASE_DIALECT == 'yashandb')


@pytest.mark.skipif(getattr(connection, 'DATABASE_DIALECT', '') != 'yashandb',
                    reason='YashanDB first-NULL array DML regression')
def test_native_yashandb_first_null_and_large_text_preserve_exact_values_in_five_calls(probe, native_driver_calls, record_property):
    table, sql = probe
    calls = native_driver_calls
    values = rows(205)
    assert connection.execute_transaction([(sql, item) for item in values]) == 205
    baseline_calls = len(calls)
    assert baseline_calls == 205
    serial_values = connection.execute_query('SELECT ITEM_ID,BODY_TEXT,STAMP,OPTIONAL_VALUE FROM ' + table)
    connection.execute('DELETE FROM ' + table)
    calls.clear()
    assert connection.execute_many(sql, values) == 205
    batch_calls = len(calls)
    assert batch_calls == 5 < baseline_calls
    assert calls == ['executemany', 'execute', 'executemany', 'executemany', 'executemany']
    assert count(table) == 205
    actual = connection.execute_query('SELECT ITEM_ID,BODY_TEXT,STAMP,OPTIONAL_VALUE FROM ' + table)
    by_id = {str(item['item_id']): item for item in actual}
    assert by_id == {str(item['item_id']): item for item in serial_values}
    for expected in values:
        item = by_id[expected['item_id']]
        assert item['body_text'] == expected['body']
        assert item['stamp'] == expected['stamp']
        assert item['optional_value'] is None
    exact = connection.execute_query_one('SELECT COUNT(*) AS N FROM ' + table +
        ' WHERE AMOUNT=:amount AND OPTIONAL_VALUE IS NULL', {'amount': values[0]['amount']})
    assert int(exact['n']) == 205
    record_property('native_serial_driver_calls', baseline_calls)
    record_property('native_batched_driver_calls', batch_calls)
    record_property('native_batch_rows', 205)
    record_property('native_batch_first_timestamp_is_null', values[0]['stamp'] is None)


@pytest.mark.skipif(getattr(connection, 'DATABASE_DIALECT', '') != 'yashandb',
                    reason='YashanDB text routing boundary regression')
def test_native_yashandb_text_routing_boundary_preserves_exact_values(probe, native_driver_calls):
    table, sql = probe
    values = rows(8)
    bodies = ['短文本', 'a' * 32766, 'a' * 32767, 'a' * 32768,
              '界' * 10922, '界' * 10923, '原生长文本' * 12000, '末尾']
    for row, body in zip(values, bodies):
        row['body'] = body
    assert connection.execute_many(sql, values) == len(values)
    assert native_driver_calls == ['executemany', 'executemany', 'execute', 'executemany', 'execute', 'execute', 'executemany']
    actual = connection.execute_query('SELECT ITEM_ID,BODY_TEXT,STAMP,LENGTH(BODY_TEXT) AS BODY_LENGTH FROM ' + table)
    by_id = {str(item['item_id']): item for item in actual}
    assert len(by_id) == len(values)
    for expected in values:
        item = by_id[expected['item_id']]
        assert item['body_text'] == expected['body']
        assert item['body_length'] == len(expected['body'])
        assert item['stamp'] == expected['stamp']
