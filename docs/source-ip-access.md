# Source IP access v5.0.0

> Installed product: **Chuanxu Community Edition**; supported backends: **oracle, pg, yashandb**; edition: **Community**; license: **Apache-2.0**. Other backends and Enterprise-only capabilities discussed below describe differences; they do not extend this package's scope.

[简体中文](source-ip-access_zh.md)

Open **Platform configuration → Capabilities & policies → Source IP access**.
This policy is available in every product and edition. Reading, previewing and
saving require an authenticated administrator with `platform.manage`; changes
also require the normal CSRF token. Source admission never grants user or Agent
permissions and never enables human registration.

## Configure and verify

The initial policy is disabled. Choose **Allowlist** to admit only matching
sources, or **Denylist** to reject matching sources. Enter one numeric IPv4 or
IPv6 address or CIDR network per line, up to 512. For example:

```text
192.0.2.10
198.51.100.0/24
2001:db8::/32
```

These are documentation addresses; replace them with your real source ranges.
The service canonicalizes networks and removes duplicates. Hostnames, ports,
zone IDs and dotted netmasks are not accepted. IPv4-mapped IPv6 is evaluated as
the corresponding IPv4. An empty allowlist admits only local recovery; an empty
denylist restricts no source. Disabling retains the saved list for later use.

Use these patterns as a starting point:

```text
# Allowlist: office and VPN egress only
198.51.100.0/24
2001:db8:1234::/48

# Allowlist: one administrator host (/32 or /128 means one address)
192.0.2.10/32
2001:db8::10/128

# Denylist: block known problematic sources while admitting others
203.0.113.0/24
2001:db8:bad::/48
```

These are still documentation-only networks and must not be copied as
production addresses. Use **Preview rules** to see the normalized result and
whether the detected source remains admitted before entering a reason and
saving. Do not include a port, hostname or `http://` in a rule.

Check the detected source, preview the rules, enter a change reason and save.
Reasons require at least 3 characters and at most 2000 UTF-8 bytes; most Chinese
characters use 3 bytes and emoji typically use 4. All three backends apply the
same byte limit before starting a write transaction.
If the preview excludes your source, the page requires an acknowledgement of
the recovery method before saving. A stale revision is rejected; reload and
review the newer policy. Changes, normalized rule entities and audit commit
together. The page shows the last 20 revisions. Other service processes refresh
within about one second; the writing process invalidates its cache immediately.

The policy covers Dashboard, Portal, login, registration, static files, health,
Gateway APIs and WebSocket admission. A rejected source receives HTTP 403 with
`Request could not be completed.` and no policy/IP details. A WebSocket may
instead receive a generic policy close if its server lacks the denial-response
extension. Established streams and connections are not forcibly terminated by
an edit. When a fresh database policy cannot be read, external admission fails
closed rather than reusing an expired permit.

## Local recovery

**Only a direct TCP peer of `127.0.0.1` without forwarding headers receives the
recovery exemption.** Proxy trust cannot include this reserved address. Login, MFA, CSRF and permissions
still apply. `::1`, other `127/8` addresses and a forwarded claim of localhost
follow ordinary policy evaluation. A rule cannot remove this exemption.

If remote access is lost, connect on the application host, or use a private SSH
tunnel (adjust SSH user, host and application port):

```bash
ssh -N -L 18000:127.0.0.1:8000 operator@application-host
```

Open `http://127.0.0.1:18000/app/`, sign in normally, then disable or repair the
policy. The tunnel must go directly to the application, not through a proxy.

## Reverse proxies

Supported launch commands use `--no-proxy-headers`. Preserve that option when
creating a custom Uvicorn service: the policy must receive the original TCP
peer. Automatic server-side rewriting of `scope.client` is unsupported.

By default the application ignores forwarded source assertions. If a proxy is
required, set **`CX_TRUSTED_PROXY_CIDRS`** in the application service environment
to a comma-separated list of its exact addresses/CIDRs, then restart. This
host-managed trust setting cannot be changed through the browser. For example:

```bash
export CX_TRUSTED_PROXY_CIDRS='192.0.2.5/32,2001:db8:1::5/128'
./start_web_server.sh start
```

Configure the edge proxy to overwrite incoming `X-Forwarded-For` with the
observed client IP. A trusted multi-proxy chain is peeled from right to left;
an untrusted hop ends the trust chain. A trusted peer must supply exactly one
valid bounded header; malformed or missing headers fail closed. Bind a local
proxy to another source (for example `127.0.0.2`, using Nginx `proxy_bind`) and
declare that address explicitly. Proxy ranges containing `127.0.0.1` are rejected
at startup; direct recovery requests carrying forwarding headers are rejected.
An undeclared local proxy that removes all forwarding evidence cannot be distinguished from
a local connection. Limit backend access so clients cannot choose an alternate
proxy path. Avoid declaring entire client networks as trusted proxies.

Health monitors are also subject to the policy. Include their sources or use a
direct local recovery connection. This application control does not replace a
host/network firewall or database-native access control.

## API and database entities

- `GET /api/platform/ip-access`: current policy, source and recent history.
- `POST /api/platform/ip-access/preview`: normalized proposed rules and whether
  the current source would retain access; this makes no database changes.
- `PUT /api/platform/ip-access`: `enabled`, `list_mode` (`ALLOWLIST` or
  `DENYLIST`), `rules`, `expected_revision`, and `reason` (at least 3 characters,
  no more than 2000 UTF-8 bytes).

Migration `102_v5_0_0_network_access.sql` adds `CX_IP_ACCESS_STATE`,
`CX_IP_ACCESS_REVISIONS` and `CX_IP_ACCESS_RULES` with the same contract in all
three adapters. Rule/revision history is immutable; ordinary Agent database
sessions cannot read or write these tables. Historical applied SQL stays
unchanged. Upgrade and verify the selected backend before starting new code.
