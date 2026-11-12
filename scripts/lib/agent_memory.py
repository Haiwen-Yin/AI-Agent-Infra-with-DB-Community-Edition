"""Independent private Gateway Memory using the existing version pipeline."""
import hashlib

from . import connection, identity_api, memory_lifecycle as memory


def create(context, payload, idempotency_key):
    agent = str(context["agent_id"])
    domain = str(context.get("security_domain_id") or "")
    if not domain:
        raise PermissionError("An active Security Domain is required")
    if not 8 <= len(idempotency_key) <= 256:
        raise ValueError("An idempotency key of 8 to 256 characters is required")
    request = memory._request({**payload, "owner_principal_id": agent, "owner_agent_id": agent,
                               "memory_scope": "AGENT_MEMORY", "security_domain_id": domain})
    request_digest = hashlib.sha256(memory._json(request.__dict__).encode()).hexdigest()
    family_id = "MF-GW-" + hashlib.sha256((agent + "\0" + idempotency_key).encode()).hexdigest()

    def commit(tx):
        # Serialize with permission/status/owner changes and concurrent retries.
        principal = tx.query_one("SELECT STATUS FROM CX_PRINCIPALS WHERE PRINCIPAL_ID=:agent "
                                 "AND PRINCIPAL_TYPE='AGENT' FOR UPDATE", {"agent": agent})
        if not principal or principal["status"] != "ACTIVE":
            raise PermissionError("Agent is unavailable")
        identity_api._require(agent, "memory.write")
        instance = tx.query_one("SELECT INSTANCE_ID FROM CX_AGENT_INSTANCES WHERE INSTANCE_ID=:instance "
                                "AND AGENT_ID=:agent AND STATUS='ACTIVE' AND REVOKED_AT IS NULL "
                                "AND LEASE_EXPIRES_AT>CURRENT_TIMESTAMP AND FENCING_TOKEN=:fence "
                                "AND SECURITY_DOMAIN_ID=:domain",
                                {"instance": context["instance_id"], "agent": agent,
                                 "fence": context["fencing_token"], "domain": domain})
        member = tx.query_one("SELECT PRINCIPAL_ID FROM CX_DOMAIN_MEMBERS WHERE PRINCIPAL_ID=:agent "
                              "AND SECURITY_DOMAIN_ID=:domain AND STATUS='ACTIVE' "
                              "AND (VALID_UNTIL IS NULL OR VALID_UNTIL>CURRENT_TIMESTAMP)", {"agent": agent, "domain": domain})
        if not instance or not member:
            raise PermissionError("Agent instance or Security Domain is unavailable")
        previous = tx.query_one("SELECT VERSION_ID,LIFECYCLE_STATE,METADATA_JSON FROM CX_MEMORY_VERSIONS "
                                "WHERE FAMILY_ID=:family AND VERSION_NUMBER=1", {"family": family_id})
        if previous:
            stored = memory._parse_json(previous.get("metadata_json"), {})
            if stored.get("gateway_request_digest") != request_digest:
                raise memory.MemoryLifecycleError("IDEMPOTENCY_CONFLICT", "Idempotency key was used for a different request")
            return {"family_id": family_id, "version_id": previous["version_id"], "version_number": 1,
                    "lifecycle_state": previous["lifecycle_state"], "idempotent": True}
        return memory.create_family(request, actor=agent, idempotency_key=idempotency_key,
                                    _transaction=tx, _family_id=family_id, _request_digest=request_digest)
    return connection.execute_transaction_callback(commit)


def get(context, family_id):
    identity_api._require(str(context["agent_id"]), "memory.read")
    result = memory.get_family(family_id, principal_id=str(context["agent_id"]))
    current = (result or {}).get("current") or {}
    if (current.get("owner_principal_id") != context["agent_id"]
            or current.get("memory_scope") != "AGENT_MEMORY"):
        return None
    return result
