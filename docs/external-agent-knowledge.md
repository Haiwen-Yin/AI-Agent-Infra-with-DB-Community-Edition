# External Agent access to platform knowledge

> Installed product: **Chuanxu Community Edition**; supported backends: **oracle, pg, yashandb**; edition: **Community**; license: **Apache-2.0**. Other backends and Enterprise-only capabilities discussed below describe differences; they do not extend this package's scope.

Reading platform Knowledge is a required part of relevant managed tasks, not
only a one-time introduction. Follow [managed work](managed-agent-work.md) before
each task/resume; retain actual source revisions and report unavailable content.

After activation, an external Agent can discover and read published platform
learning with its own Bearer token. This works without Channel membership.
Windows clients can make these HTTP calls; the Linux/Python requirements for
installing the platform server do not apply to an HTTP client.

## Permission and token

For an expired saved instance, follow [token and lease recovery](agent-session-recovery.md).
`INSTANCE_LEASE_EXPIRED` (409) is distinct from `SCOPE_DENIED` (403). A token
refresh does not renew the lease; use heartbeat while the Bearer and lease are live.

Registration and activation do not grant Knowledge access. An authorized
permission administrator opens Dashboard **Agent management → Registered Agents →
Business permissions** and allows `knowledge.read` for the selected Agent.
The current effective decision is checked when exchanging tokens and reading
content. Do not use the Human's session cookie or database credentials.

At `POST /api/gateway/token`, reuse the registered credential/proof and saved
`instance_id`, and request `scopes: ["knowledge.read"]`. This is a field of the
normal token request, not a complete request body. Use the returned
`access_token`. An earlier token does not gain new scopes after a permission
change. Keep the instance lease alive and reconcile an expired lease before
creating another instance. See [API reference](api-reference.md).

Scopes are selectable together: for example, request
`["knowledge.read", "memory.read", "memory.write", "channels.read", "channels.write"]`
only when all are needed and currently authorized. Separate tokens for each
business area are not required; requesting an unauthorized scope returns 403.
Token scopes do not grant access beyond current resource permissions.

## Discover, then read exact content

Send the following HTTP requests to the configured platform origin, with
`Authorization: Bearer <access_token>` on both:

```http
GET /api/agent-gateway/continuity/learning?role=AGENT
GET /api/agent-gateway/continuity/learning/{entity_id}?expected_digest={content_digest}
```

1. Read the directory's `status` and `items`. Each item contains `entity_id`,
   `title`, `content_digest`, `product_key`, `version`, `database`, `roles`,
   `goals` and `sources`. The directory contains metadata, not chapter text.
   `role=AGENT` is a relevance filter, not an authorization grant. An optional
   `goal=onboarding` filter narrows the result; omit goal to discover all
   applicable Agent chapters.
2. Select an item and URL-encode its `entity_id`. Supply its exact returned
   `content_digest` as `expected_digest`. Do not substitute a Memory digest or
   derive a digest from serialized JSON.
3. Read the chapter from the response's top-level `content`, along with its
   title, version and sources. There is no `entity` or `knowledge` envelope on
   this learning route. Describe the platform using the returned published
   content and its limits; reading guidance executes no operations.

The existing `scripts/lib/continuity_client.py` also exposes `learning_discover`
and `learning_read`. Its Gateway base is the origin plus
`/api/agent-gateway/continuity`; its credentials remain the Agent's own.

## Distinguish the data paths

| Need | Route and response |
|---|---|
| Discover published platform guides | `GET /api/agent-gateway/continuity/learning`; `items` metadata |
| Read an exact guide | `GET /api/agent-gateway/continuity/learning/{entity_id}?expected_digest=...`; top-level `content` |
| Read an authorized customer Knowledge item with a known ID | `GET /api/gateway/knowledge/{entity_id}`; `{"knowledge": {...}}` |
| Create/read independent private Agent Memory | `POST /api/gateway/memory`, `GET /api/gateway/memory/{family_id}`; Memory family/version contracts |

The learning directory is not a general customer-Knowledge listing. Human
routes `/api/knowledge` and `/api/platform/builtin-knowledge` are not substitutes
for Agent Bearer learning. Knowledge visibility still requires current access;
"public" does not bypass `knowledge.read`.

## Empty results and failures

- `401`: authenticate again and reconcile token/instance expiry or revocation.
- `403`: check the Agent's current `knowledge.read`, requested token scopes,
  active Domain membership and exact source access. Do not repeatedly register,
  retry as a Human, or broaden grants automatically. A source that changed or
  was withdrawn may no longer be read with an old digest; discover again.
- `200` with `NO_APPLICABLE_PUBLISHED_GUIDANCE`: no applicable published chapter.
  Community and AgentX ship four brief product summaries; the nine complete
  learning units are an optional separate JSON import by a Human with
  `platform.manage`. Those four summaries are not nine learning chapters.
  Enterprise bundles the complete learning payload for installation publication.
  See [learning delivery and import](platform-learning-delivery.md).
- `422`: check role/goal, identifier and the required 64-character digest.
- `503`: a service failure; preserve the safe error and correlation identifier
  when provided. Do not classify this as an ordinary permission denial.

This flow does not grant `knowledge.write`, publish Memory as shared Knowledge,
or authorize database access.
