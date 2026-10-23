# 共享问答与最终回答验收 v5.0.1

> 当前软件包：**川序社区版**；支持底座：**oracle, pg, yashandb**；版本类别：**Community**；许可：**Apache-2.0**。文中其他底座及企业专属能力用于说明差异，不表示此包包含或支持这些能力。

[English](answer-quality.md)

Portal 与频道共用授权检索、证据选择和回答准备。迁移 105 在已有任务连续性账本上
增加不可变验收标准、持久运行、加密输入/输出、精确来源及独立审核。用例/准备结果和
实际生成的最终回答是不同证据，任何单次结果都不能独立证明软件版本可发布。

## 回答策略与可见来源

共享入口默认请求 `hybrid`，支持 `keyword`、`fulltext`、`vector`、`hybrid`。
各检索通道在消费候选前检查人员与 Agent 当前权限，披露前再次检查精确来源。
搜索或 Embedding 能力不可用时，可以降级到获准文本检索，并记录实际通道和原因；
权限拒绝不能触发更宽范围检索。倒数排名融合用于排序，其分数不是概率，也不能证明
事实充分。

证据评估独立检查主题、问题覆盖及明确矛盾。多问句部分覆盖为 `PARTIAL_MATCH`；
授权来源相互矛盾或数据库/厂商主题不明确时可能为 `AMBIGUOUS`；没有证据为
`NO_MATCH`。再由问答策略和批准披露知识的模型配置列表决定回答：

| 回答来源 | 含义 |
|---|---|
| `KNOWLEDGE_GROUNDED` | 基于授权资料准备回答，引用正确性仍需验证 |
| `KNOWLEDGE_EXTRACTS` | 返回授权摘录，不向未批准模型发送资料正文 |
| `MODEL_SUPPLEMENT` | 没有匹配的授权知识，策略允许通用模型补充 |
| `MIXED_SOURCES` | 知识部分覆盖，允许的通用模型内容单独标注 |
| `CLARIFICATION_REQUIRED` | 主题需要先澄清 |
| `INSUFFICIENT_KNOWLEDGE` | 现有证据或策略不足以支持结论 |

Portal 与频道展示独立来源说明及检索/证据元数据。检索失败或模型失败仍是错误。
来源撤权、模型绑定变化或补充策略被关闭后，旧排队回答不能继续使用；修改策略也不
构成对旧载荷的重新授权。历史回答读取同样检查当前来源权限。排查见
[频道知识问答](channel-knowledge_zh.md)。

## 准备验收

平台管理员在 Dashboard 打开“工作区 → 工作交接 → 回顾与回答验收 → 答案验收”。
等价 API 前缀为 `/api/agent-extensions/answer-evaluation`。所有验收路由要求
`platform.manage`，同时检查当前安全域/工作区、Agent 可见性、知识读取及批准的健康
模型绑定。人用户先通过 `POST /api/auth/login` 登录 Dashboard，完成所需 MFA/初始化
设置，保存会话 Cookie 与返回的 `csrf_token`。这些会话保护接口的所有 POST（包括
只读 POST）及 GET、HEAD、OPTIONS 之外的其他方法，都须同时发送该 Cookie 与
`X-CSRF-Token`；会话过期后重新登录。独立 Gateway 机器接口使用限定范围 Bearer
认证，不使用人用户 Cookie/CSRF，其令牌不能代替这里要求的 Dashboard 会话。
Portal 不授予这些管理操作。

1. 使用 `POST /cases` 登记获准问题、预期检索状态和精确引用实体标识；
   `GET /cases` 读取用例。内容变更创建新版本并退役原活动版本；相同活动内容复用
   原版本。
2. 使用 `POST /rubrics` 为精确用例版本登记验收标准，设置必含/禁用短语、允许的回答
   来源、最少字符数、检索策略，以及是否要求真实模型和独立人工审核。保存返回的标准
   修订号。
3. 选择激活的原生 Agent，其当前模型配置必须健康，数据/模型权限符合用例。资料正文
   只按当前批准的披露策略发给模型。

用例示例：

```json
{
  "case_id": "deployment-answer-001",
  "query_text": "哪些获准的部署步骤适用于当前问题？",
  "expected_mode": "MATCHED",
  "expected_entity_ids": ["KNOWLEDGE_ENTITY_ID"],
  "reason": "批准部署问答验收用例"
}
```

标准示例中的 `case_version` 应替换为实际返回版本：

```json
{
  "case_id": "deployment-answer-001",
  "case_version": 1,
  "rubric": {
    "required_phrases": ["部署"],
    "forbidden_phrases": [],
    "allowed_answer_sources": ["KNOWLEDGE_GROUNDED"],
    "minimum_characters": 20,
    "require_real_model": true,
    "require_human_review": true,
    "strategy": "hybrid"
  },
  "reason": "固定回答内容与证据验收要求"
}
```

用例 `expected_mode` 为 `MATCHED`、`PARTIAL_MATCH`、`NO_MATCH`、`AMBIGUOUS`
之一，与上表的回答来源标签不同。最终回答验收将预期实体作为精确集合比较。
短语检查只衡量已批准的标准，不代表事实正确。

## 排队、执行和独立审核

使用 `POST /runs` 显式排队：

```json
{
  "case_id": "deployment-answer-001",
  "case_version": 1,
  "rubric_revision": 1,
  "security_domain_id": "DOMAIN_ID",
  "agent_id": "NATIVE_AGENT_ID",
  "entry_kind": "PORTAL",
  "idempotency_key": "answer-run-001",
  "reason": "执行获准问答路径验收"
}
```

所有标识和修订号都应替换为当前真实值。`entry_kind` 为 `PORTAL` 或 `CHANNEL`，
记录共享问答路径的用例入口，本身不代表完成浏览器交互、频道成员流程或 Portal 分配。
运行固定用例/标准、Agent/模型配置及策略修订，并关联 Task/Step 连续性。排队成功
不代表已经得到模型结果。

使用 `GET /runs/{run_id}` 读取。页面中单独确认可能发生模型调用后执行，或由有权限
操作者调用 `POST /runs/{run_id}/execute`。执行前复核原权限、来源版本、模型/策略及
租约栅栏，随后保存精确最终回答、生成类型、耗时和断言。
`REAL_MODEL` 与 `DETERMINISTIC` 分别记录；确定性澄清可能是正确行为，但不能满足
要求真实模型的标准。`SUCCEEDED` 是执行结果，不是事实正确证明。

另一位获准的**人用户**检查实际回答和引用，向 `POST /runs/{run_id}/reviews`
提交 `observation.output_digest` 中的 `output_digest`、`factual_correct`、
`citations_supported` 和至少三个字符的原因。请求者不能审核自己的运行；过时摘要
会被拒绝。错误回答应记录否定审核，不能只为得到 PASS 而修改用例或标准。

## 故障、重复执行与证据

运行状态为 `PENDING`、`RUNNING`、`SUCCEEDED`、`FAILED`、`UNOBSERVED`。
已完成任务返回原记录，不再次调用模型。过期尝试无法确定是否已经发送时，进入
`UNOBSERVED`，不能自动重发。权限、模型配置或策略变化会阻止继续使用。先检查
原运行、任务尝试、来源状态及错误，再提出新的授权运行；不要清租约或替换冻结凭据
来重复旧派发。

`POST /results` 保留原显式登记结果合同，调用者提供的 `passed` 不能证明生成过
最终回答；检索/准备测试也不能代替 `/runs` 的输出与审核。比较时固定用例、负载、
标准、策略和模型版本，并在验收记录中保留来源及软件包/服务资源摘要。运行自身返回
`release_acceptance: NOT_ESTABLISHED_BY_THIS_RUN`。五个确切软件包、七个真实数据库
目标、完整业务流程、浏览器检查及当前材料仍是独立的发布要求。
