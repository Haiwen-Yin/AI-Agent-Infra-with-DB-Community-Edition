# API 参考 v5.0.1

> 当前软件包：**川序社区版**；支持底座：**oracle, pg, yashandb**；版本类别：**Community**；许可：**Apache-2.0**。文中其他底座及企业专属能力用于说明差异，不表示此包包含或支持这些能力。

[English](api-reference.md)

## 权威性与当前模式

统一 Web 入口是 FastAPI `web_app:app`。请阅读正在运行的服务的 `/openapi.json`（或在暴露的 `/docs` 中）以获取确切的方法、请求模式和响应模式。保留的 Dashboard/Portal 路由通过按请求隔离的兼容桥接传递，并且并非全部出现在 FastAPI 模式中。其实现位于
[visualization/server.py](../scripts/visualization/server.py)；主入口路由
位于 [web_app.py](../scripts/web_app.py)。

此包支持 **oracle, pg, yashandb** 和 **Community** 功能。存在 API 名称并不构成调用它的授权。每个操作都会重新检查其当前的 Principal/实例、资源权限、Domain 和能力状态。Community 在物理上排除了仅限 Enterprise 的实现。

## 身份验证和请求约定

人用户登录使用 `POST /api/auth/login` 配合 `username` 和 `password`。响应和 Cookie 建立会话；`GET /api/auth/me` 报告其当前身份。在私有客户端中保留 Cookie，并发送返回的
`X-CSRF-Token` 以进行经过身份验证的变更。切勿将凭据放入 URL 中。

`GET /api/auth/registration-policy` 报告人用户注册策略。
`POST /api/auth/register` 提交允许的人用户申请；申请受理不等于账号已获准登录。人用户注册和外部 Agent 注册是独立的控制。登出、密码重置、MFA 和联合登录使用其专用的 `/api/auth/*` 路由。

外部 Agent 调用在
`POST /api/gateway/token` 处交换其签发的凭据/证明，并使用范围限定的 bearer token。Agent 和实例身份来自经过身份验证的上下文，而不是任意的 body 标识符。使用确切的模式字段、内容类型和有界输入。幂等键、预期修订版本、租约令牌、原因和审批引用在该操作声明的地方是必需的。

不要将 HTTP 成功视为排队作业的完成。轮询返回的执行/任务身份，直到达到终止状态或明确未观察到的状态。权限、冲突、验证和不可用能力的响应必须分别处理；重复的未授权调用不是重试。

## 服务、身份和管理

| 路由或族 | 用途 |
|---|---|
| `GET /api/health`, `GET /api/ready` | 进程产品/版本与数据库/控制平面就绪状态 |
| `GET /api/capabilities`, `GET /api/runtime/profile` | 当前可见的身份/版本/运行时能力投影 |
| `/api/platform/capabilities`, `/api/platform/graph-capabilities`, `/api/platform/model-capabilities` | 读取并经过修订检查的能力管理 |
| `/api/platform/administration`, `/api/platform/admin-enrollments` | 受保护的管理成员关系和注册 |
| `/api/platform/session-policies`, `/api/platform/containment` | 会话策略和归因的紧急阻断结果 |
| `/api/platform/upgrades` | 包准入、预检、独立审批、部署发布和 Skill 派发 |
| `/api/platform/native-bootstrap` | 原生管理身份引导/状态 |
| `/api/principal-options`, `/api/users`, `/api/organization/*` | 当前授权的身份目录和组织投影 |
| `/api/security-domains`, `/api/security-domains/{domain_id}/members` | 域创建、成员关系、绑定和生命周期 |
| `POST /api/agents/{agent_id}/offboard` | `agents.offboard` 及确切 Agent 访问权；平台撤销与单独审计的原生登录/本地连接结果 |

通过可读的名称/类型选择主体；提交由授权候选目录返回的不可变标识符。重复的显示名称不是身份。域成员关系先于通道成员关系，且不被其取代。
退役时继续检查 `native_identity_revocation`，不能把 HTTP 成功或 Principal 停用
视为原生撤销完成。COMPLETE 还需 `audit_status=RECORDED`，并不证明外部存量
会话已终止。前置、请求字段和恢复见[原生身份操作](native-identity_zh.md)。

## 外部 Agent 注册和协作

1. 授权的人用户使用 `POST /api/enrollment/grants` 创建范围受限的授权。在对应的 GET 路由读取授权。
2. 外部运行时在 `POST /api/enrollment/redeem` 兑换一次性授权，私下存储任何一次性密钥或提供配置的公钥证明。
3. 通过 `POST /api/gateway/activate` 完成凭据证明和激活。仅注册不授予模型、工具或数据访问权限。
4. 在 `POST /api/gateway/token` 提交注册凭据证明并申请精确作用域。首次实例不传
   `instance_id`，提交已有授权的安全域/频道绑定，保留返回的实例 ID 及专属令牌。
   已有实例则提交其精确 ID 和证明。创建实例或令牌不会授予安全域、频道成员资格。
5. 只有需要额外实例时，才持当前 Bearer 令牌调用 `POST /api/gateway/instances`
   并提交获准绑定，再以注册凭据证明向 `/api/gateway/token` 提交新实例 ID，
   换取该实例专属令牌。令牌仍绑定原实例，修改请求正文 ID 不能转移绑定。
   使用 `POST /api/gateway/events/claim` 领取有界投递批次，再以领取令牌调用
   `POST /api/gateway/events/{delivery_id}/ack` 确认。
6. 发送心跳，观察紧急阻断情况并处理凭证过期/撤销。在每次资源操作前重新检查范围。

根 [SKILL.md](../SKILL.md) 和 [framework Gateway 指南](framework-agent-gateway_zh.md) 解释了客户端契约。返回的外部数据库端点是受治理的原生连接描述符，而不是提供者密钥或 Schema Owner 回退。

| 路由或族 | 用途 |
|---|---|
| `/api/channels` 和 `/api/channels/{channel_id}/members` | 授权 Channel 的清单、创建和成员关系 |
| `/api/channels/{channel_id}/messages`、`/threads`、`/summary` | 归属消息、作用域线程上下文和摘要 |
| `/api/channels/{channel_id}/actions`、`/api/actions/{action_id}/decision` | 结构化提案和允许的决策 |
| `/api/barriers`、`/api/barriers/{barrier_id}/arrivals` | 参与者快照、结构化到达和释放 |
| `/api/bridges` | 显式跨域传输策略 |
| `/api/gateway/channels/{channel_id}/messages` | 基于 Agent-token 作用域的 Channel 发送 |
| `/api/gateway/barriers/{barrier_id}/arrivals` | 基于 Agent-token 作用域的到达报告 |
| `/api/gateway/channels/{channel_id}/actions` | 基于 Agent-token 作用域的结构化提案 |
| `/api/gateway/containment`、`/api/gateway/containment/ack` | 当前阻断状态和合作式清理回执 |

看似 Action 或 Barrier Arrival 的消息不会执行该操作。
请使用专用的结构化 API 及其确切的幂等键。

## 工作、图与连续性

| 路由或族 | 用途 |
|---|---|
| `/api/tasks` | 当前 Task Plan/Step 清单和支持的操作 |
| `/api/workspaces`、`/api/branches`、`/api/loops` | 受治理的工作上下文和有界迭代 |
| `/api/graphs`、`/api/graph-types`、`/api/graph-versions` | 图定义/类型/版本生命周期 |
| `/api/graph-runs`、`/api/graph-worker`、`/api/graph/events` | 运行操作、带隔离令牌的 Worker 操作和持久化事件 |
| `/api/graph/all`、`/api/graph/stats`、`/api/graph/search` | 授权实体关系投影 |
| `/api/db4a2a/dispatches`、`/api/db4a2a/dispatches/{dispatch_id}/branch` | 以引用传递上下文的派发和原子子 Branch |
| `/api/work-contracts`、`/api/handoffs`、`/api/context/*`、`/api/artifact-candidates`、`/api/context-publications` | 工作契约、来源、交接、候选项、审查和发布 |
| `/api/agent-extensions/*` | 受控探针、目录、推导、图诊断和已注册集成 |
| `/api/native-agents/{agent_id}/execute`、`/api/native-executions/{execution_id}` | 授权原生入队和执行状态 |

A2A/DB4A2A 任务关联复用任务计划/步骤以及精确的执行链接、
受保护的尝试、取消和未知结果的核对。标准 A2A
传输和数据库派发经过独立验证。参见
[DB4A2A](db4a2a_zh.md)、[连续性操作](continuity-operations_zh.md)、
[图工程](graph-engineering_zh.md) 和 [Agent 扩展](agent-extensions_zh.md)。

## 知识、记忆、技能和输入

| 路由或族 | 目的 |
|---|---|
| `/api/knowledge`、`/api/knowledge/inventory` | 授权的知识列表/检索 |
| `/api/knowledge/{entity_id}/access-policy` | 当前公司/组织/私有策略及允许的更新 |
| `/api/memory`、`/api/memory/inventory` | 版本化记忆生命周期和授权清单 |
| `/api/memory/{family_id}/versions`、`/chain`、`/candidates` | 不可变后继者、来源遍历和建议 |
| `/api/memory/snapshots`、`/api/memory/jobs` | 固定上下文、有界持久作业和恢复 |
| `/api/skills`、`/api/tools` | 授权的不可变技能版本和工具注册表 |
| `/api/tools/{tool_id}/mcp-exposure` | 显式暴露策略，而非执行批准 |
| `/api/platform/builtin-knowledge` | 版本化内置发布、重新索引和撤回 |
| `/api/gateway/knowledge/{entity_id}` | 独立的 Agent 授权单次知识读取 |

创建候选项不会将其发布为权威知识。快照解析会重新检查当前
来源、摘要、有效性和权限。逻辑不可用性保留历史；
物理擦除是单独的保留/法律保留工作流。受管输入和
派生上下文保留精确的来源链接。

## 记忆质量、Agent 资产与回答验收

下表使用 `/api/agent-extensions` 前缀。迁移 103 提供时间证据、工作便签和复盘；
104 提供资产、来源同步及上下文预算事实；105 提供持久化最终回答运行。
使用前同时验证三项实际结构及 APPLIED 校验和；接口存在不代表发布验收完成。

| 方法与后缀 | 路由权限及用途 |
|---|---|
| `POST /memory/time-evidence` | `workspaces.read`，读取授权精确记忆时间事实 |
| `POST /memory/{family_id}/restore` | `workspaces.write`，将历史恢复为新后继版本 |
| `POST /memory/reconciliations`、`GET /memory/reconciliations/{proposal_id}`、`POST .../{proposal_id}/reviews` | 依次需要工作区写/读/写权限，提议并独立审核精确记忆关系 |
| `GET/POST /works/{work_id}/notes`、`GET /work-notes/{note_id}` | 工作区读/写/读，列出、创建和读取结构化便签 |
| `POST /work-notes/{note_id}/revisions`、`POST .../{note_id}/state` | `workspaces.write`，按版本修订或退役便签 |
| `POST /retrospectives`、`GET /retrospectives/{job_id}`、`POST .../{job_id}/run` | 工作区写/读/写，显式关联任务的模型作业，只生成待审核候选 |
| `GET /directory`、`POST /directory/recommend`、`POST /directory/load` | `workspaces.read`，授权元数据选择与精确正文加载 |
| `GET/POST /asset-bindings`、`GET /asset-bindings/{binding_id}` | 工作区读 / `agents.operate` / 工作区读，管理 Agent 可用资产绑定 |
| `POST /asset-bindings/{binding_id}/revisions`、`POST .../{binding_id}/state` | `agents.operate`，带预期版本的变更 |
| `POST /asset-bindings/assemble` | `workspaces.write`，组装当前授权的绑定来源 |
| `GET/POST /sources`、`GET /sources/{source_id}`、`POST .../{source_id}/state` | 工作区读 / `platform.manage` / 工作区读 / `platform.manage`，配置 HTTPS 或固定 GitHub 来源 |
| `POST /sources/{source_id}/sync`、`GET /source-sync-jobs/{job_id}`、`POST .../{job_id}/run` | `agents.operate` / 工作区读 / `agents.operate`，显式执行带栅栏的增量导入 |
| `POST /context/budget`、`POST /context/derive`、`GET /context/derivations/{derivation_id}` | `workspaces.read`，保守预算与绑定来源的派生 |
| `GET/POST /answer-evaluation/cases`、`POST /answer-evaluation/results` | `platform.manage`，版本化用例与显式登记结果 |
| `POST /answer-evaluation/rubrics`、`POST /answer-evaluation/runs`、`GET /answer-evaluation/runs/{run_id}` | `platform.manage`，冻结标准与排队最终回答验收 |
| `POST /answer-evaluation/runs/{run_id}/execute`、`POST .../{run_id}/reviews` | `platform.manage`，显式生成及对精确输出摘要的独立人工审核 |

路由动作权限只是前提。服务仍检查当前 Work/安全域、归属、Agent 可见性及各底层来源；
恢复记忆还需要 `memory.write`，来源管理检查知识权限，协调审核需要独立且有权限的
审核者。安全域成员身份或单一路由权限不能替代这些条件。人用户写操作校验 CSRF。
版本冲突后先重读当前状态；同一幂等键不能用于不同载荷。

时间证据、恢复和协调接口使用 `value` 外层。例如
`POST /memory/{family_id}/restore`：

```json
{
  "value": {
    "expected_version_id": "CURRENT_VERSION_ID",
    "historical_version_id": "HISTORICAL_VERSION_ID",
    "reason": "将已复核的历史内容恢复为新版本",
    "idempotency_key": "restore-request-001"
  }
}
```

应将标识替换为授权读取到的真实值。便签、资产、来源和质量接口直接使用各自的结构化
正文，不加此 `value` 外层。创建便签提供 `expected_work_version`，修订便签、资产或
来源状态时提供 `expected_version`。完整示例、限额与恢复见
[记忆与工作便签](memory-working-notes_zh.md)、[Agent 资产](agent-context-assets_zh.md)
及[回答验收](answer-quality_zh.md)。来源导入不会自动发布知识，任务排队不代表已经
生成回答、送达模型或通过事实审核。

## 模型、嵌入和治理

| 路由或族 | 用途 |
|---|---|
| `/api/llm-provider-profiles` | 版本化的提供商配置及脱敏读取 |
| `/api/model-gateway/completions` | 可选的受治理模型转发 |
| `/api/model-gateway/credentials`, `/routing`, `/quotas` | 作用域内的网关准入、路由策略和配额 |
| `/api/model-usage/summary`, `/api/model-evidence/coverage` | 已观察到的使用情况以及明确的观察缺口 |
| `/api/model-finance/*`, `/api/model-evidence/*` | 归属明确的财务数据和经验证的导入证据 |
| `/api/wallboard`, `/api/wallboard/definitions` | 只读管理视图和单独授权的定义 |
| `/api/embedding/*` | 配置文件、不可变契约、空间、绑定和就绪状态 |
| `/api/gateway/v1/embeddings` | 作用域内的模型绑定 Embedding 生成 |
| `/api/compliance/*`, `/api/approvals`, `/api/audit` | 仅限企业版的策略/证据/审批/审计视图操作 |

必需的模型和 Embedding 授权独立于 Agent 激活。
供应商能力需针对配置修订版本通过实际探测，而非从模型名称推断。
在没有经验证的证据时，直接模型流量保持未观察状态。
参见 [model usage](model-usage-and-wallboard_zh.md) 和 [security](security_zh.md)。

## Portal 和兼容性客户端

Portal 登录/聊天路由保留在 `/portal/api/*` 下；UI 为
`/portal`。Portal 分配符合条件的本地托管 Agent 并释放其
自身的分配。它不注册外部 Agent。Portal 和 Channel
的回答共享授权的检索和标记的通用模型回退。

遗留 Python API 在 `scripts/lib/` 中可用。操作
私有资源的函数需要该模块文档中记录的已认证上下文/执行者；导入函数不会授予所有者权限。原生存储
过程和调度器 SQL 因后端而异，且不可互换。
请使用所选包的部署清单和原生授权。

API 行为必须针对当前运行的包进行验证。历史
路由快照、旧版本发布结果以及成功的健康端点均不能
证明当前工作流已通过验收。
## 来源 IP 策略

`GET /api/platform/ip-access`、`POST /api/platform/ip-access/preview` 和
`PUT /api/platform/ip-access` 需要 `platform.manage`，写入校验 CSRF。
参数、来源判断及应急恢复见[访问 IP 限制](source-ip-access_zh.md)。

