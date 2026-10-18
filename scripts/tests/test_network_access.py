"""Source admission contracts: numeric IPs, real peer, cache and every ASGI path."""
from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor

import pytest

from lib import network_access as net


@pytest.mark.parametrize("value,expected", [
    ("192.0.2.9", "192.0.2.9/32"), ("192.0.2.9/24", "192.0.2.0/24"),
    ("2001:0DB8:1::1/32", "2001:db8::/32"), ("::1", "::1/128"),
    ("::ffff:192.0.2.3", "192.0.2.3/32"), ("::ffff:192.0.2.3/120", "192.0.2.0/24"),
    ("0.0.0.0/0", "0.0.0.0/0"), ("::/0", "::/0"),
])
def test_rule_canonicalization(value, expected):
    assert net.normalize_rules([value, value]) == (expected,)


@pytest.mark.parametrize("value", ["", "localhost", "010.1.2.3", "192.0.2.3:80", "[::1]", "fe80::1%eth0",
    "192.0.2.3/33", "2001:db8::/129", "192.0.2.0/255.255.255.0", "192.0.2.0/٢٤", "a" * 65, 42])
def test_invalid_rules(value):
    with pytest.raises(net.PolicyError):
        net.normalize_rules([value])


def test_limits_and_exact_flags():
    with pytest.raises(net.PolicyError): net.normalize_rules(["::"] * 513)
    with pytest.raises(net.PolicyError): net.candidate("false", "DENYLIST", [])
    with pytest.raises(net.PolicyError): net.candidate(True, "ALLOW", [])


@pytest.mark.parametrize("mode,source,expected", [
    ("ALLOWLIST", "192.0.2.0", True), ("ALLOWLIST", "192.0.2.255", True),
    ("ALLOWLIST", "192.0.3.0", False), ("ALLOWLIST", "2001:db8::ffff", True),
    ("ALLOWLIST", "2001:db9::", False), ("DENYLIST", "192.0.2.3", False),
    ("DENYLIST", "::ffff:192.0.2.3", False), ("DENYLIST", "2001:db9::", True),
])
def test_modes_and_boundaries(mode, source, expected):
    assert net.candidate(True, mode, ["192.0.2.0/24", "2001:db8::/32"]).allows(source) is expected


def test_empty_lists_and_disabled():
    assert not net.candidate(True, "ALLOWLIST", []).allows("127.0.0.1")  # Exemption is transport-only.
    assert net.candidate(True, "DENYLIST", []).allows("::1")
    assert net.candidate(False, "ALLOWLIST", []).allows("2001:db8::1")


def scope(peer="192.0.2.1", headers=(), kind="http", path="/app/"):
    return {"type": kind, "client": (peer, 9010), "headers": list(headers), "path": path, "extensions": {}}


def test_exact_emergency_and_untrusted_forwarding():
    assert net.resolve_source(scope("127.0.0.1")).recovery
    for peer in ("127.0.0.2", "127.1.2.3", "::1", "192.0.2.1"):
        result = net.resolve_source(scope(peer, [(b"x-forwarded-for", b"127.0.0.1")]))
        assert result.ip == peer and not result.recovery
    for header in (b"x-forwarded-for", b"forwarded", b"x-real-ip", b"x-forwarded-proto", b"x-forwarded-host"):
        with pytest.raises(net.PolicyError):
            net.resolve_source(scope("127.0.0.1", [(header, b"127.0.0.1")]))


def test_proxy_chain_peels_only_trusted_hops():
    trusted = net.trusted_proxies("10.0.0.0/8,127.0.0.2,2001:db8:1::/48")
    assert net.resolve_source(scope("10.0.0.1", [(b"x-forwarded-for", b"127.0.0.1, 198.51.100.3,10.0.0.2")]), trusted).ip == "198.51.100.3"
    local = net.resolve_source(scope("127.0.0.2", [(b"x-forwarded-for", b"127.0.0.1")]), trusted)
    assert local.proxied and not local.recovery
    assert net.resolve_source(scope("2001:db8:1::1", [(b"x-forwarded-for", b"2001:db8:2::1")]), trusted).ip == "2001:db8:2::1"


@pytest.mark.parametrize("headers", [[], [(b"x-forwarded-for", b"unknown")], [(b"x-forwarded-for", b"192.0.2.1,,10.0.0.1")],
    [(b"x-forwarded-for", b"192.0.2.1"), (b"x-forwarded-for", b"127.0.0.1")], [(b"x-forwarded-for", b"a" * 4097)],
    [(b"x-forwarded-for", b"192.0.2.1," * 33)], [(b"x-forwarded-for", b"\xff")]])
def test_invalid_or_missing_trusted_forwarding_fails_closed(headers):
    with pytest.raises(net.PolicyError):
        net.resolve_source(scope("127.0.0.2", headers), net.trusted_proxies("127.0.0.2"))


@pytest.mark.parametrize("value", ["127.0.0.1", "127.0.0.0/8", "0.0.0.0/0", "::ffff:127.0.0.1"])
def test_proxy_trust_cannot_consume_emergency_address(value):
    with pytest.raises(net.PolicyError): net.trusted_proxies(value)


def test_cache_expiry_failure_and_invalidation():
    now, calls = [10.0], []
    def loader():
        calls.append(1)
        if len(calls) == 2: raise RuntimeError("DB down")
        return net.Policy(len(calls), True, "DENYLIST", ())
    cache = net.PolicyCache(loader, lambda: now[0])
    assert cache.get().revision == cache.get().revision == 1
    now[0] += 1.01
    with pytest.raises(RuntimeError): cache.get()
    assert cache.get().revision == 3  # No stale permit on a database error.
    cache.invalidate()
    assert cache.get().revision == 4


def test_cache_serializes_parallel_refresh():
    calls = []
    cache = net.PolicyCache(lambda: calls.append(1) or net.Policy(1, False, "DENYLIST", ()))
    with ThreadPoolExecutor(max_workers=8) as workers:
        assert all(item.revision == 1 for item in workers.map(lambda _: cache.get(), range(32)))
    assert len(calls) == 1


def exchange(request_scope, cache, trusted=""):
    messages, called = [], []
    async def app(s, receive, send):
        called.append(s["state"]["cx_source_ip"])
    async def send(message): messages.append(message)
    asyncio.run(net.SourceIPMiddleware(app, cache=cache, trusted_proxy_cidrs=trusted)(request_scope, None, send))
    return messages, called


@pytest.mark.parametrize("path", ["/", "/app/", "/portal", "/api/auth/login", "/api/health", "/api/ready", "/static/brand/chuanxu-mark.svg", "/api/gateway/enroll", "/api/platform/ip-access"])
def test_denial_is_generic_on_every_entry(path):
    cache = net.PolicyCache(lambda: net.Policy(1, True, "ALLOWLIST", ()))
    messages, called = exchange(scope(path=path), cache)
    assert not called and messages[0]["status"] == 403 and messages[1]["body"] == net.DENIAL
    assert (b"cache-control", b"no-store") in messages[0]["headers"]
    assert b"192.0.2" not in messages[1]["body"] and b"IP" not in messages[1]["body"]


def test_unavailable_database_recovery_and_no_proxy_spoof_bypass():
    def down(): raise RuntimeError("secret DB endpoint")
    cache = net.PolicyCache(down)
    assert exchange(scope("127.0.0.1"), cache)[1][0].recovery
    assert exchange(scope("192.0.2.3", [(b"x-forwarded-for", b"127.0.0.1")]), cache)[0][0]["status"] == 403
    assert exchange(scope("127.0.0.2", [(b"x-forwarded-for", b"198.51.100.1")]), cache, "127.0.0.2")[0][0]["status"] == 403


def test_websocket_generic_denial_and_lifespan_passthrough():
    cache = net.PolicyCache(lambda: net.Policy(1, True, "ALLOWLIST", ()))
    ws = scope(kind="websocket")
    assert exchange(ws, cache)[0][0]["code"] == 1008
    ws["extensions"]["websocket.http.response"] = {}
    assert exchange(ws, cache)[0][0]["status"] == 403
    assert exchange(ws, cache)[0][1]["body"] == net.DENIAL
    seen = []
    async def app(s, r, send): seen.append(s["type"])
    asyncio.run(net.SourceIPMiddleware(app, cache=cache)({"type": "lifespan"}, None, None))
    assert seen == ["lifespan"]


@pytest.mark.parametrize("reason", ["中" * 667, "😀" * 501, "bad\ud800"])
def test_multibyte_reason_is_rejected_before_database_access(monkeypatch, reason):
    def unexpected(*_):
        raise AssertionError("Invalid audit text must not enter database authorization or writes")
    monkeypatch.setattr(net.identity_api, "effective_access", unexpected)
    monkeypatch.setattr(net.connection, "execute_transaction_callback", unexpected)
    with pytest.raises(net.PolicyError, match="UTF-8"):
        net.update("admin", enabled=False, list_mode="DENYLIST", rules=[], expected_revision=1, reason=reason)


def test_update_permissions_and_optimistic_conflict(monkeypatch):
    monkeypatch.setattr(net.identity_api, "effective_access", lambda *_: {"decision": "DENY"})
    with pytest.raises(PermissionError):
        net.update("unprivileged", enabled=False, list_mode="DENYLIST", rules=[], expected_revision=1, reason="test")
    monkeypatch.setattr(net.identity_api, "effective_access", lambda *_: {"decision": "ALLOW"})
    class Tx:
        def query_one(self, *_): return {"REVISION": 2}
        def execute(self, *_): raise AssertionError("A stale update must perform no writes")
    monkeypatch.setattr(net.connection, "execute_transaction_callback", lambda work: work(Tx()))
    with pytest.raises(net.RevisionConflict):
        net.update("admin", enabled=True, list_mode="ALLOWLIST", rules=[], expected_revision=1, reason="test")
