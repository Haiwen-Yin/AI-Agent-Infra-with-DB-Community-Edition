# POC 就绪与证据 v5.0.1

> 当前软件包：**川序社区版**；支持底座：**oracle, pg, yashandb**；版本类别：**Community**；许可：**Apache-2.0**。文中其他底座及企业专属能力用于说明差异，不表示此包包含或支持这些能力。

[English](poc-readiness.md)

本文定义可重复的四周 POC 技术证据边界，不承诺客户已接受产品或必然取得特定效率提升。

## 验收范围

必需技术项为：在约定环境部署对应产品；注册约定 Agent 并核验清单；通过已认证操作展示状态和活动；生成一条受范围及数量限制的审计追踪；演示一次 Agent 停用或撤权。

Token 与效率只是观测，须记录数据集、负载、数据库、规模、并发和测量边界，不作为固定提升承诺。

## 就绪检查

使用可访问的 Python 3.14+，不指定安装来源。检查只读，不部署结构：

```bash
source scripts/python_runtime.sh
PYTHON_BIN="$(cx_resolve_python)"
cx_prepare_python_environment "$PYTHON_BIN"
"$PYTHON_BIN" scripts/poc_readiness.py \
  --pg-config /path/to/pg-config.json \
  --edition community \
  --output poc-readiness.json
```

只选择产品支持的底座和社区版/企业版参数。整合社区包可用独立配置逐个检查三库，单库产品不能宣称支持其他数据库；每个所选适配器使用独立进程。

报告记录配置字段是否齐全、仅 Owner 可读的文件权限、驱动、连接、数据库版本、必需对象数量、SKILL_META 合同和修复建议，不记录凭据、DSN 或原始驱动错误。PostgreSQL 可使用 peer、trust 或受限 `.pgpass`/驱动认证，不强制在配置中保存密码。缺少能力不能得到 POC 就绪结论。

## 验收证据

可将版本证据组合成 POC 报告：

```bash
"$PYTHON_BIN" scripts/poc_evidence.py \
  --manifest release_evidence/manifest.json \
  --clean release_evidence/clean-deployments.json \
  --modes release_evidence/mode-matrix.json \
  --governance release_evidence/governance-live.json \
  --readiness poc-readiness.json \
  --skill SKILL.md \
  --output poc-evidence.json
```

每个必需项关联带时间和 SHA-256 的报告。仅在记录实际可执行文件版本及操作时，才宣称原生 OpenClaw、Hermes 已验证。框架无关 SKILL.md 合同检查可单独记录，不能替代运行结果。

## 支持包

支持包只包含脱敏摘要与有界日志：

```bash
"$PYTHON_BIN" scripts/support_bundle.py \
  --manifest poc-evidence.json \
  --poc poc-evidence.json \
  --readiness poc-readiness.json \
  --config /path/to/pg-config.json \
  --output support-bundle.zip \
  --manifest-output support-bundle.json
```

排除原始配置。日志每文件最多 1 MiB，遮盖常见密码、Token、API Key 和秘密字段。

## 排除项、回滚与支持

标准 POC 不包含公网暴露、共享数据库多租户、自动发现未注册 Agent、模型质量保证、任意外部副作用恰好执行一次或无限制定制开发。

迁移前备份数据库/结构、加密配置、主密钥与确切发行包。回滚恢复配套、经过验证的数据库及兼容程序快照，不能假定历史配置能运行在当前结构上。外部副作用和已完成凭据轮换单独处理。

客户协议应明确 POC 范围、响应预期、升级联系人和例外。技术证据报告不自动构成 SLA，也不代表无限支持。
