"""Small shared constraints for adapter-owned native identity revocation.

No provisioning, database discovery, SQL, credentials or privilege escalation.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any


def snapshot_record(agent_id: str, backend: str) -> dict[str, Any]:
    if not isinstance(agent_id, str) or not agent_id or len(agent_id) > 128:
        raise ValueError("An exact Agent ID is required")
    return {
        "schema": "native-agent-identity/v1", "agent_id": agent_id, "backend": backend,
        "database_fingerprint": None, "principal_status": None,
        "permission_version": None, "registry_status": None, "registry_role": None,
        "username": None, "mapping_state": "UNAVAILABLE", "native_state": "UNAVAILABLE",
        "native_exists": None, "login_enabled": None, "account_status": None,
        "native_privileged": False,
    }


def fingerprint(backend: str, endpoint: str, owner: str, actual_database: str) -> str:
    # Endpoint may contain private infrastructure details; expose only its hash.
    value = [backend, str(endpoint), str(owner), str(actual_database)]
    return hashlib.sha256(json.dumps(value, ensure_ascii=True).encode()).hexdigest()


def finish_snapshot(value: dict[str, Any]) -> dict[str, Any]:
    body = {key: item for key, item in value.items() if key != "snapshot_digest"}
    value["snapshot_digest"] = hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    ).hexdigest()
    return value


def failure_code(error: Exception) -> str:
    # Never retain native messages, SQL, connection strings or provider payloads.
    match = re.search(r"\b(?:ORA|YAS)-[0-9]{4,6}\b", str(error))
    if match:
        return match.group(0)
    code = str(getattr(error, "pgcode", "") or "")
    return "SQLSTATE_" + code if re.fullmatch(r"[A-Z0-9]{5}", code) else "NATIVE_IDENTITY_UNAVAILABLE"


def set_principal(value: dict[str, Any], row: Any) -> bool:
    if not row:
        value["mapping_state"] = "UNMANAGED"
        return False
    value.update(principal_status=str(row[0]), permission_version=int(row[1]),
                 registry_status=str(row[2]), registry_role=str(row[3]))
    if value["agent_id"].upper().startswith("SYSTEM_") or value["registry_role"].upper() == "SYSTEM":
        value["mapping_state"] = "PROTECTED"
        return False
    return True


def revocation_guard(current: dict[str, Any], expected: dict[str, Any] | None = None) -> str | None:
    if current.get("mapping_state") != "OBSERVED" or current.get("native_state") != "OBSERVED":
        return "NATIVE_MAPPING_NOT_OBSERVED"
    if current.get("principal_status") not in {"DISABLED", "QUARANTINED", "OWNER_TRANSFER_REQUIRED"}:
        return "PRINCIPAL_NOT_DISABLED"
    if current.get("native_privileged") or str(current.get("registry_role", "")).upper() == "SYSTEM":
        return "PROTECTED_NATIVE_IDENTITY"
    if str(current.get("agent_id", "")).upper().startswith("SYSTEM_"):
        return "PROTECTED_NATIVE_IDENTITY"
    if not current.get("database_fingerprint") or not current.get("username"):
        return "NATIVE_MAPPING_NOT_OBSERVED"
    if expected is not None and (
        expected.get("agent_id") != current.get("agent_id")
        or expected.get("backend") != current.get("backend")
        or expected.get("database_fingerprint") != current.get("database_fingerprint")
        or expected.get("username") != current.get("username")
        or expected.get("snapshot_digest") != current.get("snapshot_digest")
    ):
        return "NATIVE_SNAPSHOT_CHANGED"
    return None


def revoke_record(current: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": "native-agent-revocation/v1", "agent_id": current["agent_id"],
        "backend": current["backend"], "database_fingerprint": current.get("database_fingerprint"),
        "username": current.get("username"), "status": "PENDING",
        "new_connections_blocked": None, "local_connections_closed": 0,
        "local_connection_close_failures": 0, "existing_sessions_closed": None,
        "business_access_blocked": None, "post_snapshot": current,
    }
