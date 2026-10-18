-- Idempotent public product knowledge used by the v4.4.13 Portal.
UPDATE entities SET title='川序 v4.4.13 平台总览 / Chuanxu Platform Overview'
WHERE entity_type='KNOWLEDGE' AND title='川序 v4.4.13 平台总览'
AND NOT EXISTS (SELECT 1 FROM entities x WHERE x.entity_type='KNOWLEDGE' AND x.title='川序 v4.4.13 平台总览 / Chuanxu Platform Overview');
UPDATE entities SET title='川序 v4.4.13 Portal 与知识增强问答 / Knowledge-grounded Portal'
WHERE entity_type='KNOWLEDGE' AND title='川序 v4.4.13 Portal 与知识增强问答'
AND NOT EXISTS (SELECT 1 FROM entities x WHERE x.entity_type='KNOWLEDGE' AND x.title='川序 v4.4.13 Portal 与知识增强问答 / Knowledge-grounded Portal');
UPDATE entities SET title='川序 v4.4.13 身份权限与安全治理 / Identity and Security'
WHERE entity_type='KNOWLEDGE' AND title='川序 v4.4.13 身份权限与安全治理'
AND NOT EXISTS (SELECT 1 FROM entities x WHERE x.entity_type='KNOWLEDGE' AND x.title='川序 v4.4.13 身份权限与安全治理 / Identity and Security');
UPDATE entities SET title='川序 v4.4.13 Agent 协作与工作管理 / Agent Work and Collaboration'
WHERE entity_type='KNOWLEDGE' AND title='川序 v4.4.13 Agent 协作与工作管理'
AND NOT EXISTS (SELECT 1 FROM entities x WHERE x.entity_type='KNOWLEDGE' AND x.title='川序 v4.4.13 Agent 协作与工作管理 / Agent Work and Collaboration');
UPDATE entities SET title='川序 v4.4.13 数据模型、审计与运维 / Data, Audit and Operations'
WHERE entity_type='KNOWLEDGE' AND title='川序 v4.4.13 数据模型、审计与运维'
AND NOT EXISTS (SELECT 1 FROM entities x WHERE x.entity_type='KNOWLEDGE' AND x.title='川序 v4.4.13 数据模型、审计与运维 / Data, Audit and Operations');
UPDATE entities SET title='川序 v4.4.13 PostgreSQL Enterprise 数据库能力 / Database Capabilities'
WHERE entity_type='KNOWLEDGE' AND title='川序 v4.4.13 PostgreSQL Enterprise 数据库能力'
AND NOT EXISTS (SELECT 1 FROM entities x WHERE x.entity_type='KNOWLEDGE' AND x.title='川序 v4.4.13 PostgreSQL Enterprise 数据库能力 / Database Capabilities');

WITH source(title,summary,content) AS (VALUES
 ('川序 v4.4.13 平台总览 / Chuanxu Platform Overview','川序是以数据库为权威控制面的企业 AI Agent 管理平台。Chuanxu is a database-authoritative enterprise AI Agent management platform.','川序（Chuanxu），技术工程名称 AI Agent Infra with DB，是用于部署、运营、治理和协作 AI Agent 的平台，不是单一聊天机器人。v4.4.13 为 Development Candidate，已完成工程验证但仍需独立人工审核。平台统一管理 Human 与 Agent 的身份、权限、注册、凭据、生命周期和归属，提供 Agent Pool、Portal、知识、记忆、任务、工作区、Skills、工具、频道、审批、审计、合规、安全域、模型、部署、监控与大屏。核心原则是数据库权威、最小权限、双主体授权、显式治理与全链路审计。 Chuanxu, whose engineering name is AI Agent Infra with DB, deploys, operates, governs, and coordinates AI Agents rather than acting as a single chatbot. Version 4.4.13 is a Development Candidate pending independent human review. It manages Human and Agent identities, authorization, registration, credentials, lifecycle, ownership, Portal, Knowledge, Memory, Tasks, Workspaces, Skills, Tools, Channels, approvals, audit, compliance, models, deployment, monitoring, and the wallboard.'),
 ('川序 v4.4.13 Portal 与知识增强问答 / Knowledge-grounded Portal','Portal 使用授权知识与获准模型提供知识增强问答。Portal combines authorized Knowledge with an approved model.','Portal 是用户连接获准 Agent Pool 智能体的入口。问答先验证用户与 Agent 都有 knowledge.read，再检索双方共同可访问的有效知识。命中时由获准 LLM 基于材料生成回答并附引用；未命中且策略允许模型补充时，使用模型通用能力并明确其不是企业政策。输入、知识和完整输出均经过内容安全检查。 Portal connects a user to an eligible Agent Pool Agent. It checks knowledge.read for both principals and retrieves only their shared authorized Knowledge. An approved LLM generates cited answers from matching sources. With no match, policy may allow a clearly labeled general-model answer. Inputs, Knowledge, and complete outputs pass content-security checks.'),
 ('川序 v4.4.13 身份权限与安全治理 / Identity and Security','Human 与 Agent 均是受治理主体。Humans and Agents are governed principals.','用户通过角色、权限覆盖、委派、组织和安全域获得有限访问；Agent 必须注册、激活并验证凭据。平台支持 MFA、会话策略、Portal 连接限制、Agent containment、审批、审计与合规。高影响阻断要求不可变 Action Card 和独立授权确认。v4.4.13 对输入、知识与完整模型输出实施内容检查，并采用失败关闭。 Access derives from roles, overrides, delegations, organization, and Security Domains. Agents require registration, activation, and credential proof. MFA, session policy, Portal connection limits, containment, approvals, audit, compliance, and fail-closed content checks protect the platform.'),
 ('川序 v4.4.13 Agent 协作与工作管理 / Agent Work and Collaboration','平台统一管理 Agent Pool、任务、工作区、协作与扩展。The platform governs Agent work and collaboration.','川序支持 Agent Pool 分配、心跳、休眠、释放、转移、下线与隔离。任务、工作区、上下文链、分支、循环和协作组用于长期工作；频道支持显式成员、提及、动作卡和安全域边界。Skills 与工具支持查看、编辑、下载、停用或软删除，写操作受权限与 CSRF 保护。 Chuanxu supports Agent Pool assignment and release, durable Tasks and Workspaces, context lineage, Branches, Loops, Channels, Action Cards, and Security Domain boundaries. Skill and Tool operations are permission- and CSRF-protected.'),
 ('川序 v4.4.13 数据模型、审计与运维 / Data, Audit and Operations','统一实体、能力注册表与审计构成平台基础。Unified entities, capabilities, and audit form the platform foundation.','平台以统一实体保存知识、记忆、任务输出、经验、规格、技能、Agent 与审批，以实体边表达关系。能力开关由 CX_PLATFORM_CAPABILITIES 管理。运维包括预检、迁移、配置、健康检查、模型与 Embedding 治理、审计导出及保留策略。v4.4.13 增加 Agent 诊断、摘要、能力发现和租约 fencing 恢复证据。 Unified entities store Knowledge, Memory, outputs, experience, Specs, Skills, Agents, and approvals, while edges preserve relationships. Operations cover preflight, migrations, configuration, health, model and Embedding governance, audit export, retention, diagnostics, and lease-fencing recovery evidence.'),
 ('川序 v4.4.13 PostgreSQL Enterprise 数据库能力 / Database Capabilities','PostgreSQL Enterprise 适配器的版本基线与能力。PostgreSQL Enterprise adapter baseline and capabilities.','当前适配器为川序 v4.4.13 PostgreSQL Enterprise Edition，数据库基线为 PostgreSQL 18.3+。它支持数据库角色映射、行级安全、事务与并发控制、JSON 数据、图关系的关系型投影和 Agent 独立数据库角色，并承载统一身份、权限、Portal、知识、记忆、任务、Skills、频道、审计与合规。候选版本已验证初始化、外部 Agent、原生授权与并发、Portal 策略和版本不可变性，但仍不等同于正式发布批准。 The PostgreSQL 18.3+ adapter provides role mapping, row-level security, transactions, concurrency controls, JSON, relational graph projections, and independent Agent database roles. Candidate verification is not public-release or production approval.')
), updated AS (
 UPDATE entities e SET content=s.content,summary=s.summary,category='PRODUCT',status='ACTIVE',visibility='PUBLIC',importance=10,updated_at=CURRENT_TIMESTAMP FROM source s WHERE e.entity_type='KNOWLEDGE' AND e.title=s.title RETURNING e.entity_id
)
INSERT INTO entities(entity_type,title,content,summary,category,status,visibility,importance)
SELECT 'KNOWLEDGE',s.title,s.content,s.summary,'PRODUCT','ACTIVE','PUBLIC',10 FROM source s
WHERE NOT EXISTS (SELECT 1 FROM entities e WHERE e.entity_type='KNOWLEDGE' AND e.title=s.title);

INSERT INTO knowledge_meta(entity_id,entity_type,domain,topic,difficulty)
SELECT e.entity_id,'KNOWLEDGE','PLATFORM','Chuanxu v4.4.13','INTERMEDIATE' FROM entities e
WHERE e.entity_type='KNOWLEDGE' AND e.title LIKE '川序 v4.4.13%'
AND NOT EXISTS (SELECT 1 FROM knowledge_meta km WHERE km.entity_id=e.entity_id AND km.entity_type='KNOWLEDGE');
