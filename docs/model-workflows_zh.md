# 结构化回顾与受控只读工具轮

> 当前软件包：**川序社区版**；支持底座：**oracle, pg, yashandb**；版本类别：**Community**；许可：**Apache-2.0**。文中其他底座及企业专属能力用于说明差异，不表示此包包含或支持这些能力。

本版本在既有 Task、候选、Action Card 和 Worker 上增加两条显式工作流。
模型返回的内容、JSON Schema 校验通过或工具名称都不授予执行权限。

回顾任务可选择 `TEXT_JSON` 或 `NATIVE_STRICT`。前者仍在服务端校验实际
JSON 和业务结构，但不声称提供方采用了原生严格解码。后者需要当前
Provider Profile 版本、模型、Chat Completions 方言、参数摘要和完整
`response_format` 摘要都匹配的未过期实测记录。固定 `CX_OK` 探测不能代替
业务 Schema 的探测。两条路径生成的 Memory、Knowledge、Experience 或
Skill 都只进入原有 `PENDING` 候选，后续独立审阅和发布要求继续适用。

只读工具轮的首个支持范围是：一个经过独立 Human Action Card 确认的
已注册工具、一个固定且当前可读的源版本、一个必填路径或查询参数，
HTTP 方法限于 GET，输出必须满足已注册的 JSON 对象 Schema。GET 只是
传输限制；只读影响分类来自明确的登记审核，服务不把 GET 当成无副作用证明。
HTTP 工具默认使用安装产品与版本标识 `User-Agent`，格式为
`Chuanxu/<版本>` 或 `OpenTenBase-AgentX/<版本>`。已批准请求中明确指定的
请求头值保持不变；客户端标识不改变目标地址校验、重定向、审批或源权限检查。
登记绑定当前工具版本、输入与输出契约、更新时间、源修订和摘要，重新导入、
撤销暴露或改变契约都会使旧登记不可用。

运行时先接收完整工具提案，再原子创建既有工具请求及等待批准的执行作业。
第二张独立 Human Action Card 必须确认该次准确调用；模型不能自行批准。
普通业务 Agent 可在工具轮的 `approval-requests` 入口显式提交
`{"channel_id":"<频道ID>"}`，使用当前业务频道申请该次调用审批。
频道必须处于 ACTIVE，属于工具轮的原安全域，且当前仍接纳原 Agent。
独立 Human 审批人也须保留该频道和原安全域的有效成员资格及审批权限；
原 Agent 的 `channels.write` 权限会一直复核到 Worker 实际外发前。
平台管理角色或历史成员记录不能代替这两方的当前安全域成员资格。

首次省略频道时仍使用受保护的 Platform Administration 频道，其原有准入要求继续适用。
Action Card 一旦绑定，后续省略频道会沿用原卡片的频道，显式指定其他频道会被拒绝。
业务频道及原安全域都纳入审批绑定摘要；只读工具登记和其他平台变更仍只在受保护的
Platform Administration 频道审批。

原有 Worker 在外发前检查当前租约、原 Agent 实例与凭据、调用摘要、
当前审批主体、工具暴露、源权限和治理策略。工具结果只作为 `tool` 数据消息
进入后续模型请求，保留原调用 ID，不会成为 system 指令。

每个工具轮冻结最多 2 次模型请求、1 次工具执行、0 次格式修复及总截止时间。
模型或工具结果未知时，原操作停止并保留 `UNOBSERVED`，再次读取或运行不会
自动重发。持有 Worker 租约时不等待模型容量；尚未发送而进入容量队列的
请求会取消该次 admission，并作为已知未发送失败结束。敏感或不符合输出
契约的工具结果在后续模型请求之前被拒绝。最终答案加密保存并在读取时
重新检查当前权限；流程成功不能代替独立的事实和引用质量审阅。

HTTP 入口位于 `/api/agent-extensions`；机器入口使用同样的
`/api/agent-gateway/extensions/agent-extensions` 前缀与现有 Gateway 身份验证。
实际安装以前缀配置为准。主要动作如下：

| 动作 | 路径后缀 |
| --- | --- |
| 显式实测完整输出契约 | `POST /model-output-contracts/{profile_id}/probes` |
| 申请只读登记审核 | `POST /model-read-tools/approval-requests` |
| 采用已确认的登记 Action Card | `POST /model-read-tools` |
| 读取准确工具 Schema | `GET /model-read-tools/{registration_id}/contract` |
| 创建或读取工具轮 | `POST /model-tool-turns`、`GET /model-tool-turns/{turn_id}` |
| 推进一次当前阶段 | `POST /model-tool-turns/{turn_id}/run` |
| 申请调用审批 | `POST /model-tool-turns/{turn_id}/approval-requests` |
| 采用已确认的调用审批 | `POST /model-tool-turns/{turn_id}/admit` |

GET 不启动探测、模型或 Worker。修改动作继续使用现有权限、CSRF 或机器
Scope 校验；请求 JSON 不能提供 actor、替代凭据或自报 `VERIFIED`。只读
工具轮要求当前原始 Agent transport；回顾任务可冻结原 Human Web Session
或 Agent 凭据，并在后续 dispatch 前重查。既有 Action Card 的有效期限仍然
适用，过期授权不能被新卡片静默替换。

本次增加的关系由迁移 108 安装，历史 SQL 和旧版运行门保持独立。历史回顾
记录没有新增输出契约时显示 `LEGACY_TEXT_JSON`；它不建立原生严格输出证据。
能力默认值不因安装本模块而提升，部署方应按实际探测和现有审批流程启用
所需的受控能力。
