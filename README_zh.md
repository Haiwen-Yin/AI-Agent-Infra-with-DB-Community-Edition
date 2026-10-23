# 川序社区版 v5.0.1

[English](README.md)

所有版本支持在“平台配置 → 能力与策略 → 访问 IP 限制”中设置 IPv4 / IPv6 白名单或黑名单，支持单个地址及 CIDR 网段，并保留 `127.0.0.1` 本机应急入口。参见[配置与恢复指南](docs/source-ip-access_zh.md)。

基于数据库的 AI Agent 管理平台。任务计划、协作关卡、记忆、知识、通用属性图、
权限和审计记录均以数据库实体保存。外部 Agent 通过受控注册和网关 API 接入；
Portal 对话分配平台托管的本地 Agent。

共享问答将授权检索、独立证据评估和来源标注结合。工作便签、时态记忆、Agent 资产
绑定、配置化来源同步和最终回答验收继续使用已有 Task/Step、Work/Handoff 与候选/
审核实体，保留权限、精确修订及显式发布边界。

本包名称为 **AI-Agent-Infra-with-DB-Community-Edition**，版本类型为 **Community**，许可证为
**Apache-2.0**。支持的数据库标识：**oracle, pg, yashandb**。整合社区版的每个运行
进程选择一种数据库底座；OpenTenBase AgentX 仅支持 PostgreSQL，三个企业版
仍分别交付。

## 安装与初始化

使用 Python 3.14 及以上版本，Linux 的 glibc 不低于 2.34。完整解压软件包并保留
`vendor/`，在软件包根目录执行以下步骤：

1. 将 `config.example.json` 复制为仅属主可读写的 `config.json`。整合版应分别
   选择 `config.oracle.example.json`、`config.pg.example.json` 或
   `config.yashandb.example.json`。保留明确的 `database.type`，填写数据库连接、
   会话签名密钥及可选的模型配置。
2. 执行 `bash scripts/install_offline.sh --database DB`。若先安装、后配置，设置
   `CX_DATABASE_DIALECT` 为受支持的数据库标识。安装器只安装所选底座的驱动
   依赖和原生客户端。
3. 由 DBA 准备专用空数据库/PDB、受限 Owner 和所选底座前置。v5.0.1 的 Oracle、
   YashanDB 还需由 SYS 在确切应用 PDB 中，单独执行包内
   `0_<database>_v5_0_1_native_identity_prerequisites.sql`，准备
   `SYS.CX_AGENT_ACCOUNT_STATUS`。已有数据库升级也需要此前置；PostgreSQL
   不使用该视图。初始化前按[原生身份前置](docs/native-identity_zh.md)和
   [最小权限](docs/minimum-privileges_zh.md)完成核验。
4. 将初始管理员密码存入权限为 `0600` 的文件。执行
   `bash scripts/install_platform.sh initialize --database DB --edition EDITION
   --version 5.0.1 --config /绝对路径/config.json --admin-password-file
   /绝对路径/password-file`。将 `DB` 替换为支持的数据库标识，将 `EDITION`
   替换为 `community` 或 `enterprise`。
5. 执行 `./start_web_server.sh start`。Dashboard 入口为 `/app/`，Portal 入口
   为 `/portal`；`/api/health` 返回进程和产品标识，`/api/ready` 检查数据库就绪状态。

可用 `CX_CONFIG_PATH` 指定外部私有配置文件。`CX_DATABASE_DIALECT` 必须与配置
一致；缺少选择、选择冲突或数据库不受产品支持时，启动会停止。更换底座需要重启
并准备独立目标数据库，不会自动搬迁业务数据。

### 整合社区版的三种部署方式

每个安装目录选择下表中的一种方式。初始化前完善对应配置；单库包使用自己的
`config.example.json`，只能选择该包声明支持的数据库。

| 数据库 | 配置示例 | 离线安装命令 | 完整依赖 |
|---|---|---|---|
| Oracle | `config.oracle.example.json` | `bash scripts/install_offline.sh --database oracle` | `requirements/oracle.txt` |
| PostgreSQL | `config.pg.example.json` | `bash scripts/install_offline.sh --database pg` | `requirements/pg.txt` |
| YashanDB | `config.yashandb.example.json` | `bash scripts/install_offline.sh --database yashandb` | `requirements/yashandb.txt` 及配套原生客户端 |

整合包根目录的 `requirements.txt` 仅包含公共依赖，单独执行
`pip install -r requirements.txt` 不会安装数据库驱动。`vendor/` 同时携带三库
离线文件，安装时只选择其中一种。Oracle、PG 的手工 pip 安装及 YashanDB 原生
安装方式见[部署说明](docs/deployment_zh.md#各数据库独立安装路径)。
同时运行多个底座时，使用独立安装目录和虚拟环境。若设置 `CX_VENV_DIR`，
安装、初始化和启动时都需保持相同设置。安装器会拒绝复用含有其他底座驱动的
环境；修改配置不会自动迁移依赖或业务数据。

## 使用与扩展

- [部署说明](docs/deployment_zh.md)与[迁移指南](docs/migration_zh.md)
- [架构说明](docs/architecture_zh.md)与[API 参考](docs/api-reference_zh.md)
- [Agent 扩展](docs/agent-extensions_zh.md)与[DB4A2A](docs/db4a2a_zh.md)
- [连续性操作](docs/continuity-operations_zh.md)
- [记忆证据、工作便签与任务复盘](docs/memory-working-notes_zh.md)
- [Agent 资产、上下文预算与来源同步](docs/agent-context-assets_zh.md)
- [共享问答与最终回答验收](docs/answer-quality_zh.md)
- [安全说明](docs/security_zh.md)与[交付验证](docs/release-signing_zh.md)
- [原生 Agent 退役与账户状态前置](docs/native-identity_zh.md)
- [访问 IP 配置与本机恢复](docs/source-ip-access_zh.md)
- [版本说明](RELEASE_NOTES_v5.0.1.md)

模型能力按供应商与模型逐项验证。受控集成继续执行授权、隔离、运行限额及数据库
审计检查。社区包不包含企业版专属代码和 SQL。人用户自助注册与外部 Agent 注册
分别配置。
