# v5.0.5 release notes / 发布说明

Update from v5.0.4; PostgreSQL adds a bounded native context-read migration.
从 v5.0.4 升级；PostgreSQL 追加限定范围的原生上下文读迁移。已验证环境及边界见交付清单。

## English

- Agent assets/sources share one scope selector and separate inventory and
  configuration cards. Reference imports belong to the binding workflow.
- Security Domain inventory supports server-side name/ID, classification and
  status filters within the caller's discovery scope.
- Registered platform Agents expose model configuration directly. Saving an
  active provider profile is audited and checks the expected prior binding;
  it does not activate the Agent or call the model. Activation remains separate.
- Management Channel command validation returns actionable feedback with the
  persisted message instead of a misleading identity-service error. Read-only
  commands may omit a reason; a supplied reason needs at least three characters.
- The shared model stream parser accepts cumulative usage, zero placeholder
  statistics and a consistent terminal summary without discarding completed text.
- Grounded answer preparation binds expression limits to the final authorized
  references. Source statements, local calculations, proposals, unknowns and
  conflicts remain distinct. Numerical answer confidence has no calibrated basis;
  detected self-confidence percentages are withheld before publication. This
  bounded check does not verify every natural-language claim. Grounded Channel
  replies retain the Provider stream internally until completion and screening.
- Numeric reference markers must exist in the final authorized window. A
  detected invalid marker withholds the generation and displays labelled source
  extracts; it never assigns the marker to another reference or retries a model.
- When an authorized extract explicitly reports missing execution/verification
  records, a bounded wording rule also withholds some categorical negative
  action outcomes and shows those extracts. This conservative check may withhold
  otherwise supported wording; it cannot establish success, failure or non-execution.
- Decimal measurements do not implicitly select a product release. Exact leading
  document titles receive retrieval priority, and explicit record identifiers
  remain required when natural-language references undergo semantic review.
  Partial factual questions receive concise supported values and unknowns
  without requiring an invented advice section.
- PostgreSQL migration 121 restores reads of an active Agent's own workspace
  context through its registered native identity. It opens no shared/public
  context or write permission. Other backends retain their existing schema;
  exact v5.0.4 predecessor checks run before the additive upgrade.
- Knowledge and Memory load the currently selected view independently. Graph
  previews are bounded and explicitly do not represent corpus totals.
- Knowledge graph previews batch edges and saved context within the authorized
  window. Visible-neighbour ranking uses separate indexed directions, retaining
  current source checks and excluding relationships outside that window.
- Batched original-source reads share Agent/domain checks only within each
  before/after phase and decode exact encrypted bodies with bounded CPU workers.
  Source owner, state, credentials, digests and provenance remain checked.
- General model supplements distinguish a missing retrieval match from record
  nonexistence. Stored memories and notes retain information-record semantics;
  lifecycle exclusion does not establish falsehood or physical deletion.
- Workspace navigation includes Agent assets and sources, with restorable
  authorized selections and responsive forms. Portal knowledge policy groups
  answer controls, disclosure profiles and organization coverage consistently.
- A shared secure UUID helper supports browsers without native randomUUID,
  including ordinary HTTP with getRandomValues; missing secure randomness causes
  a controlled error. Pending request identities remain stable across retries.
- Unkeyed content digests have a SHA-256 fallback when SubtleCrypto is absent.
  Operational states have Chinese display labels without changing API codes.
- All historical SQL and checksums remain unchanged. An explicit v5.0.4 upgrade
  verifies the actual predecessor before applying the selected additive steps;
  it does not replay historical migrations.

## 中文

- Agent 资产与来源统一管理范围选择，将已有记录和配置操作分卡展示；来源引用
  导入仅出现在资产绑定中。
- 安全域清单支持按名称/ID、分级和状态进行服务端筛选，保留原有可见权限范围。
- 已注册的平台 Agent 提供直接模型配置入口。保存有效服务商配置会校验原绑定
  并记录审计，不激活 Agent、不调用模型；激活仍需单独操作。
- 管理频道命令校验失败返回具体原因，保留已保存消息，不再误报身份服务不可用。
  只读命令可省略原因；如填写，至少需要三个字符。
- 公共模型流解析器兼容累计用量、零占位统计和一致的终态统计，保留已完成正文。
- 回答准备将表达约束绑定到最终授权资料，区分原文、计算、提案、未知与冲突。
  平台没有经校准的回答正确概率；检测到无依据的数字自信度时暂缓展示回答。
  这是有限规则检查，不代表逐句事实核验。知识回答在频道中接收完整模型流后，
  先检查表达约束，再发布正文。
- 正文数字引用必须存在于最终授权窗口；检测到无效标号时暂缓展示生成内容，
  仅显示明确标注的来源摘录，不把标号挪给其他资料，也不自动重试模型。
- 授权摘录明确记载缺少执行／验收记录时，有限措辞规则还会暂缓展示部分确定性
  否定操作结果，并展示原文。此保守检查可能暂缓原本有依据的措辞，不能据此
  确认操作成功、失败或未发生。
- 小数测量值不再被隐式当成产品版本。检索优先保留提问开头的精确资料标题，
  自然语言语义检查仍保留明确记录标识的约束。部分事实问题直接说明已知与未知，
  不强制展开建议或补造取值。
- 知识和记忆按当前视图独立加载。图预览有数量限制，不作为全库总数。
- 知识图在已授权窗口内批量读取关系与已存上下文，按两个方向查询可见邻居，
  保留当前来源校验，不带入窗口外关系。
- 批量原始来源读取只在每个前后复查阶段内复用相同 Agent/安全域检查，并以
  有界 CPU 工作线程解密完整正文；逐来源的归属、状态、凭据、摘要及溯源校验保留。
- 通用模型补充区分检索未命中与记录不存在；记忆和便笺按数据记录解释，停止
  使用不等于事实为假或物理删除。生成约束仍不能保证所有通用解释准确。
- 工作区增加“Agent 资产与来源”入口，支持恢复已授权的选择并适配较窄页面。
  Portal 知识策略按回答控制、模型披露与组织覆盖分组。
- 共用安全 UUID 生成方法兼容缺少原生 randomUUID 的浏览器；普通 HTTP 下可使用
  getRandomValues。安全随机源缺失时显示受控错误，待确认操作重试保留幂等身份。
- 缺少 SubtleCrypto 时，无密钥内容摘要使用 SHA-256 后备实现；补齐运行状态的
  中文显示标签，API 状态码保持原义。
- PostgreSQL 追加迁移 121，恢复 ACTIVE Agent 通过登记的专属原生身份读取自己的
  工作区上下文，不开放他人的共享/公开内容或写权限。其他底座沿用既有结构。
  显式升级先核验 v5.0.4 真实前序状态，再执行新增迁移；历史 SQL 不重放、不改写。
