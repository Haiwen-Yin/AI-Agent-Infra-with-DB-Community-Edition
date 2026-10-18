# 川序社区版 v5.0.0

[English](README.md)

所有版本支持在“平台配置 → 能力与策略 → 访问 IP 限制”中设置 IPv4 / IPv6 白名单或黑名单，支持单个地址及 CIDR 网段，并保留 `127.0.0.1` 本机应急入口。参见[配置与恢复指南](docs/source-ip-access_zh.md)。

基于数据库的 AI Agent 管理平台。任务计划、协作关卡、记忆、知识、通用属性图、
权限和审计记录均以数据库实体保存。外部 Agent 通过受控注册和网关 API 接入；
Portal 对话分配平台托管的本地 Agent。

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
2. 执行 `bash scripts/install_offline.sh`。若先安装、后配置，设置
   `CX_DATABASE_DIALECT` 为受支持的数据库标识。安装器只安装所选底座的驱动
   依赖和原生客户端。
3. 将初始管理员密码存入权限为 `0600` 的文件。执行
   `bash scripts/install_platform.sh initialize --database DB --edition EDITION
   --version 5.0.0 --config /绝对路径/config.json --admin-password-file
   /绝对路径/password-file`。将 `DB` 替换为支持的数据库标识，将 `EDITION`
   替换为 `community` 或 `enterprise`。
4. 执行 `./start_web_server.sh start`。Dashboard 入口为 `/app/`，Portal 入口
   为 `/portal`；`/api/health` 返回进程和产品标识，`/api/ready` 检查数据库就绪状态。

可用 `CX_CONFIG_PATH` 指定外部私有配置文件。`CX_DATABASE_DIALECT` 必须与配置
一致；缺少选择、选择冲突或数据库不受产品支持时，启动会停止。更换底座需要重启
并准备独立目标数据库，不会自动搬迁业务数据。

## 使用与扩展

- [部署说明](docs/deployment_zh.md)与[迁移指南](docs/migration_zh.md)
- [架构说明](docs/architecture_zh.md)与[API 参考](docs/api-reference_zh.md)
- [Agent 扩展](docs/agent-extensions_zh.md)与[DB4A2A](docs/db4a2a_zh.md)
- [连续性操作](docs/continuity-operations_zh.md)
- [安全说明](docs/security_zh.md)与[交付验证](docs/release-signing_zh.md)
- [版本说明](RELEASE_NOTES_v5.0.0.md)

模型能力按供应商与模型逐项验证。受控集成继续执行授权、隔离、运行限额及数据库
审计检查。社区包不包含企业版专属代码和 SQL。人用户自助注册与外部 Agent 注册
分别配置。
