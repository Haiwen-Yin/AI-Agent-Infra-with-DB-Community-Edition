# Runtime Isolation Contract v5.0.1

> Installed product: **Chuanxu Community Edition**; supported backends: **oracle, pg, yashandb**; edition: **Community**; license: **Apache-2.0**. Other backends and Enterprise-only capabilities discussed below describe differences; they do not extend this package's scope.

[简体中文](runtime-isolation_zh.md)

The Linux distribution and qualification matrix is maintained in
`docs/linux-platform-compatibility.md`. Platform control-plane compatibility
does not imply verified same-host Agent isolation.

This document records the current isolation boundary. Database authorization
and operating-system isolation are separate controls and both are required
where the deployment policy requires both.

## Levels

`SHARED` is for explicitly trusted tests only. `DOMAIN_ISOLATED` and
`DEDICATED_RUNTIME` describe policy and identity separation but do not prove a
container boundary. `DEDICATED_CONTAINER` and `DEDICATED_VM` require a verified
deployment adapter and evidence for process, filesystem, IPC, network, resource,
and credential boundaries.

The reference adapters shipped in the package are lifecycle references. They
return `enforcement_mode=UNVERIFIED` and `max_isolation_level=DOMAIN_ISOLATED`;
they do not create namespaces, cgroups, seccomp profiles, containers, or VMs.
An Agent must not be admitted as container- or VM-isolated from this metadata
alone.

## Same-host policy

`LinuxRuntimeAdapter` executes an argv-only bubblewrap sandbox through a
transient systemd service with an independent UID/GID, private work and
temporary directories, private `/proc`, PID/mount/network/user/IPC/UTS
namespaces, cgroup v2 CPU/memory/PID limits, seccomp, no-new-privileges,
dropped capabilities, a read-only rootfs, and default-deny networking.
Docker/container sockets and unrestricted hostPath mounts are forbidden.

Historical Oracle Linux 9.8 dedicated-host evidence verified all six boundaries,
cross-Agent process/workspace/credential negatives, ptrace denial, and revoke
termination. The adapter returns `VERIFIED` only from evidence collected from
the actual sandbox process in its cgroup; the current exact host/package must
be verified separately. Missing `bwrap`, libseccomp, cgroup
limits, privileges, or evidence fails closed. A non-empty egress allowlist also
fails closed until a privileged firewall backend is configured; historical evidence proves
default deny, not selective network allowlisting. Host root and infrastructure administrators are
outside the process-isolation threat model unless a dedicated VM boundary is
used.

## Host bootstrap and provisioning

Initial host preparation runs as root and installs the root-owned
`chuanxu-host-manager.service`. The service exposes only the versioned
`chuanxu-host-manager/v1` protocol over a protected Unix socket; it does not
accept shell text or caller-selected host paths. The Management Agent may
coordinate requests, while a `HOST_PROVISIONER` Agent is the preferred
executor for Agent Pool and platform-native Agent hosts.

Each Agent Instance receives a database-recorded UID/GID lease from the
verified host range. Agent Pool activation requires a `VERIFIED` runtime host
profile; TCP reachability and node check-in are insufficient. After the
management user completes preflight and provision/start/stop/revoke validation,
bootstrap may disable remote root SSH only when a console or cloud recovery
channel is recorded. Business and external Agents cannot access the Host
Manager or `hosts.manage` APIs.

## Deferred adapters

Container-managed, VM, MaaS, and SaaS enforcement remains a deployment-adapter
contract. Implementations for the selected target
environment must provide equivalent signed evidence before use.

## MaaS/SaaS policy

Tenant identity, worker namespace/pool, service account, NetworkPolicy,
resource quota, storage prefix/volume, and KMS binding must be recorded. High
sensitivity tenants use a dedicated worker pool or microVM. A changed runtime
identity, policy digest, rootfs digest, or namespace enters `DRAIN` and does
not accept new work until re-admitted.

## Admission rule

Missing, weaker, or inconsistent isolation evidence fails closed. Database RLS,
Data Grant, Principal, Organization, and Security Domain checks remain active
for every row access; runtime isolation never substitutes for them.
