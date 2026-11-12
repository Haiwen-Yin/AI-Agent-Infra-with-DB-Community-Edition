"""Bounded, auditable business permissions for governed Agents."""
from . import connection, identity_api

ACTIONS = ("memory.read", "memory.write", "knowledge.read", "knowledge.write")
PRIVATE_ACTIONS = frozenset({"memory.read", "memory.write"})


class PermissionConflict(ValueError):
    pass


def owner_predicate(agent_expr, human_expr):
    """Current active Human primary owner, never a sponsor or organization peer."""
    return (
        "EXISTS (SELECT 1 FROM CX_AGENT_RELATIONSHIPS po "
        "JOIN CX_PRINCIPALS ph ON ph.PRINCIPAL_ID=po.PRINCIPAL_ID "
        "JOIN CX_PRINCIPALS pa ON pa.PRINCIPAL_ID=po.AGENT_ID "
        f"WHERE po.AGENT_ID={agent_expr} AND po.PRINCIPAL_ID={human_expr} "
        "AND po.RELATIONSHIP_ROLE='PRIMARY_OWNER' AND po.STATUS='ACTIVE' "
        "AND (po.ENDED_AT IS NULL OR po.ENDED_AT>CURRENT_TIMESTAMP) "
        "AND ph.PRINCIPAL_TYPE='HUMAN' AND ph.STATUS='ACTIVE' "
        "AND pa.PRINCIPAL_TYPE='AGENT' AND pa.STATUS='ACTIVE')"
    )


def is_owner(agent, human, tx=None):
    query = tx.query_one if tx else connection.execute_query_one
    return bool(query("SELECT PRINCIPAL_ID FROM CX_PRINCIPALS WHERE PRINCIPAL_ID=:agent AND " +
                      owner_predicate(":agent", ":human"), {"agent": agent, "human": human}))


def _target(actor, agent, tx=None, lock=False):
    query = tx.query_one if tx else connection.execute_query_one
    row = query("SELECT PRINCIPAL_ID,STATUS,PERMISSION_VERSION FROM CX_PRINCIPALS "
                "WHERE PRINCIPAL_ID=:agent AND PRINCIPAL_TYPE='AGENT'" + (" FOR UPDATE" if lock else ""),
                {"agent": agent})
    if not row or not identity_api._agent_visible_to(actor, agent):
        raise PermissionError("Agent is unavailable")
    return row


def manageable(actor, agent, tx=None):
    if identity_api.effective_access(actor, "users.permissions.manage")["decision"] == "ALLOW":
        return list(ACTIONS)
    if (identity_api.effective_access(actor, "agents.manage")["decision"] == "ALLOW"
            and is_owner(agent, actor, tx)):
        return sorted(PRIVATE_ACTIONS)
    return []


def inventory(actor, agent):
    identity_api._require(actor, "agents.read")
    row = _target(actor, agent)
    direct = connection.execute_query(
        "SELECT RESOURCE_ACTION,EFFECT,DATA_SCOPE,REASON,GRANTED_BY,CREATED_AT "
        "FROM CX_USER_PERMISSION_OVERRIDES WHERE PRINCIPAL_ID=:agent "
        "AND (VALID_UNTIL IS NULL OR VALID_UNTIL>CURRENT_TIMESTAMP) ORDER BY CREATED_AT DESC",
        {"agent": agent})
    return {"agent_id": agent, "permission_version": int(row.get("permission_version") or 0),
            "manageable_actions": manageable(actor, agent), "data_scopes": ["OWNED"],
            "items": [{"resource_action": action, **identity_api.effective_access(agent, action)} for action in ACTIONS],
            "direct_overrides": direct}


def change(actor, agent, action, effect, scope, reason, expected_version):
    if action not in ACTIONS or effect not in {"ALLOW", "DENY", "RESET"} or scope != "OWNED" or not reason.strip():
        raise ValueError("Choose a supported action, effect, OWNED scope and reason")

    def commit(tx):
        row = _target(actor, agent, tx, lock=True)
        if action not in manageable(actor, agent, tx):
            raise PermissionError("Agent permission change is outside your authority")
        if int(row.get("permission_version") or 0) != expected_version:
            raise PermissionConflict("Agent permissions changed; reload before saving")
        tx.execute("UPDATE CX_USER_PERMISSION_OVERRIDES SET VALID_UNTIL=CURRENT_TIMESTAMP "
                   "WHERE PRINCIPAL_ID=:agent AND RESOURCE_ACTION=:action "
                   "AND (VALID_UNTIL IS NULL OR VALID_UNTIL>CURRENT_TIMESTAMP)", {"agent": agent, "action": action})
        if effect != "RESET":
            tx.execute("INSERT INTO CX_USER_PERMISSION_OVERRIDES "
                       "(OVERRIDE_ID,PRINCIPAL_ID,RESOURCE_ACTION,EFFECT,DATA_SCOPE,REASON,GRANTED_BY) "
                       "VALUES (:id,:agent,:action,:effect,:scope,:reason,:actor)",
                       {"id": identity_api._id("PO"), "agent": agent, "action": action, "effect": effect,
                        "scope": scope, "reason": reason[:2000], "actor": actor})
        tx.execute("UPDATE CX_PRINCIPALS SET PERMISSION_VERSION=PERMISSION_VERSION+1 WHERE PRINCIPAL_ID=:agent",
                   {"agent": agent})
        identity_api._audit_tx(tx, actor, "AGENT_PERMISSION_CHANGE", "AGENT", agent, "ALLOW", action + ": " + effect + "; " + reason)
        return {"agent_id": agent, "permission_version": expected_version + 1, "resource_action": action, "effect": effect}
    return connection.execute_transaction_callback(commit)


def grant_enrollment_memory(tx, agent, owner):
    """Explicit private grants only; no copied roles or shared publication."""
    for action in sorted(PRIVATE_ACTIONS):
        tx.execute("INSERT INTO CX_USER_PERMISSION_OVERRIDES "
                   "(OVERRIDE_ID,PRINCIPAL_ID,RESOURCE_ACTION,EFFECT,DATA_SCOPE,REASON,GRANTED_BY) "
                   "VALUES (:id,:agent,:action,'ALLOW','OWNED',:reason,:owner)",
                   {"id": identity_api._id("PO"), "agent": agent, "action": action,
                    "reason": "Enrollment: private Agent Memory", "owner": owner})


def require_business_scopes(agent, scopes):
    for action in set(scopes) & set(ACTIONS):
        if identity_api.effective_access(agent, action)["decision"] != "ALLOW":
            raise PermissionError("Requested Agent business scope is not authorized")
