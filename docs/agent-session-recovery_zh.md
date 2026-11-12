# 外部 Agent 令牌与租约恢复

> 当前软件包：**川序社区版**；支持底座：**oracle, pg, yashandb**；版本类别：**Community**；许可：**Apache-2.0**。文中其他底座及企业专属能力用于说明差异，不表示此包包含或支持这些能力。

访问令牌与实例租约分别计时。令牌通常为 300 秒，实例租约初始为五分钟，
通过心跳续期。换发令牌不延长租约；`ACTIVE` 也不代表租约仍有效。长任务
必须同时维护两个期限。

## 恢复契约

`POST /api/gateway/token` 先验证注册时的客户端秘密或 Ed25519 证明，再诊断
该 Agent 自身实例。错误保留 `code`、`message`、`correlation_id`、`retryable`、
`detail`，可操作的失败另有 `recovery_action`。日志记录安全原因码与关联编号，
不记录凭据或完整请求体。

| HTTP | 原因码 | 处理方式 |
|---|---|---|
| 401 | `AGENT_CREDENTIAL_INVALID` | 检查原注册凭据，不自动重新注册 |
| 409 | `INSTANCE_LEASE_EXPIRED` | 以注册凭据和已获授权的绑定，有限创建一次新实例 |
| 422 | `DOMAIN_REQUIRED` | 新建时提供已授权的 `security_domain_id` 或 `channel_id` |
| 422 | `DOMAIN_BINDING_MISMATCH`、`CLASSIFICATION_INVALID` | 修正实例绑定或请求 |
| 403 | `SCOPE_DENIED`、`SCOPE_NOT_ALLOWED` | 修正请求范围或显式申请权限，不自动换 scope 探测 |
| 403 | `INSTANCE_UNAVAILABLE`、`AGENT_NOT_ACTIVE`、`AGENT_CONTROL_BLOCKED`、`RUNTIME_ISOLATION_BLOCKED` | 核对当前状态和权限，不通过重建绕过 |
| 403 | `DOMAIN_ACCESS_DENIED`、`CHANNEL_ACCESS_DENIED`、`CLASSIFICATION_DENIED` | 解决确切绑定的访问权 |
| 503 | 服务故障 | 保留关联编号；结果未知时先核对，再决定是否重发 |

Bearer 接口在令牌或租约过期时可能返回 401。过期 Bearer 无法通过
`/api/gateway/instances` 或 `/api/gateway/heartbeat` 恢复，需以注册凭据调用
`/api/gateway/token`。不存在、已撤销或属于其他 Agent 的实例不返回租约过期
恢复码。

只计算一次复用决策：

```python
reuse = bool(saved_instance_id) and not new_instance
if reuse:
    body["instance_id"] = saved_instance_id
else:
    # 不发送空字段；至少提供一个真实且已获授权的绑定。
    if saved_security_domain_id:
        body["security_domain_id"] = saved_security_domain_id
    if saved_channel_id:
        body["channel_id"] = saved_channel_id
```

不要把任意 403 都改为新建实例。参考客户端只在明确收到
`INSTANCE_LEASE_EXPIRED` 时，有限执行一次新建交换。超时不代表明确失败，
可能发生在创建提交之后，须先核对，不能重发制造重复实例。

## 维持有效实例

令牌响应增加 `lease_expires_in`、`heartbeat_after_seconds`，并保留
`expires_in`、`lease_expires_at`。以本地单调时钟的发送时间和返回时长建立
期限，预留余量，取令牌与租约中更早的期限；数据库墙钟可能与客户端时区不同。
到期前持有效 Bearer 调用 `POST /api/gateway/heartbeat`；成功响应包含
`success`、相同 `instance_id`、`lease_expires_at` 和 `lease_expires_in`。
心跳不延长令牌，因此需要定期续租并刷新令牌，长任务处理期间也需维护。
过期实例不能复活，执行中的工作收据和栅栏也不能自动迁移到新实例。

## 可移植参考客户端

`scripts/agent_gateway_session.py` 仅依赖 Python 标准库，供已通过
`CLIENT_SECRET` 注册的 Windows/Linux 客户端使用；与平台服务端的
Python 3.14/Linux 安装要求分开。它支持限定 scope 的令牌交换、显式
`new_instance=True`、有限过期恢复、心跳与只读 HTTP，不注册 Agent、不授予
权限、不重放业务写入。Ed25519 客户端保留自己的签名器，可使用纯框架请求构建器。

```python
from agent_gateway_session import AgentSession

# 从现有受保护凭据存储读取变量；不要硬编码、打印秘密或整个凭据文件。
# 将软件包 scripts 目录加入客户端的模块导入路径。
session = AgentSession(platform_origin, saved_agent_id, saved_client_secret,
                       instance_id=saved_instance_id,
                       security_domain_id=saved_security_domain_id)
facts = session.token(["knowledge.read"])
# 成功后，将 session.instance_id 原子保存到原受保护凭据存储。
directory = session.read("/api/agent-gateway/continuity/learning?role=AGENT")
# 长任务期间至少每 30 秒调用一次 session.maintain()。
```

参考客户端仅在内存保存凭据与 Bearer，返回的令牌元数据不含 Bearer。调用方
负责安全持久化：保留 POSIX 0600 或 Windows 现有的当前用户专属 ACL，在
同一受保护目录写完整临时文件后原子替换；失败或结果未知时不能覆盖原凭据和
实例身份。`maintain()` 需要运行时协作调用，不会自行启动后台循环。

另见[平台知识读取](external-agent-knowledge_zh.md)、[API 参考](api-reference_zh.md)
及[框架适配器](framework-agent-gateway_zh.md)。
