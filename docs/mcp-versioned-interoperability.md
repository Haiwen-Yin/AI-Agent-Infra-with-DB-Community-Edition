# Versioned MCP interoperability

> Installed product: **Chuanxu Community Edition**; supported backends: **oracle, pg, yashandb**; edition: **Community**; license: **Apache-2.0**. Other backends and Enterprise-only capabilities discussed below describe differences; they do not extend this package's scope.

[简体中文](mcp-versioned-interoperability_zh.md)

Endpoint registration selects an exact protocol revision. The existing
`2025-06-18` and `2025-11-25` adapters retain their initialization/session rules.
The independent `2026-07-28` adapter supports a bounded HTTP discovery and
read-only tool subset; selecting its date does not enable every interaction in
that protocol.

| Interaction | 2026-07-28 adapter |
|---|---|
| Discovery | `server/discover`, including supported-version and tool-capability checks. |
| Tool directory | `tools/list`, with bounded metadata and schemas. |
| Read-only invocation | `tools/call`, after current registration, identity, exposure and source authorization. |
| Result handling | Only `resultType=complete`; declared output is validated against the supported schema subset. |
| Authentication | Current registered principal and independently validated issuer/resource contract on every request. |
| Directory cache | `ttlMs` and `cacheScope` are validated and recorded; authenticated results are fetched again and are not shared across callers. |
| Unsupported | Subscriptions, prerelease Tasks, MRTR `input_required`, session IDs and unregistered methods. No automatic interaction or version fallback. |

Requests carry `MCP-Protocol-Version`, `Mcp-Method` and, for a tool call,
`Mcp-Name`. The `_meta` object identifies the protocol revision, client
capabilities and client version. Caller data cannot replace this metadata.
A version-mismatch response fails the current operation without automatically
trying another revision or repeating an uncertain effect.

The schema subset bounds bytes, depth, node count and container sizes. It
supports ordinary object/array/scalar constraints and Boolean schemas. External
references, regular expressions and schema composition are rejected before
invocation. There is no remote schema fetch. An MRTR intermediate result is
not a completed tool result.

Changing endpoint revision, URL, issuer, resource or contract invalidates an
existing session object. Rediscovery continues to invalidate prior approval.
Neither cached metadata nor a known request ID preserves revoked authority.
The adapter does not add Sampling, Roots or Logging as new capabilities.

Current A2A 1.0.1 and DB4A2A operations keep their own authenticated contracts
and Task continuity. Protocol compatibility is demonstrated only for the
selected tested interactions; it is not a claim of compatibility with all
clients, servers, transports or extensions.
