# 迁移指南 v5.0.1

> 当前软件包：**川序社区版**；支持底座：**oracle, pg, yashandb**；版本类别：**Community**；许可：**Apache-2.0**。文中其他底座及企业专属能力用于说明差异，不表示此包包含或支持这些能力。

[English](migration.md)

## 当前合同

此包支持 **oracle, pg, yashandb**。其生成的基线清单和校验和定义了有序的部署合同。v5.0.0 保留现有架构，并通过 `102_v5_0_0_network_access.sql` 增加来源 IP 策略实体；打包和产品标识的变化不构成重命名或修改已应用 SQL 的理由。
v5.0.1 新增 103–105，分别提供记忆质量、上下文资产及最终回答验收，生成的目标终点
为 105。这里说明目标合同，不表示数据库或发布验收已经完成。

单后端基线位于 `scripts/deploy/baseline_v*.json`。在统一的 Community 包中，每个后端在 `scripts/deploy/<database>/` 下恰好有一个基线。仅使用所选后端的脚本、驱动和配置。OpenTenBase AgentX 只能使用 PostgreSQL 链。

| 先前发布的版本 | 迁移终点 |
|---|---|
| v4.4.14 | 82 |
| v4.4.15, v4.4.16, v4.5.0 | 97 |
| v4.5.1 | 100 |
| v4.5.2 | 101 |
| v5.0.0 | 102 |

这些版本是常规发布。历史迁移文件名描述的是结构引入的时间，而不是传递给当前安装程序的目标版本。已撤回的 v4.4.8 和未知的部分架构不被假定为升级源。保留历史证据并在继续之前进行调查。

## 准备现有目标

记录当前产品、数据库/PDB、所有者、运行节点、配置、加密密钥位置以及已应用的迁移校验和。验证与所选产品和社区版/企业版的兼容性。更改数据库或在社区版与企业版之间切换不是自动数据迁移。

数据库操作员负责备份和恢复。在更改现有数据之前，建立并测试相关的数据库原生恢复边界。客户端不声称验证备份。对于非交互式升级，显式 `--confirm-database-backup` 确认该责任。

保留私有配置、主加密密钥和 `.runtime/deployment/` 日志/密钥文件。切勿将这些放入公共发布或支持归档中。从所选后端确认先决条件以及 [最小权限](minimum-privileges_zh.md)；普通 Agent 不得获取部署所有者的凭据。

Oracle、YashanDB 升级至 v5.0.1 前，需由 SYS 在原有的确切应用 PDB 中单独执行
本底座的 `0_<database>_v5_0_1_native_identity_prerequisites.sql`。该管理员脚本
创建仅投影账户名称和状态的只读 `SYS.CX_AGENT_ACCOUNT_STATUS`，只向确切 Owner
授予不带转授权权利的 SELECT。它不是应用迁移，不由安装器自动执行，也不修改
历史 SQL、校验和或终点 105。接口缺失、不可读或结构不符时，只读预检必须阻断；
不能通过 DBA、完整目录访问或给 Agent 配置 Owner 凭据绕过。
详见[原生身份前置与撤销操作](native-identity_zh.md)。

## 按账本升级

使用已安装包中的 Python 环境，并从其根目录开始工作：

```bash
bash scripts/install_platform.sh upgrade \
  --database pg --edition community --version 5.0.1 \
  --config /absolute/path/config.json \
  --confirm-database-backup
```

将数据库和社区版/企业版参数替换为此软件包支持的值。
安装程序会验证基线、源状态、有序脚本摘要以及对象后置条件。仅当已应用条目的校验和与所需结构相匹配时，才会接受这些条目。后续迁移只有在自身绑定校验和的条目状态为 APPLIED 之后，才能满足较早的结构检查。

v5.0.0 通过现有的 Knowledge 实体重新发布当前的产品事实。
仅归档精确且未更改的历史产品知识种子；用户编辑和无关的 Knowledge 将保留。快照发布、公共实体、退役和审计在同一个事务中提交。这不是对客户 Knowledge 的批量重写，也不是数据库转换。

## 限制受影响的写入边界

仅排空受迁移影响的写入进程。停止这些任务的新任务领取，允许有界的在途工作完成或达到安全点，记录租约并在严格的迁移后检查后恢复。不要强加未记录的平台级写入中断。

Oracle 任务迁移 85 使用可恢复的复制，并在最终切换前进行检查。最终边界涵盖 Task Plan/Step 写入进程，而不包括无关的对话或读取。在验证允许退役之前，保留其持久化阶段和回退对象。必须检查现有的任务历史和依赖关系，而不是丢弃它们。

| 迁移 | 主要保留的结构或边界 |
|---|---|
| 85 | 稳定的任务/步骤关系和安全的状态转换 |
| 86–88 | 连续性实体、绑定和类型化的原生执行链接 |
| 89–93 | MCP 发现快照、精确的工具契约和请求来源 |
| 94 | 不可变的交接策略修订 |
| 95–96 | Worker 上下文和原始 Gateway 凭据绑定 |
| 97 | 原生源快照和源重新验证 |
| 98–100 | Agent 扩展、固定框架锁和根文件系统摘要 |
| 101 | 统一的 A2A/DB4A2A Task Plan/Step 关联和带围栏令牌的执行尝试 |
| 102 | 来源 IP 策略指针、不可变修订及规则，初始关闭 |
| 103 | 记忆时间/协调/恢复事实、不可变工作便签及显式关联任务的复盘 |
| 104 | 上下文预算/表示、Agent 资产绑定、配置来源修订及带栅栏的同步/导入检查点 |
| 105 | 版本化回答标准、关联任务的运行、加密输入/输出、精确来源及独立人工审核 |

v5.0.1 目标需检查三项新脚本及结构清单，包括实际表、键、约束和原生保护。
终点 105 账本成功不代表 103、104 对象存在。来源/模型作业复用既有任务连续性链，
不另建调度器，也不授予 Agent 对控制面表的 SQL 访问。历史证据缺少可靠事件时间时，
新时间字段保持未知，不得补造本地时间戳。见[记忆证据](memory-working-notes_zh.md)、
[Agent 资产](agent-context-assets_zh.md)及[回答验收](answer-quality_zh.md)。

PostgreSQL 在历史状态分区 Task Plan 表没有全局 PLAN_ID 键的情况下，保留服务端的稳定计划验证。这是一个明确的契约，而不是跳过验证的许可。

## 恢复并调查故障

在采取行动之前，检查返回的运行 ID、本地日志和数据库迁移账本。不要初始化现有数据库、清除账本、编辑校验和、跳过失败的片段，或假设中断的语句已提交。

```bash
bash scripts/install_platform.sh status \
  --database pg --edition community --version 5.0.1 \
  --config /absolute/path/config.json --run-id YOUR_RECORDED_RUN_ID
bash scripts/install_platform.sh resume \
  --database pg --edition community --version 5.0.1 \
  --config /absolute/path/config.json --run-id YOUR_RECORDED_RUN_ID
```

恢复操作使用原始计划和已验证的已完成操作摘要。如果初始化在管理员提交之前停止，请提供受保护的管理员密码文件。已完成接管的管理员可以在不保留明文的情况下进行验证。如果无法验证原始计划或恢复状态，请停止操作并使用数据库文档中记载的恢复程序。

## 验证并恢复服务

```bash
bash scripts/install_platform.sh verify \
  --database pg --edition community --version 5.0.1 \
  --config /absolute/path/config.json
```

验证迁移终点、无效对象、键/约束、原生身份拒绝、产品身份以及当前能力状态。然后检查健康状态、数据库就绪情况、登录、授权的读写工作流、任务状态转换、取消/恢复以及（如果使用了）Agent 注册。

仅恢复已排空的写入进程，并监控租约、尝试次数和错误。不确定的外部影响需要核对；重启并不授权重复发送。在批准的回滚期间内，保留旧程序目录和数据库恢复边界。

经过验证的升级本身并不建立客户容量、数据库集群高可用性（HA）或 RPO/RTO。请参阅 [恢复](recovery_zh.md)、
[连续性操作](continuity-operations_zh.md) 和 [部署](deployment_zh.md)。
