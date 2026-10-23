# Harness 模板系统 v5.0.1

> 当前软件包：**川序社区版**；支持底座：**oracle, pg, yashandb**；版本类别：**Community**；许可：**Apache-2.0**。文中其他底座及企业专属能力用于说明差异，不表示此包包含或支持这些能力。

[English](harness.md)

## 用途与实体

Harness 模板是可复用的 Agent 执行蓝图，以 `ENTITY_TYPE='HARNESS_TEMPLATE'`
的实体保存，由 `HARNESS_META` 扩展其元数据。模板定义输入输出结构、执行模式和
运行配置；实例化时替换变量。模板正文和变量不会授予数据库、工具、模型或部署权限。

## 生命周期

模板使用 `DRAFT`、`ACTIVE`、`ARCHIVED` 等实体状态；部署事实与模板状态分开。
发布、更新、实例化和部署都应通过对应的授权服务，不能仅通过修改正文或状态字段
绕过业务 Agent 的模板准入、负责人、模型或运行隔离要求。

## 内置模板

所选数据库的 `4_harness_templates.sql` 幂等创建以下模板。单库包位于
`scripts/deploy/`；整合包位于 `scripts/deploy/<database>/`。

| 模板 | 分类 | 执行模式 | 输入变量 | 输出字段 |
|---|---|---|---|---|
| Research Analyst | research | SEQUENTIAL | role、domain、objective、query | findings、sources |
| Code Assistant | development | SEQUENTIAL | role、language、guidelines、task | solution、explanation |
| Data Analyst | analytics | PARALLEL | role、focus_area、data_query | analysis、recommendations |
| Task Planner | orchestration | CONDITIONAL | role、constraints、objective | plan、dependencies |
| Security Auditor | security | SEQUENTIAL | role、policies、action | assessment、risks、mitigations |

初始种子使用 `IMPORTANCE=2`、`VISIBILITY='SHARED'`、`OWNED_BY_AGENT='SYSTEM'`。
这些值描述初始模板，不授予跨主体读取权限。实际能力受当前身份、资源授权、版本、
模板约束和部署目标限制。
