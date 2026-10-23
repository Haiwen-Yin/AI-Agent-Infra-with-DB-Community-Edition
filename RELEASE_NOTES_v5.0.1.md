# v5.0.1

## English

The five v5.0.1 product packages share the database-backed runtime contract;
model-provider results remain explicitly
bounded by the observed provider response and are never inferred from a timeout.

- Share authorized keyword/full-text/vector/hybrid retrieval and evidence
  assessment between Portal and Channels. Record actual strategies, bounded
  degradation, partial question coverage, ambiguity and source contradictions.
- Keep general-model supplementation and mixed-source answers explicitly
  labeled. Recheck current source, Profile and supplement policy before queued
  answers are dispatched or published.
- Add memory event/observation/applicability evidence, exact-version
  reconciliation proposals and independent reviews. Restore reviewed history
  as a new successor instead of rewinding immutable versions.
- Add typed versioned Work notes, expiry and exact Handoff references. Explicit
  Task-linked retrospectives produce pending candidates for existing review
  and publication workflows.
- Add query-aware metadata selection, Agent asset bindings, model-input budgets
  and separate content-representation/delivery facts. Required content and
  source authority remain enforced when selecting context.
- Add configured HTTPS document and pinned GitHub tree/blob synchronization.
  Reuse Task/Step continuity, leases, fencing, idempotent imports and atomic
  checkpoints; imported content remains pending independent review.
- Add versioned answer rubrics and durable final-answer runs with exact source,
  policy and model revisions, encrypted input/output and independent factual
  and citation review. Retrieval preparation and reported results remain
  distinct from observed final answers.
- Extend work-continuity controls for assets, notes, synchronization,
  retrospectives and answer evaluation while preserving current route/resource
  permissions and the Portal management boundary.
- Keep continuity inventory action labels readable on one line while long
  source identifiers wrap within their rows.
- Keep the five-product, seven-database-target delivery model. Unified Community
  installation chooses one backend dependency profile and rejects conflicting
  selections or a virtual environment containing another backend's driver.
- Add migrations 103–105 with backend-specific SQL and schema manifests.
  Deployment postflight checks actual structures as well as APPLIED checksums;
  historical SQL and applied migration identities remain unchanged.
- Direct the website's shared GitHub header icon to the canonical Community
  repository. Public product visibility and required legal notices retain
  their existing boundaries.
- Keep Agent inventories usable without platform-management authority. Load
  restricted metadata only with its existing permission, require both existing
  gates for native activation, and keep model probes explicit rather than
  triggering them during navigation or refresh.
- Repair MFA confirmation payloads for Dashboard, Portal and the compatibility
  route, preserving factor ownership, audit reasons and session promotion.
- Remove a duplicate streaming request in the retained legacy provider helper;
  never substitute provider reasoning for final content or log remote error
  bodies. These helpers are separate from the current grounded answer pipeline.
- Load monitor summary and inventory independently, and preserve the selected
  inventory cursor during periodic refresh.
- Batch Agent health reads for both compatibility and paginated inventories
  instead of querying sessions, tasks and loops per Agent. Keep current access
  scope and counts, and handle timezone-aware activity timestamps correctly.
- Extend normal Agent offboarding with exact native-account revocation and
  single-Agent cached-connection retirement. Report incomplete native work
  explicitly; locking a login does not claim to terminate external sessions.
- Before Oracle/YashanDB fresh deployment or an existing-database upgrade,
  have SYS run the backend's separate native-identity prerequisite in the exact
  application PDB. The narrow read-only status view grants only the configured
  Owner SELECT; missing or incompatible access blocks preflight. This is not
  a migration-105 change or automatic application privilege repair. PostgreSQL
  does not need that view. See [native identity operations](docs/native-identity.md).

## 中文

v5.0.1 的五个产品包共享数据库实体化运行契约；
模型服务超时或中断时仍按实际观测记录，不能据此推断模型已完成回答。

- Portal 与频道共用授权关键词、全文、向量及混合检索和证据评估，记录实际策略、
  有界降级、问题部分覆盖、歧义与来源矛盾。
- 通用模型补充及混合来源回答独立标注；排队回答在派发与发布前重新检查当前来源、
  模型配置及补充策略。
- 增加记忆事件/观察/适用时间证据、精确版本协调提案和独立审核；历史恢复创建新后继，
  不回退不可变版本。
- 增加结构化、版本化工作便签、到期和精确交接引用。显式任务复盘复用已有任务关系，
  仅生成待审核候选，继续使用原审核与发布流程。
- 增加查询感知元数据选择、Agent 资产绑定、模型输入预算及独立的内容表示/送达事实；
  选择上下文时保留必需内容与来源权限检查。
- 增加配置化 HTTPS 文档及固定 GitHub 提交的 tree/blob 同步，复用任务/步骤连续性、
  租约栅栏、幂等导入与原子检查点；导入内容仍需独立审核。
- 增加版本化回答验收标准和持久最终回答运行，绑定精确来源、策略与模型修订，保留加密
  输入/输出及独立事实、引用审核；检索准备和显式登记结果与实际最终回答分别记录。
- 工作交接页面增加资产、便签、来源同步、复盘和回答验收操作，继续执行当前路由/资源
  权限及 Portal 的管理边界。
- 工作交接清单的操作按钮保持单行可读，较长的来源标识在所在行内换行。
- 保持五个产品、七个数据库目标。整合社区版安装时选择单一底座依赖配置，拒绝选择冲突
  或复用含其他底座驱动的虚拟环境。
- 增加迁移 103–105 及三库 SQL/结构清单。部署后检查同时验证实际对象与 APPLIED
  校验和；历史 SQL 及已应用迁移标识保持不变。
- 官网统一页眉的 GitHub 图标直达社区项目仓库；公开产品信息与法定声明沿用既有边界。
- 没有平台管理权限的用户仍可查看获授权的 Agent 清单；受限元数据按原权限读取，
  原生 Agent 激活同时满足现有两层权限。模型探活保持为显式操作，浏览和刷新不调用模型。
- 修复 Dashboard、Portal 及兼容入口的 MFA 确认请求字段，保留因素归属、审计原因和
  会话认证等级提升检查。
- 移除保留的旧模型辅助函数中重复的流式请求；不以模型推理内容代替最终回答，也不记录
  远端错误正文。该辅助函数与当前知识增强回答流程相互独立。
- 监控汇总与清单独立加载；定时刷新保留当前清单分页游标。
- Agent 健康清单的兼容入口和分页入口改为分批聚合会话、任务及循环状态，避免
  按 Agent 逐项查询；保留当前权限与计数范围，并正确处理带时区的活动时间。
- Agent 正常停用增加精确原生账号撤销和单 Agent 缓存连接退役；原生撤销未完成时明确
  记录结果，不把禁止新登录等同于已终止外部现存会话。
- Oracle、YashanDB 新部署或已有数据库升级前，需由 SYS 在确切应用 PDB 中单独
  执行对应底座的原生身份前置脚本。窄只读状态视图仅向配置 Owner 授予 SELECT；
  缺失或不兼容时预检阻断。这不是迁移 105 的修改，也不是应用自动补权限；
  PostgreSQL 不需要该视图。见[原生身份操作](docs/native-identity_zh.md)。
