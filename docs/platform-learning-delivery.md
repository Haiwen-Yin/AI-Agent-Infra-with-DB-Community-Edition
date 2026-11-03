# Platform learning delivery and import

> Installed product: **Chuanxu Community Edition**; supported backends: **oracle, pg, yashandb**; edition: **Community**; license: **Apache-2.0**. Other backends and Enterprise-only capabilities discussed below describe differences; they do not extend this package's scope.

Open Platform learning on the Dashboard Knowledge page or the continuity
workbench. Knowledge creation, search and authorization remain usable without
platform learning content; absent guidance does not block startup.

Community and OpenTenBase AgentX software archives exclude the nine complete
learning units introduced in v5.0.3. Installation publishes only the four brief
product summaries. Complete guidance is supplied as a separate JSON file in
the delivery's `knowledge_packages/` directory, outside the software archives,
and is never imported automatically. Enterprise retains the complete payload
and automatic publication during installation.

An administrator with current `platform.manage` permission can sign in to the
Dashboard, open Platform learning on the Knowledge page, select the companion
for the installed product and software version, and choose Import and publish
guidance. Selecting a file does not publish it. The server checks product,
software version, backend and exact content against the software's hash pins.
Unified Community imports only its selected backend's snapshot. Modified or
incompatible content is rejected. Hash pins establish consistency with the
software delivery, not independent publisher signature authentication.

Import reuses the existing atomic, audited built-in package and Knowledge
entity lifecycle. Users discover metadata by role and goal and read exact
content by digest. Reading guidance executes no operations and grants no
authority. Repeated imports create no duplicate entities. The existing built-in
knowledge withdrawal API also retires untouched public projections; the same
withdrawn snapshot cannot be republished.

Upgrading to separate delivery preserves installed guidance, historical
snapshots and user additions. It does not delete existing knowledge or replace
it with brief summaries. Without applicable published guidance the learning
entry shows an empty state. Customer knowledge retains its current scope and
governance workflow.
