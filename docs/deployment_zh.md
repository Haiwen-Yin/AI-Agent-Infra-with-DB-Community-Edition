# 部署指南 v5.0.0

> 当前软件包：**川序社区版**；支持底座：**oracle, pg, yashandb**；版本类别：**Community**；许可：**Apache-2.0**。文中其他底座及企业专属能力用于说明差异，不表示此包包含或支持这些能力。

[English](deployment.md)

## 产品与数据库选择

v5.0.0 提供五个交付包，对应七个数据库验收目标。川序整合社区版在一个包中
提供 Oracle、PostgreSQL、YashanDB 三种底座，每个进程明确选择一种；
OpenTenBase AgentX 仅支持 PostgreSQL。三个川序企业版分别使用对应数据库。
社区版采用 Apache-2.0，企业版采用 BSL-1.1，专属模块和迁移脚本按版本物理裁剪。

数据库保存任务、步骤、记忆、知识、属性图、身份授权与审计等实体。
更改底座不是在线切换，也不会自动复制业务数据；请准备独立目标，验证配置后重启。

## 环境准备

使用 Python 3.14 及以上版本和 glibc 2.34 及以上的 Linux。
控制面可运行不代表主机已满足本地 Agent 强隔离要求，见
[平台兼容性](linux-platform-compatibility_zh.md)与[运行隔离](runtime-isolation_zh.md)。
软件包包含离线依赖；保留 `vendor/`。YashanDB 还需包内对应原生客户端。
数据库的版本和最小权限见[最小权限](minimum-privileges_zh.md)。
Oracle 使用 PDB，YashanDB 使用 PDB，PostgreSQL 使用独立数据库和非超级用户
Schema Owner。不要把数据库主机 root 或 SYS 凭据写入平台运行配置。

## 配置和安装

1. 完整解压，从包根目录操作。使用单库包的 `config.example.json`，或整合包中
   `config.oracle.example.json`、`config.pg.example.json`、
   `config.yashandb.example.json` 中的一个，复制为 `config.json`。
2. 限制配置文件权限为 `0600`。填写 `database.type`、连接信息、
   `security.secret_key`，以及模型、Embedding 和 Web 监听配置。
   PG 使用 `host/port/dbname`，Oracle 和 YashanDB 使用 `dsn`。
3. 执行 `bash scripts/install_offline.sh`，安装到包内 `.venv`。
   可设置 `PYTHON_BIN` 指定 Python，`CX_VENV_DIR` 指定虚拟环境。
   先安装后配置时，通过 `CX_DATABASE_DIALECT=pg`（或其他受支持标识）选择底座。
   只有选中底座的驱动和客户端参与安装。
4. 用 `CX_CONFIG_PATH=/绝对路径/config.json` 指定外部配置，或保留包根默认路径。
   `CX_DATABASE_DIALECT` 与配置中的类型必须一致。缺失、冲突或不支持的选择
   会在加载数据库驱动前被拒绝。选定底座在进程生命周期内固定。

`server.host` 决定监听范围，`server.port` 决定端口。外部访问时还需网络和防火墙
允许访问。反向代理场景设置 `CX_PUBLIC_BASE_URL` 为对外地址，配置可信代理
和 HTTPS。不要把未经验证的转发地址作为模型网关。

## 初始化数据库

先由数据库管理员准备空的专用 PDB 或数据库，并应用本底座的
`0_*_database_prerequisites.sql`。授予 Schema Owner 的部署权限与普通 Agent
运行权限不同，不能给业务 Agent 填入 Owner 凭据作为后备连接。

单库包的部署清单位于 `scripts/deploy/baseline_v*.json`；整合包位于
`scripts/deploy/数据库标识/baseline_v*.json`。每个底座恰有一个本版清单，
v5.0.0 沿用完整、经过校验的实体结构，终止迁移为
`102_v5_0_0_network_access.sql`。历史 SQL 的版本号和校验和保持原值。

将初始管理员密码写入权限为 `0600` 的私有文件，执行：

```bash
bash scripts/install_platform.sh initialize \
  --database pg --edition community --version 5.0.0 \
  --config /absolute/path/config.json \
  --admin-password-file /absolute/path/admin.password
```

按实际包替换 `--database` 与 `--edition`。初始化先验证目标为空，按清单执行
基础结构和迁移，建立管理员与平台 Agent、检查就绪状态，再退役临时部署身份。
初始化不依赖 LLM 或外部 Agent；模型服务用于之后的推理操作。

## 升级、恢复和验证

已有平台数据不能走空库初始化。确认数据库侧备份和恢复责任后，使用
`upgrade --confirm-database-backup`；未知或部分结构先查看部署日志，选择
原 `--run-id` 执行 `resume`。不要修改已应用迁移，也不要删除迁移账本。
详见[迁移指南](migration_zh.md)。

部署日志与密钥保存在包的私有 `.runtime/deployment/` 中。重建或替换程序目录
前保留配置、密钥和恢复日志，不要把它们放进公开软件包。

```bash
bash scripts/install_platform.sh verify \
  --database pg --edition community --version 5.0.0 \
  --config /absolute/path/config.json
./start_web_server.sh start
./start_web_server.sh status
```

Dashboard 入口是 `/app/`，Portal 入口是 `/portal`。`/api/health` 表示进程存活，
返回产品与版本；`/api/ready` 检查数据库和控制面结构就绪，二者不能互相代替。
启动器默认使用包内 `.runtime/web.pid`，不同安装目录互不复用 PID 文件。

## 治理、注册和模型

启动模式来自 `CX_RUNTIME_PROFILE`，默认 `production`，它不修改数据库治理记录。
平台能力以 `CX_PLATFORM_CAPABILITIES` 为准，图工程细分能力以
`CX_GRAPH_CAPABILITY_MATRIX` 为准；缺记录、配置不一致或数据库不可达时不可
按已启用处理。环境变量不能扩大许可证或身份权限。

人用户注册入口由人注册策略控制，外部 Agent 注册由独立策略控制。
Portal 使用本地托管 Agent；频道中的 Agent 需要成员关系、激活、运行条件和
数据访问授权。知识库未命中时可由模型回答，并显示来源标注。

为模型服务配置地址、模型名称和必要的私有密钥后，执行健康检查和能力探测。
结构化输出、工具调用或取消能力依赖具体服务，不由模型名称推断。
MCP、A2A、框架 Agent、遥测和回放能力仍受各自开关、授权和隔离条件约束。
当前能力评估见[Agent 扩展](agent-extensions_zh.md)。

停止服务使用 `./start_web_server.sh stop`；重启使用 `restart`。保留任务和
Worker 租约状态以便数据库驱动恢复，不要通过删表或清空任务来消除报错。
