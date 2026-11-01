"""Batch API and relational equivalence contracts, not native DB acceptance."""
from contextlib import contextmanager, nullcontext
from datetime import datetime
from decimal import Decimal
import importlib.util
from pathlib import Path
import sqlite3
import sys
from types import ModuleType, SimpleNamespace

import pytest

from lib import connection, continuity_assembly as assembly, continuity_handoff as handoff
from lib import continuity_work as work, memory_lifecycle as memory, context_selection
from lib import continuity_publications as publications
from .test_continuity_work import database, request as work_request
from .test_continuity_handoff import fixture, offer_request
from .test_continuity_assembly import context_db
from .test_continuity_publications import publication_db, publication, prepare


ROOT = Path(__file__).resolve().parents[2]
BACKENDS = ('oracle', 'pg', 'yashandb') if (ROOT / 'adapters').is_dir() else ('packaged',)


@pytest.fixture(params=BACKENDS)
def adapter(request, monkeypatch):
    if request.param == 'packaged':
        return connection
    # The source adapter is assembled with config_db.py during packaging. Supply
    # only the imported config names here; no configuration or DB is opened.
    backend = request.param
    pytest.importorskip({'oracle': 'oracledb', 'pg': 'psycopg2', 'yashandb': 'yaspy'}[backend])
    name = 'lib._v502_batch_' + backend
    package = ModuleType(name)
    package.__path__ = []
    config = ModuleType(name + '.config')
    config.get_config = lambda: pytest.fail('batch unit contract must not load operator config')
    config.DatabaseConfig = config.AgentModeConfig = object
    monkeypatch.setitem(sys.modules, name, package)
    monkeypatch.setitem(sys.modules, name + '.config', config)
    spec = importlib.util.spec_from_file_location(name + '.connection', ROOT / 'adapters' / backend / 'connection.py')
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    return module


class FakeCursor:
    def __init__(self, owner):
        self.owner = owner
        self.rowcount = -1
        self.closed = False
        self.sizes = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def close(self):
        self.closed = True

    def setinputsizes(self, **sizes):
        self.sizes.append(sizes)

    def executemany(self, sql, rows):
        self.owner.calls.append(('native', sql, list(rows)))
        self._apply(rows)

    def execute(self, sql, params):
        self.owner.calls.append(('single', sql, params))
        if sql.startswith('UPDATE'):
            previous = self.owner.value
            self.owner.value = previous * params[0] + params[1]
            self.rowcount = int(params[2])
        else:
            self._apply([params])

    def _apply(self, rows):
        self.rowcount = 0
        for row in rows:
            if self.owner.fail_after is not None and len(self.owner.pending) == self.owner.fail_after:
                raise self.owner.failure
            self.owner.pending.append(row)
            self.rowcount += 1


class FakeConnection:
    def __init__(self, *, fail_after=None):
        self.fail_after = fail_after
        self.failure = ValueError('middle batch constraint violation')
        self.pending = []
        self.committed = []
        self.calls = []
        self.cursors = []
        self.commits = self.rollbacks = 0
        self.value = 1

    def cursor(self, **kwargs):
        cursor = FakeCursor(self)
        self.cursors.append(cursor)
        return cursor

    def commit(self):
        self.commits += 1
        self.committed.extend(self.pending)
        self.pending.clear()

    def rollback(self):
        self.rollbacks += 1
        self.pending.clear()


def fake_session(adapter, monkeypatch, **kwargs):
    session = FakeConnection(**kwargs)
    @contextmanager
    def acquire():
        yield session
    monkeypatch.setattr(adapter, 'get_connection_for_agent', acquire)
    monkeypatch.setattr(adapter, '_transaction_reads', SimpleNamespace(bind=lambda _: nullcontext()))
    if adapter.DATABASE_DIALECT == 'postgresql':
        def native_values(cur, statement, rows, *, template, page_size):
            assert statement.endswith('VALUES %s')
            assert template == '(%s,%s,%s,%s,%s,CURRENT_TIMESTAMP,\'FIXED\')'
            assert page_size == len(rows)
            cur.owner.calls.append(('native', (statement, template), list(rows)))
            cur._apply(rows)
        monkeypatch.setattr(adapter, 'execute_values', native_values)
    return session


BATCH_SQL = ('INSERT INTO CX_BATCH_TEST(ITEM_ID,BODY_TEXT,STAMP,AMOUNT,OPTIONAL_VALUE,CREATED_AT,KIND) '
             "VALUES(:item_id,:body,:stamp,:amount,:optional_value,CURRENT_TIMESTAMP,'FIXED')")


def parameters(count):
    stamp = datetime(2026, 10, 28, 1, 2, 3, 123456)
    return [dict(item_id=str(index), body='长文本' * 12000 if index == 1 else 'short',
                 stamp=None if index == 0 else stamp, amount=Decimal('1234567890.123456789'),
                 optional_value=None) for index in range(count)]


def null_parameters(count):
    values = parameters(count)
    for row in values:
        row['body'] = 'short'
    return values


def sent_rows(session):
    return [row for kind, _, data in session.calls
            for row in ([data] if kind == 'single' else data)]


@pytest.mark.parametrize('count', [1, 100, 205])
def test_native_chunks_preserve_binds_and_commit_once(adapter, monkeypatch, count):
    session = fake_session(adapter, monkeypatch)
    rows = parameters(count)
    assert adapter.execute_many(BATCH_SQL, rows) == count
    assert session.commits == 1 and session.rollbacks == 0
    expected_calls = (count + 99) // 100
    if adapter.DATABASE_DIALECT == 'yashandb' and count > 1:
        expected_calls += 2  # Leading short row, single large text, remaining short rows.
    assert len(session.calls) == expected_calls
    assert all(len(call[2]) <= 100 for call in session.calls if call[0] == 'native')
    assert [call[0] for call in session.calls].count('single') == int(adapter.DATABASE_DIALECT == 'yashandb' and count > 1)
    actual = sent_rows(session)
    expected = ([tuple(row[name] for name in ('item_id', 'body', 'stamp', 'amount', 'optional_value'))
                 for row in rows] if adapter.DATABASE_DIALECT == 'postgresql' else rows)
    assert actual == expected == session.committed
    assert all(cursor.closed for cursor in session.cursors)
    if adapter.DATABASE_DIALECT == 'oracle' and count > 1:
        assert session.cursors[0].sizes[0]['stamp'] == adapter.oracledb.DB_TYPE_TIMESTAMP
        assert session.cursors[0].sizes[0]['body'] == adapter.oracledb.DB_TYPE_CLOB


def test_empty_batch_does_not_acquire_or_commit(adapter, monkeypatch):
    monkeypatch.setattr(adapter, 'get_connection_for_agent', lambda: pytest.fail('empty batch acquired a connection'))
    assert adapter.execute_many(BATCH_SQL, []) == 0


@pytest.mark.parametrize('fail_after', [2, 101])
def test_native_middle_or_later_chunk_failure_rolls_back_everything(adapter, monkeypatch, fail_after):
    session = fake_session(adapter, monkeypatch, fail_after=fail_after)
    with pytest.raises(ValueError, match='middle batch'):
        adapter.execute_many(BATCH_SQL, parameters(205))
    assert session.commits == 0 and session.rollbacks == 1
    assert session.pending == session.committed == []
    assert all(cursor.closed for cursor in session.cursors)


def test_transaction_batch_retains_ownership_and_rolls_back_audit_failure(adapter, monkeypatch):
    session = fake_session(adapter, monkeypatch)
    def operation(tx):
        assert tx.execute_many(BATCH_SQL, parameters(205)) == 205
        assert session.commits == 0 and len(session.pending) == 205
        raise RuntimeError('audit failed after batch')
    with pytest.raises(RuntimeError, match='audit failed'):
        adapter.execute_transaction_callback(operation)
    assert session.commits == 0 and session.rollbacks == 1
    assert not session.pending and not session.committed
    assert all(cursor.closed for cursor in session.cursors)


def test_transaction_batch_success_commits_once_and_empty_batch_adds_no_cursor(adapter, monkeypatch):
    session = fake_session(adapter, monkeypatch)
    def operation(tx):
        cursor_count = len(session.cursors)
        assert tx.execute_many(BATCH_SQL, []) == 0
        assert len(session.cursors) == cursor_count
        assert tx.execute_many(BATCH_SQL, parameters(2)) == 2
        assert session.commits == 0
        return 'business result'
    assert adapter.execute_transaction_callback(operation) == 'business result'
    assert session.commits == 1 and session.rollbacks == 0 and len(session.committed) == 2


def test_postgresql_real_execute_values_sends_one_statement_per_chunk(adapter, monkeypatch):
    if adapter.DATABASE_DIALECT != 'postgresql':
        pytest.skip('PostgreSQL driver helper contract')
    from psycopg2.extras import execute_values
    from psycopg2.extensions import adapt
    session = fake_session(adapter, monkeypatch)
    statements = []
    class MogrifyCursor(FakeCursor):
        connection = SimpleNamespace(encoding='UTF8')
        def mogrify(self, template, params):
            # Native adapters quote all scalars; the fake only supplies the
            # transport sink used by psycopg2.extras.execute_values itself.
            encoded = template.encode() if isinstance(template, str) else template
            return encoded % tuple(adapt(value).getquoted() for value in params)
        def execute(self, statement):
            statements.append(statement)
            self.rowcount = statement.count(b"CURRENT_TIMESTAMP,'FIXED')")
    cursor = MogrifyCursor(session)
    monkeypatch.setattr(session, 'cursor', lambda **kwargs: cursor)
    monkeypatch.setattr(adapter, 'execute_values', execute_values)
    rows = parameters(205)
    # Mogrify's standalone string adapter uses latin1 without a real
    # connection. Keep that driver-only transport fixture ASCII; Unicode LOB
    # values are separately asserted unchanged in the native batch facade.
    for row in rows:
        row['body'] = "quoted 'text'; SELECT ignored --"
    assert adapter.execute_many(BATCH_SQL, rows) == 205
    assert len(statements) == 3
    assert [sql.count(b"CURRENT_TIMESTAMP,'FIXED')") for sql in statements] == [100, 100, 5]
    assert b"quoted ''text''; SELECT ignored --" in statements[0]
    assert b'1234567890.123456789' in statements[0]
    assert b'2026-10-28T01:02:03.123456' in statements[0]
    assert session.commits == 1


def test_postgresql_complex_dml_preserves_order_and_exact_counts(adapter, monkeypatch, caplog):
    if adapter.DATABASE_DIALECT != 'postgresql':
        pytest.skip('PostgreSQL explicit fallback contract')
    session = fake_session(adapter, monkeypatch)
    rows = [dict(mult=2, addition=3, affected=1), dict(mult=4, addition=5, affected=0),
            dict(mult=6, addition=7, affected=2)]
    assert adapter.execute_many('UPDATE T SET N=N*:mult+:addition WHERE ID=:affected', rows) == 3
    assert session.value == ((1 * 2 + 3) * 4 + 5) * 6 + 7
    assert [call[0] for call in session.calls] == ['single'] * 3
    assert 'method=serial_fallback reason=complex_dml' in caplog.text
    assert session.commits == 1


def test_yashandb_missing_driver_batch_is_explicit_and_atomic(adapter, monkeypatch, caplog):
    if adapter.DATABASE_DIALECT != 'yashandb':
        pytest.skip('YashanDB compatibility fallback contract')
    session = fake_session(adapter, monkeypatch, fail_after=1)
    monkeypatch.setattr(FakeCursor, 'executemany', None)
    with pytest.raises(ValueError, match='middle batch'):
        adapter.execute_many(BATCH_SQL, parameters(3))
    assert 'method=serial_fallback reason=driver_missing_executemany' in caplog.text
    assert session.commits == 0 and session.rollbacks == 1 and not session.pending


def first_null_driver_session(adapter, monkeypatch, **kwargs):
    """Reproduce yaspy's observed corruption without loading operator config."""
    session = fake_session(adapter, monkeypatch, **kwargs)
    class NullLeadingCursor(FakeCursor):
        def executemany(self, sql, rows):
            self.owner.calls.append(('native', sql, list(rows)))
            transmitted = list(rows)
            broken = {key for key, value in rows[0].items() if value is None
                      and any(row.get(key) is not None for row in rows[1:])}
            if broken:
                # The live driver retained later values but damaged the first
                # row's NULL indicator. Do not mutate the caller's dictionary.
                transmitted[0] = dict(rows[0], **{key: 'driver-corrupted-NULL' for key in broken})
            for index, row in enumerate(rows):
                large = {key: rows[0].get(key) for key, value in row.items()
                         if isinstance(value, str) and len(value.encode('utf-8')) > 32767}
                if large:
                    # Native mixed arrays also returned the large row with a
                    # short leading value. Scalar execute remains exact.
                    transmitted[index] = dict(transmitted[index], **large)
            self._apply(transmitted)
    def cursor(**kwargs):
        result = NullLeadingCursor(session)
        session.cursors.append(result)
        return result
    monkeypatch.setattr(session, 'cursor', cursor)
    return session


def test_yashandb_first_null_corruption_preserves_exact_values_and_input(adapter, monkeypatch):
    if adapter.DATABASE_DIALECT != 'yashandb':
        pytest.skip('YashanDB first-NULL indicator regression')
    session = first_null_driver_session(adapter, monkeypatch)
    values = null_parameters(205)
    original_values = [dict(row) for row in values]
    original_ids = [id(row) for row in values]
    assert adapter.execute_many(BATCH_SQL, values) == 205
    assert session.committed == original_values
    assert values == original_values and [id(row) for row in values] == original_ids
    sent = [row for _, _, segment in session.calls for row in segment]
    assert [id(row) for row in sent] == original_ids
    assert [len(segment) for _, _, segment in session.calls] == [1, 99, 100, 5]
    assert {kind for kind, _, _ in session.calls} == {'native'}
    assert len(session.cursors) == 1 and session.cursors[0].closed
    assert session.commits == 1 and session.rollbacks == 0


@pytest.mark.parametrize('pattern,expected_lengths', [
    ([(None, None), (None, None), ('stamp', None), (None, 'body'),
      ('stamp', None), (None, None), ('stamp', 'body')], [2, 1, 1, 2, 1]),
    ([(None, None)] * 205, [100, 100, 5]),
    ([('stamp', 'body'), (None, None), ('stamp', 'body')], [3]),
    ([('stamp', 'body')] * 205, [100, 100, 5]),
])
def test_yashandb_multiple_null_binds_and_repeated_nulls(adapter, monkeypatch, pattern, expected_lengths):
    if adapter.DATABASE_DIALECT != 'yashandb':
        pytest.skip('YashanDB first-NULL indicator regression')
    session = first_null_driver_session(adapter, monkeypatch)
    stamp = datetime(2026, 10, 28, 1, 2, 3, 123456)
    values = [dict(item_id=str(index), body=body, stamp=stamp if marker else None,
                   amount=Decimal('1234567890.123456789'), optional_value=None)
              for index, (marker, body) in enumerate(pattern)]
    expected = [dict(row) for row in values]
    assert adapter.execute_many(BATCH_SQL, values) == len(values)
    assert session.committed == values == expected
    assert [len(segment) for _, _, segment in session.calls] == expected_lengths
    assert session.commits == 1 and session.rollbacks == 0
    assert len(session.cursors) == 1 and session.cursors[0].closed


def test_yashandb_null_segments_preserve_original_chunk_boundaries(adapter, monkeypatch):
    if adapter.DATABASE_DIALECT != 'yashandb':
        pytest.skip('YashanDB first-NULL indicator regression')
    session = first_null_driver_session(adapter, monkeypatch)
    values = null_parameters(205)
    for index in (100, 101, 200, 201, 202):
        values[index]['stamp'] = None
    assert adapter.execute_many(BATCH_SQL, values) == 205
    assert session.committed == values
    assert [len(segment) for _, _, segment in session.calls] == [1, 99, 2, 98, 3, 2]
    assert [[int(row['item_id']) for row in segment] for _, _, segment in session.calls] == [
        [0], list(range(1, 100)), [100, 101], list(range(102, 200)), [200, 201, 202], [203, 204]]


@pytest.mark.parametrize('fail_after', [2, 101])
def test_yashandb_null_segment_driver_failure_rolls_back_without_retry(adapter, monkeypatch, fail_after):
    if adapter.DATABASE_DIALECT != 'yashandb':
        pytest.skip('YashanDB first-NULL indicator regression')
    session = first_null_driver_session(adapter, monkeypatch, fail_after=fail_after)
    with pytest.raises(ValueError, match='middle batch constraint violation') as raised:
        adapter.execute_many(BATCH_SQL, null_parameters(205))
    assert raised.value is session.failure
    assert [kind for kind, _, _ in session.calls] == ['native'] * (2 if fail_after == 2 else 3)
    assert not session.pending and not session.committed
    assert session.commits == 0 and session.rollbacks == 1
    assert len(session.cursors) == 1 and session.cursors[0].closed


def test_yashandb_null_segments_remain_pending_until_callback_audit_commits(adapter, monkeypatch):
    if adapter.DATABASE_DIALECT != 'yashandb':
        pytest.skip('YashanDB first-NULL indicator regression')
    session = first_null_driver_session(adapter, monkeypatch)
    values = null_parameters(205)
    def operation(tx):
        assert tx.execute_many(BATCH_SQL, values) == 205
        assert session.pending == values and session.commits == 0
        raise RuntimeError('audit failed after NULL-safe native segments')
    with pytest.raises(RuntimeError, match='audit failed after NULL-safe'):
        adapter.execute_transaction_callback(operation)
    assert [len(segment) for _, _, segment in session.calls] == [1, 99, 100, 5]
    assert not session.pending and not session.committed
    assert session.commits == 0 and session.rollbacks == 1
    assert all(cursor.closed for cursor in session.cursors)


@pytest.mark.parametrize('large_at', [0, 1, 99, 100, 199, 200, 204])
def test_yashandb_large_text_is_routed_before_send_without_reordering(adapter, monkeypatch, large_at):
    if adapter.DATABASE_DIALECT != 'yashandb':
        pytest.skip('YashanDB mixed large-text regression')
    session = first_null_driver_session(adapter, monkeypatch)
    values = null_parameters(205)
    values[large_at]['body'] = '原生长文本' * 12000
    original = [dict(row) for row in values]
    original_ids = [id(row) for row in values]
    assert adapter.execute_many(BATCH_SQL, values) == 205
    assert session.committed == values == original
    assert [id(row) for row in sent_rows(session)] == original_ids
    assert [data for kind, _, data in session.calls if kind == 'single'] == [values[large_at]]
    for kind, _, segment in session.calls:
        if kind == 'native':
            assert max(int(row['item_id']) // 100 for row in segment) == min(int(row['item_id']) // 100 for row in segment)
            assert all(len(row['body'].encode('utf-8')) <= 32767 for row in segment)
    assert session.commits == 1 and session.rollbacks == 0
    assert len(session.cursors) == 1 and session.cursors[0].closed


@pytest.mark.parametrize('body,kind', [('a' * 32766, 'native'), ('a' * 32767, 'native'),
    ('a' * 32768, 'single'), ('界' * 10922, 'native'), ('界' * 10923, 'single')],
    ids=['ascii-32766-native', 'ascii-32767-native', 'ascii-32768-single',
         'utf8-32766-native', 'utf8-32769-single'])
def test_yashandb_text_routing_ceiling_counts_utf8_bytes(adapter, monkeypatch, body, kind):
    if adapter.DATABASE_DIALECT != 'yashandb':
        pytest.skip('YashanDB application text routing ceiling')
    session = fake_session(adapter, monkeypatch)
    values = null_parameters(1)
    values[0]['body'] = body
    assert adapter.execute_many(BATCH_SQL, values) == 1
    assert session.calls[0][0] == kind and session.committed == values


@pytest.mark.parametrize('fail_after', [1, 2, 101])
def test_yashandb_large_text_path_rolls_back_without_replay(adapter, monkeypatch, fail_after):
    if adapter.DATABASE_DIALECT != 'yashandb':
        pytest.skip('YashanDB mixed large-text transaction regression')
    session = fake_session(adapter, monkeypatch, fail_after=fail_after)
    with pytest.raises(ValueError) as raised:
        adapter.execute_many(BATCH_SQL, parameters(205))
    assert raised.value is session.failure
    assert [kind for kind, _, _ in session.calls] == (['native', 'single'] if fail_after == 1 else
        ['native', 'single', 'native'] if fail_after == 2 else ['native', 'single', 'native', 'native'])
    assert session.commits == 0 and session.rollbacks == 1
    assert not session.committed and not session.pending
    assert len(session.cursors) == 1 and session.cursors[0].closed


def test_yashandb_large_text_remains_pending_until_business_audit(adapter, monkeypatch):
    if adapter.DATABASE_DIALECT != 'yashandb':
        pytest.skip('YashanDB mixed large-text transaction regression')
    session = fake_session(adapter, monkeypatch)
    values = parameters(205)
    def operation(tx):
        assert tx.execute_many(BATCH_SQL, values) == 205
        assert session.pending == values and session.commits == 0
        raise RuntimeError('audit failed after large text')
    with pytest.raises(RuntimeError, match='audit failed after large text'):
        adapter.execute_transaction_callback(operation)
    assert [(kind, len(data) if kind == 'native' else 1) for kind, _, data in session.calls] == [
        ('native', 1), ('single', 1), ('native', 98), ('native', 100), ('native', 5)]
    assert session.commits == 0 and session.rollbacks == 1
    assert not session.committed and not session.pending


def test_yashandb_array_to_scalar_prepares_equal_statement_without_cached_array_binds(adapter, monkeypatch):
    if adapter.DATABASE_DIALECT != 'yashandb':
        pytest.skip('YashanDB same-statement array/scalar metadata regression')
    session = fake_session(adapter, monkeypatch)
    class CachedArrayCursor(FakeCursor):
        array_statement = None
        def executemany(self, sql, rows):
            self.array_statement = sql
            return super().executemany(sql, rows)
        def execute(self, sql, params):
            if sql is self.array_statement:
                raise ValueError('YAS-00202 missing terminate character from cached array bind metadata')
            return super().execute(sql, params)
    def cursor(**kwargs):
        value = CachedArrayCursor(session)
        session.cursors.append(value)
        return value
    monkeypatch.setattr(session, 'cursor', cursor)
    values = null_parameters(8)
    for row, body in zip(values, ['short', 'a'*32766, 'a'*32767, 'a'*32768,
                                  '界'*10922, '界'*10923, '原生长文本'*12000, 'tail']):
        row['body'] = body
    original = [dict(row) for row in values]
    assert adapter.execute_many(BATCH_SQL, values) == 8
    assert session.committed == values == original
    assert [kind for kind, _, _ in session.calls] == ['native', 'native', 'single', 'native', 'single', 'single', 'native']
    assert all(statement == BATCH_SQL for _, statement, _ in session.calls)
    scalar_statements = [statement for kind, statement, _ in session.calls if kind == 'single']
    assert all(statement is not BATCH_SQL for statement in scalar_statements)
    assert len({id(statement) for statement in scalar_statements}) == 3
    assert len(session.cursors) == 1 and session.cursors[0].closed
    assert session.commits == 1 and session.rollbacks == 0


def install_relational_batch(monkeypatch, db, *, native, calls, corrupt=False):
    """Count client API calls on identical relational state, not native latency."""
    original = assembly.connection.execute_transaction_callback
    def transaction(callback):
        def perform(tx):
            class Transaction:
                def execute(self, statement, params):
                    calls.append(('single', statement, 1))
                    return tx.execute(statement, params)
                def query(self, statement, params):
                    calls.append(('query', statement, 1))
                    return tx.query(statement, params)
                def query_one(self, statement, params):
                    rows = self.query(statement, params)
                    return rows[0] if rows else None
            wrapped = Transaction()
            if native:
                def execute_many(statement, rows):
                    calls.append(('batch', statement, len(rows)))
                    if corrupt and 'CX_CONTEXT_ASSEMBLY_ITEMS' in statement:
                        rows = [*rows[:1], dict(rows[1], v_item_no=1), *rows[2:]]
                    return db.executemany(statement, rows).rowcount
                wrapped.execute_many = execute_many
            return callback(wrapped)
        return original(perform)
    monkeypatch.setattr(assembly.connection, 'execute_transaction_callback', transaction)
    return original


def handoff_sources(db, count):
    sources = []
    for index in range(count):
        wid = work.create_work('owner', work_request(key='source-' + str(index)))['work_contract_id']
        hid = handoff.offer('owner', wid, offer_request(key='offer-' + str(index)))['handoff_id']
        record = handoff.read_handoff('owner', hid)
        sources.append(dict(family='HANDOFF', entity_id=hid, revision_id='1', content_digest=record['content_digest']))
    return sources


@pytest.mark.parametrize('count', [1, 8, 32])
def test_assembly_frozen_sources_have_equivalent_order_and_fewer_write_calls(context_db, monkeypatch, count):
    db, _ = context_db
    for statement in context_selection.schema_statements('pg'):
        db.execute(statement)
    db.commit()
    sources = handoff_sources(db, count)
    value = dict(request_id='frozen', security_domain_id='domain', purpose='same frozen input',
                 sources=sources, token_budget=131072, entry_limit=100, context_window=131072)
    serial_calls = []
    original = install_relational_batch(monkeypatch, db, native=False, calls=serial_calls)
    before = assembly.assemble('owner', dict(value, idempotency_key='serial'))
    baseline = assembly.read_assembly('owner', before['assembly_id'])
    monkeypatch.setattr(assembly.connection, 'execute_transaction_callback', original)
    batch_calls = []
    install_relational_batch(monkeypatch, db, native=True, calls=batch_calls)
    after = assembly.assemble('owner', dict(value, idempotency_key='batch'))
    optimized = assembly.read_assembly('owner', after['assembly_id'])
    assert before['content_digest'] == after['content_digest']
    assert baseline['text'] == optimized['text']
    fields = ('family', 'entity_id', 'revision_id', 'content_digest', 'rendered_digest', 'item_no')
    assert [[row[name] for name in fields] for row in baseline['items']] == [
        [row[name] for name in fields] for row in optimized['items']]
    assert sum('INSERT INTO CX_CONTEXT_ASSEMBLY_ITEMS' in sql for _, sql, _ in serial_calls) == count
    assert sum('INSERT INTO CX_CONTEXT_ASSEMBLY_ITEMS' in sql for _, sql, _ in batch_calls) == 1
    assert sum('INSERT INTO CX_CONTEXT_REPRESENTATIONS' in sql for _, sql, _ in serial_calls) == count
    assert sum('INSERT INTO CX_CONTEXT_REPRESENTATIONS' in sql for _, sql, _ in batch_calls) == 1
    grant_queries = [sql for kind, sql, _ in batch_calls if kind == 'query' and 'FROM CX_CONTEXT_ITEM_GRANTS' in sql]
    assert len(grant_queries) == 1 and 'ITEM_NO=:' not in grant_queries[0]
    assert [item['entity_id'] for item in optimized['items']] == [item['entity_id'] for item in sources]


def test_assembly_batch_constraint_failure_has_no_header_items_or_audit(context_db, monkeypatch):
    db, _ = context_db
    sources = handoff_sources(db, 3)
    audit_count = db.execute('SELECT COUNT(*) FROM AUDIT').fetchone()[0]
    install_relational_batch(monkeypatch, db, native=True, calls=[], corrupt=True)
    with pytest.raises(sqlite3.IntegrityError):
        assembly.assemble('owner', dict(request_id='bad', security_domain_id='domain', purpose='constraint rollback',
                                     sources=sources, idempotency_key='bad'))
    assert db.execute('SELECT COUNT(*) FROM CX_CONTEXT_ASSEMBLIES').fetchone()[0] == 0
    assert db.execute('SELECT COUNT(*) FROM CX_CONTEXT_ASSEMBLY_ITEMS').fetchone()[0] == 0
    assert db.execute('SELECT COUNT(*) FROM AUDIT').fetchone()[0] == audit_count


def test_assembly_native_items_and_grants_roll_back_when_audit_fails(publication_db, monkeypatch):
    db, source = publication_db
    publications.publish('owner', publication(source))
    audit_count = db.execute('SELECT COUNT(*) FROM AUDIT').fetchone()[0]
    calls = []
    install_relational_batch(monkeypatch, db, native=True, calls=calls)
    original = assembly.identity_api._audit_tx
    def audit(tx, actor, action, *args):
        if action == 'CONTEXT_PREPARED':
            raise RuntimeError('audit unavailable after native batches')
        return original(tx, actor, action, *args)
    monkeypatch.setattr(assembly.identity_api, '_audit_tx', audit)
    with pytest.raises(RuntimeError, match='audit unavailable'):
        prepare(source)
    assert any(kind == 'batch' and 'CX_CONTEXT_ASSEMBLY_ITEMS' in sql for kind, sql, _ in calls)
    assert any(kind == 'batch' and 'CX_CONTEXT_ITEM_GRANTS' in sql for kind, sql, _ in calls)
    for table in ('CX_CONTEXT_ASSEMBLIES', 'CX_CONTEXT_ASSEMBLY_ITEMS', 'CX_CONTEXT_ITEM_GRANTS'):
        assert db.execute('SELECT COUNT(*) FROM ' + table).fetchone()[0] == 0
    assert db.execute('SELECT COUNT(*) FROM AUDIT').fetchone()[0] == audit_count


@pytest.mark.parametrize('mutation', ['MISSING', 'REVOKED', 'EXPIRED', 'PUBLISHER_REVOKED'])
def test_batch_grant_metadata_keeps_original_publication_and_live_authority(publication_db, monkeypatch, mutation):
    db, source = publication_db
    first = publications.publish('owner', publication(source))
    prepared = prepare(source)
    publications.publish('owner', publication(source, key='replacement'))
    install_relational_batch(monkeypatch, db, native=True, calls=[])
    if mutation == 'MISSING':
        db.execute('DELETE FROM CX_CONTEXT_ITEM_GRANTS WHERE ASSEMBLY_ID=?', (prepared['assembly_id'],))
    elif mutation == 'REVOKED':
        db.execute("UPDATE CX_CONTEXT_PUBLICATIONS SET STATUS='REVOKED' WHERE PUBLICATION_ID=?", (first['publication_id'],))
    elif mutation == 'EXPIRED':
        db.execute("UPDATE CX_CONTEXT_PUBLICATIONS SET EXPIRES_AT='2000-01-01' WHERE PUBLICATION_ID=?", (first['publication_id'],))
    else:
        db.execute("UPDATE CX_DOMAIN_MEMBERS SET STATUS='REVOKED' WHERE PRINCIPAL_ID='owner' AND SECURITY_DOMAIN_ID='domain'")
    db.commit()
    if mutation != 'PUBLISHER_REVOKED':
        # A replacement is currently usable for a *new* assembly. It cannot
        # repair the frozen original assembly or its missing binding.
        assert prepare(source, key='replacement-assembly')['item_count'] == 1
    with pytest.raises(PermissionError):
        assembly.read_assembly('outsider', prepared['assembly_id'])


@pytest.mark.parametrize('fail_middle', [False, True])
def test_snapshot_members_batch_keeps_exact_order_or_rolls_back_header(fail_middle):
    db = sqlite3.connect(':memory:')
    db.execute('PRAGMA foreign_keys=ON')
    db.executescript('''
        CREATE TABLE CX_MEMORY_SNAPSHOTS(SNAPSHOT_ID TEXT PRIMARY KEY,RUN_ID TEXT,SNAPSHOT_VERSION INTEGER,
          PURPOSE TEXT,POLICY_VERSION TEXT,QUERY_DIGEST TEXT,SNAPSHOT_DIGEST TEXT,STATE TEXT,CREATED_BY TEXT,
          IDEMPOTENCY_KEY TEXT,PRINCIPAL_ID TEXT,PRINCIPAL_PERMISSION_VERSION INTEGER,AGENT_INSTANCE_ID TEXT,
          AGENT_FENCING_TOKEN INTEGER);
        CREATE TABLE CX_MEMORY_SNAPSHOT_MEMBERS(SNAPSHOT_ID TEXT REFERENCES CX_MEMORY_SNAPSHOTS(SNAPSHOT_ID),
          FAMILY_ID TEXT,VERSION_ID TEXT,REPRESENTATION_ID TEXT,SELECTION_RANK INTEGER CHECK(SELECTION_RANK>=0),
          SELECTED_TOKENS INTEGER,PRIMARY KEY(SNAPSHOT_ID,FAMILY_ID));
    ''')
    calls = []
    class Tx:
        def execute(self, sql, params):
            return db.execute(sql, params).rowcount
        def execute_many(self, sql, rows):
            calls.append(list(rows))
            if fail_middle:
                rows[1] = dict(rows[1], rank=-1)
            return db.executemany(sql, rows).rowcount
    members = [dict(family_id='family-' + str(index), version_id='version-' + str(index),
                    representation_id='representation-' + str(index), rank=index, tokens=index + 1) for index in range(4)]
    subject = dict(principal_id='owner', principal_permission_version=4, agent_instance_id='instance', agent_fencing_token=9)
    try:
        with db:
            result = memory._insert_snapshot(Tx(), snapshot_id='snapshot', run_id='run', actor='owner',
                purpose='RUNTIME_CONTEXT', query_version='frozen', idempotency_key='same', members=members, subject=subject)
    except sqlite3.IntegrityError:
        assert fail_middle
        assert db.execute('SELECT COUNT(*) FROM CX_MEMORY_SNAPSHOTS').fetchone()[0] == 0
        assert db.execute('SELECT COUNT(*) FROM CX_MEMORY_SNAPSHOT_MEMBERS').fetchone()[0] == 0
    else:
        assert not fail_middle and result['members'] == 4 and result['token_count'] == 10
        assert db.execute('SELECT PRINCIPAL_ID,PRINCIPAL_PERMISSION_VERSION,AGENT_INSTANCE_ID,AGENT_FENCING_TOKEN '
                          'FROM CX_MEMORY_SNAPSHOTS').fetchone() == ('owner', 4, 'instance', 9)
        assert db.execute('SELECT FAMILY_ID,VERSION_ID,REPRESENTATION_ID,SELECTION_RANK,SELECTED_TOKENS '
                          'FROM CX_MEMORY_SNAPSHOT_MEMBERS ORDER BY SELECTION_RANK').fetchall() == [
            tuple(member[name] for name in ('family_id', 'version_id', 'representation_id', 'rank', 'tokens')) for member in members]
    finally:
        assert len(calls) == 1
        db.close()
