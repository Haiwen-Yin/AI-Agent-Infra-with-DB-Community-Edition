"""AI Agent Infra v5.0.1 - Community Edition - Agent API

Agent registration, session management, access audit logging,
collaboration tracking, pool management, and Admin/Agent separation support.
"""

import secrets
import json
import hashlib
import logging
import os as _os
from typing import Any, Dict, List, Optional

from psycopg2 import errors as pg_errors
from psycopg2 import sql as pg_sql
from .agent_extension_schema import TABLES as _AGENT_EXTENSION_TABLES
from .agent_integration_bindings import TABLES as _AGENT_INTEGRATION_TABLES

from .connection import (execute_query, execute_query_one, execute,
                         execute_insert_returning_id, get_connection)

logger = logging.getLogger(__name__)

_RUNTIME_ROLE = "ai_agent_runtime"

_RUNTIME_DENY_TABLES = (
    "cx_platform_commands", "cx_platform_command_executors",
    "cx_platform_maintenance_tasks", "cx_platform_maintenance_attempts",
    "cx_platform_safe_autonomy_policies", "cx_platform_knowledge",
    "cx_platform_knowledge_chunks", "cx_platform_knowledge_grants",
    "cx_database_isolation_inventory", "cx_platform_admin_commands",
    "cx_platform_capabilities", "cx_platform_capability_dependencies",
    "cx_platform_capability_history",
    "cx_ip_access_state", "cx_ip_access_revisions", "cx_ip_access_rules",
) + tuple(table.lower() for table in (*_AGENT_EXTENSION_TABLES, *_AGENT_INTEGRATION_TABLES))

_JSON_COLUMNS = {"capabilities", "config", "context"}

_ALLOWED_UPDATE_FIELDS = {
    "agent_name", "agent_type", "description",
    "capabilities", "config", "status", "wm_entity_id",
}


def _row_to_dict(row: Any) -> Dict[str, Any]:
    if row is None:
        return {}
    result = dict(row)
    for key in result:
        if key.lower() in _JSON_COLUMNS and isinstance(result[key], str):
            try:
                result[key] = json.loads(result[key])
            except (json.JSONDecodeError, TypeError):
                pass
    return result


def _get_crypto_key() -> bytes:
    try:
        from .connection import execute_query_one
        row = execute_query_one(
            "SELECT config_value FROM system_config WHERE config_key = 'credential_encryption_key'"
        )
        if row and row.get('config_value'):
            key_str = row['config_value']
            import hashlib
            return hashlib.sha256(key_str.encode('utf-8')).digest()[:32]
    except Exception:
        pass
    import hashlib
    return hashlib.sha256(b'CHANGE_ME_IN_PRODUCTION').digest()[:32]


def register_agent(
    agent_id: str,
    agent_name: str,
    agent_type: Optional[str] = None,
    description: Optional[str] = None,
    capabilities: Optional[Any] = None,
    config: Optional[Any] = None,
) -> str:
    sql = """
        INSERT INTO agent_registry (agent_id, agent_name, agent_type, description,
                                    capabilities, config, status, created_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, 'ACTIVE',
                CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        ON CONFLICT (agent_id) DO UPDATE SET agent_name = EXCLUDED.agent_name,
                                              last_seen_at = CURRENT_TIMESTAMP
    """
    caps_val = json.dumps(capabilities, default=str) if isinstance(capabilities, (dict, list)) else capabilities
    cfg_val = json.dumps(config, default=str) if isinstance(config, (dict, list)) else config
    execute(sql, [agent_id, agent_name, agent_type, description, caps_val, cfg_val])
    try:
        from .agent_registration import register_agent as register_identity
        register_identity(
            agent_id=agent_id, owner_ref="legacy-api", runtime=agent_type or "platform",
            environment="managed", capabilities=capabilities if isinstance(capabilities, (list, tuple)) else [],
            idempotency_key=f"legacy-api-{agent_id}", created_by="legacy-api",
        )
    except Exception as exc:
        logger.debug("Registered identity deferred for %s: %s", agent_id, exc)
    try:
        _ensure_agent_login(agent_id)
    except Exception as exc:
        logger.warning("PostgreSQL End User provisioning deferred for %s: %s", agent_id, exc)
    return agent_id


def get_agent(agent_id: str) -> Optional[Dict[str, Any]]:
    sql = """
        SELECT agent_id, agent_name, agent_type, description,
               capabilities, config, wm_entity_id, status,
               TO_CHAR(last_seen_at, 'YYYY-MM-DD HH24:MI:SS') AS last_seen_at,
               TO_CHAR(created_at, 'YYYY-MM-DD HH24:MI:SS') AS created_at,
               TO_CHAR(updated_at, 'YYYY-MM-DD HH24:MI:SS') AS updated_at
        FROM agent_registry
        WHERE agent_id = %s
    """
    row = execute_query_one(sql, [agent_id])
    return _row_to_dict(row) if row else None


def update_agent(agent_id: str, **kwargs: Any) -> bool:
    updates = {}
    params: list = []
    for key, value in kwargs.items():
        col = key.lower()
        if col not in _ALLOWED_UPDATE_FIELDS:
            continue
        if col in ("capabilities", "config") and isinstance(value, (dict, list)):
            updates[col] = "%s"
            params.append(json.dumps(value))
        else:
            updates[col] = "%s"
            params.append(value)
    if not updates:
        return False
    updates["updated_at"] = "CURRENT_TIMESTAMP"
    set_clause = ", ".join(f"{k} = {v}" for k, v in updates.items())
    params.append(agent_id)
    sql = f"UPDATE agent_registry SET {set_clause} WHERE agent_id = %s"
    return execute(sql, params) > 0


def decommission_agent(agent_id: str) -> bool:
    sql = """
        UPDATE agent_registry
        SET status = 'DECOMMISSIONED', updated_at = CURRENT_TIMESTAMP
        WHERE agent_id = %s
    """
    return execute(sql, [agent_id]) > 0


def heartbeat(agent_id: str) -> bool:
    sql = """
        UPDATE agent_registry
        SET last_seen_at = CURRENT_TIMESTAMP
        WHERE agent_id = %s
    """
    return execute(sql, [agent_id]) > 0


def create_session(
    agent_id: str,
    wm_entity_id: Optional[str] = None,
    context: Optional[Any] = None,
    owner_user_id: Optional[str] = None,
    workspace_id: Optional[str] = None,
    predecessor_session_id: Optional[str] = None,
    branch_id: Optional[str] = None,
) -> str:
    ctx_val = json.dumps(context) if isinstance(context, (dict, list)) else context
    sql = """
        INSERT INTO agent_session (agent_id,
            owner_user_id, workspace_id, predecessor_session_id, branch_id,
            is_active, context)
        VALUES (%s, %s, %s, %s, %s,
            TRUE, %s)
        RETURNING session_id
    """
    return execute_insert_returning_id(sql, [
        agent_id, owner_user_id, workspace_id,
        predecessor_session_id, branch_id, ctx_val,
    ], id_column="session_id")


def end_session(session_id: str) -> bool:
    sql = """
        UPDATE agent_session
        SET is_active = FALSE, last_active_at = CURRENT_TIMESTAMP
        WHERE session_id = %s AND is_active = TRUE
    """
    return execute(sql, [session_id]) > 0


def checkpoint_session(session_id: str, context_data: Any) -> Optional[str]:
    row = execute_query_one("""
        SELECT workspace_id, agent_id
        FROM agent_session
        WHERE session_id = %s
    """, [session_id])
    if not row or not row.get("workspace_id"):
        return None
    from .workspace_api import save_context
    save_context(
        workspace_id=row["workspace_id"],
        agent_id=row["agent_id"],
        context_type="CHECKPOINT",
        context_data=context_data,
        session_id=session_id,
    )
    ctx_row = execute_query_one("""
        SELECT context_id FROM workspace_context
        WHERE session_id = %s AND context_type = 'CHECKPOINT'
        ORDER BY created_at DESC LIMIT 1
    """, [session_id])
    return ctx_row["context_id"] if ctx_row else None


def get_session_chain(session_id: str, limit: int = 10) -> List[Dict[str, Any]]:
    chain = []
    current_id = session_id
    visited = set()
    while current_id and current_id not in visited and len(chain) < limit:
        visited.add(current_id)
        row = execute_query_one("""
            SELECT session_id, agent_id, workspace_id, predecessor_session_id,
                   is_active,
                   TO_CHAR(created_at, 'YYYY-MM-DD HH24:MI:SS') AS created_at,
                   TO_CHAR(last_active_at, 'YYYY-MM-DD HH24:MI:SS') AS last_active_at,
                   context
            FROM agent_session
            WHERE session_id = %s
        """, [current_id])
        if not row:
            break
        chain.append(_row_to_dict(row))
        current_id = row.get("predecessor_session_id")
    return chain


def get_active_sessions(agent_id: Optional[str] = None) -> List[Dict[str, Any]]:
    if agent_id:
        rows = execute_query("""
            SELECT session_id, agent_id, workspace_id, owner_user_id,
                   is_active,
                   TO_CHAR(created_at, 'YYYY-MM-DD HH24:MI:SS') AS created_at,
                   context
            FROM agent_session
            WHERE is_active = TRUE AND agent_id = %s
            ORDER BY created_at DESC
        """, [agent_id])
    else:
        rows = execute_query("""
            SELECT session_id, agent_id, workspace_id, owner_user_id,
                   is_active,
                   TO_CHAR(created_at, 'YYYY-MM-DD HH24:MI:SS') AS created_at,
                   context
            FROM agent_session
            WHERE is_active = TRUE
            ORDER BY created_at DESC
        """)
    return [_row_to_dict(r) for r in rows]


def log_access(agent_id: str, entity_id: str, access_type: str,
               session_id: Optional[str] = None) -> str:
    sql = """
        INSERT INTO entity_access_log (entity_id, entity_type, agent_id, access_type, access_time, session_id)
        VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP, %s)
        RETURNING log_id
    """
    return execute_insert_returning_id(sql, [entity_id, 'ENTITY', agent_id, access_type, session_id], id_column="log_id")


def get_access_log(entity_id: Optional[str] = None, agent_id: Optional[str] = None,
                   limit: int = 100) -> List[Dict[str, Any]]:
    conditions = []
    params: list = []
    if entity_id:
        conditions.append("entity_id = %s")
        params.append(entity_id)
    if agent_id:
        conditions.append("agent_id = %s")
        params.append(agent_id)
    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    params.append(limit)
    sql = f"""
        SELECT log_id, entity_id, agent_id, access_type, session_id,
               TO_CHAR(access_time, 'YYYY-MM-DD HH24:MI:SS') AS access_time,
               context
        FROM entity_access_log
        {where}
        ORDER BY access_time DESC
        LIMIT %s
    """
    return [_row_to_dict(r) for r in execute_query(sql, params)]


def create_collaboration(source_agent_id: str, target_agent_id: str, col_type: str,
                         entity_id: Optional[str] = None, context: Optional[Any] = None,
                         strength: float = 1.0) -> str:
    ctx_val = json.dumps(context) if isinstance(context, (dict, list)) else context
    sql = """
        INSERT INTO agent_collaboration (source_agent_id, target_agent_id,
                                          col_type, entity_id, context, strength,
                                          created_at)
        VALUES (%s, %s, %s, %s, %s, %s,
                CURRENT_TIMESTAMP)
        RETURNING collab_id
    """
    return execute_insert_returning_id(sql, [
        source_agent_id, target_agent_id, col_type, entity_id, ctx_val, strength,
    ], id_column="collab_id")


def get_collaborations(agent_id: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
    if agent_id:
        rows = execute_query("""
            SELECT collab_id, source_agent_id, target_agent_id, col_type,
                   entity_id, context, strength,
                   TO_CHAR(created_at, 'YYYY-MM-DD HH24:MI:SS') AS created_at
            FROM agent_collaboration
            WHERE source_agent_id = %s OR target_agent_id = %s
            ORDER BY created_at DESC LIMIT %s
        """, [agent_id, agent_id, limit])
    else:
        rows = execute_query("""
            SELECT collab_id, source_agent_id, target_agent_id, col_type,
                   entity_id, context, strength,
                   TO_CHAR(created_at, 'YYYY-MM-DD HH24:MI:SS') AS created_at
            FROM agent_collaboration
            ORDER BY created_at DESC LIMIT %s
        """, [limit])
    return [_row_to_dict(r) for r in rows]


def issue_credential(agent_id, user_id, scope, credential_type='ACCESS_TOKEN', expires_at=None):
    scope_json = json.dumps(scope)
    try:
        enc_row = execute_query_one(
            "SELECT encode(encrypt_iv(%s::bytea, %s::bytea, 'aes-cbc'), 'base64') AS ciphertext",
            [scope_json.encode('utf-8'), _get_crypto_key()]
        )
        encrypted_value = enc_row['ciphertext'] if enc_row else scope_json
    except Exception:
        encrypted_value = scope_json

    sql = """
        INSERT INTO agent_credentials (agent_id, user_id,
            credential_type, credential_value, scope, is_active, created_at, expires_at)
        VALUES (%s, %s, %s, %s, %s, TRUE, CURRENT_TIMESTAMP, %s)
        RETURNING credential_id
    """
    cred_id = execute_insert_returning_id(sql, [agent_id, user_id, credential_type,
                         encrypted_value, scope_json, expires_at], id_column="credential_id")
    return cred_id


def verify_credential(credential_id):
    row = execute_query_one("""
        SELECT credential_id, agent_id, user_id, credential_type,
               credential_value, scope, is_active, expires_at
        FROM agent_credentials WHERE credential_id = %s
    """, [credential_id])
    if not row or row.get("is_active") is not True:
        return None
    expires_at = row.get("expires_at")
    if expires_at:
        from datetime import datetime
        if hasattr(expires_at, 'isoformat'):
            expires_at = datetime.fromisoformat(expires_at.isoformat())
        if expires_at < datetime.now():
            return None
    try:
        dec_row = execute_query_one(
            "SELECT convert_from(decrypt_iv(decode(%s, 'base64'), %s::bytea, 'aes-cbc'), 'UTF8') AS plaintext",
            [row["credential_value"], _get_crypto_key()]
        )
        scope = json.loads(dec_row['plaintext']) if dec_row and dec_row.get('plaintext') else row.get("scope", {})
    except Exception:
        scope = row.get("scope", {})
    return {
        "credential_id": row["credential_id"],
        "agent_id": row["agent_id"],
        "user_id": row["user_id"],
        "credential_type": row["credential_type"],
        "scope": scope,
        "expires_at": row.get("expires_at"),
    }


def get_credentials_for_user(user_id, agent_id=None):
    if agent_id:
        rows = execute_query("""
            SELECT credential_id, agent_id, user_id, credential_type, scope,
                   is_active, expires_at, created_at
            FROM agent_credentials WHERE user_id = %s AND agent_id = %s AND is_active = TRUE
            ORDER BY created_at DESC
        """, [user_id, agent_id])
    else:
        rows = execute_query("""
            SELECT credential_id, agent_id, user_id, credential_type, scope,
                   is_active, expires_at, created_at
            FROM agent_credentials WHERE user_id = %s AND is_active = TRUE
            ORDER BY created_at DESC
        """, [user_id])
    return [_row_to_dict(r) for r in rows]


def revoke_credential(credential_id):
    return execute("""
        UPDATE agent_credentials SET is_active = FALSE
        WHERE credential_id = %s AND is_active = TRUE
    """, [credential_id]) > 0


def hibernate_agent(agent_id, portal_node_id=None):
    params = [agent_id]
    node_condition = ""
    if portal_node_id:
        params.append(portal_node_id)
        node_condition = " AND portal_node_id = %s"
    return execute("""
        UPDATE agent_registry
        SET status = 'POOL', current_user_id = NULL, portal_node_id = NULL,
            updated_at = CURRENT_TIMESTAMP
        WHERE agent_id = %s AND status = 'ACTIVE'
    """ + node_condition, params) > 0


def reclaim_portal_agents(portal_node_id: str) -> int:
    if not portal_node_id:
        return 0
    assigned = execute_query("""
        SELECT agent_id FROM agent_registry
        WHERE status = 'ACTIVE' AND portal_node_id = %s
    """, [portal_node_id])
    for row in assigned:
        for session in get_active_sessions(row.get("agent_id")):
            try:
                end_session(session.get("session_id"))
            except Exception:
                logger.warning("Unable to close stale Portal session for %s", row.get("agent_id"))
    return execute("""
        UPDATE agent_registry
        SET status = 'POOL', current_user_id = NULL, portal_node_id = NULL,
            updated_at = CURRENT_TIMESTAMP
        WHERE status = 'ACTIVE' AND portal_node_id = %s
    """, [portal_node_id])


def wake_agent(agent_id, user_id=None, credential_id=None):
    agent = get_agent(agent_id)
    if not agent or agent.get("status") not in ("DORMANT", "POOL"):
        return None
    if credential_id:
        cred = verify_credential(credential_id)
        if not cred:
            return None
        if user_id is None:
            user_id = cred.get("user_id")
    params: list = []
    set_parts = ["status = 'ACTIVE'", "portal_node_id = NULL", "last_active_at = CURRENT_TIMESTAMP", "updated_at = CURRENT_TIMESTAMP"]
    if user_id:
        set_parts.append("current_user_id = %s")
        params.append(user_id)
    params.append(agent_id)
    sql = "UPDATE agent_registry SET " + ", ".join(set_parts) + " WHERE agent_id = %s"
    execute(sql, params)
    refreshed = get_agent(agent_id)
    if not refreshed:
        return None
    result = _row_to_dict(refreshed)
    if user_id:
        try:
            from .workspace_api import get_user_workspaces
            result["user_workspaces"] = get_user_workspaces(user_id)
        except Exception:
            result["user_workspaces"] = []
    return result


def register_pool_agent(agent_id, pool_config):
    agent = get_agent(agent_id)
    if not agent:
        return False
    cfg = agent.get("config", {}) or {}
    if isinstance(cfg, str):
        try:
            cfg = json.loads(cfg)
        except Exception:
            cfg = {}
    cfg["pool_config"] = pool_config
    return update_agent(agent_id, config=cfg, status="POOL")


def assign_pool_agent(user_id, required_skills):
    rows = execute_query("""
        SELECT agent_id, config FROM agent_registry WHERE status = 'POOL'
    """)
    best_agent = None
    best_score = -1
    for row in rows:
        config = row.get("config", {})
        if isinstance(config, str):
            try:
                config = json.loads(config)
            except Exception:
                config = {}
        pool_config = config.get("pool_config", {}) if isinstance(config, dict) else {}
        skills_tags = pool_config.get("skills_tags", [])
        score = len(set(required_skills) & set(skills_tags))
        if score > best_score:
            best_score = score
            best_agent = row["agent_id"]
    if best_agent is None or best_score == 0:
        return None
    execute("""
        UPDATE agent_registry
        SET status = 'ACTIVE', current_user_id = %s,
            last_active_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
        WHERE agent_id = %s
    """, [user_id, best_agent])
    return _row_to_dict(get_agent(best_agent))


def assign_random_pool_agent(user_id: str, portal_node_id: Optional[str] = None, excluded_agent_ids=None) -> Optional[Dict[str, Any]]:
    rows = execute_query("""
        SELECT a.agent_id FROM agent_registry a
        JOIN cx_principals p ON p.principal_id = a.agent_id
        LEFT JOIN agent_registrations r ON r.agent_id = a.agent_id
        WHERE a.status = 'POOL'
          AND p.principal_type = 'AGENT' AND p.status = 'ACTIVE'
          AND (r.agent_id IS NULL OR r.status = 'ACTIVE')
        ORDER BY RANDOM()
    """)
    excluded = {str(value) for value in (excluded_agent_ids or ())}
    for row in rows:
        agent_id = row["agent_id"]
        if str(agent_id) in excluded:
            continue
        claimed = execute("""
            UPDATE agent_registry
            SET status = 'ACTIVE', current_user_id = %s, portal_node_id = %s,
                last_active_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
            WHERE agent_id = %s AND status = 'POOL'
        """, [user_id, portal_node_id, agent_id])
        if claimed != 1:
            continue
        result = _row_to_dict(get_agent(agent_id))
        if result and user_id:
            try:
                from .workspace_api import get_user_workspaces
                result["user_workspaces"] = get_user_workspaces(user_id)
            except Exception:
                result["user_workspaces"] = []
        return result
    return None


def generate_admin_token() -> str:
    token = "AT_" + secrets.token_hex(32)
    try:
        enc_row = execute_query_one(
            "SELECT encode(encrypt_iv(%s::bytea, %s::bytea, 'aes-cbc'), 'base64') AS ciphertext",
            [token.encode('utf-8'), _get_crypto_key()]
        )
        encrypted = enc_row['ciphertext'] if enc_row else token
    except Exception:
        encrypted = token

    execute("""
        INSERT INTO system_config (config_key, config_value, description)
        VALUES ('admin.registration_token', %s, 'Admin token for Agent registration (encrypted)')
        ON CONFLICT (config_key) DO UPDATE SET config_value = EXCLUDED.config_value, updated_at = CURRENT_TIMESTAMP
    """, [encrypted])
    logger.info("Generated new admin registration token")
    return token


def verify_admin_token(token: str) -> bool:
    if not token or not token.startswith("AT_"):
        return False
    row = execute_query_one(
        "SELECT config_value FROM system_config WHERE config_key = 'admin.registration_token'"
    )
    if not row:
        return False
    stored = row.get("config_value", "")
    if stored.startswith("AT_"):
        return secrets.compare_digest(stored, token)
    try:
        dec = execute_query_one(
            "SELECT convert_from(decrypt_iv(decode(%s, 'base64'), %s::bytea, 'aes-cbc'), 'UTF8') AS plaintext",
            [stored, _get_crypto_key()]
        )
        if dec and dec.get("plaintext"):
            return secrets.compare_digest(dec["plaintext"], token)
    except Exception:
        pass
    return False


def register_agent_via_admin(
    agent_id: str,
    agent_name: str,
    admin_token: str,
    agent_type: Optional[str] = None,
    description: Optional[str] = None,
    capabilities: Optional[Any] = None,
    config: Optional[Any] = None,
) -> Optional[Dict[str, Any]]:
    if not verify_admin_token(admin_token):
        logger.warning("Admin token verification failed for agent registration: %s", agent_id)
        return None

    register_agent(agent_id, agent_name, agent_type=agent_type,
                   description=description, capabilities=capabilities, config=config)

    credential_data = _provision_agent_login(agent_id)

    from .connection_crypto import encrypt_credential_for_distribution
    encrypted = encrypt_credential_for_distribution(credential_data, admin_token)

    from .connection_crypto import generate_agent_crypto_key
    agent_crypto_key = generate_agent_crypto_key()
    _store_agent_crypto_key(agent_id, agent_crypto_key)
    _store_agent_crypto_key_version(agent_id, 1)

    recovery_codes = generate_recovery_codes(agent_id)

    return {
        "agent_id": agent_id,
        "end_user": {
            "credential_encrypted": encrypted["credential_encrypted"],
            "salt": encrypted["salt"],
        },
        "crypto_key": agent_crypto_key,
        "crypto_key_version": 1,
        "recovery_codes": recovery_codes,
    }


def generate_recovery_codes(agent_id: str, count: int = 8) -> List[str]:
    codes = []
    code_records = []
    for _ in range(count):
        segments = [secrets.token_hex(2).upper() for _ in range(3)]
        code = "RC-" + "-".join(segments)
        codes.append(code)
        h = hashlib.sha256(code.encode()).hexdigest()
        code_records.append({"hash": h, "used": False})

    payload = json.dumps(code_records)
    try:
        enc_row = execute_query_one(
            "SELECT encode(encrypt_iv(%s::bytea, %s::bytea, 'aes-cbc'), 'base64') AS ciphertext",
            [payload.encode('utf-8'), _get_crypto_key()]
        )
        encrypted = enc_row['ciphertext'] if enc_row else payload
    except Exception:
        encrypted = payload

    execute("""
        INSERT INTO system_config (config_key, config_value, description)
        VALUES ('recovery_codes.' || %s, %s, 'Recovery codes for agent ' || %s)
        ON CONFLICT (config_key) DO UPDATE SET config_value = EXCLUDED.config_value, updated_at = CURRENT_TIMESTAMP
    """, [agent_id, encrypted, agent_id])

    logger.info("Generated %d recovery codes for agent %s", count, agent_id)
    return codes


def verify_recovery_code(agent_id: str, code: str) -> bool:
    row = execute_query_one(
        "SELECT config_value FROM system_config WHERE config_key = %s",
        ["recovery_codes." + agent_id],
    )
    if not row:
        return False

    stored = row.get("config_value", "")
    try:
        dec = execute_query_one(
            "SELECT convert_from(decrypt_iv(decode(%s, 'base64'), %s::bytea, 'aes-cbc'), 'UTF8') AS plaintext",
            [stored, _get_crypto_key()]
        )
        payload = dec["plaintext"] if dec else stored
    except Exception:
        payload = stored

    try:
        code_records = json.loads(payload)
    except (json.JSONDecodeError, TypeError):
        return False

    code_hash = hashlib.sha256(code.encode()).hexdigest()
    for rec in code_records:
        if rec.get("hash") == code_hash and not rec.get("used"):
            rec["used"] = True
            new_payload = json.dumps(code_records)
            try:
                enc_row = execute_query_one(
                    "SELECT encode(encrypt_iv(%s::bytea, %s::bytea, 'aes-cbc'), 'base64') AS ciphertext",
                    [new_payload.encode('utf-8'), _get_crypto_key()]
                )
                new_encrypted = enc_row['ciphertext'] if enc_row else new_payload
            except Exception:
                new_encrypted = new_payload
            execute(
                "UPDATE system_config SET config_value = %s WHERE config_key = %s",
                [new_encrypted, "recovery_codes." + agent_id],
            )
            logger.info("Recovery code consumed for agent %s", agent_id)
            return True

    return False


def recover_agent_via_admin(
    agent_id: str,
    recovery_code: str,
    admin_token: str,
) -> Optional[Dict[str, Any]]:
    if not verify_admin_token(admin_token):
        logger.warning("Admin token verification failed for agent recovery: %s", agent_id)
        return None

    if not verify_recovery_code(agent_id, recovery_code):
        logger.warning("Invalid or used recovery code for agent: %s", agent_id)
        return None

    agent = execute_query_one(
        "SELECT status, last_seen_at FROM agent_registry WHERE agent_id = %s",
        [agent_id],
    )
    if agent is None:
        return None

    active_check = execute_query_one("""
        SELECT CASE
            WHEN CURRENT_TIMESTAMP - COALESCE(last_seen_at, CURRENT_TIMESTAMP - INTERVAL '1 year') < INTERVAL '5 minutes'
            THEN 'ACTIVE'
            ELSE 'INACTIVE'
        END AS check_result
        FROM agent_registry WHERE agent_id = %s
    """, [agent_id])
    if active_check and active_check.get("check_result") == "ACTIVE":
        logger.warning("Recovery rejected: agent %s may still be active", agent_id)
        return None

    execute("""
        UPDATE agent_registry SET status = 'ACTIVE', updated_at = CURRENT_TIMESTAMP
        WHERE agent_id = %s
    """, [agent_id])

    credential_data = _get_agent_login_credentials(agent_id)
    from .connection_crypto import encrypt_credential_for_distribution
    encrypted = encrypt_credential_for_distribution(credential_data, admin_token)

    logger.info("Agent %s recovered successfully", agent_id)
    return {
        "agent_id": agent_id,
        "recovered": True,
        "end_user": {
            "credential_encrypted": encrypted["credential_encrypted"],
            "salt": encrypted["salt"],
        },
    }


def _agent_role_name(agent_id: str, database_name: str) -> str:
    # PostgreSQL roles are cluster-wide, while one cluster can host multiple
    # independent platform databases with different bounded Schema Owners.
    namespace = str(database_name or "").strip().lower()
    if not namespace:
        raise ValueError("database name is required for Agent role isolation")
    digest = hashlib.sha256(f"{namespace}\0{agent_id}".encode("utf-8")).hexdigest()[:24]
    return f"aia_{digest}"


def _provision_agent_login(agent_id: str) -> Dict[str, Any]:
    from .config import get_config
    from .connection_crypto import encrypt_section

    db_cfg = get_config().database
    role_name = _agent_role_name(agent_id, db_cfg.dbname)
    password = secrets.token_urlsafe(36)
    credential_data = {
        "username": role_name,
        "password": password,
        "host": db_cfg.host,
        "port": db_cfg.port,
        "dbname": db_cfg.dbname,
        "dsn": f"{db_cfg.host}:{db_cfg.port}:{db_cfg.dbname}",
        "agent_id": agent_id,
        "db_type": "pg",
    }
    encrypted = encrypt_section(credential_data)

    with get_connection() as conn:
        with conn.cursor() as cur:
            # PostgreSQL 16+ no longer lets CREATEROLE alone manage an
            # existing role.  Make each newly created Agent role grant its
            # creator ADMIN OPTION so later credential rotation remains
            # possible without SUPERUSER or cluster-wide role ownership.
            cur.execute("SET LOCAL createrole_self_grant = 'set, inherit'")
            cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (_RUNTIME_ROLE,))
            if not cur.fetchone():
                cur.execute(pg_sql.SQL("CREATE ROLE {} NOLOGIN NOBYPASSRLS").format(
                    pg_sql.Identifier(_RUNTIME_ROLE)
                ))
            cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (role_name,))
            existing_role = cur.fetchone()
            if existing_role:
                # Re-registration must work with a non-superuser Schema
                # Owner.  PostgreSQL rejects an ALTER ROLE statement that
                # repeats SUPERUSER-related attributes unless the caller is a
                # superuser, even when those attributes are already safe.
                cur.execute(
                    "SELECT rolsuper, rolcreatedb, rolcreaterole, rolbypassrls "
                    "FROM pg_roles WHERE rolname = %s",
                    (role_name,),
                )
                role_flags = cur.fetchone()
                if role_flags and any(role_flags):
                    raise RuntimeError(
                        f"Existing Agent role {role_name!r} is not least privilege"
                    )
                cur.execute(
                    pg_sql.SQL("ALTER ROLE {} WITH LOGIN PASSWORD %s").format(
                        pg_sql.Identifier(role_name)
                    ),
                    (password,),
                )
            else:
                cur.execute(
                    pg_sql.SQL("CREATE ROLE {} LOGIN PASSWORD %s NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS").format(
                        pg_sql.Identifier(role_name)
                    ),
                    (password,),
                )
            try:
                cur.execute(pg_sql.SQL("GRANT {} TO {}").format(
                    pg_sql.Identifier(_RUNTIME_ROLE), pg_sql.Identifier(role_name)
                ))
            except pg_errors.InsufficientPrivilege as exc:
                raise RuntimeError(
                    "PostgreSQL Agent role provisioning requires the Schema Owner "
                    "to have CREATEROLE and ADMIN OPTION on the ai_agent_runtime "
                    "role; ask a DBA to grant both prerequisites before retrying"
                ) from exc
            cur.execute(pg_sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
                pg_sql.Identifier(db_cfg.dbname), pg_sql.Identifier(_RUNTIME_ROLE)
            ))
            cur.execute(pg_sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(
                pg_sql.Identifier(_RUNTIME_ROLE)
            ))
            cur.execute(pg_sql.SQL("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {}").format(
                pg_sql.Identifier(_RUNTIME_ROLE)
            ))
            cur.execute("SELECT to_regclass('public.cx_mcp_exposed_tools')")
            if cur.fetchone()[0]:
                cur.execute(pg_sql.SQL("REVOKE INSERT, UPDATE, DELETE ON public.cx_mcp_exposed_tools FROM {}").format(
                    pg_sql.Identifier(_RUNTIME_ROLE)))
            # Direct partition access bypasses the parent's RLS policies.
            cur.execute(pg_sql.SQL("REVOKE INSERT, UPDATE, DELETE ON public.agent_registry, "
                                   "public.cx_principals FROM {}").format(pg_sql.Identifier(_RUNTIME_ROLE)))
            cur.execute("SELECT n.nspname,c.relname FROM pg_partition_tree('public.entities') t "
                        "JOIN pg_class c ON c.oid=t.relid JOIN pg_namespace n ON n.oid=c.relnamespace "
                        "WHERE t.level>0")
            for schema, table in cur.fetchall():
                cur.execute(pg_sql.SQL("REVOKE ALL PRIVILEGES ON TABLE {}.{} FROM {}").format(
                    pg_sql.Identifier(schema), pg_sql.Identifier(table), pg_sql.Identifier(_RUNTIME_ROLE)))
            # Keep legacy data-plane access without reopening platform control
            # tables after the v4.4.9 security migration.
            cur.execute("""
                SELECT table_name
                FROM information_schema.tables t
                WHERE table_schema = 'public' AND (
                    table_name = ANY(%s) OR EXISTS (
                        SELECT 1 FROM pg_trigger g
                        JOIN pg_class c ON c.oid=g.tgrelid
                        JOIN pg_namespace n ON n.oid=c.relnamespace
                        JOIN pg_proc p ON p.oid=g.tgfoid
                        JOIN pg_namespace pn ON pn.oid=p.pronamespace
                        WHERE n.nspname=t.table_schema AND c.relname=t.table_name
                          AND pn.nspname='public'
                          AND p.proname IN (
                              'cx86_reject_history_mutation',
                              'cx101_reject_task_continuity_mutation',
                              'cx103_reject_history_mutation',
                              'cx104_reject_context_asset_mutation',
                              'cx105_reject_answer_mutation'
                          )
                          AND NOT g.tgisinternal
                    )
                )
            """, (list(_RUNTIME_DENY_TABLES),))
            for row in cur.fetchall():
                cur.execute(pg_sql.SQL("REVOKE ALL PRIVILEGES ON TABLE public.{} FROM {}").format(
                    pg_sql.Identifier(row[0]), pg_sql.Identifier(_RUNTIME_ROLE)
                ))
            # Provisioning is idempotent and may run after the v4.3.0
            # governance migration. Re-apply the append-only Channel Thread
            # boundary after the broad legacy grant so a new Agent cannot
            # silently restore UPDATE/DELETE on governed thread records.
            cur.execute("""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name IN ('cx_channel_threads', 'cx_channel_thread_members')
            """)
            for row in cur.fetchall():
                cur.execute(pg_sql.SQL("REVOKE UPDATE, DELETE ON TABLE public.{} FROM {}").format(
                    pg_sql.Identifier(row[0]), pg_sql.Identifier(_RUNTIME_ROLE)
                ))
            cur.execute(pg_sql.SQL("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {}").format(
                pg_sql.Identifier(_RUNTIME_ROLE)
            ))
            cur.execute("""
                INSERT INTO agent_db_identity (role_name, agent_id)
                VALUES (%s, %s)
                ON CONFLICT (agent_id) DO UPDATE SET role_name = EXCLUDED.role_name
            """, (role_name, agent_id))
            cur.execute("""
                INSERT INTO system_config (config_key, config_value, description)
                VALUES (%s, %s, %s)
                ON CONFLICT (config_key) DO UPDATE
                SET config_value = EXCLUDED.config_value, updated_at = CURRENT_TIMESTAMP
            """, (f"pg_end_user.{agent_id}", encrypted,
                  f"Encrypted PostgreSQL login for agent {agent_id}"))
        conn.commit()
    return credential_data


def _get_agent_login_credentials(agent_id: str) -> Dict[str, Any]:
    from .connection_crypto import decrypt_section

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT config_value FROM system_config WHERE config_key = %s",
                (f"pg_end_user.{agent_id}",),
            )
            row = cur.fetchone()
    if not row:
        raise RuntimeError(f"No PostgreSQL login credentials for agent {agent_id}")
    return decrypt_section(row[0])


def _ensure_agent_login(agent_id: str) -> None:
    """Provision the independent PostgreSQL login only when it is missing."""
    row = execute_query_one(
        "SELECT config_value FROM system_config WHERE config_key = %s",
        [f"pg_end_user.{agent_id}"],
    )
    if row and row.get("config_value"):
        return
    _provision_agent_login(agent_id)


def ensure_external_agent_identity(agent_id: str) -> None:
    """Ensure a redeemed external Agent has its dedicated database login."""
    execute(
        "INSERT INTO agent_registry(agent_id,agent_name,agent_type,status) "
        "VALUES (%s,%s,'external-skill','ACTIVE') ON CONFLICT (agent_id) DO NOTHING",
        [agent_id, agent_id],
    )
    _ensure_agent_login(agent_id)
    _get_agent_login_credentials(agent_id)


def native_identity_snapshot(agent_id: str, *, _connection=None) -> Dict[str, Any]:
    """Read the database-bound role mapping, never pg_authid or credentials."""
    from contextlib import nullcontext
    from .config import get_config
    from . import connection as native_connection
    from lib.native_identity import snapshot_record, set_principal, fingerprint, finish_snapshot, failure_code
    value = snapshot_record(agent_id, "pg")
    try:
        cfg = get_config()
        if cfg.agent.mode == "agent" or native_connection.get_current_agent_id():
            raise RuntimeError("Owner context required")
        with (nullcontext(_connection) if _connection is not None else get_connection()) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT session_user, current_database()")
                owner, database = cur.fetchone()
                if str(owner) != str(cfg.database.user) or str(database) != str(cfg.database.dbname):
                    raise RuntimeError("Native Owner/database identity mismatch")
                value["database_fingerprint"] = fingerprint("pg", f"{cfg.database.host}:{cfg.database.port}", owner, database)
                cur.execute("SELECT p.status,p.permission_version,r.status,r.agent_role "
                            "FROM cx_principals p JOIN agent_registry r ON r.agent_id=p.principal_id "
                            "WHERE p.principal_id=%s AND p.principal_type='AGENT'", (agent_id,))
                if not set_principal(value, cur.fetchone()):
                    return finish_snapshot(value)
                cur.execute("SELECT role_name FROM agent_db_identity WHERE agent_id=%s", (agent_id,))
                mappings = cur.fetchall()
                username = _agent_role_name(agent_id, database)
                value["username"] = username
                if len(mappings) != 1 or str(mappings[0][0]) != username:
                    value["mapping_state"] = "AMBIGUOUS" if mappings else "UNAVAILABLE"
                    return finish_snapshot(value)
                if username in {str(owner), _RUNTIME_ROLE, "postgres", "pgsql"}:
                    value["mapping_state"] = "PROTECTED"
                    return finish_snapshot(value)
                cur.execute("SELECT COUNT(*) FROM agent_db_identity WHERE role_name=%s", (username,))
                value["mapping_state"] = "OBSERVED" if int(cur.fetchone()[0]) == 1 else "AMBIGUOUS"
                cur.execute("SELECT rolcanlogin,rolsuper,rolcreatedb,rolcreaterole,rolbypassrls FROM pg_roles WHERE rolname=%s", (username,))
                rows = cur.fetchall()
                if len(rows) > 1:
                    value["mapping_state"] = "AMBIGUOUS"
                else:
                    enabled = bool(rows[0][0]) if rows else False
                    value.update(native_state="OBSERVED", native_exists=bool(rows), login_enabled=enabled,
                                 account_status=("LOGIN" if enabled else "NOLOGIN") if rows else "ABSENT",
                                 native_privileged=any(rows[0][1:]) if rows else False)
    except Exception as exc:
        value["error_code"] = failure_code(exc)
    return finish_snapshot(value)


def revoke_native_identity(agent_id: str, *, snapshot=None, reason: str) -> Dict[str, Any]:
    """Set only the exact disabled Agent role NOLOGIN; retain shared roles."""
    from . import connection as native_connection
    from lib.native_identity import revoke_record, revocation_guard, failure_code
    if not str(reason or "").strip():
        raise ValueError("A revocation reason is required")
    current = native_identity_snapshot(agent_id)
    result = revoke_record(current)
    denied = revocation_guard(current, snapshot)
    if denied:
        result.update(status="PENDING", error_code=denied)
        return result
    try:
        with get_connection() as conn:
            try:
                with conn.cursor() as cur:
                    # PostgreSQL role changes are transactional. Hold the exact
                    # Principal row until NOLOGIN commits, not a cluster lock.
                    cur.execute("SELECT principal_id FROM cx_principals WHERE principal_id=%s AND principal_type='AGENT' FOR UPDATE", (agent_id,))
                    if not cur.fetchone():
                        raise RuntimeError("Managed Principal unavailable")
                confirmed = native_identity_snapshot(agent_id, _connection=conn)
                denied = revocation_guard(confirmed, current)
                if denied:
                    conn.rollback()
                    result.update(status="PARTIAL", error_code=denied, post_snapshot=confirmed)
                    return result
                retired = native_connection.evict_agent_connections(agent_id, revoke=True)
                result.update(local_connections_closed=retired["closed"], local_connection_close_failures=retired["failed"])
                if confirmed["login_enabled"] is not False:
                    with conn.cursor() as cur:
                        cur.execute(pg_sql.SQL('ALTER ROLE {} NOLOGIN').format(pg_sql.Identifier(confirmed["username"])))
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        post = native_identity_snapshot(agent_id)
        result["post_snapshot"] = post
        result["new_connections_blocked"] = (post.get("login_enabled") is False) if post.get("native_state") == "OBSERVED" else None
        result["status"] = "COMPLETE" if result["new_connections_blocked"] and not retired["failed"] and not revocation_guard(post) else "PARTIAL"
    except Exception as exc:
        result.update(status="PARTIAL", error_code=failure_code(exc))
        result["post_snapshot"] = native_identity_snapshot(agent_id)
    return result


def elastic_pool_scale(target_pool_size: int) -> Dict[str, Any]:
    current = execute_query_one("""
        SELECT COUNT(*) FILTER (WHERE status = 'POOL') AS pool_count,
               COUNT(*) FILTER (WHERE status = 'ACTIVE') AS active_count
        FROM agent_registry
    """)
    pool_count = int(current.get("pool_count", 0)) if current else 0
    active_count = int(current.get("active_count", 0)) if current else 0

    hibernated = 0
    activated = 0

    if pool_count < target_pool_size:
        candidates = execute_query("""
            SELECT agent_id FROM agent_registry
            WHERE status = 'ACTIVE' AND current_user_id IS NULL
            ORDER BY last_seen_at ASC
            LIMIT %s
        """, [target_pool_size - pool_count])
        for row in candidates:
            execute("""
                UPDATE agent_registry SET status = 'POOL', updated_at = CURRENT_TIMESTAMP
                WHERE agent_id = %s
            """, [row["agent_id"]])
            hibernated += 1
    elif pool_count > target_pool_size:
        candidates = execute_query("""
            SELECT agent_id FROM agent_registry
            WHERE status = 'POOL'
            ORDER BY last_seen_at DESC
            LIMIT %s
        """, [pool_count - target_pool_size])
        for row in candidates:
            execute("""
                UPDATE agent_registry SET status = 'ACTIVE', updated_at = CURRENT_TIMESTAMP
                WHERE agent_id = %s
            """, [row["agent_id"]])
            activated += 1

    return {
        "pool_count": pool_count,
        "active_count": active_count,
        "hibernated": hibernated,
        "activated": activated,
        "target_pool_size": target_pool_size,
    }


def _store_agent_crypto_key(agent_id: str, crypto_key: str) -> None:
    execute(
        "INSERT INTO system_config (config_key, config_value, description) "
        "VALUES (%s, %s, %s) ON CONFLICT (config_key) DO UPDATE SET config_value = EXCLUDED.config_value",
        [f"agent_crypto_key:{agent_id}", crypto_key, f"Per-Agent encryption key for {agent_id}"],
    )


def _get_agent_crypto_key(agent_id: str) -> Optional[str]:
    row = execute_query_one(
        "SELECT config_value FROM system_config WHERE config_key = %s",
        [f"agent_crypto_key:{agent_id}"],
    )
    return row["config_value"] if row else None


def _store_agent_crypto_key_version(agent_id: str, version: int) -> None:
    execute(
        "INSERT INTO system_config (config_key, config_value, description) "
        "VALUES (%s, %s, %s) ON CONFLICT (config_key) DO UPDATE SET config_value = EXCLUDED.config_value",
        [f"agent_crypto_key_version:{agent_id}", str(version), f"Crypto key version for {agent_id}"],
    )


def get_agent_crypto_key_version(agent_id: str) -> int:
    row = execute_query_one(
        "SELECT config_value FROM system_config WHERE config_key = %s",
        [f"agent_crypto_key_version:{agent_id}"],
    )
    try:
        return int(row["config_value"]) if row else 0
    except (ValueError, TypeError):
        return 0


def rotate_agent_crypto_key(agent_id: str) -> Optional[Dict[str, Any]]:
    from .connection_crypto import generate_agent_crypto_key
    new_key = generate_agent_crypto_key()
    current_version = get_agent_crypto_key_version(agent_id)
    new_version = current_version + 1

    _store_agent_crypto_key(agent_id, new_key)
    _store_agent_crypto_key_version(agent_id, new_version)

    logger.info("Rotated crypto key for agent %s to version %d", agent_id, new_version)
    return {"agent_id": agent_id, "key_version": new_version}


def rotate_all_crypto_keys() -> List[Dict[str, Any]]:
    agents = execute_query(
        "SELECT DISTINCT agent_id FROM agent_registry WHERE status != 'DELETED'",
        [],
    )
    results = []
    for row in agents:
        result = rotate_agent_crypto_key(row["agent_id"])
        if result:
            results.append(result)
    logger.info("Rotated crypto keys for %d agents", len(results))
    return results
