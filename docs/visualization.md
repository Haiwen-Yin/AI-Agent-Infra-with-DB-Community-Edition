# Dashboard and Portal v5.0.0

> Installed product: **Chuanxu Community Edition**; supported backends: **oracle, pg, yashandb**; edition: **Community**; license: **Apache-2.0**. Other backends and Enterprise-only capabilities discussed below describe differences; they do not extend this package's scope.

[简体中文](visualization_zh.md)

## Start and authenticate

The single FastAPI/Uvicorn entry point `web_app:app` serves Dashboard at
`/app`, Portal at `/portal`, and authenticated compatibility routes. From an
initialized package, run `bash start_web_server.sh start`; use `status`,
`stop`, `restart` or `log` for that installation. Confirm its path and
port before stopping a service. Configuration and external reachability are
covered in [deployment](deployment.md).

Dashboard and Portal have separate sessions. The login pages link to each
other and show registration according to the current human-registration
policy. External Agent registration has an independent policy and lifecycle.
There is no universal default administrator password. A rejected password and
an expired authenticated session produce different messages.

The shell supports Chinese/English and light/dark themes. Its name, logo,
edition, database support and version come from the installed product.
OpenTenBase AgentX has an independent identity and supports PostgreSQL only.
The Chinese Chuanxu name uses the original vector wordmark. Navigation is
divided into two ordered rows with balanced destination counts. Narrow
viewports scroll each row without losing the first destination.

## Dashboard destinations

Destinations are filtered by current server-side capabilities and permissions.
A missing control never substitutes for an authorization check.

| Route | Main operations |
|---|---|
| `/app/monitor` | Platform activity and status |
| `/app/wallboard` | Authenticated read-only operating picture, Token/cost trends and freshness |
| `/app/agents` | External and native Agent inventory, lifecycle and ownership |
| `/app/tasks` | Task Plans, Steps, status and execution relationships |
| `/app/workspaces` | Workspaces and the work-continuity view |
| `/app/knowledge` | Authorized Knowledge inventory, details and visibility |
| `/app/memory` | Memory families, versions and lifecycle |
| `/app/skills` | Skills and the tools catalog |
| `/app/specs`, `/app/branches`, `/app/loops` | Specifications, branches and iterative work |
| `/app/graph` | Entity graph, Graph Definitions, Runs and diagnostics |
| `/app/channels`, `/app/barriers` | Attributable discussions and collaboration decisions |
| `/app/users`, `/app/organization`, `/app/security-domains` | People, responsibility hierarchy and collaboration grants |
| `/app/platform` | Capability policies, deployment, model and runtime operations |
| `/app/approvals`, `/app/compliance`, `/app/audit` | Licensed Enterprise governance views |

Use `/app/workspaces?view=continuity` for contracts, handoffs, context
assemblies, candidates and diagnostics. Use `/app/skills?view=tools` for
tool discovery/import and explicit exposure. [Continuity operations](continuity-operations.md)
and [Agent extensions](agent-extensions.md) describe complete workflows.

## People, Agents and Channels

Searchable selectors show names, usernames and subject types, and submit exact
immutable IDs. Same-name subjects require checking their type and username.
Opening a bounded candidate overlay must not shift the surrounding form.
Keyboard selection, retry, pagination, removal and stale-search cancellation
are supported. Typed query text alone is not a valid required selection.

To add a Channel member, first grant membership in its Security Domain. Then
open Channel management, search for the eligible member and add it. Expired,
inactive and existing members are excluded. Threads organize discussions;
they do not add members or grant Knowledge, model, Skill or Tool access.
Discussion threads, existing members and member addition have distinct panels.

An explicit Agent mention requires an eligible, active member with an approved
model, deployment target and template-required isolation. Platform Agent names
remain in English for mentions. Enterprise provides a separate Compliance
Agent. A proposal, queued execution, completed response and failed dispatch are
different states. The client updates one stable streaming response row and
retains manual scroll position.

## Portal

Portal assigns an eligible local managed Agent from the available pool.
External Agent enrollment does not supply the Portal pool. The current user
and assigned Agent must both be authorized to read each Knowledge source.
Matched answers carry citations; general-model supplementation is separately
labeled when policy permits it. Ambiguous or unrelated questions must not be
answered by copying unrelated product Knowledge.

The user can start a conversation, select an allowed model, inspect authorized
Knowledge, use work-continuity entry points and release the assigned Agent.
Exit/logout releases the connection and its slot; expiry follows the
server-issued lease. See [channel and knowledge answers](channel-knowledge.md).

## Platform configuration

Capabilities, Graph posture, external registration and session policies have
separate subviews. Runtime operations cover provider profiles, model usage,
Admin Agent admission/management, Agent Pool, signed upgrade/Skill distribution
and emergency containment. Deployment includes model/embedding configuration.

Direct and gateway routing switches are independent. Draft changes require an
explicit confirmation and reason; the generated forwarding address stays
read-only. Health requires an observed completion from the configured model.
The wallboard has no mutation controls and distinguishes empty, stale,
unavailable and partially observed usage.

Forms keep labels, hints and buttons within their panels. Governed dense
details use a wider drawer that collapses to one column on narrow screens.
Long names and IDs wrap or scroll within their own control. Hiding overflow
does not count as a layout fix. All visible status values have localized labels.

## APIs, security and diagnostics

New clients use authenticated `/api/auth/*`, resource and Gateway contracts
from the [API reference](api-reference.md). `/api/health` reports the
process/version; `/api/ready` checks database/control-plane readiness and
returns 503 while unavailable. Compatibility handlers run in-process with the
same authorization boundary; they do not start an independent server.

Graph traversals use the selected adapter and current visibility policy.
They must not advertise Oracle syntax as a requirement for every backend.
A relationship edge is never a data grant.

After login the shell reloads with current session/CSRF state. HTML and
control-plane assets use no-store cache behavior so an upgrade does not leave
an old bundle active. For failures, record product/version, route, language,
viewport and sanitized error; never include a session cookie, password or raw
configuration in screenshots or support reports. Release captures must show
the authenticated current page after loading, with backend version and served
asset digests bound to the same package.
