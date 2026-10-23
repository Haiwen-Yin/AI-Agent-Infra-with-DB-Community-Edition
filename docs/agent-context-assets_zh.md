# Agent 资产与查询感知上下文 v5.0.1

> 当前软件包：**川序社区版**；支持底座：**oracle, pg, yashandb**；版本类别：**Community**；许可：**Apache-2.0**。文中其他底座及企业专属能力用于说明差异，不表示此包包含或支持这些能力。

[English](agent-context-assets.md)

Agent 资产通过绑定关系引用已有知识、记忆、Skill、已采集图或已同步来源的精确修订，
不会转移所有权或授予访问权限。迁移 104 保存绑定、不可变修订、上下文使用、来源配置、
同步任务及预算/表示事实；使用前应通过本安装包完整迁移链的校验。

## 准备权限并选择资产

在 Dashboard 打开“工作区 → 工作交接”，选择安全域。“Agent 资产”区域分别提供
资产绑定、来源同步和 Skill 推荐。从授权目录中选择激活的 Agent。操作者和 Agent
都必须保留当前安全域与来源访问权限；把私有来源绑定给 Agent 不会使其变成共享资料。

下文 HTTP 前缀为 `/api/agent-extensions`。人用户先通过 `POST /api/auth/login`
登录 Dashboard，完成所需 MFA/初始化设置，保存会话 Cookie 和返回的 `csrf_token`。
这些会话保护接口的所有 POST（包括只读的 `/directory/recommend`、`/directory/load`）
及 GET、HEAD、OPTIONS 之外的其他方法，都须同时发送该 Cookie 与 `X-CSRF-Token`；
会话过期后重新登录。独立 Gateway 机器接口使用自身的限定范围 Bearer 认证，不使用
人用户 Cookie/CSRF，其令牌不能代替这里要求的 Dashboard 会话。

读取需要 `workspaces.read`，绑定变更与同步派发需要
`agents.operate`，组装还需要 `workspaces.write`，来源配置和状态变更需要
`platform.manage`。服务同时检查 Agent 可见性、来源归属/范围及对应知识、记忆或
Skill 权限；只有页面或路由权限不够。Portal 不是平台配置入口。

记忆元数据读取先检查资源范围内的 `memory.read` 权限，再复用已有记忆读取器判断
归属、范围及 `RUNTIME_CONTEXT` 用途，不另设“仅所有者或 `ALL`”的限制。因此，
人用户拥有的记忆可供已获明确授权的 `ASSIGNED` Agent 读取，但该范围本身不授予
安全域成员资格或来源访问权。操作者与 Agent 分别接受当前成员关系、精确修订与摘要、
记忆家族当前生命周期、有效期和适用时间的检查。选择阶段仅读取标题与安全元数据，
不加载记忆正文。被拒绝、受阻、已失效或尚未适用的条目不会出现在绑定列表中；
已有绑定或准备完成的组装也不能恢复被撤销的访问权。其他来源类型仍沿用各自的
归属与范围规则。

1. 使用 `GET /directory?security_domain_id=DOMAIN_ID&family=SKILL&query=QUERY`
   搜索授权元数据，使用 `after`、`limit` 翻页。搜索结果不代表执行授权。
2. 使用 `POST /directory/recommend` 获取与问题相关的 Skill 候选。请求包含
   `security_domain_id`、`query`，可设 `limit`（1–20）与 `candidate_limit`
   （1–100）；没有合适选择是正常结果。
3. 仅对选定记录调用 `POST /directory/load`，提交
   `{ "value": { "security_domain_id": "DOMAIN_ID", "family": "SKILL",
   "entity_id": "ENTITY_ID", "version": "REVISION_ID",
   "content_digest": "ACTUAL_SHA256" } }`。替换为授权结果中的标识和摘要；
   加载正文时会重新检查当前权限及摘要。

## 绑定并组装

使用 `POST /asset-bindings` 创建绑定：

```json
{
  "security_domain_id": "DOMAIN_ID",
  "agent_id": "AGENT_ID",
  "source": {
    "family": "KNOWLEDGE",
    "entity_id": "ENTITY_ID",
    "revision_id": "REVISION_ID",
    "content_digest": "ACTUAL_SHA256"
  },
  "purpose": "为授权问答准备资料",
  "priority": 50,
  "resolution_policy": "PINNED",
  "reason": "绑定已经审核的参考资料",
  "idempotency_key": "binding-request-001"
}
```

示例中的标识和 `ACTUAL_SHA256` 均为占位符；应替换为服务返回的真实标识及
64 位小写十六进制摘要。`PINNED` 固定精确引用，`CURRENT` 在使用时解析当前可用
版本并重新授权；已采集的 `GRAPH`、`SOURCE` 必须固定修订。可选的 `valid_until`
必须是带时区的未来时间。优先级范围为 0–100，不能越过来源权限。

使用 `GET /asset-bindings?security_domain_id=DOMAIN_ID&agent_id=AGENT_ID`
列出绑定，使用 `GET /asset-bindings/{binding_id}` 读取详情。修订时向
`POST /asset-bindings/{binding_id}/revisions` 提交完整绑定字段及
`expected_version`。暂停、恢复或撤销时向 `POST .../{binding_id}/state`
提交 `expected_version`、`status`（`ACTIVE`、`PAUSED`、`REVOKED`）、`reason`
和 `idempotency_key`。版本冲突后先重读并明确决定，不要自动替换预期版本重试。

`POST /asset-bindings/assemble` 包含 `binding_ids`（1–50 项）与 `assembly`。
组装请求必须有 `request_id`、`security_domain_id`、`purpose`、`idempotency_key`，
可关联 Work/Handoff，并设置问题与预算。例如：

```json
{
  "binding_ids": ["BINDING_ID"],
  "assembly": {
    "request_id": "assembly-001",
    "security_domain_id": "DOMAIN_ID",
    "query_text": "哪些经过审核的部署步骤适用于当前问题？",
    "token_budget": 4096,
    "context_window": 16384,
    "output_reserve": 2048,
    "entry_limit": 20,
    "allow_partial": false,
    "purpose": "为部署对话准备上下文",
    "idempotency_key": "assembly-request-001"
  }
}
```

选择过程先授权元数据，再加载精确版本正文，可以省略不相关的可选来源。
`mandatory_sources` 中的必要来源不能因预算不足丢失必需约束。
`system_text`、`tool_text` 和 `output_reserve` 先占用窗口，余量再分给来源。
已在本地初始化且可识别的计数器可以提供 token 数；否则使用
`UTF8_UPPER_BOUND`，按 UTF-8 字节保守估算，不是模型实测用量。
读取过程不会下载计数器或执行调用者提供的计数代码。

表示状态（`COMPLETE`、`PARTIAL`、`OMITTED`）与送达状态（`PREPARED`、
`CONFIRMED`、`UNOBSERVED`、`OMITTED`）分别持久化。准备完组装不代表模型已经
收到；已有输入回执链需确认精确的渲染摘要和条目数。固定标识也不能绕过来源撤权、
过期或当前权限变化。执行及回执见[连续性操作](continuity-operations_zh.md)。

## 配置并同步来源

在“Agent 资产 → 来源同步”中，由平台管理员配置来源，再由有权限的操作者排队并
显式运行任务。导入生成待审核的知识候选；仍需独立审核和显式发布，才能成为正式知识。

`POST /sources` 的文档来源示例：

```json
{
  "security_domain_id": "DOMAIN_ID",
  "agent_id": "AGENT_ID",
  "kind": "DOCUMENT",
  "endpoint": "https://docs.example.com/platform/deployment.html",
  "paths": ["/"],
  "content_types": ["text/html", "text/markdown", "text/plain"],
  "max_bytes": 16384,
  "max_attempts": 3,
  "reason": "同步已批准的文档页面",
  "idempotency_key": "source-config-001"
}
```

`DOCUMENT` 读取配置中的精确 HTTPS 页面，不递归抓取整个 wiki。
`GITHUB` 使用精确的 `https://github.com/OWNER/REPOSITORY`，
`pinned_commit` 为完整的 40 位小写提交 SHA，`paths` 为获准路径前缀，例如
`["docs"]`。不支持移动分支名、shell Git 传输、子模块和符号链接。
有界 tree/blob 读取会校验 blob 标识，仅加载符合要求的 UTF-8 文本，不执行代码。

地址仅支持无内嵌凭据、443 端口的 HTTPS 和允许的公网目标；拒绝重定向、私网、
链路本地、回环目标、二进制文本及压缩响应。`content_types` 支持纯文本、Markdown、
HTML、JSON。`max_bytes` 范围为 128–262144，Git 按所选内容合计，最多选择 50 个
文件；`max_attempts` 范围为 1–5。需要凭据时填写大写的主机托管
`credential_ref`，不在 URL 或请求正文中传密钥；缺失或撤销的凭据会阻止使用。

向 `POST /sources/{source_id}/sync` 提交 `reason`、`idempotency_key`，可附已有
`task_id`。通过 `GET /source-sync-jobs/{job_id}` 读取，再显式调用
`POST /source-sync-jobs/{job_id}/run`。任务复用 Task/Step 连续性、租约和栅栏；
新修订、待审核候选、导入关系、检查点与审计原子提交。已完成请求使用同一幂等键
重复调用不会重复导入。这是显式增量同步，不会自动开启定时计划。

## 暂停、排查和恢复

`GET /sources` 与 `GET /sources/{source_id}` 返回配置/状态，不返回凭据值。
`POST /sources/{source_id}/state` 接收 `expected_version`、`status`、`reason`、
`idempotency_key`。`PAUSED` 可恢复为 `ACTIVE`；`REVOKED`、`RETIRED` 对该来源
标识不可逆，需要重新配置新的获准来源，不能静默复活原来源。

检查任务状态（`PENDING`、`RUNNING`、`SUCCEEDED`、`FAILED`、`BLOCKED`）、
`attempt_count`、`error_code`、当前来源状态和原请求者。撤权会阻止使用；404 不代表
获准删除或撤回先前发布的内容。网络或内容错误不能推进检查点。尝试次数耗尽、租约
过期或配置变化时，先调查，再提交新的授权请求。保留原证据和候选审核历史，不通过
清账本或降低权限将失败任务改成成功。
