"""Database-authoritative source IP admission, independent of user authority."""

from __future__ import annotations

import ipaddress
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from functools import cached_property
from typing import Any, Callable

from . import connection, identity_api

CACHE_SECONDS = 1.0
MAX_RULES = 512
DENIAL = b'{"detail":"Request could not be completed."}'
FORWARD_HEADERS = {b"x-forwarded-for", b"forwarded", b"x-real-ip"}


class PolicyError(ValueError):
    """Invalid administrator input; never returned to a rejected source."""


class RevisionConflict(PolicyError):
    pass


@contextmanager
def _owner():
    previous = connection.get_current_agent_id()
    connection.set_agent_context(None)
    try:
        yield
    finally:
        connection.set_agent_context(previous)


def address(value: str):
    if not isinstance(value, str) or not value or "%" in value or value != value.strip():
        raise PolicyError("Invalid IP address")
    try:
        parsed = ipaddress.ip_address(value)
    except ValueError as exc:
        raise PolicyError("Invalid IP address") from exc
    return parsed.ipv4_mapped if isinstance(parsed, ipaddress.IPv6Address) and parsed.ipv4_mapped else parsed


def normalize_rules(values: list[str] | tuple[str, ...]) -> tuple[str, ...]:
    if not isinstance(values, (list, tuple)) or len(values) > MAX_RULES:
        raise PolicyError("At most 512 IP addresses or CIDR networks are allowed")
    result = []
    for value in values:
        if not isinstance(value, str) or not value.strip() or len(value) > 64 or "%" in value:
            raise PolicyError("Each rule must be an IP address or CIDR network")
        value = value.strip()
        # Only numeric prefix lengths: dotted netmasks and hostnames are not CIDRs.
        if "/" in value and not value.rsplit("/", 1)[1].isascii():
            raise PolicyError("Invalid CIDR prefix")
        if "/" in value and not value.rsplit("/", 1)[1].isdigit():
            raise PolicyError("Invalid CIDR prefix")
        try:
            network = ipaddress.ip_network(value, strict=False)
        except ValueError as exc:
            raise PolicyError("Each rule must be an IP address or CIDR network") from exc
        if isinstance(network, ipaddress.IPv6Network) and network.network_address.ipv4_mapped:
            network = ipaddress.ip_network(f"{network.network_address.ipv4_mapped}/{network.prefixlen - 96}")
        canonical = str(network)
        if canonical not in result:
            result.append(canonical)
    return tuple(result)


@dataclass(frozen=True)
class Policy:
    revision: int
    enabled: bool
    list_mode: str
    rules: tuple[str, ...]

    @cached_property
    def networks(self):
        return tuple(ipaddress.ip_network(item) for item in self.rules)

    def allows(self, source: str) -> bool:
        parsed = address(source)
        if not self.enabled:
            return True
        matched = any(parsed.version == network.version and parsed in network for network in self.networks)
        return matched if self.list_mode == "ALLOWLIST" else not matched

    def public(self) -> dict[str, Any]:
        return {"revision": self.revision, "enabled": self.enabled,
                "list_mode": self.list_mode, "rules": list(self.rules)}


def candidate(enabled: bool, list_mode: str, rules: list[str]) -> Policy:
    if type(enabled) is not bool or list_mode not in {"ALLOWLIST", "DENYLIST"}:
        raise PolicyError("Invalid policy state or list mode")
    return Policy(0, enabled, list_mode, normalize_rules(rules))


def _lower(row: dict) -> dict:
    return {str(key).lower(): value for key, value in row.items()}


def load_policy() -> Policy:
    # One statement provides a coherent snapshot even during a concurrent edit.
    with _owner():
        rows = connection.execute_query(
            "SELECT r.REVISION,r.ENABLED,r.LIST_MODE,n.NETWORK_CIDR "
            "FROM CX_IP_ACCESS_STATE s JOIN CX_IP_ACCESS_REVISIONS r ON r.REVISION=s.REVISION "
            "LEFT JOIN CX_IP_ACCESS_RULES n ON n.REVISION=r.REVISION "
            "WHERE s.POLICY_KEY='GLOBAL' ORDER BY n.RULE_NO", {})
    rows = [_lower(row) for row in rows]
    if not rows:
        raise RuntimeError("Source policy is unavailable")
    first = rows[0]
    enabled, list_mode = first["enabled"], first["list_mode"]
    if enabled not in {"Y", "N"} or list_mode not in {"ALLOWLIST", "DENYLIST"}:
        raise RuntimeError("Source policy is invalid")
    rules = tuple(str(row["network_cidr"]) for row in rows if row.get("network_cidr"))
    return Policy(int(first["revision"]), enabled == "Y", list_mode, normalize_rules(rules))


class PolicyCache:
    def __init__(self, loader: Callable[[], Policy] = load_policy, clock: Callable[[], float] = time.monotonic):
        self.loader, self.clock = loader, clock
        self.lock = threading.Lock()
        self.value: Policy | None = None
        self.expires = 0.0

    def invalidate(self) -> None:
        with self.lock:
            self.expires = 0.0

    def get(self) -> Policy:
        with self.lock:
            if self.value is not None and self.clock() < self.expires:
                return self.value
            # Age starts before the read: a slow DB must not extend stale admission.
            started = self.clock()
            self.value = self.loader()
            self.expires = started + CACHE_SECONDS
            return self.value


policy_cache = PolicyCache()


def _manage(actor: str) -> None:
    if identity_api.effective_access(actor, "platform.manage").get("decision") != "ALLOW":
        raise PermissionError("Platform management permission required")


def configuration(actor: str) -> dict:
    with _owner():
        _manage(actor)
        policy = load_policy()
        history = connection.execute_query(
            "SELECT REVISION,ENABLED,LIST_MODE,UPDATED_BY,REASON,CREATED_AT FROM CX_IP_ACCESS_REVISIONS "
            "WHERE REVISION > :min_revision ORDER BY REVISION DESC",
            {"min_revision": max(0, policy.revision - 20)})
    return {**policy.public(), "history": [_lower(row) for row in history],
            "emergency_ip": "127.0.0.1", "propagation_seconds": CACHE_SECONDS}


def update(actor: str, *, enabled: bool, list_mode: str, rules: list[str], expected_revision: int, reason: str) -> dict:
    proposed = candidate(enabled, list_mode, rules)
    reason = str(reason or "").strip()
    if type(expected_revision) is not int or expected_revision < 1 or not 3 <= len(reason) <= 2000:
        raise PolicyError("A current revision and a change reason of 3–2000 characters are required")
    try:
        reason_bytes = len(reason.encode("utf-8"))
    except UnicodeEncodeError as exc:
        raise PolicyError("Change reason must be valid UTF-8") from exc
    # Oracle's policy and existing audit columns use byte-length semantics.
    # Validate the shared bound before any database transaction is started.
    if reason_bytes > 2000:
        raise PolicyError("Change reason must not exceed 2000 UTF-8 bytes")
    with _owner():
        _manage(actor)

        def work(tx):
            current = tx.query_one("SELECT REVISION FROM CX_IP_ACCESS_STATE WHERE POLICY_KEY='GLOBAL' FOR UPDATE", {})
            if not current or int(_lower(current)["revision"]) != expected_revision:
                raise RevisionConflict("Policy changed; reload before saving")
            revision = expected_revision + 1
            tx.execute("INSERT INTO CX_IP_ACCESS_REVISIONS(REVISION,ENABLED,LIST_MODE,UPDATED_BY,REASON) "
                       "VALUES (:revision,:enabled,:list_mode,:actor_id,:reason)",
                       {"revision": revision, "enabled": "Y" if enabled else "N", "list_mode": list_mode,
                        "actor_id": actor, "reason": reason})
            for index, network in enumerate(proposed.rules, 1):
                tx.execute("INSERT INTO CX_IP_ACCESS_RULES(REVISION,RULE_NO,NETWORK_CIDR,IP_VERSION) "
                           "VALUES (:revision,:rule_no,:network_cidr,:ip_version)",
                           {"revision": revision, "rule_no": index, "network_cidr": network,
                            "ip_version": ipaddress.ip_network(network).version})
            tx.execute("UPDATE CX_IP_ACCESS_STATE SET REVISION=:revision WHERE POLICY_KEY='GLOBAL'", {"revision": revision})
            identity_api._audit_tx(tx, actor, "SOURCE_IP_POLICY_UPDATE", "IP_ACCESS_POLICY", str(revision), "ALLOW", reason)
            return {**proposed.public(), "revision": revision}

        result = connection.execute_transaction_callback(work)
    policy_cache.invalidate()
    return result


@dataclass(frozen=True)
class Source:
    ip: str
    recovery: bool
    proxied: bool


def trusted_proxies(value: str) -> tuple:
    if not value.strip():
        return ()
    networks = tuple(ipaddress.ip_network(rule) for rule in normalize_rules(value.split(",")))
    recovery = ipaddress.ip_address("127.0.0.1")
    if any(net.version == 4 and recovery in net for net in networks):
        raise PolicyError("127.0.0.1 is reserved for recovery; bind local proxies to a different source address")
    return networks


def resolve_source(scope: dict, trusted: tuple = ()) -> Source:
    peer = address(scope.get("client", (None, 0))[0])
    headers = [(key.lower(), value) for key, value in scope.get("headers", [])]
    has_forwarding = any(key in FORWARD_HEADERS or key.startswith(b"x-forwarded-") for key, _ in headers)

    def is_proxy(ip) -> bool:
        return any(ip.version == net.version and ip in net for net in trusted)

    if not is_proxy(peer):
        if str(peer) == "127.0.0.1" and has_forwarding:
            raise PolicyError("Recovery connections must be direct")
        return Source(str(peer), str(peer) == "127.0.0.1" and not has_forwarding, False)
    forwarded = [value for key, value in headers if key == b"x-forwarded-for"]
    if len(forwarded) != 1 or len(forwarded[0]) > 4096:
        raise PolicyError("Invalid forwarding chain")
    try:
        parts = forwarded[0].decode("ascii").split(",")
        if not 1 <= len(parts) <= 32:
            raise ValueError()
        chain = [address(part.strip()) for part in parts]
    except (ValueError, UnicodeError) as exc:
        raise PolicyError("Invalid forwarding chain") from exc
    source = peer
    for hop in reversed(chain):
        if not is_proxy(source):
            break
        source = hop
    return Source(str(source), False, True)


class SourceIPMiddleware:
    """Outermost ASGI admission, including static files and WebSocket upgrades.

    The ASGI server MUST have automatic proxy-header rewriting disabled.
    """

    def __init__(self, app, *, trusted_proxy_cidrs: str = "", cache: PolicyCache | None = None):
        self.app, self.trusted = app, trusted_proxies(trusted_proxy_cidrs)
        self.cache = cache if cache is not None else policy_cache

    async def __call__(self, scope, receive, send):
        if scope["type"] not in {"http", "websocket"}:
            return await self.app(scope, receive, send)
        try:
            source = resolve_source(scope, self.trusted)
            allowed = source.recovery
            if not allowed:
                from starlette.concurrency import run_in_threadpool
                allowed = (await run_in_threadpool(self.cache.get)).allows(source.ip)
        except Exception:
            allowed = False
        if allowed:
            scope.setdefault("state", {})["cx_source_ip"] = source
            return await self.app(scope, receive, send)
        headers = [(b"content-type", b"application/json"), (b"cache-control", b"no-store"),
                   (b"content-length", str(len(DENIAL)).encode("ascii"))]
        if scope["type"] == "websocket":
            if "websocket.http.response" not in scope.get("extensions", {}):
                return await send({"type": "websocket.close", "code": 1008, "reason": "Request could not be completed."})
            await send({"type": "websocket.http.response.start", "status": 403, "headers": headers})
            return await send({"type": "websocket.http.response.body", "body": DENIAL})
        await send({"type": "http.response.start", "status": 403, "headers": headers})
        await send({"type": "http.response.body", "body": DENIAL})


def schema_statements(database: str) -> list[str]:
    text_type = "VARCHAR"
    return [
        f"CREATE TABLE CX_IP_ACCESS_REVISIONS (REVISION INTEGER PRIMARY KEY CHECK(REVISION>0), ENABLED {text_type}(1) NOT NULL CHECK(ENABLED IN ('Y','N')), LIST_MODE {text_type}(16) NOT NULL CHECK(LIST_MODE IN ('ALLOWLIST','DENYLIST')), UPDATED_BY {text_type}(128) NOT NULL, REASON {text_type}(2000) NOT NULL, CREATED_AT TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL)",
        f"CREATE TABLE CX_IP_ACCESS_STATE (POLICY_KEY {text_type}(16) PRIMARY KEY CHECK(POLICY_KEY='GLOBAL'), REVISION INTEGER NOT NULL REFERENCES CX_IP_ACCESS_REVISIONS(REVISION))",
        f"CREATE TABLE CX_IP_ACCESS_RULES (REVISION INTEGER NOT NULL REFERENCES CX_IP_ACCESS_REVISIONS(REVISION), RULE_NO INTEGER NOT NULL CHECK(RULE_NO>=1 AND RULE_NO<=512), NETWORK_CIDR {text_type}(64) NOT NULL, IP_VERSION INTEGER NOT NULL CHECK(IP_VERSION IN (4,6)), PRIMARY KEY(REVISION,RULE_NO), UNIQUE(REVISION,NETWORK_CIDR))",
    ]
