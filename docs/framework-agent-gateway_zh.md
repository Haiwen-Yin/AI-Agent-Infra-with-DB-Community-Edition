# 框架无关的 Agent Gateway 适配器 v5.0.5

> 当前软件包：**川序社区版**；支持底座：**oracle, pg, yashandb**；版本类别：**Community**；许可：**Apache-2.0**。文中其他底座及企业专属能力用于说明差异，不表示此包包含或支持这些能力。

运行时集成方必须将[受管工作规约](managed-agent-work_zh.md)接入任务、检查点、
交接和结束钩子。仅换取令牌不代表已接入知识、记忆和工作事实；企业策略须进入
可信运行配置，检索取得的内容不能授予权限。

`scripts/lib/agent_framework_adapters.py` 是面向 OpenClaw 和 Hermes Agent 等外部运行时的纯转换边界。它不实现第二个 Channel、Barrier、Action、身份或执行引擎。它仅构建现有的 Gateway 路由描述符，并验证这些路由返回的响应。

该适配器是无状态的。它不执行任何数据库、文件系统、环境或网络操作，也不存储任何凭证、令牌、事件或框架客户端对象。`OpenClawGatewayAdapter` 和 `HermesGatewayAdapter` 类是对同一 `FrameworkGatewayAdapter` 契约的小型外观（facade）；它们不改变授权行为。

## 信任边界

令牌/租约维护及机器可读恢复原因见[会话恢复](agent-session-recovery_zh.md)。
`build_token_request` 支持 `new_instance=True`，忽略旧实例 ID 并要求已授权的
安全域/频道绑定。可移植 HTTP 参考为 `scripts/agent_gateway_session.py`，
与此纯转换适配器分开。

Agent Bearer 发现/读取已发布的平台指南，使用
`/api/agent-gateway/continuity/learning` 及其精确正文接口，要求
`knowledge.read`，无需加入频道。这些既有连续性接口不在下方框架适配器操作表内；
无需人用户会话或通用知识列表。流程见[外部 Agent 读取平台知识](external-agent-knowledge_zh.md)。

独立私有记忆调用 `/api/gateway/memory`，不使用知识或频道候选代替；字段与
响应信封见 [API 参考](api-reference_zh.md)。保存返回的 `instance_id`，
租约有效时复用该实例刷新令牌；心跳续期不改变实例 ID。
以 `expires_in` 判断令牌时长，到期时间使用数据库时钟。到期前续期；
401 需要重新认证并核对租约，不能据此重复注册。
403 表示权限拒绝，409 表示冲突，503 是服务故障并附 `correlation_id`。
不要将被拒绝的记忆写入改投知识，也不要反复新建实例。

Gateway 而非框架负载是身份的权威来源：

- 注册通过一次性用户签发的注册令牌（Enrollment Token）绑定新的 Agent。
- 实例创建从经过身份验证的 bearer-token 上下文中解析 Agent。实例请求故意不包含 `agent_id` 字段。
- Pull、确认、Barrier Arrival 和 Action 调用从 access-token 上下文中解析 Agent 和 Instance。它们的请求体不包含客户端提供的 Agent 或 Instance 身份。
- 响应验证器要求调用方提供其已经信任的 Agent、Instance、投递、Barrier 或 Channel 身份。任何与该绑定不匹配的响应在传递给框架之前都会被拒绝。
- 传入的框架消息或确认中的身份声明如果存在会被验证，但会从 Gateway 主体中丢弃。它们绝不是授权输入。

普通的 Channel 消息不是 Action，类似 Arrival Report 的消息也不会改变 Barrier。结构化的 Arrival 和 Action 请求必须使用下文所述的专用操作。

## 请求描述符

每个 `build_*_request` 函数返回一个传输中立的描述符：

```json
{
  "schema": "agent-gateway/1",
  "method": "POST",
  "path": "/api/gateway/events/claim",
  "query": {"limit": 50},
  "body": {}
}
```

`body` 是现有 HTTP 路由的确切 JSON 主体。MCP 或 Skill 客户端可以使用相同的主体和操作映射，而无需依赖 Python Web 客户端。`schema` 是适配器元数据，不是数据库命令。

## 操作

| 适配器功能 | 现有路由 | 边界 |
|---|---|---|
| `build_registration_request` | `POST /api/enrollment/redeem` | 一次性注册令牌；可选公钥；无客户端密钥输入 |
| `build_token_request` | `POST /api/gateway/token` | 一次性兼容密钥或 Ed25519 证明；返回实例作用域令牌 |
| `build_instance_request` | `POST /api/gateway/instances` | 通道或安全域绑定；Agent 来自持有者上下文 |
| `build_pull_request` | `POST /api/gateway/events/claim` | 有界拉取限制；服务器选择符合条件的租约投递 |
| `build_ack_request` | `POST /api/gateway/events/{delivery_id}/ack` | 领取令牌、成功标志以及可选的失败原因 |
| `build_arrival_request` | `POST /api/gateway/barriers/{barrier_id}/arrivals` | 结构化报告、参与者角色以及必需的幂等键 |
| `build_action_request` | `POST /api/gateway/channels/{channel_id}/actions` | 结构化提案、原因以及必需的幂等键 |

对应的 `validate_*_response` 函数会拒绝未知字段、格式错误的 ID、不一致的计数、非成功的传输状态、身份不匹配、非有限 JSON 以及无效的状态/摘要值。拉取响应会被转换为框架信封，其中租约元数据被隐藏；领取令牌仅保留在该投递所需的确认信封中。

## 凭证处理

Gateway 永远不会向外部运行时提供数据库或 Schema Owner 凭证。当部署策略使用 `CLIENT_SECRET` 时，注册时可能一次性返回兼容客户端密钥；Ed25519 注册不会返回客户端密钥。调用方必须仅将该值用于令牌交换，并根据其运行时策略将其从自身内存中移除。

适配器不会写入或缓存该值。它会拒绝事件、消息、Arrival 和 Action JSON 中的类凭证字段，包括密码、API 密钥、访问/刷新令牌、私钥和密钥摘要。`claim_token` 和短生命周期的 `access_token` 仅允许出现在 Gateway 契约要求的专用瞬态请求/响应位置中。

## 兼容性证据

对应的单元测试套件是
`scripts/tests/test_agent_framework_adapters.py`。它涵盖了通用、OpenClaw 和 Hermes 标签的通用契约、请求构建、响应绑定、身份声明拒绝、凭据字段拒绝、结构化 JSON 验证以及失败情况。这些测试仅验证适配器边界；它们并不声称某个特定的 OpenClaw 或 Hermes 版本已通过针对已部署数据库的实时端到端测试。
