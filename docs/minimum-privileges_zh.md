# 数据库最小权限 v5.0.0

> 当前软件包：**川序社区版**；支持底座：**oracle, pg, yashandb**；版本类别：**Community**；许可：**Apache-2.0**。文中其他底座及企业专属能力用于说明差异，不表示此包包含或支持这些能力。

[English](minimum-privileges.md)

## 身份与范围

本产品支持 oracle, pg, yashandb。部署 Owner 由运维控制，用于创建和迁移平台对象。人用户会话、平台原生 Agent 和外部 Agent 使用不同身份；普通运行请求不能回退到 Owner。数据库授权与主机隔离是独立控制。

授权前检查所选包中的前置 SQL。单库包路径为 `scripts/deploy/`，整合社区包为 `scripts/deploy/<database>/`。使用独立数据库/PDB、Owner 和有限存储或表空间配额，系统库、基线库和受保护 TEST PDB 不能当作空目标。

## PostgreSQL

DBA 在独立应用数据库中执行 `0_pg_database_prerequisites.sql`，将 `schema_owner` 设置为配置中的非超级用户 Owner。先安装要求的 vector/AGE 扩展，再检查脚本的精确授权。受限 Owner 需要目标结构和数据库创建、AGE 目录/函数/序列访问以及 Agent 角色管理权限。

前置脚本在角色不存在时创建共享运行角色，属性为 NOLOGIN、NOSUPERUSER、NOCREATEDB、NOCREATEROLE、NOINHERIT、NOBYPASSRLS。Owner 需要 CREATEROLE 及该角色的 ADMIN OPTION；Agent 不获得管理权限。初始化前必须通过 `PG_AGE_OWNER_PRIVILEGES` 和 `PG_AGENT_ROLE_ADMIN` 预检。

每个 Agent 单独创建 LOGIN。事务局部的 `createrole_self_grant='set, inherit'` 使 Owner 仅能管理自己刚创建的角色。外部预先创建的角色在轮换凭据前，可能需要 DBA 显式补充 ADMIN OPTION，不能通过授予 SUPERUSER 或 BYPASSRLS 解决。

强制 RLS 与 SESSION_USER 绑定必须在注册后仍然有效。父表策略不会保护被直接授权的叶分区，应使用独立 Agent 登录分别验证父表和分区。收敛历史广泛授权后，连续性控制面表仍须拒绝 Agent 访问。

## Oracle

DBA 检查 `0_oracle_database_prerequisites.sql` 的 `SCHEMA_OWNER`、`APP_TABLESPACE`、`APP_QUOTA`。使用应用 PDB、AL32UTF8，以及具备 Partitioning 的 Oracle Home。脚本明确结构 DDL、API、调度、触发器、原生图和 Oracle Text 所需授权。Text 前置包括 CTXAPP 及对 CTXSYS.CTX_DDL 的显式 EXECUTE；这些属于部署 Owner。

Oracle 企业版还要求受支持的 End User、Data Role、Data Grant 能力。存储 PL/SQL 或 Data Grant 解析不能使用继承角色权限时，必须直接授权。综合前置脚本创建仅具 CREATE SESSION 的 `DEEP_SEC_SESSION_ROLE`，并为 Owner 提供受管附加所需的 ADMIN OPTION。

不能把 DBA、SELECT ANY DICTIONARY 或 UNLIMITED TABLESPACE 当作便捷前置。使用有限配额，并仅按版本/对象检查需要授予精确目录访问。业务 End User 使用独立凭据和过滤条件；连接失败不能切换 Owner。数据库内 Embedding 的可选联网需要精确 UTL_HTTP 授权与 ACL，不代表无限制网络访问。

任务步骤使用迁移 85 建立的稳定任务关联，不能照旧示例恢复依赖可变状态的引用分区，也不能改写已应用迁移。

## YashanDB

DBA 在独立应用 PDB 中执行 `0_yashandb_database_prerequisites.sql`。受限 Owner 除结构 DDL 外，还需要 CREATE USER、ALTER USER，以创建和轮换独立 Agent 登录。前置脚本建立最小会话角色及 Owner 管理授权，不授予 DBA、SYSDBA 或无限制对象访问。

迁移 70 及后继将授权视图和私有写入入口绑定到 SESSION_USER。历史定义者权限包与基表不是业务 Agent API。调用者不能通过选择当前 Schema 冒充授权会话。除直接授权外，还要检查 ROLE_TAB_PRIVS 中的角色授权。详见适配器原生安全指南，不复制 Oracle 专有异常或授权语法。

## 核验与变更授权

按[部署](deployment_zh.md)运行当前带账本预检和 `verify`，再完成[迁移](migration_zh.md)后的核验。检查所需结构、无效对象、迁移摘要、凭据创建和原生拒绝访问测试。仅列出授权不能证明执行有效。

撤销过大权限前，明确主体、当前依赖、替代授权和恢复路径。DDL 与拒绝测试使用独立临时目标，不能把历史破坏性示例用于基线或生产结构。

操作系统还需要独立的已验证运行适配器部署权限。数据库授权不能证明容器/虚拟机隔离，也不授予 Host Manager 访问。详见[运行隔离](runtime-isolation_zh.md)。
