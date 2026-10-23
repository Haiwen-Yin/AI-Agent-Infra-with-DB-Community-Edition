# 运行隔离合同 v5.0.1

> 当前软件包：**川序社区版**；支持底座：**oracle, pg, yashandb**；版本类别：**Community**；许可：**Apache-2.0**。文中其他底座及企业专属能力用于说明差异，不表示此包包含或支持这些能力。

[English](runtime-isolation.md)

Linux 发行版和环境验证矩阵见 [Linux 平台兼容性](linux-platform-compatibility_zh.md)。控制面可运行不代表已证明同主机 Agent 隔离。数据库授权与操作系统隔离是独立控制，部署策略要求二者时须分别满足。

## 隔离级别

`SHARED` 仅用于明确受信任的测试。`DOMAIN_ISOLATED` 与 `DEDICATED_RUNTIME` 描述策略与身份分离，不能证明存在容器边界。`DEDICATED_CONTAINER`、`DEDICATED_VM` 必须由已验证部署适配器提供进程、文件系统、IPC、网络、资源和凭据隔离证据。

包内生命周期参考适配器返回 `enforcement_mode=UNVERIFIED`、`max_isolation_level=DOMAIN_ISOLATED`，不会创建 namespace、cgroup、seccomp、容器或虚拟机。不能根据这些元数据将 Agent 接纳为容器或虚拟机隔离。

## 同主机策略

`LinuxRuntimeAdapter` 仅接受 argv，通过临时 systemd 服务执行 bubblewrap 沙箱，采用独立 UID/GID、私有工作和临时目录、私有 `/proc`、PID/mount/network/user/IPC/UTS namespace、cgroup v2 CPU/内存/PID 限制、seccomp、no-new-privileges、能力剥离、只读根文件系统和默认拒绝网络。禁止 Docker/容器 socket 与无限制主机路径挂载。

历史 Oracle Linux 9.8 专用主机验证覆盖六类边界、跨 Agent 进程/工作区/凭据拒绝、ptrace 拒绝与撤销终止。适配器仅根据实际沙箱进程及其 cgroup 证据返回 VERIFIED，当前主机与发行包仍须单独验证。缺少 bwrap、libseccomp、cgroup 限制、权限或证据时拒绝执行。非空出站允许列表在配置特权防火墙后端前也拒绝执行；历史证据只证明默认拒绝，不证明选择性联网。主机 root 和基础设施管理员不在进程隔离威胁模型内，专用虚拟机另行建立边界。

## 主机准备与配置

首次准备由 root 安装 root 所有的 `chuanxu-host-manager.service`。服务只通过受保护 Unix socket 接收版本化 `chuanxu-host-manager/v1` 协议，不接收 Shell 文本或调用者指定的主机路径。Management Agent 可协调请求，Agent Pool 和平台原生 Agent 主机优先由 HOST_PROVISIONER 执行。

每个 Agent Instance 从已验证主机范围取得数据库记录的 UID/GID 租约。Agent Pool 激活要求 VERIFIED 主机配置，仅 TCP 连通或节点签到不足。管理用户完成预检、准备、启动、停止及撤销验证后，只有已记录控制台或云恢复渠道，初始化流程才可关闭远程 root SSH。业务和外部 Agent 不能访问 Host Manager 或 `hosts.manage` API。

## 其他适配器与 MaaS/SaaS

容器管理、虚拟机、MaaS 和 SaaS 执行仍需具体部署适配器，在目标环境提供同等签名证据后才能使用。

记录租户身份、Worker namespace/池、服务账户、NetworkPolicy、资源配额、存储前缀/卷与 KMS 绑定。高敏感租户使用专用 Worker 池或 microVM。运行身份、策略摘要、根文件系统摘要或 namespace 改变时进入 DRAIN，重新接纳前不领取新任务。

## 接纳规则

缺失、较弱或不一致的隔离证据均拒绝接纳。每次读取仍执行数据库 RLS、Data Grant、Principal、组织和安全域检查，运行隔离不能替代这些授权。
