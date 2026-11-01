"""Durable admission at one explicitly selected database coordination authority.

This ledger grants transport capacity, never business or model permission.
Every network wait happens outside its transactions. Once dispatch starts,
ownership transfers to a durable attempt; expiration cannot prove completion.
Separate installations must use this same authority (for example through the
authenticated model gateway), rather than creating independent local groups.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from urllib.parse import urlsplit, urlunsplit

from . import connection, identity_api, continuity_work as work
from .agent_extension_contracts import digest, identifier, registered_url
from .continuity_state import ContinuityConflict, require_idempotent_request, require_version
from .effective_capabilities import authorize
from .model_endpoint_contracts import (
    CapacityAlias, CapacityCancellation, CapacityObservation, CapacityOrigin,
    CapacityOriginState, CapacityRevision, ModelAdmission, NewCapacityGroup,
    ReservationClaim,
)

OCCUPIED = frozenset({"RESERVED", "DISPATCHING", "UNKNOWN"})
TERMINAL = frozenset({"COMPLETED", "REJECTED", "CANCELLED", "EXPIRED"})


def endpoint_url(value):
    """Canonicalize registered aliases, preserving case-sensitive path bytes."""
    parts = urlsplit(registered_url(value))
    hostname = parts.hostname.lower()
    host = "[" + hostname + "]" if ":" in hostname else hostname
    port = parts.port
    if port is not None and port != (443 if parts.scheme.lower() == "https" else 80):
        host += ":" + str(port)
    return urlunsplit((parts.scheme.lower(), host, parts.path.rstrip("/"), "", ""))


def alias_key(value):
    return hashlib.sha256(endpoint_url(value).encode("utf-8")).hexdigest()


def _now_ms(tx):
    # Reuse the existing adapter-aware UTC clock. A process-local clock is not
    # allowed to decide that another process's reservation has expired.
    value = tx.query_one("SELECT " + connection.utc_wall_clock_expression() + " AS NOW_UTC" + connection.scalar_select_suffix(), {})["now_utc"]
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if not isinstance(value, datetime):
        raise RuntimeError("Coordinator clock is unavailable")
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return int(value.timestamp() * 1000)


def _admin(tx, actor):
    work._lock_actor(tx, actor)
    authorize(actor, "model_gateway.manage")


def _group(tx, group_id):
    group = tx.query_one("SELECT * FROM CX_MODEL_CAP_GROUPS WHERE GROUP_ID=:group_id FOR UPDATE", {"group_id": group_id})
    if not group:
        raise PermissionError("Endpoint capacity group is unavailable")
    policy = tx.query_one("SELECT * FROM CX_MODEL_CAP_REVISIONS WHERE GROUP_ID=:group_id AND REVISION_NO=:revision",
                          {"group_id": group_id, "revision": group["current_revision"]})
    if not policy:
        raise RuntimeError("Endpoint capacity policy is incomplete")
    return group, policy


def _origin(tx, actor, group_id, origin_id):
    authorize(actor, "model_gateway.forward")
    origin = tx.query_one("SELECT * FROM CX_MODEL_CAP_ORIGINS WHERE GROUP_ID=:group_id AND ORIGIN_ID=:origin_id",
                          {"group_id": group_id, "origin_id": origin_id})
    if not origin or origin["status"] != "ACTIVE" or origin["principal_id"] != actor:
        raise PermissionError("Authenticated Principal is not an active coordinator origin")
    return origin


def _fingerprint(group_id, value):
    return digest({"group_id": group_id, "request": value.model_dump(mode="json")})


def _receipt(tx, actor, operation, group_id, value):
    stored = tx.query_one("SELECT * FROM CX_MODEL_CAP_REQUESTS WHERE ACTOR_ID=:actor AND OPERATION=:operation AND IDEMPOTENCY_KEY=:idem_key",
                          {"actor": actor, "operation": operation, "idem_key": value.idempotency_key})
    if stored:
        require_idempotent_request(stored["request_digest"], _fingerprint(group_id, value))
    return stored


def _record(tx, actor, operation, group_id, value, version, *, admission_id=None):
    tx.execute("INSERT INTO CX_MODEL_CAP_REQUESTS(ACTOR_ID,OPERATION,IDEMPOTENCY_KEY,REQUEST_DIGEST,GROUP_ID,ADMISSION_ID,RESOURCE_VERSION,CREATED_AT_MS) "
               "VALUES(:actor,:operation,:idem_key,:fingerprint,:group_id,:admission_id,:revision,:now_ms)",
               {"actor": actor, "operation": operation, "idem_key": value.idempotency_key,
                "fingerprint": _fingerprint(group_id, value), "group_id": group_id,
                "admission_id": admission_id, "revision": version, "now_ms": _now_ms(tx)})
    identity_api._audit_tx(tx, actor, operation, "MODEL_CAPACITY", admission_id or group_id, "ALLOW", value.reason)


def _policy(tx, actor, group_id, revision, policy, reason):
    tx.execute("INSERT INTO CX_MODEL_CAP_REVISIONS(GROUP_ID,REVISION_NO,CAPACITY,QUEUE_MS,SOCKET_MS,IDLE_MS,OVERALL_MS,RESERVATION_MS,CREATED_BY,REASON,CREATED_AT_MS) "
               "VALUES(:group_id,:revision,:capacity,:queue_ms,:socket_ms,:idle_ms,:overall_ms,:reservation_ms,:actor,:reason,:now_ms)",
               {"group_id": group_id, "revision": revision, **policy.model_dump(),
                "actor": actor, "reason": reason, "now_ms": _now_ms(tx)})


def create_group(actor, value):
    request = NewCapacityGroup.model_validate(value)
    def create(tx):
        _admin(tx, actor)
        replay = _receipt(tx, actor, "MODEL_CAP_GROUP_CREATE", None, request)
        if replay:
            return {"group_id": replay["group_id"], "version": int(replay["resource_version"]), "replayed": True}
        group_id = identifier("MCG")
        tx.execute("INSERT INTO CX_MODEL_CAP_GROUPS(GROUP_ID,RESOURCE_KEY,COORDINATOR_ID,CURRENT_REVISION,NEXT_SEQUENCE,VERSION,STATUS,CREATED_BY,CREATED_AT_MS) "
                   "VALUES(:group_id,:resource_key,:coordinator_id,1,1,1,'ACTIVE',:actor,:now_ms)",
                   {"group_id": group_id, "resource_key": request.resource_key, "coordinator_id": request.coordinator_id,
                    "actor": actor, "now_ms": _now_ms(tx)})
        _policy(tx, actor, group_id, 1, request.policy, request.reason)
        # Creation fingerprints have no caller-selected group ID.
        tx.execute("INSERT INTO CX_MODEL_CAP_REQUESTS(ACTOR_ID,OPERATION,IDEMPOTENCY_KEY,REQUEST_DIGEST,GROUP_ID,RESOURCE_VERSION,CREATED_AT_MS) "
                   "VALUES(:actor,'MODEL_CAP_GROUP_CREATE',:idem_key,:fingerprint,:group_id,1,:now_ms)",
                   {"actor": actor, "idem_key": request.idempotency_key, "fingerprint": _fingerprint(None, request),
                    "group_id": group_id, "now_ms": _now_ms(tx)})
        identity_api._audit_tx(tx, actor, "MODEL_CAP_GROUP_CREATE", "MODEL_CAPACITY", group_id, "ALLOW", request.reason)
        return {"group_id": group_id, "version": 1, "replayed": False}
    return connection.execute_transaction_callback(create)


def revise_group(actor, group_id, value):
    request = CapacityRevision.model_validate(value)
    def revise(tx):
        _admin(tx, actor)
        group, _ = _group(tx, group_id)
        replay = _receipt(tx, actor, "MODEL_CAP_GROUP_REVISE", group_id, request)
        if replay:
            return {"group_id": group_id, "version": int(replay["resource_version"]), "replayed": True}
        require_version(int(group["version"]), request.expected_version)
        revision, version = int(group["current_revision"]) + 1, int(group["version"]) + 1
        _policy(tx, actor, group_id, revision, request.policy, request.reason)
        tx.execute("UPDATE CX_MODEL_CAP_GROUPS SET CURRENT_REVISION=:revision,VERSION=:version,STATUS=:status WHERE GROUP_ID=:group_id",
                   {"revision": revision, "version": version, "status": request.status, "group_id": group_id})
        _record(tx, actor, "MODEL_CAP_GROUP_REVISE", group_id, request, version)
        return {"group_id": group_id, "version": version, "replayed": False}
    return connection.execute_transaction_callback(revise)


def register_origin(actor, group_id, value):
    request = CapacityOrigin.model_validate(value)
    def register(tx):
        _admin(tx, actor)
        _group(tx, group_id)
        replay = _receipt(tx, actor, "MODEL_CAP_ORIGIN_REGISTER", group_id, request)
        if replay:
            return {"origin_id": request.origin_id, "version": int(replay["resource_version"]), "replayed": True}
        principal = tx.query_one("SELECT STATUS FROM CX_PRINCIPALS WHERE PRINCIPAL_ID=:principal", {"principal": request.principal_id})
        if not principal or principal["status"] != "ACTIVE":
            raise PermissionError("Origin requires an active authenticated coordinator Principal")
        tx.execute("INSERT INTO CX_MODEL_CAP_ORIGINS(GROUP_ID,ORIGIN_ID,PRINCIPAL_ID,INSTALLATION_KEY,STATUS,VERSION,REGISTERED_BY,CREATED_AT_MS) "
                   "VALUES(:group_id,:origin_id,:principal,:installation,'ACTIVE',1,:actor,:now_ms)",
                   {"group_id": group_id, "origin_id": request.origin_id, "principal": request.principal_id,
                    "installation": request.installation_key, "actor": actor, "now_ms": _now_ms(tx)})
        _record(tx, actor, "MODEL_CAP_ORIGIN_REGISTER", group_id, request, 1)
        return {"origin_id": request.origin_id, "version": 1, "replayed": False}
    return connection.execute_transaction_callback(register)


def change_origin(actor, group_id, origin_id, value):
    request = CapacityOriginState.model_validate(value)
    operation = "MODEL_CAP_ORIGIN_STATE"
    # The origin locator participates in the fingerprint, even though it is
    # outside the body. An idempotency key cannot mutate another membership.
    scope = group_id + ":" + origin_id
    def change(tx):
        _admin(tx, actor)
        _group(tx, group_id)
        origin = tx.query_one("SELECT VERSION FROM CX_MODEL_CAP_ORIGINS WHERE GROUP_ID=:group_id AND ORIGIN_ID=:origin_id",
                              {"group_id": group_id, "origin_id": origin_id})
        if not origin:
            raise PermissionError("Coordinator origin is unavailable")
        replay = _receipt(tx, actor, operation, scope, request)
        if replay:
            return {"origin_id": origin_id, "version": int(replay["resource_version"]), "replayed": True}
        require_version(int(origin["version"]), request.expected_version)
        version = int(origin["version"]) + 1
        tx.execute("UPDATE CX_MODEL_CAP_ORIGINS SET STATUS=:status,VERSION=:revision WHERE GROUP_ID=:group_id AND ORIGIN_ID=:origin_id",
                   {"status": request.status, "revision": version, "group_id": group_id, "origin_id": origin_id})
        _record_scoped(tx, actor, operation, group_id, scope, request, version)
        return {"origin_id": origin_id, "version": version, "replayed": False}
    return connection.execute_transaction_callback(change)


def _record_scoped(tx, actor, operation, group_id, scope, request, version, *, admission_id=None):
    # Store the real FK group separately from the operation's exact locator.
    tx.execute("INSERT INTO CX_MODEL_CAP_REQUESTS(ACTOR_ID,OPERATION,IDEMPOTENCY_KEY,REQUEST_DIGEST,GROUP_ID,ADMISSION_ID,RESOURCE_VERSION,CREATED_AT_MS) "
               "VALUES(:actor,:operation,:idem_key,:fingerprint,:group_id,:admission_id,:revision,:now_ms)",
               {"actor": actor, "operation": operation, "idem_key": request.idempotency_key,
                "fingerprint": _fingerprint(scope, request), "group_id": group_id,
                "admission_id": admission_id, "revision": version, "now_ms": _now_ms(tx)})
    identity_api._audit_tx(tx, actor, operation, "MODEL_CAPACITY", admission_id or group_id, "ALLOW", request.reason)


def register_alias(actor, group_id, value):
    request = CapacityAlias.model_validate(value)
    url, key = endpoint_url(request.endpoint_url), alias_key(request.endpoint_url)
    def register(tx):
        _admin(tx, actor)
        group, _ = _group(tx, group_id)
        replay = _receipt(tx, actor, "MODEL_CAP_ALIAS_REGISTER", group_id, request)
        if replay:
            return {"group_id": group_id, "version": int(replay["resource_version"]), "replayed": True}
        require_version(int(group["version"]), request.expected_version)
        existing = tx.query_one("SELECT GROUP_ID FROM CX_MODEL_CAP_ALIASES WHERE ALIAS_KEY=:alias_key", {"alias_key": key})
        if existing and existing["group_id"] != group_id:
            raise ContinuityConflict("ALIAS_ALREADY_BOUND", "Endpoint alias already belongs to another coordinator group")
        if not existing:
            tx.execute("INSERT INTO CX_MODEL_CAP_ALIASES(ALIAS_KEY,ENDPOINT_URL,GROUP_ID,REGISTERED_BY,CREATED_AT_MS) "
                       "VALUES(:alias_key,:endpoint_url,:group_id,:actor,:now_ms)",
                       {"alias_key": key, "endpoint_url": url, "group_id": group_id, "actor": actor, "now_ms": _now_ms(tx)})
        if request.profile_id:
            profile = tx.query_one("SELECT PROVIDER_URL,STATUS FROM CX_LLM_PROVIDER_PROFILES WHERE PROFILE_ID=:profile", {"profile": request.profile_id})
            if not profile or profile["status"] != "ACTIVE" or alias_key(profile["provider_url"]) != key:
                raise PermissionError("Profile must currently use the exact registered alias")
            binding = tx.query_one("SELECT GROUP_ID FROM CX_MODEL_CAP_BINDINGS WHERE PROFILE_ID=:profile", {"profile": request.profile_id})
            if binding and binding["group_id"] != group_id:
                raise ContinuityConflict("PROFILE_ALREADY_BOUND", "Profile already belongs to another coordinator group")
            if not binding:
                tx.execute("INSERT INTO CX_MODEL_CAP_BINDINGS(PROFILE_ID,GROUP_ID,REGISTERED_BY,CREATED_AT_MS) "
                           "VALUES(:profile,:group_id,:actor,:now_ms)",
                           {"profile": request.profile_id, "group_id": group_id, "actor": actor, "now_ms": _now_ms(tx)})
        version = int(group["version"]) + 1
        tx.execute("UPDATE CX_MODEL_CAP_GROUPS SET VERSION=:revision WHERE GROUP_ID=:group_id", {"revision": version, "group_id": group_id})
        _record(tx, actor, "MODEL_CAP_ALIAS_REGISTER", group_id, request, version)
        return {"group_id": group_id, "version": version, "replayed": False}
    return connection.execute_transaction_callback(register)


def selected_group(tx, profile_id, url):
    """Both Profile and endpoint aliases must agree; another Profile is no bypass."""
    key = alias_key(url)
    endpoint = tx.query_one("SELECT GROUP_ID FROM CX_MODEL_CAP_ALIASES WHERE ALIAS_KEY=:alias_key", {"alias_key": key})
    binding = tx.query_one("SELECT GROUP_ID FROM CX_MODEL_CAP_BINDINGS WHERE PROFILE_ID=:profile", {"profile": profile_id}) if profile_id else None
    if binding and (not endpoint or binding["group_id"] != endpoint["group_id"]):
        raise PermissionError("Capacity-controlled Profile changed to an unregistered endpoint")
    return endpoint["group_id"] if endpoint else None


def _profile(tx, actor, record):
    profile = tx.query_one("SELECT VERSION,MODEL_ID,PROVIDER_URL,STATUS FROM CX_LLM_PROVIDER_PROFILES WHERE PROFILE_ID=:profile FOR UPDATE",
                           {"profile": record["profile_id"]})
    if (not profile or profile["status"] != "ACTIVE" or int(profile["version"]) != int(record["profile_version"])
            or profile["model_id"] != record["model_id"] or alias_key(profile["provider_url"]) != record["alias_key"]
            or selected_group(tx, record["profile_id"], profile["provider_url"]) != record["group_id"]):
        raise PermissionError("Provider Profile or endpoint capacity binding changed")


def _state(tx, admission_id):
    record = tx.query_one("SELECT * FROM CX_MODEL_ADMISSIONS WHERE ADMISSION_ID=:admission_id", {"admission_id": admission_id})
    if not record:
        raise PermissionError("Model admission is unavailable")
    return record


def _view(tx, record, *, replayed=False):
    attempt = tx.query_one("SELECT ATTEMPT_ID FROM CX_MODEL_CAP_ATTEMPTS WHERE ADMISSION_ID=:admission_id", {"admission_id": record["admission_id"]})
    value = {key: record[key] for key in (
        "admission_id", "group_id", "origin_id", "status", "version", "fencing_token", "lease_until_ms",
        "queue_until_ms", "overall_until_ms", "cancel_state", "finish_code", "policy_revision",
    )}
    for key in ("version", "fencing_token", "lease_until_ms", "queue_until_ms", "overall_until_ms", "policy_revision"):
        value[key] = int(value[key]) if value[key] is not None else None
    return value | {"attempt_id": attempt["attempt_id"] if attempt else None, "replayed": replayed,
                   "occupies_capacity": record["status"] in OCCUPIED}


def _transition(tx, record, status, finish_code, *, cancel_state=None, lease_until_ms=None, fence=None):
    version = int(record["version"]) + 1
    params = {"status": status, "finish_code": finish_code, "revision": version,
              "cancel_state": cancel_state or record["cancel_state"],
              "lease_until_ms": lease_until_ms if lease_until_ms is not None else record["lease_until_ms"],
              "fence": fence if fence is not None else record["fencing_token"], "admission_id": record["admission_id"]}
    tx.execute("UPDATE CX_MODEL_ADMISSIONS SET STATUS=:status,FINISH_CODE=:finish_code,VERSION=:revision,CANCEL_STATE=:cancel_state," 
               "LEASE_UNTIL_MS=:lease_until_ms,FENCING_TOKEN=:fence WHERE ADMISSION_ID=:admission_id", params)
    record.update(status=status, finish_code=finish_code, version=version, cancel_state=params["cancel_state"],
                  lease_until_ms=params["lease_until_ms"], fencing_token=params["fence"])


def _sweep(tx, actor, group, now):
    rows = tx.query("SELECT * FROM CX_MODEL_ADMISSIONS WHERE GROUP_ID=:group_id AND STATUS IN ('QUEUED','RESERVED','DISPATCHING') ORDER BY QUEUE_SEQUENCE",
                    {"group_id": group["group_id"]})
    for record in rows:
        status, code = None, None
        if record["status"] == "QUEUED" and (now > int(record["queue_until_ms"]) or now >= int(record["overall_until_ms"])):
            status, code = "EXPIRED", "QUEUE_DEADLINE"
        elif record["status"] == "RESERVED" and now >= min(int(record["lease_until_ms"]), int(record["overall_until_ms"])):
            status, code = "EXPIRED", "UNCONSUMED_RESERVATION_EXPIRED"
        elif record["status"] == "DISPATCHING" and now >= int(record["overall_until_ms"]):
            status, code = "UNKNOWN", "OVERALL_DEADLINE_REMOTE_UNCONFIRMED"
        if status:
            _transition(tx, record, status, code)
            if status == "UNKNOWN":
                tx.execute("UPDATE CX_MODEL_CAP_ATTEMPTS SET STATUS='UNKNOWN',FINISH_CODE=:finish_code WHERE ADMISSION_ID=:admission_id",
                           {"finish_code": code, "admission_id": record["admission_id"]})
            identity_api._audit_tx(tx, actor, "MODEL_CAPACITY_EXPIRED", "MODEL_CAPACITY", record["admission_id"], "ALLOW", code)


def _reserve(tx, actor, record, group, policy, now):
    if record["status"] != "QUEUED":
        return
    if group["status"] != "ACTIVE" or int(record["policy_revision"]) != int(group["current_revision"]):
        _transition(tx, record, "REJECTED", "CAPACITY_POLICY_CHANGED")
        return
    occupied = tx.query_one("SELECT COUNT(*) AS OCCUPIED_COUNT FROM CX_MODEL_ADMISSIONS WHERE GROUP_ID=:group_id AND STATUS IN ('RESERVED','DISPATCHING','UNKNOWN')",
                            {"group_id": group["group_id"]})
    ahead = tx.query_one("SELECT COUNT(*) AS AHEAD_COUNT FROM CX_MODEL_ADMISSIONS WHERE GROUP_ID=:group_id AND STATUS='QUEUED' AND QUEUE_SEQUENCE<:sequence_no",
                        {"group_id": group["group_id"], "sequence_no": record["queue_sequence"]})
    if int(occupied["occupied_count"]) + int(ahead["ahead_count"]) >= int(policy["capacity"]):
        return
    _transition(tx, record, "RESERVED", None, lease_until_ms=min(now + int(policy["reservation_ms"]), int(record["overall_until_ms"])),
                fence=int(record["fencing_token"]) + 1)
    identity_api._audit_tx(tx, actor, "MODEL_CAPACITY_RESERVED", "MODEL_CAPACITY", record["admission_id"], "ALLOW", "Durable capacity reservation")


def admit(actor, group_id, value):
    request = ModelAdmission.model_validate(value)
    def enqueue(tx):
        work._lock_actor(tx, actor)
        group, policy = _group(tx, group_id)
        _origin(tx, actor, group_id, request.origin_id)
        replay = _receipt(tx, actor, "MODEL_CAP_ADMIT", group_id, request)
        if replay:
            return _view(tx, _state(tx, replay["admission_id"]), replayed=True)
        if group["status"] != "ACTIVE":
            raise ContinuityConflict("CAPACITY_DRAINING", "Endpoint group accepts no new requests")
        record = {**request.model_dump(), "group_id": group_id, "alias_key": alias_key(request.endpoint_url)}
        _profile(tx, actor, record)
        now = _now_ms(tx)
        _sweep(tx, actor, group, now)
        admission_id, sequence = identifier("MAD"), int(group["next_sequence"])
        tx.execute("UPDATE CX_MODEL_CAP_GROUPS SET NEXT_SEQUENCE=:sequence_no WHERE GROUP_ID=:group_id", {"sequence_no": sequence + 1, "group_id": group_id})
        params = {"admission_id": admission_id, "group_id": group_id, "policy_revision": group["current_revision"],
                  "origin_id": request.origin_id, "actor": actor, "profile": request.profile_id, "profile_version": request.profile_version,
                  "model_id": request.model_id, "alias_key": record["alias_key"], "input_digest": request.input_digest,
                  "credential_digest": request.credential_digest, "fingerprint": _fingerprint(group_id, request),
                  "source_kind": request.source_kind, "source_id": request.source_id, "source_attempt": request.source_attempt_id,
                  "sequence_no": sequence, "queue_until": now + int(policy["queue_ms"]), "overall_until": now + int(policy["overall_ms"]), "now_ms": now}
        tx.execute("INSERT INTO CX_MODEL_ADMISSIONS(ADMISSION_ID,GROUP_ID,POLICY_REVISION,ORIGIN_ID,ACTOR_ID,PROFILE_ID,PROFILE_VERSION,MODEL_ID,ALIAS_KEY," 
                   "INPUT_DIGEST,CREDENTIAL_DIGEST,REQUEST_DIGEST,SOURCE_KIND,SOURCE_ID,SOURCE_ATTEMPT_ID,QUEUE_SEQUENCE,STATUS,VERSION,FENCING_TOKEN," 
                   "QUEUE_UNTIL_MS,OVERALL_UNTIL_MS,CANCEL_STATE,CREATED_AT_MS) VALUES(:admission_id,:group_id,:policy_revision,:origin_id,:actor,:profile," 
                   ":profile_version,:model_id,:alias_key,:input_digest,:credential_digest,:fingerprint,:source_kind,:source_id,:source_attempt,:sequence_no," 
                   "'QUEUED',1,0,:queue_until,:overall_until,'NOT_REQUESTED',:now_ms)", params)
        record = _state(tx, admission_id)
        _reserve(tx, actor, record, group, policy, now)
        _record(tx, actor, "MODEL_CAP_ADMIT", group_id, request, int(record["version"]), admission_id=admission_id)
        return _view(tx, record)
    return connection.execute_transaction_callback(enqueue)


def _locked_admission(tx, actor, admission_id, *, administrator=False, lock_principals=()):
    # Trusted dispatchers declare every local Principal their authorization
    # callbacks may lock. Acquire the complete set in a stable order before
    # the group, preventing cross-Agent callbacks from inverting that order.
    for principal in sorted({actor, *lock_principals}):
        work._lock_actor(tx, principal)
    location = _state(tx, admission_id)
    group, policy = _group(tx, location["group_id"])
    record = _state(tx, admission_id)
    if administrator:
        authorize(actor, "model_gateway.manage")
    else:
        _origin(tx, actor, group["group_id"], record["origin_id"])
        if record["actor_id"] != actor:
            raise PermissionError("Model admission belongs to a different authenticated origin")
    return record, group, policy


def read_admission(actor, admission_id, *, reserve=False, administrator=False):
    def read(tx):
        record, group, policy = _locked_admission(tx, actor, admission_id, administrator=administrator)
        if reserve:
            if administrator:
                raise PermissionError("Administrator reads cannot dispatch an origin's request")
            now = _now_ms(tx)
            _sweep(tx, actor, group, now)
            record = _state(tx, admission_id)
            try:
                _profile(tx, actor, record)
            except PermissionError:
                if record["status"] in {"QUEUED", "RESERVED"}:
                    _transition(tx, record, "REJECTED", "CURRENT_PROFILE_DENIED")
            _reserve(tx, actor, record, group, policy, now)
        return _view(tx, record)
    return connection.execute_transaction_callback(read)


def begin_dispatch(actor, admission_id, value, *, reauthorize, lock_principals=()):
    """Commit the possible-send boundary immediately before the network send.

    ``reauthorize(tx, record)`` is a trusted dispatcher callback, never a caller
    claim. It must check the original credential, Agent, Worker and disclosure.
    An exception records a terminal non-dispatched denial atomically.
    """
    request = ReservationClaim.model_validate(value)
    def begin(tx):
        record, group, policy = _locked_admission(tx, actor, admission_id, lock_principals=lock_principals)
        replay = _receipt(tx, actor, "MODEL_CAP_DISPATCH", admission_id, request)
        if replay:
            # A returned identity is observation only, never permission to send
            # again after a client lost the response to the first dispatch.
            return _view(tx, record, replayed=True) | {"dispatch_authorized": False}
        require_version(int(record["version"]), request.expected_version)
        now = _now_ms(tx)
        if (record["status"] != "RESERVED" or int(record["fencing_token"]) != request.fencing_token
                or request.credential_digest != record["credential_digest"]):
            raise ContinuityConflict("FENCING_MISMATCH", "Current unconsumed reservation and original credential are required")
        if now >= min(int(record["lease_until_ms"]), int(record["overall_until_ms"])):
            _transition(tx, record, "EXPIRED", "UNCONSUMED_RESERVATION_EXPIRED")
        elif group["status"] != "ACTIVE" or int(group["current_revision"]) != int(record["policy_revision"]):
            _transition(tx, record, "REJECTED", "CAPACITY_POLICY_CHANGED")
        else:
            try:
                _profile(tx, actor, record)
                reauthorize(tx, dict(record))
            except PermissionError:
                _transition(tx, record, "REJECTED", "CURRENT_DISPATCH_AUTHORITY_DENIED")
            else:
                _transition(tx, record, "DISPATCHING", None)
                tx.execute("INSERT INTO CX_MODEL_CAP_ATTEMPTS(ATTEMPT_ID,ADMISSION_ID,FENCING_TOKEN,WORKER_KEY,STATUS,DISPATCH_AT_MS) "
                           "VALUES(:attempt,:admission_id,:fence,:worker,'DISPATCHING',:now_ms)",
                           {"attempt": identifier("MCA"), "admission_id": admission_id, "fence": request.fencing_token,
                            "worker": request.worker_key, "now_ms": now})
        _record_scoped(tx, actor, "MODEL_CAP_DISPATCH", group["group_id"], admission_id, request, int(record["version"]), admission_id=admission_id)
        return _view(tx, record) | {"dispatch_authorized": record["status"] == "DISPATCHING",
                                   "socket_ms": int(policy["socket_ms"]), "idle_ms": int(policy["idle_ms"])}
    return connection.execute_transaction_callback(begin)


def cancel_admission(actor, admission_id, value):
    request = CapacityCancellation.model_validate(value)
    def cancel(tx):
        record, group, _ = _locked_admission(tx, actor, admission_id)
        replay = _receipt(tx, actor, "MODEL_CAP_CANCEL", admission_id, request)
        if replay:
            return _view(tx, record, replayed=True)
        require_version(int(record["version"]), request.expected_version)
        if record["status"] in {"QUEUED", "RESERVED"}:
            _transition(tx, record, "CANCELLED", "CANCELLED_BEFORE_DISPATCH", cancel_state="QUEUE_CANCELLED")
        elif record["status"] in {"DISPATCHING", "UNKNOWN"}:
            _transition(tx, record, "UNKNOWN", "LOCAL_CANCEL_REMOTE_UNCONFIRMED", cancel_state="LOCAL_CANCELLED")
            tx.execute("UPDATE CX_MODEL_CAP_ATTEMPTS SET STATUS='UNKNOWN',FINISH_CODE='LOCAL_CANCEL_REMOTE_UNCONFIRMED' WHERE ADMISSION_ID=:admission_id", {"admission_id": admission_id})
        _record_scoped(tx, actor, "MODEL_CAP_CANCEL", group["group_id"], admission_id, request, int(record["version"]), admission_id=admission_id)
        return _view(tx, record)
    return connection.execute_transaction_callback(cancel)


def observe_completion(actor, admission_id, value, *, reconcile=False, transaction=None):
    """Record trusted transport evidence or a separately authorized resolution.

    HTTP callers only receive the administrator reconciliation route. Business
    success is deliberately separate: refusal/invalid output may still be a
    completed provider request and release the transport slot.
    """
    request = CapacityObservation.model_validate(value)
    if reconcile:
        if request.evidence_kind not in {"LOCAL_LIFECYCLE", "OPERATOR_CONFIRMATION", "REMOTE_TERMINATED"}:
            raise ValueError("Reconciliation needs explicit completion evidence")
    elif request.evidence_kind not in {"COMPLETE_RESPONSE", "REMOTE_TERMINATED", "TRANSPORT_UNKNOWN"}:
        raise PermissionError("Independent lifecycle evidence requires administrator reconciliation")
    operation = "MODEL_CAP_RECONCILE" if reconcile else "MODEL_CAP_OBSERVE"
    def observe(tx):
        record, group, _ = _locked_admission(tx, actor, admission_id, administrator=reconcile)
        replay = _receipt(tx, actor, operation, admission_id, request)
        if replay:
            return _view(tx, record, replayed=True)
        require_version(int(record["version"]), request.expected_version)
        attempt = tx.query_one("SELECT * FROM CX_MODEL_CAP_ATTEMPTS WHERE ADMISSION_ID=:admission_id", {"admission_id": admission_id})
        if (not attempt or attempt["attempt_id"] != request.attempt_id or int(attempt["fencing_token"]) != request.fencing_token
                or int(record["fencing_token"]) != request.fencing_token):
            raise ContinuityConflict("FENCING_MISMATCH", "Completion evidence must identify the exact dispatch attempt")
        if record["status"] not in {"DISPATCHING", "UNKNOWN"}:
            raise ContinuityConflict("INVALID_TRANSITION", "A terminal admission cannot be resolved again")
        if reconcile and record["status"] != "UNKNOWN":
            raise ContinuityConflict("INVALID_TRANSITION", "Reconciliation resolves an uncertain dispatch")
        unknown = request.evidence_kind == "TRANSPORT_UNKNOWN"
        _transition(tx, record, "UNKNOWN" if unknown else "COMPLETED", request.finish_code,
                    cancel_state="REMOTE_CONFIRMED" if request.evidence_kind == "REMOTE_TERMINATED" else None)
        now = _now_ms(tx)
        tx.execute("INSERT INTO CX_MODEL_CAP_EVIDENCE(EVIDENCE_ID,ADMISSION_ID,ATTEMPT_ID,ACTOR_ID,RESOURCE_VERSION,EVIDENCE_KIND,EVIDENCE_DIGEST,FINISH_CODE,REASON,CREATED_AT_MS) "
                   "VALUES(:evidence,:admission_id,:attempt,:actor,:revision,:evidence_kind,:evidence_digest,:finish_code,:reason,:now_ms)",
                   {"evidence": identifier("MCE"), "admission_id": admission_id, "attempt": request.attempt_id, "actor": actor,
                    "revision": record["version"], "evidence_kind": request.evidence_kind, "evidence_digest": request.evidence_digest,
                    "finish_code": request.finish_code, "reason": request.reason, "now_ms": now})
        tx.execute("UPDATE CX_MODEL_CAP_ATTEMPTS SET STATUS=:status,FINISH_CODE=:finish_code,COMPLETED_AT_MS=:completed WHERE ATTEMPT_ID=:attempt",
                   {"status": "UNKNOWN" if unknown else ("RECONCILED" if reconcile else "COMPLETED"), "finish_code": request.finish_code,
                    "completed": None if unknown else now, "attempt": request.attempt_id})
        _record_scoped(tx, actor, operation, group["group_id"], admission_id, request, int(record["version"]), admission_id=admission_id)
        return _view(tx, record)
    return observe(transaction) if transaction is not None else connection.execute_transaction_callback(observe)


def list_groups(actor, *, after="", limit=20):
    if type(limit) is not int or not 1 <= limit <= 50 or not isinstance(after, str) or len(after) > 128:
        raise ValueError("Invalid capacity group page")
    def read(tx):
        _admin(tx, actor)
        rows = tx.query("SELECT GROUP_ID,RESOURCE_KEY,COORDINATOR_ID,CURRENT_REVISION,VERSION,STATUS FROM "
                        "(SELECT GROUP_ID,RESOURCE_KEY,COORDINATOR_ID,CURRENT_REVISION,VERSION,STATUS,ROW_NUMBER() OVER(ORDER BY GROUP_ID) AS PAGE_ROW "
                        "FROM CX_MODEL_CAP_GROUPS WHERE (:after_id IS NULL OR GROUP_ID>:after_id)) page WHERE PAGE_ROW<=:page_limit ORDER BY GROUP_ID",
                        {"after_id": after or None, "page_limit": limit + 1})
        return {"groups": rows[:limit], "next_after": rows[limit - 1]["group_id"] if len(rows) > limit else None,
                "coordination_scope": "ONE_DATABASE_AUTHORITY"}
    return connection.execute_transaction_callback(read)


def read_group(actor, group_id):
    def read(tx):
        _admin(tx, actor)
        group, policy = _group(tx, group_id)
        origins = tx.query("SELECT ORIGIN_ID,PRINCIPAL_ID,INSTALLATION_KEY,STATUS,VERSION FROM CX_MODEL_CAP_ORIGINS WHERE GROUP_ID=:group_id ORDER BY ORIGIN_ID",
                           {"group_id": group_id})
        aliases = tx.query("SELECT ENDPOINT_URL FROM CX_MODEL_CAP_ALIASES WHERE GROUP_ID=:group_id ORDER BY ALIAS_KEY", {"group_id": group_id})
        occupancy = tx.query("SELECT STATUS,COUNT(*) AS REQUEST_COUNT FROM CX_MODEL_ADMISSIONS WHERE GROUP_ID=:group_id AND STATUS IN ('QUEUED','RESERVED','DISPATCHING','UNKNOWN') GROUP BY STATUS",
                             {"group_id": group_id})
        return {"group_id": group_id, "resource_key": group["resource_key"], "coordinator_id": group["coordinator_id"],
                "version": int(group["version"]), "status": group["status"], "policy_revision": int(group["current_revision"]),
                "policy": {key: int(policy[key]) for key in ("capacity", "queue_ms", "socket_ms", "idle_ms", "overall_ms", "reservation_ms")},
                "origins": origins, "aliases": aliases, "occupancy": occupancy, "coordination_scope": "ONE_DATABASE_AUTHORITY"}
    return connection.execute_transaction_callback(read)


def list_group_admissions(actor, group_id, *, after_sequence=0, limit=20):
    """Bounded operator metadata; no source names, prompts or credentials."""
    if type(after_sequence) is not int or after_sequence < 0 or type(limit) is not int or not 1 <= limit <= 50:
        raise ValueError("Invalid capacity admission page")
    def read(tx):
        _admin(tx, actor)
        _group(tx, group_id)
        values = tx.query("SELECT ADMISSION_ID,QUEUE_SEQUENCE FROM (SELECT ADMISSION_ID,QUEUE_SEQUENCE,"
            "ROW_NUMBER() OVER(ORDER BY QUEUE_SEQUENCE) AS PAGE_ROW FROM CX_MODEL_ADMISSIONS "
            "WHERE GROUP_ID=:group_id AND QUEUE_SEQUENCE>:after_sequence) page WHERE PAGE_ROW<=:page_limit ORDER BY QUEUE_SEQUENCE",
            {"group_id": group_id, "after_sequence": after_sequence, "page_limit": limit + 1})
        records = [_view(tx, _state(tx, value["admission_id"])) for value in values[:limit]]
        return {"items": records, "next_sequence": int(values[limit - 1]["queue_sequence"]) if len(values) > limit else None}
    return connection.execute_transaction_callback(read)
