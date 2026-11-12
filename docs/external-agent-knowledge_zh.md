# 外部 Agent 读取平台知识

> 当前软件包：**川序社区版**；支持底座：**oracle, pg, yashandb**；版本类别：**Community**；许可：**Apache-2.0**。文中其他底座及企业专属能力用于说明差异，不表示此包包含或支持这些能力。

外部 Agent 激活后，可以用自己的 Bearer 令牌发现并读取已发布的平台学习指南，
无需加入频道。Windows 客户端可直接调用这些 HTTP 接口；平台服务端的
Linux/Python 安装要求不适用于纯 HTTP 客户端。

## 授权与令牌

注册、激活不自动授予知识读取权限。有权限的权限管理员进入 Dashboard
“智能体管理 → 已注册 Agent → 业务权限”，为选定 Agent 允许 `knowledge.read`。
签发令牌和读取内容时都会检查当前有效权限。不要使用人用户会话或数据库凭据。

调用 `POST /api/gateway/token`，复用注册凭据/证明与已保存的 `instance_id`，
请求 `scopes: ["knowledge.read"]`。这是正常令牌请求中的一个字段，不是完整
请求体。使用返回的 `access_token`；已有令牌不会因后台补授权而自动获得新
scope。维持实例租约，过期时先核对状态，再判断是否需要新实例。字段见
[API 参考](api-reference_zh.md)。

可以同时申请多组 scope。例如确有需要且均已获授权时，请求
`["knowledge.read", "memory.read", "memory.write", "channels.read", "channels.write"]`。
不必在知识、记忆和频道之间强制换令牌；任一请求范围未获授权时会返回 403。
scope 不能扩大当前资源访问权限。

## 先发现目录，再读精确正文

向配置的平台地址发送下列请求，两次均携带
`Authorization: Bearer <access_token>`：

```http
GET /api/agent-gateway/continuity/learning?role=AGENT
GET /api/agent-gateway/continuity/learning/{entity_id}?expected_digest={content_digest}
```

1. 读取目录的 `status` 和 `items`。每项包含 `entity_id`、`title`、
   `content_digest`、`product_key`、`version`、`database`、`roles`、`goals`、
   `sources`；目录返回元数据，不含章节正文。`role=AGENT` 是相关性筛选，
   不授予权限。可加 `goal=onboarding` 筛选入门章节；省略 goal 可发现全部
   适用于 Agent 的章节。
2. 选择条目，将其 `entity_id` 按 URL 路径编码，原样使用返回的
   `content_digest` 作为 `expected_digest`。不要用记忆摘要替换，也不要对
   整个 JSON 重新计算摘要。
3. 从章节响应顶层的 `content` 读取正文，同时保留标题、版本与来源。
   此学习接口没有 `entity` 或 `knowledge` 信封。介绍平台时依据实际返回的
   已发布内容及其边界；读取指南不会执行任何操作。

包内 `scripts/lib/continuity_client.py` 也提供 `learning_discover` 和
`learning_read`。其 Gateway 基地址是平台地址加
`/api/agent-gateway/continuity`，继续使用该 Agent 自身凭据。

## 区分数据入口

| 目的 | 接口与响应 |
|---|---|
| 发现已发布的平台指南 | `GET /api/agent-gateway/continuity/learning`；`items` 元数据 |
| 读取精确章节 | `GET /api/agent-gateway/continuity/learning/{entity_id}?expected_digest=...`；顶层 `content` |
| 已知 ID 时读取获授权的客户知识 | `GET /api/gateway/knowledge/{entity_id}`；`{"knowledge": {...}}` |
| 写入/读取独立私有 Agent 记忆 | `POST /api/gateway/memory`、`GET /api/gateway/memory/{family_id}`；记忆家族/版本契约 |

学习目录不是任意客户知识的列表。人用户路由 `/api/knowledge`、
`/api/platform/builtin-knowledge` 不能代替 Agent Bearer 学习接口。
知识可见性仍需当前权限；“公有”不表示可绕过 `knowledge.read`。

## 空目录与失败处理

- `401`：重新认证，核对令牌、实例的过期与撤销状态。
- `403`：检查 Agent 当前的 `knowledge.read`、令牌 scope、安全域有效成员关系
  和精确来源访问权。不要重复注册、改用人用户身份或自动扩大授权。
  来源变更或撤回后，旧摘要可能无法读取，应重新发现目录。
- `200` 且 `NO_APPLICABLE_PUBLISHED_GUIDANCE`：没有适用的已发布章节。
  社区版/AgentX 安装时只有四类简要产品说明，九章完整指南由具有
  `platform.manage` 的人管理员选择独立 JSON 导入；四类说明不是九章目录。
  企业版包含完整学习内容，供安装时发布。见[交付与导入](platform-learning-delivery_zh.md)。
- `422`：检查角色/目标、标识符，以及必填的 64 位十六进制摘要。
- `503`：服务故障，保留安全错误和返回时提供的关联编号，不要当作普通权限拒绝。

这一流程不授予 `knowledge.write`，不把私有记忆发布成共享知识，也不授权直连数据库。
