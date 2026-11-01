# v5.0.2

## English

v5.0.2 connects model results, capacity and processing recovery to the existing
database Task, authorization and review contracts. It retains five products and
seven database targets. The package manifest records its actual build date;
development candidates are not final release approval.

- Parse supported Chat Completions responses through one bounded result
  contract. Distinguish final content, completed tool proposals, refusal,
  truncation, malformed output and interrupted/unknown requests. Keep output
  inspection and source-disclosure checks before business use.
- Register shared model resources, endpoint aliases, participants and exact
  Profile revisions in a database-authoritative capacity group. Capacity
  defaults to one. Separate databases use an explicitly enrolled coordinator
  route with original Gateway credentials and short-lived proofs for exact
  payloads, reservations and Worker fences.
- Separate cancellation before sending, local cancellation after sending and
  unknown remote outcomes. Unknown requests retain occupancy until exact
  completion or an explicit evidence-bound transport resolution. Transport
  termination does not establish a valid answer or authorize automatic retry.
- Record available input/output, cache and reasoning token counts with
  provenance, plus client-observed queue, first-content and request durations.
  Missing values remain unknown; details are not added twice to totals.
  Gateway quota settlement remains exactly once. Origin observations preserve
  authenticated remote usage without charging it a second time.
- Use exact Provider contracts for structured retrospective candidates and
  bounded approved read-only model/tool/result turns. Proposals remain pending
  existing independent review. A tool proposal does not grant resource access
  or approve its own execution.
- Batch supported context metadata, permission and representation reads and
  native writes. Keep bounded chunks, exact identities, atomic rollback and
  current source authorization. Selected tool schemas count toward complete
  model-input budgets; mandatory constraints cannot disappear to fit a budget.
- Extend existing Task/attempt continuity with typed processing diagnostics,
  persistent request/step/token budgets, repeated-action/no-progress limits and
  explicit bounded recovery. Reads and refreshes do not generate or reset
  budgets. Recovery uses the original source, Profile and credentials; unknown
  effects reconcile before a separate retry decision.
- Add the independent MCP `2026-07-28` discovery and read-only tool subset,
  including request metadata, bounded schema checks and complete-result
  validation. Retain the `2025-06-18` and `2025-11-25` adapters with current
  authorization checks on every request. Subscriptions, prerelease MCP Tasks
  and unrestricted MRTR remain outside this selected subset.
- Add bilingual runtime, workflow and recovery guidance, bounded observation
  views and explicit processing-recovery controls. Feature visibility follows
  the installed runtime contract and current permissions.
- Add migrations 106–109 and native schema manifests for Oracle, PostgreSQL
  and YashanDB, including independent Human review of imported observed
  answers. PostgreSQL also adds migration 110 to reconcile organization
  approval constraints. Verify the complete predecessor chain, actual structures,
  immutable history and native access restrictions. Historical applied SQL
  and checksums remain unchanged.

Provider capabilities depend on exact observed endpoint/Profile contracts.
Supported protocol subsets do not claim all-client or all-server compatibility.
Existing controlled capability defaults and deployment authorization remain in
effect. See [model capacity](docs/model-endpoint-capacity.md),
[processing recovery](docs/processing-recovery.md),
[model workflows](docs/model-workflows.md) and
[versioned MCP](docs/mcp-versioned-interoperability.md).

## 中文

v5.0.2 将模型结果、容量和处理恢复接入现有数据库 Task、授权及审核契约，
继续交付五个产品、覆盖七个数据库目标。包清单记录实际构建日期；开发候选包
不代表最终发布验收通过。

- 受支持的 Chat Completions 响应共用有界结果解析，区分最终回答、完整工具提案、
  拒答、截断、格式错误及中断/未知请求。业务使用前保留输出检查和来源披露校验。
- 在数据库中登记共享模型资源、地址别名、参与方及精确 Profile 版本，默认容量为 1。
  跨数据库通过明确登记的协调器路由接入，保留原 Gateway 凭据，并以短期证明绑定
  精确请求内容、预留及 Worker fence。
- 分别记录发送前取消、发送后本地取消及远程结果未知。未知请求继续占用容量，
  直至取得精确完成证据或有依据的明确传输处理记录。传输终止不代表回答有效，
  也不会自动允许重试。
- 保存可观测的输入、输出、缓存及推理 token、来源和客户端排队、首内容、请求时长。
  缺失保持未知，明细不重复加入总量。Gateway 配额保持一次结算，本地保存经过认证
  的远程用量观测时不再收费。
- 结构化复盘候选和有界、经过批准的只读模型/工具/结果轮次使用精确 Provider 契约。
  提案继续进入原独立审核流程；工具提案不能自行授予资源权限或批准执行。
- 分批读取受支持的上下文元数据、权限及内容表示，使用原生批量写入；保留批次上限、
  精确身份、原子回滚和当前来源权限。所选工具 schema 计入完整模型输入预算，
  不能为压缩预算丢弃必需约束。
- 扩展现有 Task/attempt 连续性，增加结构化处理诊断、持久请求/步骤/token 预算、
  重复操作及无进展限制和显式有界恢复。读取、刷新不生成、不重置预算；恢复继续
  使用原来源、Profile 和凭据，未知影响先核对，再单独决定是否重试。
- 增加独立 MCP `2026-07-28` 发现和只读工具子集，验证请求元数据、有界 schema
  及完整结果。保留 `2025-06-18`、`2025-11-25` 适配器，逐请求复查当前授权。
  订阅、预发布 MCP Tasks 及不受限 MRTR 不属于本次支持范围。
- 增加双语模型运行、工作流及恢复指南，有界观测页面和显式处理恢复操作；
  功能显示取决于已安装运行契约与当前权限。
- Oracle、PostgreSQL、YashanDB 增加迁移 106–109 和原生结构清单，包含导入观测答案的
  独立 Human 审核；PostgreSQL 另增迁移 110，协调组织审批约束。同时验证完整前置链、
  实际对象、不可变历史和原生访问限制；不修改历史已应用 SQL 或校验和。

模型能力以具体端点及 Profile 的实际观测契约为准；协议子集不代表所有客户端和
服务端均兼容。现有受控能力默认值和部署授权继续生效。参见
[模型容量](docs/model-endpoint-capacity_zh.md)、
[处理恢复](docs/processing-recovery_zh.md)、
[模型工作流](docs/model-workflows_zh.md)和
[分版本 MCP](docs/mcp-versioned-interoperability_zh.md)。
