# 版本化记忆生命周期 v5.0.1

> 当前软件包：**川序社区版**；支持底座：**oracle, pg, yashandb**；版本类别：**Community**；许可：**Apache-2.0**。文中其他底座及企业专属能力用于说明差异，不表示此包包含或支持这些能力。

[English](memory-lifecycle.md)

## 目的

版本化生命周期使记忆优化在 Agent 操作过程中保持安全，同时不将记忆文本、模型输出、提示词、图可见性或检索历史视为授权依据。记忆族（Memory Family）是稳定的逻辑标识。记忆版本（Memory Version）是不可变的内容和解释状态。每个族指向一个当前版本，且仅在单个数据库事务中，以预期的当前版本作为前提进行发布。

类型为 `EPISODIC`、`FACT`、`PREFERENCE`、`DECISION`、`PROCEDURAL` 和 `EXPERIENCE`。作用域是独立的：`RUNTIME_CONTEXT`、`CHANNEL_MEMORY`、`AGENT_MEMORY`、`WORKSPACE_MEMORY` 或 `ENTERPRISE_KNOWLEDGE`。作用域本身从不授予访问权限；每次读取仍须应用主体（Principal）、Agent、目的、安全域、组织、所有权、分类、有效性以及资源检查。

## 生命周期与遗忘

版本可能处于 `CANDIDATE`、`ACTIVE`、`STALE`、`CONFLICTED`、`SUPERSEDED`、`EXPIRED`、`MIGRATED`、`ARCHIVED`、`QUARANTINED` 或 `UNAVAILABLE` 状态。普通的删除请求会创建一个带有理由的逻辑不可用后继版本，而不是物理删除证据。常规搜索会排除不可用、已归档和已隔离的版本；授权的历史记录保留族、版本、摘要、关系、操作者和原因。

物理擦除是一个独立的合规工作流。它必须评估保留策略、法律保留、依赖版本、制品（Artifacts）、备份、导出和证据。它不能声称能够召回已被模型读取或已导出到平台之外的内容。

## 表示、链与任务

事件时间、观察/适用区间、精确协调、恢复为后继版本、工作便签和显式复盘作业见
[记忆证据与工作便签](memory-working-notes_zh.md)。迁移 103 在当前 Memory/Work/
候选实体上扩展这些事实，不替换原生命周期，也不授权直接写控制面 SQL。历史数据
缺失的事件时间保持未知，关系审核与候选内容发布仍是独立操作。

一个受治理的源表示可以拥有原子事实、短摘要、标准摘要、主题摘要和链式摘要。每个摘要都记录源版本、摘要、生成方法、验证状态和 Token 计数。确定性提取在未配置 LLM 的情况下也能工作。经过批准的模型仅在通过端点、传输、分类、目的和结构检查后，才可提议结构化输出；它生成的是候选项，而非直接的事实或直接激活的版本。经过批准的语义候选项仅通过第二个带有理由的操作激活，该操作创建一个不可变的后继版本。

来源、摘要、迁移、使用、结果、范围和时间关系均作为关系型事实进行记录。相似性、重叠、替换、冲突和提升存储方法、证据、置信度及审核状态。遍历、度数、候选项和链大小均受到限制。Oracle 和 YashanDB 原生 Property Graph 以及 PostgreSQL AGE 是可重建的投影；关系查询仍以原始事实为准，并在投影延迟期间继续有效。

Memory Jobs 使用数据库记录、有界的 Job Items、租约、围栏令牌、检查点、取消、重试和幂等性。创建 Job 时会冻结一个有界的输入分区；只有持有当前租约且匹配围栏令牌的持有者才能完成其 Job 或 Item。首先在预演模式下启动整合，检查影响和候选项，然后在策略要求时使用审批/审核。使用和反馈是不可变的归因事件；访问频率不能重写基础重要性，也不能独立提升共享知识。

显式快照刷新会选择其成员，持久化替换内容，有条件地将先前快照标记为已刷新，并在一个数据库事务中写入其 Outbox 事件；普通 Version 激活永远不会重写现有的 Run 上下文。即使版本已被固定，快照解析对于 `QUARANTINED`、`UNAVAILABLE`、`ARCHIVED` 和 `EXPIRED` 版本也会拒绝访问。当 Run 提供其 Principal 和 Agent-instance 上下文时，快照还会存储 Principal 权限版本和实例围栏令牌。解析过程在返回任何固定成员之前，会重新检查这两个值、Principal 状态以及每个选定的安全域成员资格。因此，撤销、离职、域移除、实例替换或令牌围栏都会拒绝访问，而无需等待正常的快照刷新。
普通过期则返回受治理的 `PAUSE`、`HUMAN_DECISION` 或显式的 `RISK_CONTINUE` 边界，并且永远不会静默延长有效期。

投影事件使用独立的数据库 Outbox，具备条件领取、租约、围栏、延迟重试、积压指标以及有界的重建请求。
Oracle/YashanDB 原生属性图（Property Graph）和 PostgreSQL AGE 工作进程可以消费该 Outbox，但它们的投影仅为缓存：关系型事实仍然是授权和正确性的来源，并在投影工作滞后或不可用时使用。

## Agent 技能与 MCP 边界

经过身份验证的 MCP 接口暴露了 `memory_lifecycle_create`、
`memory_lifecycle_chain`、`memory_lifecycle_feedback` 以及
`memory_lifecycle_candidate`。传输身份从注册的 Agent 令牌中解析，绝不从工具参数中解析。创建操作仅限于
Agent 的 `AGENT_MEMORY` 或 `RUNTIME_CONTEXT` 范围。链式读取、反馈以及
候选提交要求源 Version 由同一 Agent 拥有。候选提交永远不会发布 Version；必须由授权审核人
批准，并且需要单独的受治理激活提供理由。

HTTP API 提供相应的 Dashboard 和自动化路径：
`/api/memory`、`/api/memory/{family_id}/versions`、
`/api/memory/{family_id}/chain`、`/api/memory/{family_id}/candidates`、
`/api/memory/snapshots`、`/api/memory/snapshots/{snapshot_id}/refresh`、
`/api/memory/snapshots/{snapshot_id}/resolve`、`/api/memory/jobs`、
`/api/memory/jobs/{job_id}/cancel`、`/api/memory/jobs/{job_id}/retry` 以及
`/api/memory/projections/metrics`。身份验证、当前 Principal 授权以及
产品版本功能检查均在服务器端执行；Skill 文档、MCP 工具名称
或隐藏的 Dashboard 控件均不授予访问权限。

## 升级

使用可恢复的备份记录运行带账本的升级：

```bash
bash scripts/install_platform.sh upgrade --version 5.0.1 \
  --edition community --database pg --config config.json \
  --confirm-database-backup
```

将数据库和社区版/企业版参数替换为此包支持的目标。运行完整的当前基线；不要仅停留在这些历史引入步骤。
步骤 `23_v4_3_2_memory_lifecycle.sql` 将现有的 `MEMORY` 实体纳入
版本一，且不更改其外部 ID。步骤
`24_v4_3_2_memory_digest_alignment.sql` 随后将历史导入摘要
转换为 SHA-256，且不更改 Family 或 Version 身份。步骤
`25_v4_3_2_disable_legacy_memory_fusion.sql` 移除了过时的直接
变更调度器；后续记忆整理操作均使用受治理的持久化作业和
审核候选项。如果中断，请重新运行相同的命令。不要编辑
账本校验和，也不要使用直接表删除作为回滚方法。
