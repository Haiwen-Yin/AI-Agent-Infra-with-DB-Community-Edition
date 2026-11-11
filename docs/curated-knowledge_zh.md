# 策展文档快照入库

> 当前软件包：**川序社区版**；支持底座：**oracle, pg, yashandb**；版本类别：**Community**；许可：**Apache-2.0**。文中其他底座及企业专属能力用于说明差异，不表示此包包含或支持这些能力。

本入口用于经明确审阅的本地文档，不把它伪装成 HTTPS 响应或已抓取的 Git 提交。
它复用已有 Document Source、精确来源修订、知识候选、独立审核和显式晋升；
导入不会自动发布或执行正文。通用入库流程见[知识入库引导](knowledge-intake_zh.md)。

## 准备完整来源单元

每个单元包含 `path`、`title`、精确 `text`、`content_type`、`origin` 和可选 `intake`。
正文限制为 1–4000 个 Unicode 字符，类型为 `text/plain` 或 `text/markdown`。
优先提交完整短文；长文需要作者准备自足单元并审阅相关上下文，不能为满足长度
限制切断表格、代码围栏、条件、单位、否定或例外。服务不会按固定字符数截断。

`origin` 保留原始 `locator`、确切 `revision`、`parent_sha256`、
`parent_char_count`、Unicode 字符位置 `start`/`end`、`decision_status`、
`context_reviewed: true` 和具体的 `context_note`。状态为 `CURRENT`、`PROPOSED`、
`HISTORICAL`、`REJECTED` 或 `SUPERSEDED`。原文与审阅说明仍是数据，不授予执行权限。

完整原文会核对 SHA-256；每个单元的正文和来源说明共同绑定不可变修订。对于摘录，
服务可以核对已提交文本的长度、范围和绑定，不能独立证明未提交父文档的真实性
或摘录的语义完整性。策展者须核对父文档字节及上下文。AI 审阅按 AI 审阅记录，
不能称为人工审核。适用信息缺失时保留候选；不能用观察或入库时间代替原文生效
时间。策展者明确作出的适用声明须如实标明其决定来源。

## 配置与导入

用 `lib.knowledge_curated.Document` 验证单元，调用 `manifest_digest(documents)`
计算精确来源载荷摘要；候选的 intake 元数据不参与该来源清单摘要。通过
`POST /api/agent-extensions/sources` 配置 Document Source，地址为
`urn:chuanxu:curated:sha256:<manifest_digest>`，路径与单元一致，类型仅允许文本。
`max_bytes` 需覆盖合计正文，范围为 128–262144。原有安全域、活动 Agent、来源
所有者/Agent 的当前权限仍有效；配置入口继续要求平台管理权限。

向 `POST /api/agent-extensions/sources/{source_id}/curated-import` 提交
`expected_version`、`documents`、`reason`、`idempotency_key`。每批 1–50 个不重复
路径，JSON 不超过 1 MiB，必须匹配配置的摘要、路径、类型和正文总字节限制。
沿用身份认证、CSRF 与当前来源写权限。该 URN 不接受网络凭据或 Git commit；
调用 `/sync` 会明确拒绝，不会产生伪造的远程抓取。

加密精确修订、待审核候选、检查点、请求回执及必要审计在同一事务提交。审计失败
则一起回滚。相同幂等请求复用修订和候选，不能重新激活已退役修订或绕过来源
撤销。返回的 `CURATOR_SUPPLIED_NOT_REMOTE_FETCHED` 明确说明材料的获取方式。

Agent 可通过现有 Gateway 调用同一导入服务：
`POST /api/agent-gateway/continuity/sources/{source_id}/curated-import`。
MCP 的 `continuity` 工具与 CLI `python -m lib.continuity_cli call --request-file request.json`
共用以下严格类型的请求信封；`request` 只额外加入 `source_id`，其余字段同上：

```json
{"operation":"source_curated_import","request":{"source_id":"<已配置来源ID>","expected_version":1,"documents":["<完整的文档对象>"],"reason":"导入已审阅来源","idempotency_key":"<唯一请求ID>"}}
```

此结构示意中的文档占位符须替换为真实对象。`source_read` 操作只需 `source_id`，
用于按需读取配置元数据；不会加载全部正文。Gateway 继续要求真实 Agent token、
instance 与当前 `knowledge.write` 权限，导入仍会核对来源及安全域。它不提供
平台管理凭据，也不替 Agent 配置新来源；人类 Web Session 的写操作继续受 CSRF 保护。

## 审核、发布与更新

继续使用候选预览、修订、独立审核和显式晋升。提交者不能自审；缺项、权限和
责任人规则不变。晋升后的 Knowledge 保持私有，预期受众不会自动扩大可见性。
共享或跨域上下文发布仍需各自的当前授权。

精确来源读取、候选派生的上下文与 Knowledge 单项读取会以当前读者重新核对
原始来源。来源撤销后这些后续读取被阻止，已发布历史保留；先前已送达的数据
不会因此被收回。此服务行为不能代替原生 SQL、全部目录入口或端到端验收。

带当前身份的 Knowledge 搜索和分页目录也核对原始来源，不因管理员的目录权限
绕过此检查。目录计数只描述本次返回的获准条目，不返回未经来源授权筛选的
总数。分页游标按扫描位置前进，因此撤销来源可能使一页少于所选数量；如仍有
后续游标，可继续下一页。游标仍绑定当前身份和查询条件。

新建任务上下文使用 `SOURCE_CONTEXT_V2` 渲染策略，将正文和适用信息一起计入
预算与输入摘要；多层派生保留原来源的状态，摘要不能把原提案变成现行政策。
预算不足时整项省略，不把适用条件截掉。旧上下文继续按原策略复原字节和摘要，
同时仍核对当前来源权限；派发前撤销来源会阻止发送。

字节与来源说明不变时复用同一快照；清单变化时配置新的内容寻址 Source。保留
前驱 SourceRef 和真实决策状态，需要替代旧知识时走显式 replacement 候选。
新导入不会自动取代旧政策，也不能覆盖已发布的内置手册快照；内置学习内容
沿用受信任发布生命周期。同一产品版本的手册修正生成独立来源快照，保留旧
快照和用户修改，流程见[知识入库引导](knowledge-intake_zh.md)。

项目研发历史、租户业务知识、公开产品手册和评测标签保持各自的所有权与受众。
凭据、私有归档和标准答案标签不得作为知识事实入库。

## 显式检索适用范围

共享 Knowledge 检索和回答准备接受可选的 `applicability`：`product` 为准确产品标识，
`version` 为准确版本，`as_of` 为带时区的生效判断时刻，`decision_statuses` 为允许的
决策状态。Portal 发送入口使用 `knowledge_scope` 传递同一对象。例如：

```json
{"product":"unified-community","version":"5.0.5","as_of":"2026-11-11T00:00:00+08:00","decision_statuses":["CURRENT"]}
```

Task 上下文组装通过可选的 `applicability` 字段接收同一对象。不适用的可选来源
产生 `SOURCE_NOT_APPLICABLE` 省略回执；必需来源不适用时在持久化前拒绝整个组装。
省略此字段保持历史请求摘要不变。

各检索策略在最终选取来源前检查声明，发送和发布前继续复核引用。摘要的原始来源
也必须符合条件。正文提到其他版本、相关性更高或导入较新均不能覆盖相反声明。
版本按准确标识比较，数字前的 `v` 可省略；不猜测版本范围或产品别名。
生效区间含开始、不含结束。问题提到的日期可能是事件时间，不自动作为生效时刻。

问题里的明确版本同样约束检索。未声明适用信息的旧知识仍可用于不带结构化范围的
查询；其原文中的准确版本可支持问题版本。缺少声明不能满足结构化产品、版本、
生效时间或决策状态过滤。不指定决策状态时保留提案和历史材料的真实标签，而不将
其自动排成现行政策。过滤不授予任何额外读取或执行权限。
