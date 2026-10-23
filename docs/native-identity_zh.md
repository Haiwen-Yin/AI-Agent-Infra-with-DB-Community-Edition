# 原生 Agent 身份操作 v5.0.1

> 当前软件包：**川序社区版**；支持底座：**oracle, pg, yashandb**；版本类别：**Community**；许可：**Apache-2.0**。文中其他底座及企业专属能力用于说明差异，不表示此包包含或支持这些能力。

[English](native-identity.md)

## 身份与保留记录

Agent Principal、原生数据库账户和 Gateway 凭据是不同身份。退役操作保留 Principal、
原生映射、归属历史和审计，不删除账户，也不轮换密码。人管理员与平台系统 Agent
不能作为业务 Agent 退役目标。身份与状态以数据库实体为准。

PostgreSQL 为每个受管 Agent 映射绑定数据库的 LOGIN 角色；Oracle 使用受管 End User；
YashanDB 使用映射的本地 PDB 用户。适配器先核对当前数据库、配置 Owner、确切
Principal 和唯一映射，再修改一个账户。映射缺失、有歧义或已变化时不能猜测账户，
也不能回退到 Owner。

## Oracle、YashanDB 的管理员前置

v5.0.1 在初始化、升级、恢复部署或验证前，需由 SYS 在确切应用 PDB 中准备只读
状态接口。它独立于既有数据库前置和应用迁移链：

| 底座 | 新增脚本 | `SYS.CX_AGENT_ACCOUNT_STATUS` 的投影来源 |
|---|---|---|
| Oracle | `0_oracle_v5_0_1_native_identity_prerequisites.sql` | `SYS.DBA_END_USERS` |
| YashanDB | `0_yashandb_v5_0_1_native_identity_prerequisites.sql` | `SYS.DBA_USERS` |

单库包位于 `scripts/deploy/`；整合社区包位于 `scripts/deploy/oracle/` 或
`scripts/deploy/yashandb/`。PostgreSQL 不使用这两个脚本或该 SYS 视图。

1. 明确确切 PDB 和配置中的 Schema Owner，审阅脚本并显式设置 `TARGET_PDB`、
   `SCHEMA_OWNER`。`REPLACE_WITH_APPLICATION_PDB` 是待替换占位内容，不是可用的
   部署选择。不能按名称前缀推断，也不能仅凭“不是 `CDB$ROOT`”就继续。
2. 在该 PDB 中以 SYS 连接。脚本检查管理员身份、确切 PDB 和所选 Owner 是否存在，
   拒绝禁止的 Owner 名称、未知同名对象、额外列、可写定义或额外对象授权。DBA 还须
   核对 `SCHEMA_OWNER` 与平台配置一致。遇到冲突先调查；脚本不能通过
   `OR REPLACE` 或自动撤销已有授权来修整对象。
3. 视图恰有 `USERNAME, ACCOUNT_STATUS` 两列，显式使用 `WITH READ ONLY`。
   仅向确切 Owner 授予不带转授权权利的 SELECT；不向 PUBLIC、Agent 或运行角色
   授权，也不开放完整源目录。
4. 使用配置 Owner 执行包内只读预检或 `verify`，检查 `NATIVE_IDENTITY_STATUS_VIEW`。
   接口缺失、不可读或结构不符时为 `BLOCKED`，不能据此认定 Agent 账户不存在。
5. 使用隔离验收账户，检查 Owner 可读、独立 Agent 被拒绝，另一个 Agent 与 Owner
   的访问不变。预检通过不等于原生访问控制或 HTTP 注册流程已验收。

应用查询使用完全限定的 SYS 视图，不自动建视图、补 GRANT，也不采用 Owner 下的
同名视图。新增管理员脚本不修改历史 SQL、校验和或迁移终点 105。不要将 SYS 凭据
放入平台配置。另见[最小权限](minimum-privileges_zh.md)和[部署](deployment_zh.md)。

## 退役一个受管 Agent

通过已认证的退役流程操作；操作者须具备 `agents.offboard` 权限，并能访问确切目标
Agent。Dashboard API 为 `POST /api/agents/{agent_id}/offboard`，使用 Dashboard
会话 Cookie 与 `X-CSRF-Token`，不使用普通 Agent 的原生凭据。填写明确原因以及
真实的负责人、责任组和运行环境处置条件。

例如，先独立确认以下处置条件确实适用于所选业务 Agent，再向包含其精确 ID 的
路由提交此 JSON：

```json
{
  "owner_type": "HUMAN",
  "has_responsible_group": false,
  "environment": "DEVELOPMENT",
  "reason": "退役这个已获准的开发环境 Agent"
}
```

这些字段用于处置判断，不能为了得到期望结果而将生产 Agent 改称开发 Agent。
应填写目标真实记录的责任和运行环境，检查返回处置；没有核实目标时不能照抄示例值。

流程先提交平台状态、令牌/凭据撤销、派发围栏和待处理审计。处置要求原生撤销时，
第二步重新核对精确映射，阻止新的原生登录：PG 设置 `NOLOGIN`，Oracle End User
设置 `ACCOUNT LOCK`，YashanDB 本地用户设置 `ACCOUNT LOCK CONTAINER=CURRENT`。
同时仅关闭本进程跟踪的该 Agent 连接；不改其他 Agent、共享角色或 Owner 授权。
不执行 `DROP`、密码轮换或 `CONTAINER=ALL`。

原生 DDL、平台状态和最终审计不是一个跨层原子事务；Oracle、YashanDB 的账户
DDL 还可能隐式提交。HTTP 成功或 Principal 已停用，均不能单独证明原生撤销成功，
需继续检查 `native_identity_revocation` 及结果审计。

| 结果 | 本次原生操作范围内的含义 |
|---|---|
| `PENDING` | 前置条件不足，无法确认有权完成原生撤销；保留已停用的平台状态并调查。 |
| `PARTIAL` | 部分操作、观测或审计失败；检查后置快照、本地连接关闭失败与审计状态，不能报告完整成功。 |
| `COMPLETE` | 已观测新原生登录被阻断，本进程跟踪连接关闭无失败，当前身份核验通过。 |
| `SKIPPED` | 所选处置保留原生身份，不代表原生登录已经停用。 |

最终审计结果还需 `audit_status=RECORDED`。保留操作 ID、数据库指纹及前后观察；
未知字段保持未知，不能写成 false 或 0。处理原因后，只通过获授权流程重试；不能
为了获得成功状态而解锁、重新注册、清空历史或扩大权限。

## 存量会话与事件处置

`COMPLETE` 仅说明新登录和本地缓存范围的结果，不保证外部已建立数据库会话终止、
全部业务读写失效、其他应用进程的连接池关闭或远端 Agent 进程退出。
`existing_sessions_closed`、`business_access_blocked` 未另行观测时保持未知。
新连接被拒绝与旧外部连接仍能查询，可以同时成立。

如果事件处置要求终止存量会话或进程，应另行授权 DBA 或基础设施操作，解析确切
目标并验证实际结果；不能终止无关会话或整个平台工作。保留审计和独立对照账户的
观察。另见[安全](security_zh.md)、[恢复](recovery_zh.md)和[迁移](migration_zh.md)。
