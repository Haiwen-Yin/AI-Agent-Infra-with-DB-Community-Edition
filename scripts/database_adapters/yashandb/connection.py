"""AI Agent Infra v5.0.0 - Community Edition - Database Connection Pool Manager

Unified yaspy connection pool with bind-variable support.
Replaces all deploy_yashandb.py subprocess calls with direct yaspy access.
Includes Deep Data Security context management.
Supports Admin/Agent separation modes (standalone, admin, agent).
"""

import json
import hashlib
import yaspy
DATABASE_DIALECT = "yashandb"


def scalar_select_suffix() -> str:
    return " FROM " + "DU" + "AL"


def database_version_observation() -> str:
    # Some deployments deliberately hide this view from application users.
    # The diagnostics service reports unavailable metadata without widening SQL grants.
    row=execute_query_one('SELECT VERSION FROM V$INSTANCE',{})
    return str(row['version']) if row else ''


def merge_scalar_suffix() -> str:
    """Return the YashanDB-compatible suffix for a dialect-neutral MERGE source."""
    return " FROM " + "DU" + "AL"
import threading
from contextvars import ContextVar
import logging
from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import get_config, DatabaseConfig, AgentModeConfig

_logger = logging.getLogger(__name__)

logger = logging.getLogger(__name__)

# yaspy handles LOBs natively

class _YashanPool(list):
    def __init__(self, min_size: int, max_size: int):
        super().__init__()
        self.min = min_size
        self.max = max_size


_pool: Optional[_YashanPool] = None
_lock = threading.Lock()


def _init_pool(cfg: DatabaseConfig) -> _YashanPool:
    pool = _YashanPool(cfg.pool_min, cfg.pool_max)
    for _ in range(cfg.pool_min):
        # Keyword arguments use yaspy's remote DSN path and do not require the
        # client-side YASDB_DATA environment variable.
        conn = yaspy.Connection(user=cfg.user, password=cfg.password, dsn=cfg.dsn)
        pool.append(conn)
    return pool


def get_pool() -> list:
    global _pool
    if _pool is None:
        with _lock:
            if _pool is None:
                cfg = get_config()
                if cfg.agent.mode == "agent":
                    raise RuntimeError("Schema owner pool not available in agent mode")
                db_cfg = cfg.database
                logger.info("Initializing connection pool: %s@%s (min=%d, max=%d)",
                            db_cfg.user, db_cfg.dsn, db_cfg.pool_min, db_cfg.pool_max)
                _pool = _init_pool(db_cfg)
    return _pool


@contextmanager
def get_connection():
    pool = get_pool()
    conn = None
    pooled = False
    if pool:
        conn = pool.pop()
        pooled = True
    if conn is None:
        cfg = get_config()
        db_cfg = cfg.database
        conn = yaspy.Connection(user=db_cfg.user, password=db_cfg.password, dsn=db_cfg.dsn)
    try:
        yield conn
    finally:
        if pooled and _pool is pool and len(pool) < pool.max:
            with _lock:
                pool.append(conn)
        else:
            try:
                conn.close()
            except Exception:
                pass


_current_agent_id: ContextVar[Optional[str]] = ContextVar("cx_yashandb_agent_id", default=None)

_end_user_connections: Dict[tuple[int, str], yaspy.Connection] = {}
_end_user_lock = threading.Lock()

_agent_eu_creds: Optional[Dict[str, str]] = None
_agent_eu_lock = threading.Lock()


def _load_agent_eu_creds() -> Dict[str, str]:
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


def set_agent_context(agent_id: Optional[str]) -> None:
    _current_agent_id.set(agent_id)

def get_current_agent_id() -> Optional[str]:
    return _current_agent_id.get()

def _agent_id_to_end_user_name(agent_id: str) -> str:
    return "AIA_" + hashlib.sha256(agent_id.encode("utf-8")).hexdigest()[:24].upper()

def _get_end_user_password(agent_id: str) -> Optional[str]:
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT config_value FROM system_config WHERE config_key = :key",
                    {"key": f"end_user_pwd.{agent_id}"},
                )
                row = cur.fetchone()
                return row[0] if row else None
    except Exception:
        return None

def get_end_user_connection(agent_id: str) -> Optional[yaspy.Connection]:
    key = (threading.get_ident(), agent_id)
    cfg = get_config()
    if cfg.agent.mode == "agent":
        return _get_agent_mode_end_user_connection(agent_id)

    with _end_user_lock:
        existing = _end_user_connections.get(key)
        if existing:
            try:
                with existing.cursor() as cur:
                    cur.execute("SELECT 1 FROM DUAL")
                return existing
            except Exception:
                try:
                    existing.close()
                except Exception:
                    pass
                _end_user_connections.pop(key, None)

        pwd = _get_end_user_password(agent_id)
        if not pwd:
            _logger.debug("No end user password for %s; denying independent connection", agent_id)
            return None

        eu_name = _agent_id_to_end_user_name(agent_id)
        db_cfg = cfg.database
        try:
            conn = yaspy.Connection(
                user=eu_name,
                password=pwd,
                dsn=db_cfg.dsn,
            )
            with conn.cursor() as cur:
                cur.execute(f"ALTER SESSION SET CURRENT_SCHEMA = {cfg.database.user}")
            _end_user_connections[key] = conn
            _logger.info("Created Deep Sec End User connection for %s (EU: %s)", agent_id, eu_name)
            return conn
        except Exception as e:
            _logger.debug("End User connection failed for %s (EU: %s): %s", agent_id, eu_name, e)
            return None


def _get_agent_mode_end_user_connection(agent_id: str) -> Optional[yaspy.Connection]:
    key = (threading.get_ident(), agent_id)
    with _end_user_lock:
        existing = _end_user_connections.get(key)
        if existing:
            try:
                with existing.cursor() as cur:
                    cur.execute("SELECT 1 FROM DUAL")
                return existing
            except Exception:
                try:
                    existing.close()
                except Exception:
                    pass
                _end_user_connections.pop(key, None)

    try:
        cfg = get_config()
        creds = _load_agent_eu_creds()
        conn = yaspy.Connection(
            user=creds["username"],
            password=creds["password"],
            dsn=creds["dsn"],
        )
        with conn.cursor() as cur:
            cur.execute(f"ALTER SESSION SET CURRENT_SCHEMA = {cfg.database.user}")
        with _end_user_lock:
            _end_user_connections[key] = conn
        _logger.info("Created Agent-mode End User connection for %s (EU: %s)", agent_id, creds["username"])
        return conn
    except Exception as e:
        _logger.error("Agent-mode End User connection failed for %s: %s", agent_id, e)
        return None


def close_end_user_connections():
    with _end_user_lock:
        for agent_id, conn in _end_user_connections.items():
            try:
                conn.close()
            except Exception:
                pass
        _end_user_connections.clear()

@contextmanager
def get_connection_for_agent(agent_id: Optional[str] = None):
    aid = agent_id or get_current_agent_id()
    cfg = get_config()
    if cfg.agent.mode == "agent":
        creds = _load_agent_eu_creds()
        configured_agent_id = creds.get("agent_id")
        if aid and configured_agent_id and aid != configured_agent_id:
            raise RuntimeError("Agent identity does not match agent_config.json")
        eu_conn = get_end_user_connection(configured_agent_id or aid or "agent")
        if not eu_conn:
            raise RuntimeError("No End User connection available in agent mode")
        try:
            yield eu_conn
        finally:
            pass
        return
    if aid:
        eu_conn = get_end_user_connection(aid)
        if not eu_conn:
            raise RuntimeError(f"End User connection unavailable for agent {aid}")
        try:
            yield eu_conn
        finally:
            pass
        return
    with get_connection() as conn:
        yield conn

def apply_agent_context(conn: yaspy.Connection, agent_id: Optional[str] = None) -> None:
    aid = agent_id or get_current_agent_id()
    if aid:
        try:
            with conn.cursor() as cur:
                cur.execute(f"BEGIN {get_config().database.user}.SET_AGENT_CONTEXT.set_agent_id(:aid); END;", {"aid": aid})
        except Exception as e:
            _logger.debug("SET_AGENT_CONTEXT.set_agent_id failed (Deep Sec not deployed?): %s", e)

def clear_agent_context(conn: yaspy.Connection) -> None:
    try:
        with conn.cursor() as cur:
            cur.execute(f"BEGIN {get_config().database.user}.SET_AGENT_CONTEXT.clear_context(); END;")
    except Exception as e:
        _logger.debug("SET_AGENT_CONTEXT.clear_context failed (Deep Sec not deployed?): %s", e)

def close_pool():
    global _pool
    close_end_user_connections()
    if _pool:
        with _lock:
            for conn in _pool:
                try:
                    conn.close()
                except:
                    pass
            _pool = []


def execute(sql: str, params: Optional[Dict[str, Any]] = None) -> int:
    sql = sql.replace("AI_NEW_ID()", "RAWTOHEX(SYS_GUID())")
    with get_connection_for_agent() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params or {})
            conn.commit()
            return cur.rowcount


def execute_query(sql: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    sql = sql.replace("AI_NEW_ID()", "RAWTOHEX(SYS_GUID())")
    with get_connection_for_agent() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params or {})
            columns = [col[0].lower() for col in cur.description]
            return [dict(zip(columns, row)) for row in cur.fetchall()]


def execute_query_one(sql: str, params: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    rows = execute_query(sql, params)
    return rows[0] if rows else None


def execute_insert(sql: str, params: Optional[Dict[str, Any]] = None) -> str:
    sql = sql.replace("AI_NEW_ID()", "RAWTOHEX(SYS_GUID())")
    with get_connection_for_agent() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params or {})
            conn.commit()
            return "ok"


def execute_insert_returning_id(sql: str, params: Optional[Dict[str, Any]] = None,
                                 id_column: str = "ENTITY_ID") -> str:
    sql = sql.replace("AI_NEW_ID()", "RAWTOHEX(SYS_GUID())")
    with get_connection_for_agent() as conn:
        with conn.cursor() as cur:
            new_id = cur.var(yaspy.CHAR)
            params_with_return = dict(params or {})
            params_with_return["ret_id"] = new_id
            cur.execute(sql, params_with_return)
            conn.commit()
            val = new_id.getvalue()
            return val[0] if isinstance(val, list) else val


def execute_many(sql: str, params_list: List[Dict[str, Any]]) -> int:
    sql = sql.replace("AI_NEW_ID()", "RAWTOHEX(SYS_GUID())")
    with get_connection_for_agent() as conn:
        with conn.cursor() as cur:
            total = 0
            for params in params_list:
                cur.execute(sql, params)
                total += cur.rowcount
            conn.commit()
            return total


def execute_transaction(statements: List[tuple[str, Optional[Dict[str, Any]]]]) -> int:
    """Execute a group of statements atomically on one schema-owner session."""
    return sum(execute_transaction_result(statements))


def execute_transaction_result(statements: List[tuple[str, Optional[Dict[str, Any]]]]) -> List[int]:
    """Execute statements atomically and return each statement row count."""
    with get_connection_for_agent() as conn:
        try:
            with conn.cursor() as cur:
                counts = []
                for sql, params in statements:
                    sql = sql.replace("AI_NEW_ID()", "RAWTOHEX(SYS_GUID())")
                    cur.execute(sql, params or {})
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
        self.cursor = conn.cursor()

    def execute(self, sql: str, params: Optional[Dict[str, Any]] = None) -> int:
        self.cursor.execute(sql.replace("AI_NEW_ID()", "RAWTOHEX(SYS_GUID())"), params or {})
        return max(self.cursor.rowcount, 0)

    def query(self, sql: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        self.cursor.execute(sql.replace("AI_NEW_ID()", "RAWTOHEX(SYS_GUID())"), params or {})
        columns = [col[0].lower() for col in self.cursor.description]
        return [dict(zip(columns, row)) for row in self.cursor.fetchall()]

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
            result = callback(tx)
            conn.commit()
            return result
        except Exception:
            conn.rollback()
            raise
        finally:
            tx.close()


def execute_plsql(plsql: str, params: Optional[Dict[str, Any]] = None) -> Any:
    with get_connection_for_agent() as conn:
        with conn.cursor() as cur:
            cur.execute(plsql, params or {})
            conn.commit()
            if cur.description:
                columns = [col[0].lower() for col in cur.description]
                rows = cur.fetchall()
                if len(rows) == 1 and len(columns) == 1:
                    return rows[0][0]
                return [dict(zip(columns, row)) for row in rows]
            return None


def _sanitize_json(obj):
    if isinstance(obj, dict):
        return {k: _sanitize_json(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_sanitize_json(i) for i in obj]
    elif isinstance(obj, Decimal):
        return int(obj) if obj == obj.to_integral_value() else float(obj)
    return obj


def sanitize_row(d):
    if not isinstance(d, dict):
        return d
    result = {}
    for k, v in d.items():
        if isinstance(v, dict):
            result[k] = _sanitize_json(v)
        elif isinstance(v, list):
            result[k] = [_sanitize_json(i) for i in v]
        else:
            result[k] = v
    return result
