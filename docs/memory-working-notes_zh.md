# 记忆证据、工作便签与任务复盘 v5.0.1

> 当前软件包：**川序社区版**；支持底座：**oracle, pg, yashandb**；版本类别：**Community**；许可：**Apache-2.0**。文中其他底座及企业专属能力用于说明差异，不表示此包包含或支持这些能力。

[English](memory-working-notes.md)

记忆、工作契约、任务计划和审核候选继续由数据库实体保存。时态证据与工作便签依赖迁移 103；
在数据库结构通过迁移校验前，不应启动这些服务。

人用户先通过 `POST /api/auth/login` 登录 Dashboard，完成所需 MFA/初始化设置，
保存登录返回的会话 Cookie 与 `csrf_token`。调用下述会话保护接口时，所有 POST
（包括 `/memory/time-evidence` 这类只读 POST）及 GET、HEAD、OPTIONS 之外的
其他方法，都须同时发送该 Cookie 与 `X-CSRF-Token`。会话过期后重新登录。
独立 Gateway 机器接口使用自身的限定范围 Bearer 认证，不使用人用户 Cookie/CSRF；
Gateway 令牌不能代替这里要求的 Dashboard 会话。

下文路由前缀为 `/api/agent-extensions`；工作区读写权限之外，仍检查当前记忆、
Work、任务、安全域及精确来源权限。路由权限表见[API 参考](api-reference_zh.md)。

## 时态证据与历史恢复

新记忆版本分别保存事件时间、观察时间和入库时间。缺失的事件时间保持未知；没有时区偏移的
时间保留原文并标记为 `UNKNOWN_OFFSET`，不会自动套用服务器时区。适用起止时间必须携带
明确时区。不在适用区间内的证据不能用于新的上下文消费。

较旧事件不能仅因较晚入库，就覆盖当前较新的适用事实。应先对精确版本进行协调。
显式纠正需记录被纠正的当前版本、纠正范围和适用起点。协调提案保存两个已授权来源版本、
判断方法、策略版本及置信度含义；判断服务不可用时，保留为未决状态。另一位具备权限的
审核者可以批准关系提案，但批准并不激活内容。内容发布仍经过已有的候选、审核和发布链。

恢复历史记忆时，需要提供预期当前版本、选定历史版本、原因和幂等键。恢复会创建新的后继
版本，记录历史来源，不会直接把当前指针退回旧版本，不会改写历史，也不会降低当前密级。
操作时重新检查当前来源、安全域和写入权限。新版本、来源回执、投影事件与审计在同一事务
中提交；任一步失败都会回滚。

通过已有生命周期创建记忆版本时，时间字段包括 `event_at`、`observed_at`、
`applies_from`、`applies_until`、`corrects_version_id`、`correction_scope`。
`POST /memory/time-evidence` 用
`{ "value": { "family": "MEMORY", "entity_id": "FAMILY_ID", "revision_id":
"VERSION_ID", "content_digest": "ACTUAL_SHA256" } }` 读取精确授权时间来源，
不是改写已记录时间的入口。旧版本缺少时间事实时，将可信的创建时间标为历史
入库/观察时间，事件时间仍为 `UNKNOWN`。

`POST /memory/reconciliations` 的 `value` 包含 `security_domain_id`、恰好两个
`sources`、`relation_kind`（`DUPLICATE`、`CONTRADICTION`、`REPLACEMENT`、
`UNRESOLVED`）、`method`、`policy_revision`、可选 0–1 的 `confidence`、
`confidence_meaning`、`judgment_available`、`reason`、`idempotency_key`。
通过 `GET /memory/reconciliations/{proposal_id}` 读取；另一位获准审核者向
`POST .../{proposal_id}/reviews` 提交 `decision`（`APPROVED` 或 `REJECTED`）
及 `reason`。判断不可用保持 `UNRESOLVED`，通过审核不会发布内容。

恢复使用 `POST /memory/{family_id}/restore`，`value` 包含
`expected_version_id`、`historical_version_id`、`reason`、`idempotency_key`。
先读取真实当前/历史版本，当前版本变化时返回冲突。响应返回新的 `version_id` 与
历史 `origin_version_id`；保留回执并验证当前状态，不自动改预期版本重试。
所有来源示例都需替换真实标识及服务返回的 64 位小写 SHA-256 摘要，不能原样提交
`ACTUAL_SHA256`。

## 工作便签

便签附属于已有工作契约。类型包括发现（`FINDING`）、已否决方案（`REJECTED_APPROACH`）、
验证结果（`VALIDATION`）、未决问题（`OPEN_QUESTION`）和下一步（`NEXT_ACTION`）。便签
包含标题、正文、精确证据引用，并可设置明确时区的到期时间。创建时校验工作版本，修订时
校验便签版本，并新增不可变的内容与来源修订。工作结束后不能再创建或修改便签。

交接以 `WORKING_NOTE` 类型引用便签 ID、规范正整数修订号和 SHA-256 内容摘要。接收者仍
须具备工作契约与各底层来源的当前读取权限；安全域成员身份不能代替私有交接的参与者权限。
即使交接在便签到期前固定了版本，到期或退役后也不能再次将其作为有效上下文读取。
具备权限的用户仍可查阅历史。便签不能直接跨安全域发布，也不会自动进入长期记忆、知识库
或 Skill。

在“工作区 → 工作交接”选中 Work 后进入“工作便签”，使用
`POST /works/{work_id}/notes` 创建：

```json
{
  "expected_work_version": 1,
  "content": {
    "note_type": "VALIDATION",
    "title": "部署验证",
    "body": "记录实际结果和仍待验证的内容。",
    "sources": []
  },
  "reason": "记录当前工作证据",
  "idempotency_key": "note-create-001"
}
```

使用真实 Work 版本。依赖证据时增加精确来源，可不设置到期时间，或提供带时区的
`expires_at`。使用 `GET /works/{work_id}/notes` 列表读取（有界 `limit`、可选
`after`），`GET /work-notes/{note_id}?revision=1` 读取修订。
向 `POST /work-notes/{note_id}/revisions` 提交 `expected_version`、完整
`content`、`reason`、`idempotency_key`。退役使用 `POST .../{note_id}/state`，
提交 `expected_version`、`status: RETIRED`、原因和幂等键。并发冲突后重读并协调，
不覆盖新版本；查历史不会重新激活过期内容或重新打开已结束的 Work。

## 显式任务复盘

有权限的请求者选择已有任务、触发类型（成功、失败、纠正或反馈）、精确输入来源、输出
类型、策略版本、健康的模型配置及其版本、预算。创建复盘会增加任务步骤，并关联已有运行
连续性记录，不另建调度器，也不会自动启用定时策略。

Worker 在消费前重新检查原请求者、任务归属、安全域、来源权限、模型配置版本和租约栅栏。
默认模型 Worker 还要求模型配置位于当前批准的来源披露列表中。请求使用已登记的服务地址，
禁止重定向，并应用该服务已验证的参数合同。密钥在本地解析，不写入任务或返回客户端。

请求按保守的 UTF-8 字节上界估算输入 token，并预留输出 token；这是估计值，不是模型
实测用量。证据不会被静默截断，超过预算的请求在派发前失败。回复必须与选定模型匹配，
完整返回非空候选，且属于冻结的输出类型。模型的推理内容不会被当作候选正文。

复盘结果进入已有候选链，初始状态为待审核，仍须独立审核和显式发布。不确定是否送达的
模型请求标记为 `UNOBSERVED`，不会自动重发。已完成任务的重复操作返回既有结果，不再次
调用模型。这些控制不代表已收到信息的外部模型能够撤回或遗忘先前披露的内容。

在 Dashboard“回顾与回答验收 → 工作回顾”选择已有 Task、精确来源和批准的健康
模型配置。页面的模型/策略选择需要管理权限，HTTP 服务同时检查原请求者及底层
任务/来源权限。`POST /retrospectives` 包含 `security_domain_id`、`task_id`、
`trigger`、`target_family`（`MEMORY`、`KNOWLEDGE`、`EXPERIENCE`、`SKILL`）、
非空 `sources`、`policy_revision`、`profile_id`、`profile_version`、
`token_budget`（128–32768）、`reason`、`idempotency_key`；可选 `replaces` 为输出
类型的精确来源。使用 `GET /retrospectives/{job_id}` 读取，明确批准可能的模型派发后
调用 `POST /retrospectives/{job_id}/run`。

`PENDING`、`RUNNING`、`PROPOSED`、`FAILED`、`UNOBSERVED` 描述作业状态，不表示
内容已发布。`PROPOSED` 后检查候选，再独立审核和发布。模型/来源过时、预算失败或
发送不明时保留原作业先调查，不删除状态或盲目重跑。
