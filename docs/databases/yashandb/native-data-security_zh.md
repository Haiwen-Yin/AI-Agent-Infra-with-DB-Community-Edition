# 原生实体访问 v5.0.1

> 当前软件包：**川序社区版**；支持底座：**oracle, pg, yashandb**；版本类别：**Community**；许可：**Apache-2.0**。文中其他底座及企业专属能力用于说明差异，不表示此包包含或支持这些能力。

[English](native-data-security.md)

当前基线保留迁移 70 及后继，适用于社区版和企业版。独立 Agent 用户不能直接访问 ENTITIES、KNOWLEDGE_META、ENTITY_EMBEDDINGS、ENTITY_EDGES、ENTITY_TAGS，不能执行历史 Owner 定义者权限包。平台 Owner API 与 Agent API 分开，Agent 不接收 Owner 凭据，也不能在失败时回退 Owner。

## 读取接口

| 视图 | 内容 |
|---|---|
| CX_AGENT_ENTITY_READ | 获准实体 |
| CX_AGENT_KNOWLEDGE_READ | 获准知识实体 |
| CX_AGENT_KNOWLEDGE_META_READ | 获准实体的元数据 |
| CX_AGENT_EMBEDDING_READ | 获准实体的向量 |
| CX_AGENT_EDGE_READ | 两端均获准的关系边 |

数据库将 SESSION_USER 绑定到 CX_AGENT_DB_IDENTITIES 及有效 CX_PRINCIPALS 记录。知识策略按当前公司、主体、组织闭包和有效期判断，优先于历史 VISIBILITY。没有策略时仅所有权或 PUBLIC 允许读取，SHARED 本身不授予全公司权限。独立业务用户不能修改身份映射或策略表。

## 私有写入

```sql
BEGIN
  CX_AGENT_ENTITY_API.CREATE_PRIVATE(
    'unique-client-generated-id', 'KNOWLEDGE', 'Title', 'Content');
END;
/
COMMIT;
```

CREATE_PRIVATE 只接受 MEMORY、KNOWLEDGE，从实际登录推导所有者，始终创建 PRIVATE 数据。UPDATE_PRIVATE 接收 ID、标题和正文，只能修改调用者自己且没有受管知识策略的私有实体。两个过程均不提交调用者事务。

这些只是最小原生实体操作，不是完整记忆生命周期或共享治理 API。生命周期、策略、组织和图修改使用已认证平台 API。历史基表集成须改用上述视图/过程或平台 API，不能用 Owner 凭据作为兼容方案。

## 迁移诊断

早期未发布的迁移 70 曾因动态 SQL 重复转义 USERENV 报 YAS-04209，修正后使用普通视图 DDL。撤权仅忽略已知“授权不存在/被授权者不存在”错误，其他错误阻止部署。初始化报告数据库错误码和语句序号，不输出含密码 SQL。不能通过覆盖已应用校验和修复客户部署。

当前验证使用明确分类的独立版本测试库，不使用生产、基线或 TEST PDB。这些检查只证明所列实体接口，不能扩大为对全部历史表、过程或图算法的隔离承诺。
