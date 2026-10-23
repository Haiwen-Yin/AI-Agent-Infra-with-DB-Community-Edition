"""AI Agent Infra v5.0.1 - Community Edition - Database Connection Pool Manager

psycopg2-based connection pool with parameterized query support.
Supports Admin/Agent separation modes (standalone, admin, agent).
"""

import json
import re
import threading
from contextvars import ContextVar
import logging
import time
from contextlib import contextmanager
from typing import Any, Dict, List, Optional

import psycopg2
from psycopg2 import pool as pg_pool
from psycopg2.extras import RealDictCursor

from .config import get_config, DatabaseConfig, AgentModeConfig
from lib.transaction_reads import TransactionReads, connection_identity

logger = logging.getLogger(__name__)
DATABASE_DIALECT = "postgresql"


def scalar_select_suffix() -> str:
    return ""


def database_version_observation() -> str:
    """Server handshake metadata, not the client library version."""
    with get_connection_for_agent() as conn:
        value=int(conn.server_version)
        return f'{value//10000}.{value%10000}'


def merge_scalar_suffix() -> str:
    """PostgreSQL permits a scalar SELECT without a table source."""
    return ""

_pool: Optional[pg_pool.ThreadedConnectionPool] = None
_lock = threading.Lock()
_pool_slots: Optional[threading.BoundedSemaphore] = None
_POOL_WAIT_SECONDS = 5.0


def _init_pool(cfg: DatabaseConfig) -> pg_pool.ThreadedConnectionPool:
    pool = pg_pool.ThreadedConnectionPool(
        minconn=cfg.min_conn,
        maxconn=cfg.max_conn,
        host=cfg.host,
        port=cfg.port,
        dbname=cfg.dbname,
        user=cfg.user,
        password=cfg.password,
    )
    pool.min = cfg.min_conn
    pool.max = cfg.max_conn
    return pool


def get_pool() -> pg_pool.ThreadedConnectionPool:
    global _pool, _pool_slots
    if _pool is None:
        with _lock:
            if _pool is None:
                cfg = get_config()
                if cfg.agent.mode == "agent":
                    raise RuntimeError("Schema owner pool not available in agent mode")
                db_cfg = cfg.database
                logger.info("Initializing connection pool: %s@%s:%d/%s (min=%d, max=%d)",
                            db_cfg.user, db_cfg.host, db_cfg.port, db_cfg.dbname,
                            db_cfg.min_conn, db_cfg.max_conn)
                _pool = _init_pool(db_cfg)
                # psycopg2 raises PoolError immediately when its configured
                # maximum is in use. Dashboard views legitimately issue a
                # short burst of guarded reads, so queue briefly while still
                # honoring the configured database connection ceiling.
                _pool_slots = threading.BoundedSemaphore(db_cfg.max_conn)
    return _pool


_agent_eu_creds = None
_agent_eu_lock = threading.Lock()
_end_user_connections: dict = {}
_end_user_lock = threading.Lock()
_end_user_generations: dict[str, int] = {}
_revoked_end_users: set[str] = set()


def _load_agent_eu_creds() -> dict:
    global _agent_eu_creds
    with _agent_eu_lock:
        if _agent_eu_creds is not None:
            return _agent_eu_creds
        cfg = get_config()
        config_path = cfg.project_root / "agent_config.json"
        if not config_path.exists():
            raise FileNotFoundError(f"agent_config.json not found at {config_path}")
        from .connection_crypto import load_agent_config
        creds = load_agent_config(config_path)
        _agent_eu_creds = creds
        return _agent_eu_creds


def _connect_with_credentials(creds: dict):
    dsn = creds.get("dsn", "")
    dsn_parts = dsn.split(":", 2) if dsn else []
    host = creds.get("host") or (dsn_parts[0] if len(dsn_parts) == 3 else "localhost")
    port = creds.get("port") or (dsn_parts[1] if len(dsn_parts) == 3 else 5432)
    dbname = creds.get("dbname") or (dsn_parts[2] if len(dsn_parts) == 3 else dsn)
    conn = psycopg2.connect(
        host=host,
        port=int(port),
        dbname=dbname,
        user=creds.get("username"),
        password=creds.get("password"),
    )
    conn.autocommit = False
    return conn


def _get_agent_mode_connection():
    return _connect_with_credentials(_load_agent_eu_creds())


def _load_admin_mode_agent_credentials(agent_id: str) -> dict:
    from .connection_crypto import decrypt_section

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT config_value FROM system_config WHERE config_key = %s",
                (f"pg_end_user.{agent_id}",),
            )
            row = cur.fetchone()
    if not row or not row[0]:
        raise RuntimeError(f"No PostgreSQL login credentials for agent {agent_id}")
    return decrypt_section(row[0])


@contextmanager
def get_connection():
    cfg = get_config()
    if cfg.agent.mode == "agent":
        creds = _load_agent_eu_creds()
        with _independent_agent_connection(creds, creds.get("agent_id") or "agent") as conn:
            yield conn
        return
    pool = get_pool()
    slots = _pool_slots
    if slots is None or not slots.acquire(timeout=_POOL_WAIT_SECONDS):
        raise RuntimeError(
            f"PostgreSQL connection pool is busy after {_POOL_WAIT_SECONDS:g}s; "
            "reduce concurrent requests or increase database.pool_max"
        )
    conn = None
    try:
        conn = pool.getconn()
        yield conn
    finally:
        try:
            if conn is not None:
                try:
                    conn.rollback()
                except Exception:
                    pass
                pool.putconn(conn)
        finally:
            slots.release()


def normalize_execution_reference(kind: str, value: str):
    """Native Task/Workspace identifiers are BIGINT; reject invalid locators before SQL."""
    if kind not in {'TASK','WORKSPACE'}:
        return value
    text=str(value)
    if not text.isascii() or not text.isdecimal() or len(text)>19:
        raise ValueError('Invalid native execution identifier')
    number=int(text)
    if number<1 or number>9223372036854775807 or str(number)!=text:
        raise ValueError('Invalid native execution identifier')
    return number


def get_current_agent_id() -> Optional[str]:
    return _agent_context.get()


_agent_context: ContextVar[Optional[str]] = ContextVar("cx_pg_agent_id", default=None)


def set_agent_context(agent_id: Optional[str]) -> None:
    _agent_context.set(agent_id)


def _transaction_read_identity():
    cfg = get_config()
    credentials = _load_agent_eu_creds() if cfg.agent.mode == "agent" else None
    return connection_identity(cfg, get_current_agent_id(), credentials)


_transaction_reads = TransactionReads(_transaction_read_identity)


def evict_agent_connections(agent_id: str, *, revoke: bool = False) -> dict:
    """Close only locally tracked connections, never shared roles or sessions."""
    with _end_user_lock:
        _end_user_generations[agent_id] = _end_user_generations.get(agent_id, 0) + 1
        if revoke:
            _revoked_end_users.add(agent_id)
        keys = [key for key in _end_user_connections if key[1] == agent_id]
        retired = [(key, _end_user_connections.pop(key)) for key in keys]
    closed = failed = 0
    for key, conn in retired:
        try:
            conn.close()
            closed += 1
        except Exception:
            failed += 1
            with _end_user_lock:
                _end_user_connections[(key[0], agent_id, "retired", id(conn))] = conn
    return {"closed": closed, "failed": failed}


def close_end_user_connections():
    with _end_user_lock:
        agents = set(_end_user_generations) | {key[1] for key in _end_user_connections}
    for agent_id in agents:
        evict_agent_connections(agent_id)


@contextmanager
def _independent_agent_connection(creds: dict, agent_id: str):
    with _end_user_lock:
        if agent_id in _revoked_end_users:
            raise RuntimeError("Agent native identity is revoked")
        generation = _end_user_generations.setdefault(agent_id, 0)
    conn = _connect_with_credentials(creds)
    key = (threading.get_ident(), agent_id, id(conn))
    try:
        apply_agent_context(conn, agent_id)
        with _end_user_lock:
            if agent_id in _revoked_end_users or _end_user_generations.get(agent_id, 0) != generation:
                raise RuntimeError("Agent native identity changed during connection")
            _end_user_connections[key] = conn
        yield conn
    finally:
        with _end_user_lock:
            _end_user_connections.pop(key, None)
        try:
            if not conn.closed:
                conn.rollback()
        finally:
            conn.close()


@contextmanager
def get_connection_for_agent(agent_id: Optional[str] = None):
    cfg = get_config()
    aid = agent_id or get_current_agent_id()
    if cfg.agent.mode == "agent":
        creds = _load_agent_eu_creds()
        configured_agent_id = creds.get("agent_id")
        if aid and configured_agent_id and aid != configured_agent_id:
            raise RuntimeError("Agent identity does not match agent_config.json")
        with _independent_agent_connection(creds, configured_agent_id or aid or "agent") as conn:
            yield conn
        return
    if aid:
        creds = _load_admin_mode_agent_credentials(aid)
        with _independent_agent_connection(creds, aid) as conn:
            yield conn
        return
    with get_connection() as conn:
        yield conn


def apply_agent_context(conn, agent_id: Optional[str] = None) -> None:
    aid = agent_id or get_current_agent_id()
    if not aid:
        return
    with conn.cursor() as cur:
        cur.execute("SELECT set_config('app.current_agent_id', %s, true)", (aid,))


def clear_agent_context(conn) -> None:
    with conn.cursor() as cur:
        cur.execute("SELECT set_config('app.current_agent_id', '', true)")


def close_pool():
    global _pool, _pool_slots
    close_end_user_connections()
    if _pool is not None:
        _pool.closeall()
        _pool = None
    _pool_slots = None


def _convert_params(sql: str, params: Optional[Any]) -> tuple:
    """Convert Oracle-style :param to psycopg2 %s style.
    Supports both dict params (:param style) and tuple/list params (%s style).
    
    For dict params:
    - Each :param is replaced with %s and value collected in order of appearance
    - Existing %s placeholders get values from dict keys 'limit', 'offset', etc.
      (for backwards compat with PG-native SQL that uses LIMIT %s)
    
    For tuple/list params:
    - %s placeholders are used as-is with values in order
    """
    sql = sql.replace("AI_NEW_ID()", "md5(random()::text || clock_timestamp()::text)")
    if params is None:
        return sql, None
    if isinstance(params, dict):
        import re
        ordered_values = []
        
        # First, replace all :param with %s and collect values
        def replace_param(match):
            key = match.group(1)
            if key in params:
                ordered_values.append(params[key])
                return '%s'
            return match.group(0)
        converted = re.sub(r':(\w+)', replace_param, sql)

        # Keep shared Oracle/YashanDB pagination SQL portable.  PostgreSQL's
        # parameterized LIMIT form is accepted consistently by psycopg2,
        # including queries generated by the governance APIs.
        converted = re.sub(
            r'FETCH\s+FIRST\s+%s\s+ROWS\s+ONLY',
            'LIMIT %s',
            converted,
            flags=re.IGNORECASE,
        )
        
        # Now handle any remaining %s placeholders that weren't from :param
        # These come from PG-native SQL (e.g., LIMIT %s)
        # We need to provide values for them from the dict
        # Count remaining %s and try to match with dict values not yet used
        remaining_s = converted.count('%s') - len(ordered_values)
        if remaining_s > 0:
            # Find dict keys that weren't used by :param replacement
            used_keys = set()
            for m in re.finditer(r':(\w+)', sql):
                if m.group(1) in params:
                    used_keys.add(m.group(1))
            # Common positional keys in order of typical SQL appearance
            positional_keys = ['limit', 'offset', 'status', 'agent_id', 'workspace_id']
            for key in positional_keys:
                if key in params and key not in used_keys and remaining_s > 0:
                    ordered_values.append(params[key])
                    used_keys.add(key)
                    remaining_s -= 1
            # If still remaining, add any unused values
            for key in params:
                if remaining_s <= 0:
                    break
                if key not in used_keys:
                    ordered_values.append(params[key])
                    used_keys.add(key)
                    remaining_s -= 1
        
        return converted, tuple(ordered_values)
    elif isinstance(params, (list, tuple)):
        return sql, tuple(params)
    return sql, None


def execute(sql: str, params: Optional[Dict[str, Any]] = None) -> int:
    sql, pg_params = _convert_params(sql, params)
    with get_connection_for_agent() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, pg_params)
            conn.commit()
            return cur.rowcount


def execute_query(sql: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    sql, pg_params = _convert_params(sql, params)
    with _transaction_reads.connection(get_connection_for_agent) as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, pg_params)
            return [dict(row) for row in cur.fetchall()]


def execute_query_one(sql: str, params: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    sql, pg_params = _convert_params(sql, params)
    with _transaction_reads.connection(get_connection_for_agent) as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, pg_params)
            row = cur.fetchone()
            if not _transaction_reads.owns(conn):
                conn.commit()
            return dict(row) if row else None


def execute_insert(sql: str, params: Optional[Dict[str, Any]] = None) -> str:
    sql, pg_params = _convert_params(sql, params)
    with get_connection_for_agent() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, pg_params)
            conn.commit()
            return "ok"


def execute_insert_returning_id(
    sql: str,
    params: Optional[Dict[str, Any]] = None,
    returning_col: str = None,
    id_column: str = None
) -> str:
    """Execute INSERT with RETURNING clause and return the ID.
    
    For PostgreSQL, the RETURNING clause is already in the SQL.
    The :ret_id bind variable should be removed from the SQL before calling.
    `id_column` is an alias for `returning_col` for Oracle API compatibility.
    
    Handles Oracle-style SQL that supplies an ID via `'PREFIX_' || RAWTOHEX(SYS_GUID())`
    in the VALUES list: if the target column is a GENERATED ALWAYS AS IDENTITY column,
    the ID column and its value expression are stripped from the INSERT so PG's
    IDENTITY sequence generates the value instead.
    """
    import re
    if id_column and not returning_col:
        returning_col = id_column
    if not returning_col:
        match = re.search(r'\bRETURNING\s+([A-Za-z_][\w]*)', sql, re.IGNORECASE)
        if match:
            returning_col = match.group(1)
    sql, pg_params = _convert_params(sql, params)
    # Remove any RETURNING ... INTO :ret_id clause (Oracle-specific)
    if "INTO :ret_id" in sql:
        sql = sql.replace("INTO :ret_id", "")
    if "RETURNING" in sql.upper() and "INTO" in sql:
        sql = re.sub(r'\s+INTO\s+:\w+', '', sql, flags=re.IGNORECASE)

    # If RETURNING clause is not in SQL, add it
    if returning_col and "RETURNING" not in sql.upper():
        col = returning_col.lower() if not returning_col.startswith(':') else returning_col
        sql = sql.rstrip().rstrip(';') + f' RETURNING {col}'

    # Strip IDENTITY-column + value expression if PG schema uses GENERATED ALWAYS AS IDENTITY.
    # This translates Oracle-style "INSERT INTO T (ID, A, B) VALUES (expr, :a, :b) RETURNING ID"
    # into PG-style "INSERT INTO T (A, B) VALUES (:a, :b) RETURNING ID".
    if returning_col:
        sql = _strip_identity_column(sql, returning_col)

    with get_connection_for_agent() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, pg_params)
            row = cur.fetchone()
            conn.commit()
            if row:
                val = row[0]
                if isinstance(val, int):
                    return val
                return str(val)
            return None


_identity_cache: Dict[str, bool] = {}


def _is_identity_column(conn, table: str, column: str) -> bool:
    """Cached check: is (table.column) GENERATED ALWAYS AS IDENTITY?"""
    key = f"{table.lower()}.{column.lower()}"
    cached = _identity_cache.get(key)
    if cached is not None:
        return cached
    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT is_identity FROM information_schema.columns
                   WHERE table_name = LOWER(%s) AND column_name = LOWER(%s)""",
                (table.lower(), column.lower()),
            )
            row = cur.fetchone()
            is_ident = bool(row and row[0] == "YES")
    except Exception:
        is_ident = False
    _identity_cache[key] = is_ident
    return is_ident


def _strip_identity_column(sql: str, id_col: str) -> str:
    """If the INSERT supplies a value for an IDENTITY column, strip both the
    column from the column list and its value expression from the VALUES list.

    Only the *first* positional column (the ID) is stripped, matching the
    Oracle-style layout where the ID is the first column.
    """
    m = re.search(
        r'INSERT\s+INTO\s+([A-Za-z_][\w.]*)\s*\(\s*([^)]+)\)\s*VALUES\s*\(',
        sql,
        re.IGNORECASE,
    )
    if not m:
        return sql
    table = m.group(1).split('.')[-1]
    col_list = [c.strip().strip('"').lower() for c in m.group(2).split(',')]
    id_col_l = id_col.lower()
    if id_col_l not in col_list:
        return sql
    idx = col_list.index(id_col_l)
    if idx != 0:
        return sql  # only handle leading ID column

    # Lazy: check identity status against a fresh connection
    try:
        with get_connection() as conn:
            if not _is_identity_column(conn, table, id_col):
                return sql
    except Exception:
        return sql

    # Split columns and values by top-level commas (values may contain commas inside parens)
    vals_start = sql.index('VALUES', m.start()) + len('VALUES')
    vals_open = sql.index('(', vals_start)
    vals_close = _find_matching_paren(sql, vals_open)

    new_cols = [c for i, c in enumerate(col_list) if i != idx]
    val_items = _split_top_level_commas(sql[vals_open + 1:vals_close])
    new_vals = [v for i, v in enumerate(val_items) if i != idx]

    insert_kw = sql[:m.start()]
    after_vals = sql[vals_close + 1:]
    new_col_str = ', '.join(f'"{c.upper()}"' if c.isupper() else c for c in new_cols)
    # Use original column-name casing from the source SQL where possible
    orig_cols = [c.strip() for c in m.group(2).split(',')]
    orig_cols_kept = [c for i, c in enumerate(orig_cols) if i != idx]
    new_col_str = ', '.join(orig_cols_kept)
    new_val_str = ', '.join(v.strip() for v in new_vals)
    return f"{insert_kw}INSERT INTO {m.group(1)} ({new_col_str}) VALUES ({new_val_str}){after_vals}"


def _find_matching_paren(s: str, open_idx: int) -> int:
    depth = 0
    for i in range(open_idx, len(s)):
        c = s[i]
        if c == '(':
            depth += 1
        elif c == ')':
            depth -= 1
            if depth == 0:
                return i
    return -1


def _split_top_level_commas(s: str) -> List[str]:
    parts = []
    depth = 0
    cur = ''
    for c in s:
        if c == '(':
            depth += 1
            cur += c
        elif c == ')':
            depth -= 1
            cur += c
        elif c == ',' and depth == 0:
            parts.append(cur)
            cur = ''
        else:
            cur += c
    if cur.strip():
        parts.append(cur)
    return parts


def execute_many(sql: str, params_list) -> int:
    """Execute a batch INSERT/UPDATE/DELETE."""
    with get_connection_for_agent() as conn:
        with conn.cursor() as cur:
            for params in params_list:
                converted_sql, converted_params = _convert_params(sql, params)
                cur.execute(converted_sql, converted_params)
            conn.commit()
            return cur.rowcount


def execute_transaction(statements: List[tuple[str, Optional[Dict[str, Any]]]]) -> int:
    """Execute shared-style SQL statements atomically on one PG session."""
    return sum(execute_transaction_result(statements))


def execute_transaction_result(statements: List[tuple[str, Optional[Dict[str, Any]]]]) -> List[int]:
    """Execute statements atomically and return each statement row count."""
    with get_connection_for_agent() as conn:
        try:
            with conn.cursor() as cur:
                counts = []
                for sql, params in statements:
                    converted_sql, converted_params = _convert_params(sql, params)
                    cur.execute(converted_sql, converted_params)
                    counts.append(max(cur.rowcount, 0))
            conn.commit()
            return counts
        except Exception:
            conn.rollback()
            raise


class _Transaction:
    """Small DB-API transaction facade shared by Graph Runtime."""

    def __init__(self, conn):
        self.conn = conn
        self.cursor = conn.cursor(cursor_factory=RealDictCursor)

    def execute(self, sql: str, params: Optional[Dict[str, Any]] = None) -> int:
        converted_sql, converted_params = _convert_params(sql, params)
        self.cursor.execute(converted_sql, converted_params)
        return max(self.cursor.rowcount, 0)

    def query(self, sql: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        converted_sql, converted_params = _convert_params(sql, params)
        self.cursor.execute(converted_sql, converted_params)
        return [dict(row) for row in self.cursor.fetchall()]

    def query_one(self, sql: str, params: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        rows = self.query(sql, params)
        return rows[0] if rows else None

    def close(self) -> None:
        self.cursor.close()


def execute_transaction_callback(callback):
    """Run a callback with query and write access on one atomic connection."""
    with get_connection_for_agent() as conn:
        tx = _Transaction(conn)
        try:
            with _transaction_reads.bind(conn):
                result = callback(tx)
                conn.commit()
                return result
        except Exception:
            conn.rollback()
            raise
        finally:
            tx.close()


def sanitize_row(row) -> Dict[str, Any]:
    """Convert a RealDictRow to a plain dict, handling Decimal and datetime."""
    if row is None:
        return {}
    d = dict(row) if not isinstance(row, dict) else row
    # Convert Decimal to float for JSON serialization
    for k, v in d.items():
        if isinstance(v, Decimal):
            d[k] = float(v)
    return d


def _row_to_dict(row) -> Dict[str, Any]:
    return sanitize_row(row)


# Import Decimal for sanitize_row
from decimal import Decimal
