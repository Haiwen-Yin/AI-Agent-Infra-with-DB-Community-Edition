# External Agent token and lease recovery

> Installed product: **Chuanxu Community Edition**; supported backends: **oracle, pg, yashandb**; edition: **Community**; license: **Apache-2.0**. Other backends and Enterprise-only capabilities discussed below describe differences; they do not extend this package's scope.

An access token and its instance lease are separate deadlines. Tokens normally
last 300 seconds; an instance lease starts at five minutes and is renewed by
heartbeat. Refreshing a token does not extend that lease. `ACTIVE` alone is not
proof of a live lease. Maintain both deadlines during long tasks.

## Recovery contract

Credential exchange at `POST /api/gateway/token` authenticates the registered
client secret or Ed25519 proof before diagnosing the Agent's own instance.
Errors retain `code`, `message`, `correlation_id`, `retryable` and `detail`;
actionable failures also return `recovery_action`. Log safe reason codes and
correlation IDs, never credentials or full request bodies.

| HTTP | Code | Required handling |
|---|---|---|
| 401 | `AGENT_CREDENTIAL_INVALID` | Check the registered credential; do not register again automatically |
| 409 | `INSTANCE_LEASE_EXPIRED` | Use registered credentials to create one new instance with an authorized binding |
| 422 | `DOMAIN_REQUIRED` | Supply an authorized `security_domain_id` or `channel_id` when creating an instance |
| 422 | `DOMAIN_BINDING_MISMATCH`, `CLASSIFICATION_INVALID` | Correct the instance binding/request |
| 403 | `SCOPE_DENIED`, `SCOPE_NOT_ALLOWED` | Correct scopes or request explicit permission; do not probe with other scopes |
| 403 | `INSTANCE_UNAVAILABLE`, `AGENT_NOT_ACTIVE`, `AGENT_CONTROL_BLOCKED`, `RUNTIME_ISOLATION_BLOCKED` | Resolve current status/authority; do not bypass it by creating instances |
| 403 | `DOMAIN_ACCESS_DENIED`, `CHANNEL_ACCESS_DENIED`, `CLASSIFICATION_DENIED` | Resolve the exact binding authority |
| 503 | Service failure | Preserve the correlation ID; reconcile any unknown outcome before resending |

The bare Bearer routes can return 401 when a token or lease is expired. An
expired Bearer cannot call `/api/gateway/instances` or `/api/gateway/heartbeat`
to recover. Use the registered credential at `/api/gateway/token`. A missing,
revoked or another Agent's instance does not receive the expiry recovery code.

Compute the reuse decision once:

```python
reuse = bool(saved_instance_id) and not new_instance
if reuse:
    body["instance_id"] = saved_instance_id
else:
    # Omit empty fields. At least one real authorized binding is required.
    if saved_security_domain_id:
        body["security_domain_id"] = saved_security_domain_id
    if saved_channel_id:
        body["channel_id"] = saved_channel_id
```

Do not retry an arbitrary 403 as a new instance. Only an explicit
`INSTANCE_LEASE_EXPIRED` response allows the reference client one bounded
new-instance exchange. A timeout is not a definite rejection: it may follow a
committed creation. Reconcile it rather than creating duplicates.

## Keep a live instance alive

Token responses include `expires_in`, `lease_expires_in`, `lease_expires_at` and
`heartbeat_after_seconds`. Use monotonic local deadlines based on the send time
and returned durations, with margin; database wall-clock timestamps may use a
different timezone from the client. Treat the earlier deadline as the limit.
Send `POST /api/gateway/heartbeat` with the current live Bearer before expiry;
its successful response includes `success`, the same `instance_id`,
`lease_expires_at` and `lease_expires_in`. Heartbeat does not extend the token.
Renew the lease and refresh the token periodically, including while a long
task is processing. Do not resurrect expired instances or migrate in-flight
work receipts/fencing to a replacement instance automatically.

## Portable reference client

`scripts/agent_gateway_session.py` is a Python-standard-library HTTP reference
for Windows/Linux clients that are already registered with `CLIENT_SECRET`.
It is distinct from the platform server's Python 3.14/Linux installation.
It supports scoped token exchange, explicit `new_instance=True`, bounded expiry
recovery, heartbeat and read-only HTTP calls. It does not register an Agent,
grant permissions or replay business writes. Ed25519 clients retain their own
proof signer and can use the pure framework request builder.

```python
from agent_gateway_session import AgentSession

# Read these values from your existing protected credential store; do not
# hardcode secrets or log the store. Add the package's scripts to your import path.
session = AgentSession(platform_origin, saved_agent_id, saved_client_secret,
                       instance_id=saved_instance_id,
                       security_domain_id=saved_security_domain_id)
facts = session.token(["knowledge.read"])
# Persist session.instance_id atomically in your protected store after success.
directory = session.read("/api/agent-gateway/continuity/learning?role=AGENT")
# During long work, call session.maintain() at least every 30 seconds.
```

The client keeps credentials and Bearer tokens only in memory and excludes the
Bearer from returned token metadata. The calling runtime owns secure state
persistence: preserve POSIX 0600 or the existing Windows user-only ACL, write a
complete temporary file in the same protected directory and replace atomically.
Never overwrite credentials/instance identity on a failed or unknown exchange.
`maintain()` is cooperative; it does not launch an unattended background loop.

See [platform knowledge access](external-agent-knowledge.md),
[API reference](api-reference.md) and [framework adapter](framework-agent-gateway.md).
