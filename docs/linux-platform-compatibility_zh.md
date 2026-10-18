# Linux 平台兼容性 v5.0.0

> 当前软件包：**川序社区版**；支持底座：**oracle, pg, yashandb**；版本类别：**Community**；许可：**Apache-2.0**。文中其他底座及企业专属能力用于说明差异，不表示此包包含或支持这些能力。

[English](linux-platform-compatibility.md)

本文档定义了 v4.4.11 及更高版本的操作系统基线。
完整的平台功能，包括数据库服务、Agent 执行、Embedding/模型网关以及 Linux 运行时适配器，需要 RHEL 9.8+
（Oracle Linux 9.8+），或具有 glibc
2.34 或更新版本的等效受维护 Linux 发行版。

## 支持级别

### 平台控制面

Web/API 服务、数据库适配器、外部 Agent 网关、文档、
构建和数据库迁移工具需要：

- 具有 glibc 2.34 或更新版本的 x86_64 Linux；
- Python 3.14 或更新版本以及该包的兼容离线依赖项；
- 受支持的 Oracle、PostgreSQL 或 YashanDB 客户端路径；
- 适用于部署的系统服务、文件系统、TLS、防火墙和密钥存储控制。

旧版 RHEL/OL 8 主机和 glibc 2.28 环境不受平台基线支持，
不得用于发布验证。

### 本地 Agent 强隔离

允许本地或平台管理的不可信 Agent 的主机必须通过
打包的 `v411_linux_runtime_isolation_gate.py`。当前测试基线为：

- x86_64、glibc 2.34 或更新版本，以及 Python 3.14 或更新版本；
- systemd 252 或独立测试的兼容版本，具有
  `/usr/bin/systemd-run` 和 `/usr/bin/systemctl`；
- 具有 `cpu`、`memory`、`pids` 和 `cpuset` 控制器的统一 cgroup v2；
- 内核支持 user、PID、mount、network、IPC 和 UTS 命名空间；
- bubblewrap 0.6.3 或独立测试的兼容版本；
- libseccomp 2.5.2 或独立测试的兼容 `libseccomp.so.2`；
- 强制执行的 LSM 策略，通常为 SELinux 或 AppArmor，加上
  `kernel.yama.ptrace_scope=1`、`kernel.unprivileged_bpf_disabled=1` 和
  `fs.suid_dumpable=0`；
- 能够创建每个 Agent 的身份、
  临时单元、命名空间、cgroups、工作区和密钥挂载的特权平台启动器。

默认拒绝网络已验证。选择性非空出站流量在实现并证明特权防火墙后端之前
保持拒绝执行。
主机 root 和基础设施管理员仍位于隔离威胁模型之外。

## 发行版矩阵

发行版名称不是安全证据。每个确切的镜像、内核、
systemd 构建、安全策略和补丁级别在记录为支持强隔离之前
必须通过门禁。

| 发行版系列 | 控制面 | 本地强隔离 | 状态 |
|---|---|---|---|
| Oracle Linux 9.8 x86_64, UEK 6.12 | 支持基线 | 须验证具体主机 | 历史记录为 `VERIFIED`、22/22；当前包与主机须重新验证 |
| RHEL 9, Rocky Linux 9, AlmaLinux 9 | 预期兼容 | 需要门禁 | 同一平台系列；尚未完成本项目环境验证 |
| CentOS Stream 9 | 开发候选 | 需要门禁 | 滚动构建不是生产环境验证目标 |
| Ubuntu Server 22.04/24.04 LTS | 预期兼容 | 需要门禁 | AppArmor 及软件包/路径差异需要证据 |
| Debian 12/13 | 预期兼容 | 需要门禁 | 软件包版本和 LSM 策略需要证据 |
| SUSE Linux Enterprise Server 15 SP5+ | 预期兼容 | 需要门禁 | AppArmor/systemd 集成需要证据 |
| openEuler 22.03 LTS SP 系列和 24.03 LTS | 候选 | 需要门禁 | 优先使用统一的 cgroup v2 镜像；必须测试确切的服务镜像 |
| Anolis OS 23 | 候选 | 需要门禁 | 不要根据 RHEL 兼容性声明推断支持情况 |
| OpenCloudOS 9 和 TencentOS Server 4 | 候选 | 需要门禁 | 必须在目标镜像上检查内核和 cgroup 默认设置 |
| Kylin Advanced Server V10/V11 | 候选 | 需要门禁 | 产品/SP 镜像存在差异；旧版 cgroup v1 镜像不足以满足要求 |
| UnionTech UOS Server V20/V20E | 候选 | 需要门禁 | 产品/更新镜像存在差异；LSM 和 cgroup 证据是强制性的 |
| Anolis OS 8, RHEL 8 衍生版，旧版 Kylin/UOS 镜像 | 不支持 | 不支持 | 低于 v4.4.11 glibc/运行时基线 |

“预期兼容”和“候选”并非客户支持声明。它们
标识了接下来需要环境验证的镜像。后续发行版版本绝不会
仅因为其版本号更高而自动获得支持。

## 环境验证命令

在安装了 bubblewrap 和 libseccomp 之后，在专用的非生产
主机上以 root 身份从解压的当前包中运行：

```bash
python3.14 scripts/tools/v411_linux_runtime_isolation_gate.py \
  --base /var/lib/chuanxu-runtime-gate \
  --output /root/current-linux-runtime-isolation.json
```

JSON 结果必须报告 `passed=true` 和
`evidence.enforcement_mode=VERIFIED`。仅存储经过脱敏的证据。确认
运行结束后没有 `cx-agent-*` 临时单元保持活动状态。

## 部署决策

- 仅控制面，配合外部 Agent：控制面基线已足够；请勿宣传同主机运行时隔离。
- 本地受信任的开发 Agent：较弱的主机仅在通过显式开发策略时方可被接受，且仍保持为 `UNVERIFIED`。
- 本地不受信任的 Agent、Agent Pool 执行、MaaS 或 SaaS 工作节点：请使用通过强隔离门禁的主机，或使用经过单独验证的容器或虚拟机适配器。缺失证据将导致拒绝执行。
