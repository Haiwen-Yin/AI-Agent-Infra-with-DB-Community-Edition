-- ============================================================================
-- AI Agent Infrastructure - PG Community Edition - Seed Data
-- ============================================================================
-- Target: PostgreSQL 16+ with pgvector extension
-- Database: ai_agent
-- Idempotent: uses ON CONFLICT DO NOTHING throughout
-- Uses dynamic ID lookups via workspace_alias/branch_name
-- ============================================================================

SET client_encoding = 'UTF8';
SET search_path = public, pg_catalog;

-- ============================================================================
-- 1. SYSTEM USERS (3 users)
-- ============================================================================
INSERT INTO system_users (username, password_hash, salt, role, status, auth_source, last_login, created_at, updated_at)
VALUES
  ('admin',   'SHA256:1BEDE517DE467F3C8367510C85FE15610AA2560AABF56DFAB60E750B72263554', 'system', 'ADMIN',   'ACTIVE', 'LOCAL', CURRENT_TIMESTAMP - INTERVAL '1 hour',   CURRENT_TIMESTAMP - INTERVAL '30 days', CURRENT_TIMESTAMP),
  ('analyst', 'SHA256:8F6D3890D52BCB8F3513EFAE5631E44C8F9B717E7CE9FC5C3970FAFCB5F3E01B', 'system', 'USER',    'ACTIVE', 'LOCAL', CURRENT_TIMESTAMP - INTERVAL '3 hours',  CURRENT_TIMESTAMP - INTERVAL '15 days', CURRENT_TIMESTAMP),
  ('operator','SHA256:9F86D081884C7D659A2FEAA0C55AD015A3BF4F1B2B0B822CD15D6C15B0F00A08', 'system', 'SERVICE', 'ACTIVE', 'LOCAL', CURRENT_TIMESTAMP - INTERVAL '12 hours', CURRENT_TIMESTAMP - INTERVAL '7 days',  CURRENT_TIMESTAMP)
ON CONFLICT (username) DO NOTHING;

-- ============================================================================
-- 2. AGENT REGISTRY (8 agents)
-- ============================================================================
INSERT INTO agent_registry (agent_id, agent_name, agent_type, agent_role, description, capabilities, config, status, current_user_id, last_active_at, last_seen_at, created_at, updated_at)
VALUES
  ('agent-alpha',   'Alpha Worker',      'WORKER',     'WORKER',     'Primary task execution agent for general-purpose workflows',           '["code_generation","file_operations","search"]'::jsonb,           '{"max_tokens":4096,"temperature":0.7}'::jsonb, 'ACTIVE', 'admin',    CURRENT_TIMESTAMP - INTERVAL '5 minutes',  CURRENT_TIMESTAMP - INTERVAL '5 minutes',  CURRENT_TIMESTAMP - INTERVAL '30 days', CURRENT_TIMESTAMP),
  ('agent-bravo',   'Bravo Coordinator', 'COORDINATOR','COORDINATOR','Orchestration agent that coordinates multi-agent workflows',           '["task_routing","agent_selection","progress_tracking"]'::jsonb,   '{"max_tokens":8192,"temperature":0.3}'::jsonb, 'ACTIVE', 'admin',    CURRENT_TIMESTAMP - INTERVAL '2 minutes',  CURRENT_TIMESTAMP - INTERVAL '2 minutes',  CURRENT_TIMESTAMP - INTERVAL '25 days', CURRENT_TIMESTAMP),
  ('agent-charlie', 'Charlie Analyst',   'WORKER',     'WORKER',     'Data analysis and reporting specialist',                               '["data_analysis","visualization","reporting"]'::jsonb,            '{"max_tokens":4096,"temperature":0.5}'::jsonb, 'ACTIVE', 'analyst',  CURRENT_TIMESTAMP - INTERVAL '1 hour',     CURRENT_TIMESTAMP - INTERVAL '1 hour',     CURRENT_TIMESTAMP - INTERVAL '20 days', CURRENT_TIMESTAMP),
  ('agent-delta',   'Delta Researcher',  'WORKER',     'WORKER',     'Research and knowledge synthesis agent',                               '["web_search","document_analysis","summarization"]'::jsonb,       '{"max_tokens":8192,"temperature":0.4}'::jsonb, 'ACTIVE', 'analyst',  CURRENT_TIMESTAMP - INTERVAL '15 minutes', CURRENT_TIMESTAMP - INTERVAL '15 minutes', CURRENT_TIMESTAMP - INTERVAL '18 days', CURRENT_TIMESTAMP),
  ('agent-echo',    'Echo Validator',    'WORKER',     'WORKER',     'Quality assurance and validation agent for code and outputs',          '["code_review","test_execution","compliance_check"]'::jsonb,      '{"max_tokens":4096,"temperature":0.2}'::jsonb, 'ACTIVE', 'operator', CURRENT_TIMESTAMP - INTERVAL '30 minutes', CURRENT_TIMESTAMP - INTERVAL '30 minutes', CURRENT_TIMESTAMP - INTERVAL '14 days', CURRENT_TIMESTAMP),
  ('agent-foxtrot', 'Foxtrot Builder',   'WORKER',     'WORKER',     'CI/CD and infrastructure automation agent',                            '["pipeline_management","deployment","monitoring"]'::jsonb,        '{"max_tokens":4096,"temperature":0.3}'::jsonb, 'ACTIVE', 'operator', CURRENT_TIMESTAMP - INTERVAL '45 minutes', CURRENT_TIMESTAMP - INTERVAL '45 minutes', CURRENT_TIMESTAMP - INTERVAL '10 days', CURRENT_TIMESTAMP),
  ('agent-golf',    'Golf System',       'SYSTEM',     'SYSTEM',     'System maintenance and health monitoring agent',                       '["health_check","log_analysis","alert_management"]'::jsonb,       '{"max_tokens":2048,"temperature":0.1}'::jsonb,  'ACTIVE', NULL,       CURRENT_TIMESTAMP - INTERVAL '10 minutes', CURRENT_TIMESTAMP - INTERVAL '10 minutes', CURRENT_TIMESTAMP - INTERVAL '30 days', CURRENT_TIMESTAMP),
  ('agent-hotel',   'Hotel Sentinel',    'SYSTEM',     'SYSTEM',     'Security and compliance monitoring agent',                             '["security_audit","access_control","compliance_reporting"]'::jsonb,'{"max_tokens":2048,"temperature":0.1}'::jsonb,  'ACTIVE', NULL,       CURRENT_TIMESTAMP - INTERVAL '8 minutes',  CURRENT_TIMESTAMP - INTERVAL '8 minutes',  CURRENT_TIMESTAMP - INTERVAL '30 days', CURRENT_TIMESTAMP)
ON CONFLICT (agent_id) DO NOTHING;

-- ============================================================================
-- 3. WORKSPACES (5 workspaces)
-- ============================================================================
WITH seed(workspace_name, workspace_type, workspace_alias, isolation_mode,
          owner_user_id, current_agent_id, summary, metadata, status,
          created_at, updated_at) AS (
  VALUES
    ('Project Alpha',   'PROJECT',    'proj-alpha',  'SHARED',   'admin',    'agent-bravo',   'Main product development workspace with cross-team collaboration',   '{"priority":"high","deadline":"2026-09-30"}'::jsonb,          'ACTIVE', CURRENT_TIMESTAMP - INTERVAL '30 days', CURRENT_TIMESTAMP),
    ('Project Beta',    'PROJECT',    'proj-beta',   'SHARED',   'analyst',  'agent-charlie',  'Data analytics pipeline development and optimization',              '{"priority":"medium","deadline":"2026-12-15"}'::jsonb,        'ACTIVE', CURRENT_TIMESTAMP - INTERVAL '25 days', CURRENT_TIMESTAMP),
    ('Research Lab',    'PROJECT',    'research',    'ISOLATED', 'analyst',  'agent-delta',    'Experimental research workspace for AI/ML exploration',             '{"budget_code":"R-2026-04","review_cycle":"weekly"}'::jsonb, 'ACTIVE', CURRENT_TIMESTAMP - INTERVAL '20 days', CURRENT_TIMESTAMP),
    ('Code Review',     'TASK_CHAIN', 'code-review', 'SHARED',   'operator', 'agent-echo',     'Automated code review and quality assurance workspace',             '{"auto_review":true,"min_approvers":2}'::jsonb,               'ACTIVE', CURRENT_TIMESTAMP - INTERVAL '14 days', CURRENT_TIMESTAMP),
    ('DevOps Pipeline', 'AUTONOMOUS', 'devops',      'ISOLATED', 'operator', 'agent-foxtrot',  'CI/CD pipeline management and deployment orchestration',            '{"env":"production","region":"us-east-1"}'::jsonb,            'ACTIVE', CURRENT_TIMESTAMP - INTERVAL '10 days', CURRENT_TIMESTAMP)
)
INSERT INTO workspaces (workspace_name, workspace_type, workspace_alias, isolation_mode,
                        owner_user_id, current_agent_id, summary, metadata, status,
                        created_at, updated_at)
SELECT s.*
FROM seed s
WHERE NOT EXISTS (
  SELECT 1 FROM workspaces existing
  WHERE existing.workspace_alias = s.workspace_alias
);

-- ============================================================================
-- 4. ENTITIES (55 entities across 8 partition types)
-- ============================================================================

-- 4a. MEMORY entities (15)
INSERT INTO entities (entity_type, title, content, summary, category, status, importance, owned_by_agent, source_agent, visibility, workspace_id, retrieval_count, created_at, updated_at)
VALUES
  ('MEMORY', 'Q1 Planning Session Notes', 'Attended Q1 planning meeting on Jan 15. Key decisions: migrate to microservices, adopt event-driven architecture, hire 3 more engineers. Action items assigned to team leads.', 'Q1 planning: microservices migration, event-driven arch, 3 hires', 'MEETING_NOTES', 'ACTIVE', 8, 'agent-bravo', 'agent-bravo', 'SHARED', (SELECT workspace_id FROM workspaces WHERE workspace_alias='proj-alpha'), 12, CURRENT_TIMESTAMP - INTERVAL '25 days', CURRENT_TIMESTAMP - INTERVAL '2 days'),
  ('MEMORY', 'Database Performance Troubleshooting', 'PostgreSQL query performance degraded on the entities table. Root cause: missing index on (entity_type, status). Added composite index, query time dropped from 800ms to 12ms.', 'Fixed slow queries on entities table with composite index', 'TROUBLESHOOTING', 'ACTIVE', 9, 'agent-echo', 'agent-echo', 'SHARED', (SELECT workspace_id FROM workspaces WHERE workspace_alias='proj-alpha'), 24, CURRENT_TIMESTAMP - INTERVAL '20 days', CURRENT_TIMESTAMP - INTERVAL '1 day'),
  ('MEMORY', 'API Design Preferences', 'Team prefers RESTful APIs with consistent error format. Use snake_case for JSON keys. Version in URL path (/v1/, /v2/). Rate limit: 100 req/min per agent.', 'Team API conventions: REST, snake_case, URL versioning, 100 req/min limit', 'PREFERENCES', 'ACTIVE', 7, 'agent-alpha', 'agent-alpha', 'SHARED', (SELECT workspace_id FROM workspaces WHERE workspace_alias='proj-alpha'), 8, CURRENT_TIMESTAMP - INTERVAL '18 days', CURRENT_TIMESTAMP - INTERVAL '5 days'),
  ('MEMORY', 'Weekly Standup 2026-05-28', 'Alpha: completed auth module. Bravo: coordinating Sprint 14. Charlie: data pipeline 80% done. Delta: literature review for RAG optimization. Echo: found 3 critical bugs. Foxtrot: deployed v2.3.1.', 'Standup: auth done, Sprint 14 in progress, pipeline 80%, 3 bugs found, v2.3.1 staged', 'MEETING_NOTES', 'ACTIVE', 5, 'agent-bravo', 'agent-bravo', 'SHARED', (SELECT workspace_id FROM workspaces WHERE workspace_alias='proj-alpha'), 6, CURRENT_TIMESTAMP - INTERVAL '19 days', CURRENT_TIMESTAMP - INTERVAL '19 days'),
  ('MEMORY', 'Infrastructure Capacity Notes', 'Current cluster: 8 nodes, 64GB RAM each. Peak usage at 72%. Recommend scaling to 12 nodes before Q3. DB storage at 45%. Need data archival for entities older than 180 days.', 'Cluster at 72% peak, scale to 12 nodes, DB at 45%, need archival policy', 'CAPACITY', 'ACTIVE', 8, 'agent-foxtrot', 'agent-foxtrot', 'SHARED', (SELECT workspace_id FROM workspaces WHERE workspace_alias='devops'), 15, CURRENT_TIMESTAMP - INTERVAL '15 days', CURRENT_TIMESTAMP - INTERVAL '3 days'),
  ('MEMORY', 'Customer Feedback Summary Q1', 'Top 3 complaints: (1) Dashboard load time > 3s, (2) Missing export to CSV, (3) Inconsistent notification delivery. NPS score improved from 32 to 41. Enterprise renewal rate: 94%.', 'Q1 feedback: slow dashboard, missing CSV export, notification issues. NPS 32 to 41', 'FEEDBACK', 'ACTIVE', 7, 'agent-charlie', 'agent-charlie', 'SHARED', (SELECT workspace_id FROM workspaces WHERE workspace_alias='proj-beta'), 10, CURRENT_TIMESTAMP - INTERVAL '22 days', CURRENT_TIMESTAMP - INTERVAL '7 days'),
  ('MEMORY', 'Security Audit Findings 2026', 'Annual security audit completed. 2 high-severity: (1) SSH keys not rotated on 3 servers, (2) S3 bucket misconfigured as public. 5 medium. Remediation deadline: 30 days.', 'Security audit: 2 high-sev (SSH keys, S3 bucket), 5 medium. 30-day remediation.', 'SECURITY', 'ACTIVE', 10, 'agent-hotel', 'agent-hotel', 'SHARED', (SELECT workspace_id FROM workspaces WHERE workspace_alias='devops'), 18, CURRENT_TIMESTAMP - INTERVAL '12 days', CURRENT_TIMESTAMP - INTERVAL '1 day'),
  ('MEMORY', 'Onboarding Checklist for New Agents', 'New agent onboarding: (1) Register in agent_registry, (2) Assign to workspace, (3) Configure capabilities, (4) Set up credentials, (5) Run health check, (6) Add to collab_groups, (7) Verify task_plan creation.', '7-step agent onboarding: register, workspace, capabilities, credentials, health, groups, tasks', 'ONBOARDING', 'ACTIVE', 6, 'agent-golf', 'agent-golf', 'SHARED', (SELECT workspace_id FROM workspaces WHERE workspace_alias='proj-alpha'), 5, CURRENT_TIMESTAMP - INTERVAL '28 days', CURRENT_TIMESTAMP - INTERVAL '10 days'),
  ('MEMORY', 'Project Alpha Architecture Decision', 'Decided on hexagonal architecture for Project Alpha. Domain layer isolated from infrastructure. Ports and adapters pattern. Event sourcing for audit trail. CQRS for read/write separation.', 'Hexagonal arch with event sourcing and CQRS for Project Alpha', 'ARCHITECTURE', 'ACTIVE', 9, 'agent-alpha', 'agent-bravo', 'SHARED', (SELECT workspace_id FROM workspaces WHERE workspace_alias='proj-alpha'), 20, CURRENT_TIMESTAMP - INTERVAL '26 days', CURRENT_TIMESTAMP - INTERVAL '4 days'),
  ('MEMORY', 'Deployment Runbook v2.3', 'Deployment steps: (1) Run integration tests, (2) Build Docker images, (3) Push to ECR, (4) Update helm values, (5) Rolling deploy via ArgoCD, (6) Smoke test, (7) Monitor error rates for 30min.', '7-step deploy: test, build, push, helm, ArgoCD deploy, smoke test, monitor', 'RUNBOOK', 'ACTIVE', 8, 'agent-foxtrot', 'agent-foxtrot', 'SHARED', (SELECT workspace_id FROM workspaces WHERE workspace_alias='devops'), 30, CURRENT_TIMESTAMP - INTERVAL '8 days', CURRENT_TIMESTAMP - INTERVAL '1 day'),
  ('MEMORY', 'Team Vacation Calendar 2026', 'June: Alpha team off Jun 20-22. July: Bravo lead off Jul 1-5. August: Full team retreat Aug 15-19. September: No overlapping PTO allowed due to Q3 release.', 'Key PTO dates: Jun 20-22, Jul 1-5, Aug 15-19 retreat. No overlap in Sep.', 'SCHEDULING', 'ACTIVE', 4, 'agent-bravo', 'agent-bravo', 'SHARED', (SELECT workspace_id FROM workspaces WHERE workspace_alias='proj-alpha'), 3, CURRENT_TIMESTAMP - INTERVAL '10 days', CURRENT_TIMESTAMP - INTERVAL '10 days'),
  ('MEMORY', 'Error Handling Patterns', 'Standard error handling: (1) Transient errors - retry with exponential backoff, (2) Validation errors - return 400, (3) Auth errors - return 401, (4) Not found - return 404, (5) Internal - return 500 with correlation ID.', 'Error patterns: retry transients, 400 validation, 401 auth, 404 missing, 500 with correlation', 'PATTERNS', 'ACTIVE', 7, 'agent-echo', 'agent-echo', 'SHARED', (SELECT workspace_id FROM workspaces WHERE workspace_alias='proj-alpha'), 9, CURRENT_TIMESTAMP - INTERVAL '16 days', CURRENT_TIMESTAMP - INTERVAL '6 days'),
  ('MEMORY', 'Monitoring Alert Thresholds', 'Alert thresholds: CPU >80% for 5min, Memory >90% for 2min, Disk >85%, Error rate >1%, Latency p99 >2s, DB connections >80% pool. PagerDuty for P1/P2, Slack for P3/P4.', 'Alerts: CPU>80%, Mem>90%, Disk>85%, Err>1%, p99>2s, DB conn>80%. PagerDuty P1/P2', 'MONITORING', 'ACTIVE', 7, 'agent-golf', 'agent-golf', 'SHARED', (SELECT workspace_id FROM workspaces WHERE workspace_alias='devops'), 14, CURRENT_TIMESTAMP - INTERVAL '14 days', CURRENT_TIMESTAMP - INTERVAL '2 days'),
  ('MEMORY', 'Code Style Guidelines Update', 'Updated code style: TypeScript strict mode mandatory. ESLint with strict rules. No any types. Prefer interface over type. Zod for runtime validation. 80% test coverage.', 'TS strict mode, no any, interface over type, Zod validation, 80% coverage', 'GUIDELINES', 'ACTIVE', 6, 'agent-echo', 'agent-echo', 'SHARED', (SELECT workspace_id FROM workspaces WHERE workspace_alias='code-review'), 7, CURRENT_TIMESTAMP - INTERVAL '9 days', CURRENT_TIMESTAMP - INTERVAL '3 days'),
  ('MEMORY', 'Vendor API Rate Limits', 'OpenAI: 60 RPM tier 1, 500 RPM tier 2. Anthropic: 50 RPM. Google Vertex: 300 RPM. Cache responses for 5min TTL. Priority queue for production agents.', 'Rate limits: OpenAI 60/500 RPM, Anthropic 50, Vertex 300. Cache 5min TTL.', 'INTEGRATION', 'ACTIVE', 6, 'agent-delta', 'agent-delta', 'SHARED', (SELECT workspace_id FROM workspaces WHERE workspace_alias='research'), 11, CURRENT_TIMESTAMP - INTERVAL '11 days', CURRENT_TIMESTAMP - INTERVAL '5 days')
ON CONFLICT DO NOTHING;

-- 4b. KNOWLEDGE entities (10)
INSERT INTO entities (entity_type, title, content, summary, category, status, importance, owned_by_agent, source_agent, visibility, workspace_id, retrieval_count, created_at, updated_at)
VALUES
  ('KNOWLEDGE', 'Retrieval-Augmented Generation (RAG)', 'RAG combines information retrieval with text generation. Pipeline: (1) Index documents into vector store, (2) Encode query, (3) Retrieve top-k chunks, (4) Inject into prompt, (5) Generate response. Hybrid search combining BM25 and vector similarity yields best results.', 'RAG pipeline: index, encode, retrieve top-k, inject into prompt, generate. Hybrid search recommended.', 'AI_ML', 'ACTIVE', 9, 'agent-delta', 'agent-delta', 'SHARED', (SELECT workspace_id FROM workspaces WHERE workspace_alias='research'), 45, CURRENT_TIMESTAMP - INTERVAL '20 days', CURRENT_TIMESTAMP - INTERVAL '1 day'),
  ('KNOWLEDGE', 'Event-Driven Architecture Patterns', 'Core patterns: (1) Event Sourcing, (2) CQRS, (3) Saga Pattern, (4) Event Streaming with Kafka, (5) Dead Letter Queue. Benefits: loose coupling, auditability, scalability. Challenges: eventual consistency, debugging complexity.', 'EDA patterns: Event Sourcing, CQRS, Saga, Event Streaming, DLQ. Benefits: coupling, audit, scale.', 'ARCHITECTURE', 'ACTIVE', 8, 'agent-alpha', 'agent-alpha', 'SHARED', (SELECT workspace_id FROM workspaces WHERE workspace_alias='proj-alpha'), 38, CURRENT_TIMESTAMP - INTERVAL '25 days', CURRENT_TIMESTAMP - INTERVAL '3 days'),
  ('KNOWLEDGE', 'PostgreSQL Performance Tuning Best Practices', 'Key tuning: shared_buffers=25% RAM, effective_cache_size=75% RAM, work_mem=RAM/(max_conn*3), random_page_cost=1.1 for SSD. Use EXPLAIN ANALYZE. Enable pg_stat_statements. Partition large tables.', 'PG tuning: shared_buffers 25% RAM, effective_cache_size 75%, SSD random_page_cost.', 'DATABASE', 'ACTIVE', 8, 'agent-foxtrot', 'agent-foxtrot', 'SHARED', (SELECT workspace_id FROM workspaces WHERE workspace_alias='devops'), 32, CURRENT_TIMESTAMP - INTERVAL '18 days', CURRENT_TIMESTAMP - INTERVAL '5 days'),
  ('KNOWLEDGE', 'Microservices Communication Patterns', 'Synchronous: REST, gRPC. Asynchronous: RabbitMQ, Kafka. Service mesh (Istio/Linkerd). Circuit breaker for fault tolerance. Backpressure for flow control. API Gateway for external traffic.', 'Microservice comms: REST/gRPC sync, Kafka/RabbitMQ async, service mesh, circuit breaker.', 'ARCHITECTURE', 'ACTIVE', 7, 'agent-bravo', 'agent-bravo', 'SHARED', (SELECT workspace_id FROM workspaces WHERE workspace_alias='proj-alpha'), 27, CURRENT_TIMESTAMP - INTERVAL '22 days', CURRENT_TIMESTAMP - INTERVAL '6 days'),
  ('KNOWLEDGE', 'Vector Embedding Optimization', 'Optimize embeddings: (1) Quantize float32 to int8 for 4x storage reduction, (2) Use HNSW index (ef_construction=128, m=16), (3) Batch embedding requests, (4) Cache frequent queries. HNSW preferred for recall.', 'Embedding optimization: quantization, HNSW index (ef=128, m=16), batch requests, cache.', 'AI_ML', 'ACTIVE', 8, 'agent-delta', 'agent-delta', 'SHARED', (SELECT workspace_id FROM workspaces WHERE workspace_alias='research'), 29, CURRENT_TIMESTAMP - INTERVAL '15 days', CURRENT_TIMESTAMP - INTERVAL '2 days'),
  ('KNOWLEDGE', 'CI/CD Pipeline Design Principles', 'Core principles: (1) Every commit triggers build, (2) Fail fast with unit tests first, (3) Immutable artifacts, (4) Environment parity, (5) Canary deployments, (6) Automated rollback, (7) Semantic versioning, (8) Security scanning.', 'CI/CD principles: commit triggers build, fail fast, immutable artifacts, canary deploy.', 'DEVOPS', 'ACTIVE', 7, 'agent-foxtrot', 'agent-foxtrot', 'SHARED', (SELECT workspace_id FROM workspaces WHERE workspace_alias='devops'), 22, CURRENT_TIMESTAMP - INTERVAL '12 days', CURRENT_TIMESTAMP - INTERVAL '4 days'),
  ('KNOWLEDGE', 'OAuth 2.0 and JWT Security Best Practices', 'OAuth 2.0 flows: Authorization Code (web), PKCE (SPAs), Client Credentials (M2M). JWT: RS256 signing, 15min access tokens, rotate refresh tokens. HttpOnly cookies. Validate issuer, audience, expiry.', 'OAuth2: Auth Code, PKCE, Client Credentials. JWT: RS256, 15min access, rotate refresh.', 'SECURITY', 'ACTIVE', 9, 'agent-hotel', 'agent-hotel', 'SHARED', (SELECT workspace_id FROM workspaces WHERE workspace_alias='proj-alpha'), 35, CURRENT_TIMESTAMP - INTERVAL '10 days', CURRENT_TIMESTAMP - INTERVAL '1 day'),
  ('KNOWLEDGE', 'Observability Trinity: Logs, Metrics, Traces', 'Three pillars: (1) Logs - structured JSON, correlation IDs, (2) Metrics - RED for services, USE for resources, (3) Traces - OpenTelemetry distributed tracing. Tools: ELK/Loki, Prometheus, Jaeger.', 'Observability: structured logs with correlation IDs, RED/USE metrics, OpenTelemetry traces.', 'MONITORING', 'ACTIVE', 7, 'agent-golf', 'agent-golf', 'SHARED', (SELECT workspace_id FROM workspaces WHERE workspace_alias='devops'), 26, CURRENT_TIMESTAMP - INTERVAL '8 days', CURRENT_TIMESTAMP - INTERVAL '3 days'),
  ('KNOWLEDGE', 'Data Partitioning Strategies', 'Strategies: (1) Range - by date/numeric, ideal for time-series, (2) List - by discrete values, (3) Hash - uniform distribution. PG native supports all three. Keep partitions under 100GB, use partition pruning.', 'Partitioning: Range (time-series), List (discrete values), Hash (uniform). PG native.', 'DATABASE', 'ACTIVE', 7, 'agent-foxtrot', 'agent-foxtrot', 'SHARED', (SELECT workspace_id FROM workspaces WHERE workspace_alias='devops'), 19, CURRENT_TIMESTAMP - INTERVAL '14 days', CURRENT_TIMESTAMP - INTERVAL '5 days'),
  ('KNOWLEDGE', 'Agent Coordination Protocols', 'Multi-agent coordination: (1) Centralized - single coordinator, (2) Decentralized - self-organize, (3) Hierarchical - tree of coordinators, (4) Market-based - agents bid. Consensus: Raft, Paxos. Conflict: CRDTs.', 'Agent coordination: Centralized, Decentralized, Hierarchical, Market-based. Consensus: Raft.', 'AI_ML', 'ACTIVE', 8, 'agent-bravo', 'agent-bravo', 'SHARED', (SELECT workspace_id FROM workspaces WHERE workspace_alias='proj-alpha'), 41, CURRENT_TIMESTAMP - INTERVAL '6 days', CURRENT_TIMESTAMP - INTERVAL '1 day')
ON CONFLICT DO NOTHING;

-- 4c. TASK_OUTPUT entities (5)
INSERT INTO entities (entity_type, title, content, summary, category, status, importance, owned_by_agent, source_agent, visibility, workspace_id, retrieval_count, created_at, updated_at)
VALUES
  ('TASK_OUTPUT', 'Code Review: Auth Module PR #247', 'Reviewed auth module changes. CRITICAL: Password hashing uses SHA-256 instead of bcrypt. MEDIUM: Session tokens not invalidated on password change. LOW: Missing rate limiting on login endpoint. Overall: REQUEST_CHANGES.', 'Auth module review: SHA-256 instead of bcrypt (critical), session invalidation missing.', 'CODE_REVIEW', 'ACTIVE', 9, 'agent-echo', 'agent-echo', 'SHARED', (SELECT workspace_id FROM workspaces WHERE workspace_alias='code-review'), 8, CURRENT_TIMESTAMP - INTERVAL '7 days', CURRENT_TIMESTAMP - INTERVAL '6 days'),
  ('TASK_OUTPUT', 'Integration Test Results: Sprint 14', 'Test suite: 847 tests, 839 passed, 5 failed, 3 skipped. Coverage: 83.2%. Failed tests include entity_search timeout, concurrent_workspace deadlock, large_embedding OOM.', 'Sprint 14 tests: 839/847 passed, 5 failed. 83.2% coverage.', 'TEST_RESULTS', 'ACTIVE', 7, 'agent-echo', 'agent-echo', 'SHARED', (SELECT workspace_id FROM workspaces WHERE workspace_alias='code-review'), 5, CURRENT_TIMESTAMP - INTERVAL '5 days', CURRENT_TIMESTAMP - INTERVAL '5 days'),
  ('TASK_OUTPUT', 'Data Pipeline Performance Benchmark', 'ETL v3.1 benchmark: Ingestion 12.5K records/sec. Transformation p50=45ms, p95=120ms, p99=340ms. Bottleneck: JSON parsing 40% CPU. Recommendation: simdjson for 3x speedup.', 'ETL benchmark: 12.5K rec/sec, p99=340ms. JSON parsing bottleneck, recommend simdjson.', 'BENCHMARK', 'ACTIVE', 6, 'agent-charlie', 'agent-charlie', 'SHARED', (SELECT workspace_id FROM workspaces WHERE workspace_alias='proj-beta'), 4, CURRENT_TIMESTAMP - INTERVAL '4 days', CURRENT_TIMESTAMP - INTERVAL '3 days'),
  ('TASK_OUTPUT', 'Security Scan Report: May 2026', 'SAST: 0 critical, 2 high (SQL injection, hardcoded API key), 12 medium, 23 low. DAST: 1 reflected XSS. SCA: 4 vulnerable packages. Remediate high findings within 48h.', 'Security scan: 0 critical, 2 high (SQL injection, hardcoded key), 1 XSS.', 'SECURITY_SCAN', 'ACTIVE', 8, 'agent-hotel', 'agent-hotel', 'SHARED', (SELECT workspace_id FROM workspaces WHERE workspace_alias='code-review'), 6, CURRENT_TIMESTAMP - INTERVAL '3 days', CURRENT_TIMESTAMP - INTERVAL '2 days'),
  ('TASK_OUTPUT', 'API Contract Test Results: v2.4.0', '156 endpoints tested. 148 conformant, 8 violations: wrong status codes, missing headers, incorrect error schema. All violations logged as P2 bugs.', 'API contract tests: 148/156 conformant. 8 violations: wrong status codes, missing headers.', 'TEST_RESULTS', 'ACTIVE', 6, 'agent-echo', 'agent-echo', 'SHARED', (SELECT workspace_id FROM workspaces WHERE workspace_alias='code-review'), 3, CURRENT_TIMESTAMP - INTERVAL '2 days', CURRENT_TIMESTAMP - INTERVAL '1 day')
ON CONFLICT DO NOTHING;

-- 4d. EXPERIENCE entities (5)
INSERT INTO entities (entity_type, title, content, summary, category, status, importance, owned_by_agent, source_agent, visibility, workspace_id, retrieval_count, created_at, updated_at)
VALUES
  ('EXPERIENCE', 'Incident Post-Mortem: Database Connection Pool Exhaustion', 'Date: 2026-04-15. Duration: 45min. Impact: 12% of requests failed with 503. Root cause: Connection pool set to 100 but app opened 120 concurrent connections during batch import. Fix: Increased pool to 200, added connection timeout with queue, implemented circuit breaker.', 'DB pool exhaustion: 45min outage, 12% failures. Fix: increase pool, add queue, circuit breaker.', 'INCIDENT', 'ACTIVE', 10, 'agent-golf', 'agent-golf', 'SHARED', (SELECT workspace_id FROM workspaces WHERE workspace_alias='devops'), 22, CURRENT_TIMESTAMP - INTERVAL '30 days', CURRENT_TIMESTAMP - INTERVAL '10 days'),
  ('EXPERIENCE', 'Lesson Learned: Premature Microservices Decomposition', 'Split monolith into 15 microservices too early. Result: distributed complexity without scale benefits. Network latency added 200ms. Debugging 10x harder. Team of 4 could not maintain 15 codebases. Resolution: Consolidated to 5 services.', 'Premature microservices: 15 services too many for team of 4. Consolidated to 5.', 'LESSON_LEARNED', 'ACTIVE', 9, 'agent-bravo', 'agent-bravo', 'SHARED', (SELECT workspace_id FROM workspaces WHERE workspace_alias='proj-alpha'), 31, CURRENT_TIMESTAMP - INTERVAL '25 days', CURRENT_TIMESTAMP - INTERVAL '7 days'),
  ('EXPERIENCE', 'Incident Post-Mortem: Vector Search Degradation', 'Date: 2026-05-03. Duration: 2 hours. Impact: Search relevance dropped 40%, latency increased 8x. Root cause: IVFFlat index not rebuilt after 50K bulk import. Fix: Switched to HNSW index, added index freshness monitoring.', 'Vector search degraded: stale IVFFlat index after bulk import. Switched to HNSW, added monitoring.', 'INCIDENT', 'ACTIVE', 9, 'agent-delta', 'agent-delta', 'SHARED', (SELECT workspace_id FROM workspaces WHERE workspace_alias='research'), 18, CURRENT_TIMESTAMP - INTERVAL '20 days', CURRENT_TIMESTAMP - INTERVAL '5 days'),
  ('EXPERIENCE', 'Lesson Learned: Over-Engineering Agent State Management', 'Built 23-state machine for agent lifecycle. Most agents only used 5 states. Resolution: Simplified to 6 core states (INIT, ACTIVE, PAUSED, ERROR, COMPLETED, TERMINATED) with extensible metadata.', 'Over-engineered 23-state machine. Simplified to 6 core states with extensible metadata.', 'LESSON_LEARNED', 'ACTIVE', 8, 'agent-alpha', 'agent-alpha', 'SHARED', (SELECT workspace_id FROM workspaces WHERE workspace_alias='proj-alpha'), 15, CURRENT_TIMESTAMP - INTERVAL '18 days', CURRENT_TIMESTAMP - INTERVAL '8 days'),
  ('EXPERIENCE', 'Incident Post-Mortem: Cascading Agent Failure', 'Date: 2026-05-20. Duration: 90min. Impact: 3 of 6 worker agents unresponsive. Root cause: coordinator memory leak in task routing. Workers entered infinite retry loop. Fix: Fixed leak, added retry budget, health checks with auto-restart.', 'Cascading failure: coordinator memory leak caused worker infinite retries. Added retry budget, health checks.', 'INCIDENT', 'ACTIVE', 10, 'agent-bravo', 'agent-bravo', 'SHARED', (SELECT workspace_id FROM workspaces WHERE workspace_alias='proj-alpha'), 25, CURRENT_TIMESTAMP - INTERVAL '10 days', CURRENT_TIMESTAMP - INTERVAL '2 days')
ON CONFLICT DO NOTHING;

-- 4e. HARNESS_TEMPLATE entities (5)
INSERT INTO entities (entity_type, title, content, summary, category, status, importance, owned_by_agent, source_agent, visibility, workspace_id, retrieval_count, created_at, updated_at)
VALUES
  ('HARNESS_TEMPLATE', 'Code Review Harness', 'Automated code review: (1) Checkout PR, (2) Run linter, (3) Type check, (4) Unit tests with coverage, (5) SAST scan, (6) Generate review summary. Timeout: 10 minutes per step.', 'Automated code review: lint, type check, unit test, SAST, review summary. 10min timeout.', 'AUTOMATION', 'ACTIVE', 8, 'agent-echo', 'agent-echo', 'SHARED', (SELECT workspace_id FROM workspaces WHERE workspace_alias='code-review'), 16, CURRENT_TIMESTAMP - INTERVAL '12 days', CURRENT_TIMESTAMP - INTERVAL '2 days'),
  ('HARNESS_TEMPLATE', 'Data Ingestion Pipeline Harness', 'Data ingestion: (1) Validate input schema, (2) Parse and transform, (3) Deduplicate, (4) Batch write (1000), (5) Verify record count, (6) Generate report. Supports CSV, JSON, Parquet.', 'Data ingestion: validate, parse, dedup, batch write (1000), verify, report. CSV/JSON/Parquet.', 'DATA_PIPELINE', 'ACTIVE', 7, 'agent-charlie', 'agent-charlie', 'SHARED', (SELECT workspace_id FROM workspaces WHERE workspace_alias='proj-beta'), 12, CURRENT_TIMESTAMP - INTERVAL '10 days', CURRENT_TIMESTAMP - INTERVAL '3 days'),
  ('HARNESS_TEMPLATE', 'Security Scan Harness', 'Comprehensive scanning: (1) SAST via Semgrep, (2) Deps via Snyk, (3) Container via Trivy, (4) Secrets via Gitleaks, (5) Consolidated report. Block deployment on critical/high.', 'Security scan: SAST (Semgrep), deps (Snyk), container (Trivy), secrets (Gitleaks). Block on critical.', 'SECURITY', 'ACTIVE', 9, 'agent-hotel', 'agent-hotel', 'SHARED', (SELECT workspace_id FROM workspaces WHERE workspace_alias='code-review'), 14, CURRENT_TIMESTAMP - INTERVAL '8 days', CURRENT_TIMESTAMP - INTERVAL '1 day'),
  ('HARNESS_TEMPLATE', 'Deployment Verification Harness', 'Post-deploy verification: (1) Health check, (2) Smoke tests, (3) Migration check, (4) Cache warming, (5) Monitor error rates 10min, (6) Validate feature flags. Auto-rollback on failure.', 'Deploy verification: health check, smoke test, migration, cache, error monitor, auto-rollback.', 'DEPLOYMENT', 'ACTIVE', 8, 'agent-foxtrot', 'agent-foxtrot', 'SHARED', (SELECT workspace_id FROM workspaces WHERE workspace_alias='devops'), 20, CURRENT_TIMESTAMP - INTERVAL '6 days', CURRENT_TIMESTAMP - INTERVAL '1 day'),
  ('HARNESS_TEMPLATE', 'Knowledge Extraction Harness', 'Knowledge extraction: (1) Load document, (2) Chunk text (512 tokens, 50 overlap), (3) Generate embeddings, (4) Store vectors, (5) Extract entities and relations, (6) Create graph edges, (7) Generate summary.', 'Knowledge extraction: chunk, embed, store vector, extract entities/relations, graph edges.', 'AI_ML', 'ACTIVE', 7, 'agent-delta', 'agent-delta', 'SHARED', (SELECT workspace_id FROM workspaces WHERE workspace_alias='research'), 9, CURRENT_TIMESTAMP - INTERVAL '5 days', CURRENT_TIMESTAMP - INTERVAL '2 days')
ON CONFLICT DO NOTHING;

-- 4f. SPEC entities (5)
INSERT INTO entities (entity_type, title, content, summary, category, status, importance, owned_by_agent, source_agent, visibility, workspace_id, retrieval_count, created_at, updated_at)
VALUES
  ('SPEC', 'Entity Search API Specification', 'API spec: POST /v1/entities/search. Request: query, filters, pagination, sort. Response: results, total_count, facets. Full-text, vector similarity, and hybrid search. Latency SLA: p99 < 500ms.', 'Entity search API: POST /v1/entities/search. Full-text, vector, hybrid search. p99 < 500ms.', 'API_SPEC', 'ACTIVE', 9, 'agent-alpha', 'agent-bravo', 'SHARED', (SELECT workspace_id FROM workspaces WHERE workspace_alias='proj-alpha'), 28, CURRENT_TIMESTAMP - INTERVAL '20 days', CURRENT_TIMESTAMP - INTERVAL '3 days'),
  ('SPEC', 'Agent Credential Management Specification', 'Credential lifecycle: Create, Rotate, Revoke, Audit. AES-256 encrypted at rest. Support OAuth2 tokens, API keys, certificates. TTL: default 90 days. Per-agent and per-workspace scope.', 'Credential spec: create, rotate, revoke, audit. AES-256. OAuth2/API key/cert. 90-day TTL.', 'SECURITY_SPEC', 'ACTIVE', 9, 'agent-hotel', 'agent-hotel', 'SHARED', (SELECT workspace_id FROM workspaces WHERE workspace_alias='proj-alpha'), 22, CURRENT_TIMESTAMP - INTERVAL '15 days', CURRENT_TIMESTAMP - INTERVAL '4 days'),
  ('SPEC', 'Workspace Isolation Specification', 'Isolation levels: SHARED, ISOLATED, SANDBOX. Cross-workspace access requires explicit permission. Audit trail for all cross-workspace operations.', 'Workspace isolation: SHARED, ISOLATED, SANDBOX. Cross-workspace needs permission. Audit all.', 'ARCHITECTURE_SPEC', 'ACTIVE', 8, 'agent-bravo', 'agent-bravo', 'SHARED', (SELECT workspace_id FROM workspaces WHERE workspace_alias='proj-alpha'), 17, CURRENT_TIMESTAMP - INTERVAL '12 days', CURRENT_TIMESTAMP - INTERVAL '5 days'),
  ('SPEC', 'Entity Versioning Specification', 'Versioning: immutable entity versions. ETag-based optimistic locking. Three-way merge for concurrent edits. Full history accessible. 90-day retention.', 'Entity versioning: immutable versions, ETag optimistic locking, three-way merge, 90-day retention.', 'DATA_SPEC', 'ACTIVE', 7, 'agent-alpha', 'agent-alpha', 'SHARED', (SELECT workspace_id FROM workspaces WHERE workspace_alias='proj-alpha'), 13, CURRENT_TIMESTAMP - INTERVAL '10 days', CURRENT_TIMESTAMP - INTERVAL '6 days'),
  ('SPEC', 'Real-time Event Notification Specification', 'Event bus: WebSocket connections for agents. Event types: ENTITY_CREATED, ENTITY_UPDATED, TASK_STATUS_CHANGED, AGENT_JOINED, AGENT_LEFT. At-least-once delivery. Per-entity ordering. Backpressure: drop oldest if buffer > 10K.', 'Event bus: WebSocket, 5 event types, at-least-once delivery, per-entity ordering, 10K buffer.', 'ARCHITECTURE_SPEC', 'ACTIVE', 7, 'agent-bravo', 'agent-bravo', 'SHARED', (SELECT workspace_id FROM workspaces WHERE workspace_alias='proj-alpha'), 11, CURRENT_TIMESTAMP - INTERVAL '8 days', CURRENT_TIMESTAMP - INTERVAL '2 days')
ON CONFLICT DO NOTHING;

-- 4g. SKILL entities (5)
INSERT INTO entities (entity_type, title, content, summary, category, status, importance, owned_by_agent, source_agent, visibility, workspace_id, retrieval_count, created_at, updated_at)
VALUES
  ('SKILL', 'Web Search and Synthesis', 'Search web and synthesize: (1) Formulate queries from intent, (2) Parallel search across engines, (3) Rank/filter, (4) Extract key info, (5) Synthesize with citations. Rate: 10 searches/min.', 'Web search: formulate queries, parallel search, rank/filter, extract, synthesize with citations.', 'RETRIEVAL', 'ACTIVE', 7, 'agent-delta', 'agent-delta', 'SHARED', (SELECT workspace_id FROM workspaces WHERE workspace_alias='research'), 33, CURRENT_TIMESTAMP - INTERVAL '18 days', CURRENT_TIMESTAMP - INTERVAL '2 days'),
  ('SKILL', 'Code Generation and Refactoring', 'Code gen/refactor: (1) Generate boilerplate from specs, (2) Refactor following SOLID, (3) Add error handling, (4) Generate unit tests, (5) Optimize bottlenecks. Supports TS, Python, Java, Go.', 'Code gen/refactor: boilerplate, SOLID refactor, error handling, tests, optimization. TS/Py/Java/Go.', 'DEVELOPMENT', 'ACTIVE', 8, 'agent-alpha', 'agent-alpha', 'SHARED', (SELECT workspace_id FROM workspaces WHERE workspace_alias='proj-alpha'), 47, CURRENT_TIMESTAMP - INTERVAL '15 days', CURRENT_TIMESTAMP - INTERVAL '1 day'),
  ('SKILL', 'Data Analysis and Visualization', 'Data analysis: (1) Profile dataset, (2) Identify patterns, (3) Statistical summaries, (4) Visualizations (charts, dashboards), (5) Narrative report. Supports CSV, Parquet, DB queries.', 'Data analysis: profile, patterns, stats, visualizations, narrative report. CSV/Parquet/DB.', 'ANALYTICS', 'ACTIVE', 7, 'agent-charlie', 'agent-charlie', 'SHARED', (SELECT workspace_id FROM workspaces WHERE workspace_alias='proj-beta'), 25, CURRENT_TIMESTAMP - INTERVAL '12 days', CURRENT_TIMESTAMP - INTERVAL '3 days'),
  ('SKILL', 'Infrastructure Automation', 'Infra automation: (1) Provision cloud resources, (2) Configure networking, (3) Deploy containers/K8s, (4) Set up monitoring, (5) Manage secrets. Safety: dry-run default, approval for prod.', 'Infra automation: provision, configure, deploy K8s, monitoring, secrets. Dry-run default.', 'INFRASTRUCTURE', 'ACTIVE', 8, 'agent-foxtrot', 'agent-foxtrot', 'SHARED', (SELECT workspace_id FROM workspaces WHERE workspace_alias='devops'), 19, CURRENT_TIMESTAMP - INTERVAL '9 days', CURRENT_TIMESTAMP - INTERVAL '2 days'),
  ('SKILL', 'Security Assessment and Remediation', 'Security assessment: (1) SAST/DAST/SCA scan, (2) CIS benchmark compliance, (3) Access control review, (4) Remediation plan with priority, (5) Track progress. OWASP Top 10, CWE, CVE.', 'Security assessment: SAST/DAST/SCA, CIS benchmarks, access review, remediation tracking.', 'SECURITY', 'ACTIVE', 8, 'agent-hotel', 'agent-hotel', 'SHARED', (SELECT workspace_id FROM workspaces WHERE workspace_alias='proj-alpha'), 21, CURRENT_TIMESTAMP - INTERVAL '7 days', CURRENT_TIMESTAMP - INTERVAL '1 day')
ON CONFLICT DO NOTHING;

-- ============================================================================
-- 5. KNOWLEDGE_META
-- ============================================================================
INSERT INTO knowledge_meta (entity_id, entity_type, domain, topic, difficulty, review_count, last_reviewed, next_review)
SELECT e.entity_id, e.entity_type,
  CASE e.title WHEN 'Retrieval-Augmented Generation (RAG)' THEN 'Artificial Intelligence' WHEN 'Event-Driven Architecture Patterns' THEN 'Software Architecture' WHEN 'PostgreSQL Performance Tuning Best Practices' THEN 'Database Engineering' WHEN 'Microservices Communication Patterns' THEN 'Software Architecture' WHEN 'Vector Embedding Optimization' THEN 'Artificial Intelligence' WHEN 'CI/CD Pipeline Design Principles' THEN 'DevOps' WHEN 'OAuth 2.0 and JWT Security Best Practices' THEN 'Security' WHEN 'Observability Trinity: Logs, Metrics, Traces' THEN 'Site Reliability' WHEN 'Data Partitioning Strategies' THEN 'Database Engineering' WHEN 'Agent Coordination Protocols' THEN 'Artificial Intelligence' END,
  CASE e.title WHEN 'Retrieval-Augmented Generation (RAG)' THEN 'Information Retrieval' WHEN 'Event-Driven Architecture Patterns' THEN 'Event Sourcing' WHEN 'PostgreSQL Performance Tuning Best Practices' THEN 'Query Optimization' WHEN 'Microservices Communication Patterns' THEN 'Service Mesh' WHEN 'Vector Embedding Optimization' THEN 'Approximate Nearest Neighbor' WHEN 'CI/CD Pipeline Design Principles' THEN 'Continuous Delivery' WHEN 'OAuth 2.0 and JWT Security Best Practices' THEN 'Authentication' WHEN 'Observability Trinity: Logs, Metrics, Traces' THEN 'Distributed Tracing' WHEN 'Data Partitioning Strategies' THEN 'Table Partitioning' WHEN 'Agent Coordination Protocols' THEN 'Multi-Agent Systems' END,
  CASE e.title WHEN 'Retrieval-Augmented Generation (RAG)' THEN 'INTERMEDIATE' WHEN 'Event-Driven Architecture Patterns' THEN 'ADVANCED' WHEN 'PostgreSQL Performance Tuning Best Practices' THEN 'ADVANCED' WHEN 'Microservices Communication Patterns' THEN 'INTERMEDIATE' WHEN 'Vector Embedding Optimization' THEN 'ADVANCED' WHEN 'CI/CD Pipeline Design Principles' THEN 'INTERMEDIATE' WHEN 'OAuth 2.0 and JWT Security Best Practices' THEN 'ADVANCED' WHEN 'Observability Trinity: Logs, Metrics, Traces' THEN 'INTERMEDIATE' WHEN 'Data Partitioning Strategies' THEN 'INTERMEDIATE' WHEN 'Agent Coordination Protocols' THEN 'ADVANCED' END,
  CASE e.title WHEN 'Retrieval-Augmented Generation (RAG)' THEN 5 WHEN 'Event-Driven Architecture Patterns' THEN 3 WHEN 'PostgreSQL Performance Tuning Best Practices' THEN 4 WHEN 'Microservices Communication Patterns' THEN 2 WHEN 'Vector Embedding Optimization' THEN 6 WHEN 'CI/CD Pipeline Design Principles' THEN 3 WHEN 'OAuth 2.0 and JWT Security Best Practices' THEN 4 WHEN 'Observability Trinity: Logs, Metrics, Traces' THEN 2 WHEN 'Data Partitioning Strategies' THEN 3 WHEN 'Agent Coordination Protocols' THEN 7 END,
  CASE e.title WHEN 'Retrieval-Augmented Generation (RAG)' THEN CURRENT_TIMESTAMP - INTERVAL '1 day' WHEN 'Event-Driven Architecture Patterns' THEN CURRENT_TIMESTAMP - INTERVAL '3 days' WHEN 'PostgreSQL Performance Tuning Best Practices' THEN CURRENT_TIMESTAMP - INTERVAL '5 days' WHEN 'Microservices Communication Patterns' THEN CURRENT_TIMESTAMP - INTERVAL '6 days' WHEN 'Vector Embedding Optimization' THEN CURRENT_TIMESTAMP - INTERVAL '2 days' WHEN 'CI/CD Pipeline Design Principles' THEN CURRENT_TIMESTAMP - INTERVAL '4 days' WHEN 'OAuth 2.0 and JWT Security Best Practices' THEN CURRENT_TIMESTAMP - INTERVAL '1 day' WHEN 'Observability Trinity: Logs, Metrics, Traces' THEN CURRENT_TIMESTAMP - INTERVAL '3 days' WHEN 'Data Partitioning Strategies' THEN CURRENT_TIMESTAMP - INTERVAL '5 days' WHEN 'Agent Coordination Protocols' THEN CURRENT_TIMESTAMP - INTERVAL '1 day' END,
  CASE e.title WHEN 'Retrieval-Augmented Generation (RAG)' THEN CURRENT_TIMESTAMP + INTERVAL '14 days' WHEN 'Event-Driven Architecture Patterns' THEN CURRENT_TIMESTAMP + INTERVAL '27 days' WHEN 'PostgreSQL Performance Tuning Best Practices' THEN CURRENT_TIMESTAMP + INTERVAL '25 days' WHEN 'Microservices Communication Patterns' THEN CURRENT_TIMESTAMP + INTERVAL '24 days' WHEN 'Vector Embedding Optimization' THEN CURRENT_TIMESTAMP + INTERVAL '12 days' WHEN 'CI/CD Pipeline Design Principles' THEN CURRENT_TIMESTAMP + INTERVAL '26 days' WHEN 'OAuth 2.0 and JWT Security Best Practices' THEN CURRENT_TIMESTAMP + INTERVAL '14 days' WHEN 'Observability Trinity: Logs, Metrics, Traces' THEN CURRENT_TIMESTAMP + INTERVAL '27 days' WHEN 'Data Partitioning Strategies' THEN CURRENT_TIMESTAMP + INTERVAL '25 days' WHEN 'Agent Coordination Protocols' THEN CURRENT_TIMESTAMP + INTERVAL '13 days' END
FROM entities e
WHERE e.entity_type = 'KNOWLEDGE'
  AND e.title IN ('Retrieval-Augmented Generation (RAG)','Event-Driven Architecture Patterns','PostgreSQL Performance Tuning Best Practices','Microservices Communication Patterns','Vector Embedding Optimization','CI/CD Pipeline Design Principles','OAuth 2.0 and JWT Security Best Practices','Observability Trinity: Logs, Metrics, Traces','Data Partitioning Strategies','Agent Coordination Protocols')
ON CONFLICT DO NOTHING;

-- ============================================================================
-- 6. HARNESS_META
-- ============================================================================
INSERT INTO harness_meta (entity_id, entity_type, template_version, input_schema, output_schema, execution_mode)
SELECT e.entity_id, e.entity_type,
  CASE e.title WHEN 'Code Review Harness' THEN '2.1.0' WHEN 'Data Ingestion Pipeline Harness' THEN '1.4.0' WHEN 'Security Scan Harness' THEN '3.0.0' WHEN 'Deployment Verification Harness' THEN '2.0.0' WHEN 'Knowledge Extraction Harness' THEN '1.2.0' END,
  CASE e.title WHEN 'Code Review Harness' THEN '{"type":"object","properties":{"pr_url":{"type":"string"},"timeout_minutes":{"type":"integer","default":10}}}'::jsonb WHEN 'Data Ingestion Pipeline Harness' THEN '{"type":"object","properties":{"source_uri":{"type":"string"},"format":{"type":"string","enum":["csv","json","parquet"]},"batch_size":{"type":"integer","default":1000}}}'::jsonb WHEN 'Security Scan Harness' THEN '{"type":"object","properties":{"repo_path":{"type":"string"},"scan_types":{"type":"array"},"block_on_high":{"type":"boolean"}}}'::jsonb WHEN 'Deployment Verification Harness' THEN '{"type":"object","properties":{"service_name":{"type":"string"},"environment":{"type":"string","enum":["staging","production"]}}}'::jsonb WHEN 'Knowledge Extraction Harness' THEN '{"type":"object","properties":{"document_uri":{"type":"string"},"chunk_size":{"type":"integer","default":512}}}'::jsonb END,
  CASE e.title WHEN 'Code Review Harness' THEN '{"type":"object","properties":{"findings":{"type":"array"},"coverage_percent":{"type":"number"},"recommendation":{"type":"string"}}}'::jsonb WHEN 'Data Ingestion Pipeline Harness' THEN '{"type":"object","properties":{"records_processed":{"type":"integer"},"errors":{"type":"integer"}}}'::jsonb WHEN 'Security Scan Harness' THEN '{"type":"object","properties":{"critical_count":{"type":"integer"},"high_count":{"type":"integer"},"blocked":{"type":"boolean"}}}'::jsonb WHEN 'Deployment Verification Harness' THEN '{"type":"object","properties":{"health_status":{"type":"string"},"rollback_triggered":{"type":"boolean"}}}'::jsonb WHEN 'Knowledge Extraction Harness' THEN '{"type":"object","properties":{"chunks_created":{"type":"integer"},"summary":{"type":"string"}}}'::jsonb END,
  CASE e.title WHEN 'Code Review Harness' THEN 'SEQUENTIAL' WHEN 'Data Ingestion Pipeline Harness' THEN 'PARALLEL' WHEN 'Security Scan Harness' THEN 'PARALLEL' WHEN 'Deployment Verification Harness' THEN 'SEQUENTIAL' WHEN 'Knowledge Extraction Harness' THEN 'SEQUENTIAL' END
FROM entities e
WHERE e.entity_type = 'HARNESS_TEMPLATE'
  AND e.title IN ('Code Review Harness','Data Ingestion Pipeline Harness','Security Scan Harness','Deployment Verification Harness','Knowledge Extraction Harness')
ON CONFLICT DO NOTHING;

-- ============================================================================
-- 7. SPEC_META
-- ============================================================================
INSERT INTO spec_meta (entity_id, entity_type, spec_version, spec_status, acceptance_criteria, spec_constraints, spec_scope, complexity, parent_spec_id)
SELECT e.entity_id, e.entity_type,
  CASE e.title WHEN 'Entity Search API Specification' THEN 3 WHEN 'Agent Credential Management Specification' THEN 2 WHEN 'Workspace Isolation Specification' THEN 1 WHEN 'Entity Versioning Specification' THEN 2 WHEN 'Real-time Event Notification Specification' THEN 1 END,
  CASE e.title WHEN 'Entity Search API Specification' THEN 'APPROVED' WHEN 'Agent Credential Management Specification' THEN 'REVIEWED' WHEN 'Workspace Isolation Specification' THEN 'APPROVED' WHEN 'Entity Versioning Specification' THEN 'DRAFT' WHEN 'Real-time Event Notification Specification' THEN 'DRAFT' END,
  CASE e.title WHEN 'Entity Search API Specification' THEN '{"latency_p99_ms":500,"max_results":1000,"support_hybrid_search":true}'::jsonb WHEN 'Agent Credential Management Specification' THEN '{"rotation_zero_downtime":true,"encryption_at_rest":"AES-256","max_ttl_days":90}'::jsonb WHEN 'Workspace Isolation Specification' THEN '{"no_implicit_cross_workspace_access":true,"audit_cross_workspace_ops":true}'::jsonb WHEN 'Entity Versioning Specification' THEN '{"immutable_versions":true,"three_way_merge":true}'::jsonb WHEN 'Real-time Event Notification Specification' THEN '{"delivery_guarantee":"at_least_once","max_buffer_size":10000}'::jsonb END,
  CASE e.title WHEN 'Entity Search API Specification' THEN '{"max_query_length":1000,"rate_limit_per_agent":100}'::jsonb WHEN 'Agent Credential Management Specification' THEN '{"max_credentials_per_agent":50}'::jsonb WHEN 'Workspace Isolation Specification' THEN '{"max_workspaces_per_agent":10}'::jsonb WHEN 'Entity Versioning Specification' THEN '{"max_versions_per_entity":1000}'::jsonb WHEN 'Real-time Event Notification Specification' THEN '{"max_subscriptions_per_agent":100}'::jsonb END,
  CASE e.title WHEN 'Entity Search API Specification' THEN 'GLOBAL' WHEN 'Agent Credential Management Specification' THEN 'GLOBAL' WHEN 'Workspace Isolation Specification' THEN 'WORKSPACE' WHEN 'Entity Versioning Specification' THEN 'ENTITY' WHEN 'Real-time Event Notification Specification' THEN 'GLOBAL' END,
  CASE e.title WHEN 'Entity Search API Specification' THEN 'HIGH' WHEN 'Agent Credential Management Specification' THEN 'HIGH' WHEN 'Workspace Isolation Specification' THEN 'MEDIUM' WHEN 'Entity Versioning Specification' THEN 'MEDIUM' WHEN 'Real-time Event Notification Specification' THEN 'HIGH' END,
  NULL
FROM entities e
WHERE e.entity_type = 'SPEC'
  AND e.title IN ('Entity Search API Specification','Agent Credential Management Specification','Workspace Isolation Specification','Entity Versioning Specification','Real-time Event Notification Specification')
ON CONFLICT DO NOTHING;

-- ============================================================================
-- 8. SKILL_META (v4.0.1 entity extension contract)
-- ============================================================================
INSERT INTO skill_meta (
  entity_id, entity_type, skill_name, skill_version, skill_type, skill_format,
  text_content, resource_uri, dependencies, skill_status, skill_description
)
SELECT e.entity_id,
  'SKILL',
  e.title,
  CASE e.title WHEN 'Web Search and Synthesis' THEN '2.3.0' WHEN 'Code Generation and Refactoring' THEN '3.1.0' WHEN 'Data Analysis and Visualization' THEN '1.8.0' WHEN 'Infrastructure Automation' THEN '2.0.0' WHEN 'Security Assessment and Remediation' THEN '1.5.0' END,
  'BUILTIN',
  'TEXT',
  e.content,
  CASE e.title WHEN 'Web Search and Synthesis' THEN '/skills/retrieval/web-search/v2.3.0' WHEN 'Code Generation and Refactoring' THEN '/skills/development/code-gen/v3.1.0' WHEN 'Data Analysis and Visualization' THEN '/skills/analytics/data-viz/v1.8.0' WHEN 'Infrastructure Automation' THEN '/skills/infra/automation/v2.0.0' WHEN 'Security Assessment and Remediation' THEN '/skills/security/assessment/v1.5.0' END,
  CASE e.title WHEN 'Web Search and Synthesis' THEN '{"deps":["http_client","html_parser"]}'::jsonb WHEN 'Code Generation and Refactoring' THEN '{"deps":["code_parser","linter"]}'::jsonb WHEN 'Data Analysis and Visualization' THEN '{"deps":["data_connector"]}'::jsonb WHEN 'Infrastructure Automation' THEN '{"deps":["cloud_sdk","kubernetes_client"]}'::jsonb WHEN 'Security Assessment and Remediation' THEN '{"deps":["semgrep","trivy"]}'::jsonb END,
  'ACTIVE',
  e.summary
FROM entities e
WHERE e.entity_type = 'SKILL'
  AND e.title IN ('Web Search and Synthesis','Code Generation and Refactoring','Data Analysis and Visualization','Infrastructure Automation','Security Assessment and Remediation')
ON CONFLICT DO NOTHING;

-- ============================================================================
-- 9. CONTEXT BRANCHES (5 branches)
-- ============================================================================
INSERT INTO context_branches (workspace_id, parent_branch_id, branch_name, branch_type, status, source_context_id, agent_id, created_at, description, is_lesson, lesson_tags)
VALUES
  ((SELECT workspace_id FROM workspaces WHERE workspace_alias='proj-alpha'), NULL, 'main',                'FORK',       'ACTIVE',   NULL, 'agent-bravo',   CURRENT_TIMESTAMP - INTERVAL '30 days', 'Main development branch for Project Alpha',     false, NULL),
  ((SELECT workspace_id FROM workspaces WHERE workspace_alias='proj-alpha'), (SELECT branch_id FROM context_branches WHERE branch_name='main' AND workspace_id=(SELECT workspace_id FROM workspaces WHERE workspace_alias='proj-alpha')), 'feature/auth-v2', 'EXPLORATION','MERGED',   NULL, 'agent-alpha',   CURRENT_TIMESTAMP - INTERVAL '20 days', 'Auth module v2 exploration branch',             true,  '{"tags":["authentication","security"]}'::jsonb),
  ((SELECT workspace_id FROM workspaces WHERE workspace_alias='proj-beta'),  NULL, 'main',                'FORK',       'ACTIVE',   NULL, 'agent-charlie',  CURRENT_TIMESTAMP - INTERVAL '25 days', 'Main branch for Project Beta',                  false, NULL),
  ((SELECT workspace_id FROM workspaces WHERE workspace_alias='research'),   NULL, 'main',                'FORK',       'ACTIVE',   NULL, 'agent-delta',    CURRENT_TIMESTAMP - INTERVAL '20 days', 'Main branch for Research Lab',                  false, NULL),
  ((SELECT workspace_id FROM workspaces WHERE workspace_alias='research'),   (SELECT branch_id FROM context_branches WHERE branch_name='main' AND workspace_id=(SELECT workspace_id FROM workspaces WHERE workspace_alias='research')), 'experiment/rag-v2', 'EXPLORATION','ABANDONED',NULL, 'agent-delta',    CURRENT_TIMESTAMP - INTERVAL '10 days', 'RAG v2 experiment - abandoned in favor of v3',  true,  '{"tags":["rag","experiment"]}'::jsonb),
  ((SELECT workspace_id FROM workspaces WHERE workspace_alias='code-review'),NULL, 'main',                'FORK',       'ACTIVE',   NULL, 'agent-echo',     CURRENT_TIMESTAMP - INTERVAL '14 days', 'Main branch for Code Review',                   false, NULL),
  ((SELECT workspace_id FROM workspaces WHERE workspace_alias='devops'),     NULL, 'main',                'FORK',       'ACTIVE',   NULL, 'agent-foxtrot',  CURRENT_TIMESTAMP - INTERVAL '10 days', 'Main branch for DevOps Pipeline',               false, NULL)
ON CONFLICT DO NOTHING;

-- ============================================================================
-- 10. WORKSPACE_CONTEXT (12 contexts)
-- ============================================================================
INSERT INTO workspace_context (workspace_id, agent_id, context_type, context_data, parent_context_id, branch_id, visibility, created_at)
VALUES
  ((SELECT workspace_id FROM workspaces WHERE workspace_alias='proj-alpha'), 'agent-bravo',   'SUMMARY',      '{"project":"Project Alpha","status":"on_track","sprint":"Sprint 14","velocity":42}'::jsonb,                                                                                                    NULL, (SELECT branch_id FROM context_branches WHERE branch_name='main' AND workspace_id=(SELECT workspace_id FROM workspaces WHERE workspace_alias='proj-alpha')), 'SHARED', CURRENT_TIMESTAMP - INTERVAL '28 days'),
  ((SELECT workspace_id FROM workspaces WHERE workspace_alias='proj-alpha'), 'agent-alpha',   'CHECKPOINT',   '{"decision":"Use hexagonal architecture","rationale":"Clean domain separation","alternatives_considered":["layered","microkernel"],"consensus":true}'::jsonb,       1,    (SELECT branch_id FROM context_branches WHERE branch_name='main' AND workspace_id=(SELECT workspace_id FROM workspaces WHERE workspace_alias='proj-alpha')), 'SHARED', CURRENT_TIMESTAMP - INTERVAL '26 days'),
  ((SELECT workspace_id FROM workspaces WHERE workspace_alias='proj-alpha'), 'agent-echo',    'CHECKPOINT',   '{"item":"Complete auth module v2","assignee":"agent-alpha","priority":"HIGH","due_date":"2026-06-20"}'::jsonb,                                                            1,    (SELECT branch_id FROM context_branches WHERE branch_name='main' AND workspace_id=(SELECT workspace_id FROM workspaces WHERE workspace_alias='proj-alpha')), 'SHARED', CURRENT_TIMESTAMP - INTERVAL '22 days'),
  ((SELECT workspace_id FROM workspaces WHERE workspace_alias='proj-alpha'), 'agent-bravo',   'BRANCH_POINT','{"decision":"Adopt event sourcing for audit trail","rationale":"Regulatory compliance","decided_by":"agent-bravo"}'::jsonb,                                                   1,    (SELECT branch_id FROM context_branches WHERE branch_name='main' AND workspace_id=(SELECT workspace_id FROM workspaces WHERE workspace_alias='proj-alpha')), 'SHARED', CURRENT_TIMESTAMP - INTERVAL '24 days'),
  ((SELECT workspace_id FROM workspaces WHERE workspace_alias='proj-beta'),  'agent-charlie', 'SUMMARY',      '{"project":"Project Beta","status":"at_risk","pipeline_completion":80,"performance_target":"12K records/sec","current_performance":"8.5K records/sec"}'::jsonb,    NULL, (SELECT branch_id FROM context_branches WHERE branch_name='main' AND workspace_id=(SELECT workspace_id FROM workspaces WHERE workspace_alias='proj-beta')),  'SHARED', CURRENT_TIMESTAMP - INTERVAL '23 days'),
  ((SELECT workspace_id FROM workspaces WHERE workspace_alias='proj-beta'),  'agent-charlie', 'CHECKPOINT',   '{"item":"Optimize JSON parsing in ETL pipeline","assignee":"agent-charlie","priority":"CRITICAL","approach":"Evaluate simdjson"}'::jsonb,                                      5,    (SELECT branch_id FROM context_branches WHERE branch_name='main' AND workspace_id=(SELECT workspace_id FROM workspaces WHERE workspace_alias='proj-beta')),  'SHARED', CURRENT_TIMESTAMP - INTERVAL '21 days'),
  ((SELECT workspace_id FROM workspaces WHERE workspace_alias='proj-beta'),  'agent-charlie', 'BRANCH_POINT','{"decision":"Switch to simdjson","rationale":"3x performance improvement","decided_by":"agent-charlie"}'::jsonb,                                                          5,    (SELECT branch_id FROM context_branches WHERE branch_name='main' AND workspace_id=(SELECT workspace_id FROM workspaces WHERE workspace_alias='proj-beta')),  'SHARED', CURRENT_TIMESTAMP - INTERVAL '18 days'),
  ((SELECT workspace_id FROM workspaces WHERE workspace_alias='research'),   'agent-delta',   'SUMMARY',      '{"project":"Research Lab","status":"active","current_experiments":["RAG optimization","embedding quantization"],"publications":2}'::jsonb,                                        NULL, (SELECT branch_id FROM context_branches WHERE branch_name='main' AND workspace_id=(SELECT workspace_id FROM workspaces WHERE workspace_alias='research')),   'SHARED', CURRENT_TIMESTAMP - INTERVAL '19 days'),
  ((SELECT workspace_id FROM workspaces WHERE workspace_alias='code-review'),'agent-echo',    'SUMMARY',      '{"project":"Code Review","status":"active","reviews_completed":156,"avg_review_time":"4.2 hours","critical_findings":3}'::jsonb,                                               NULL, (SELECT branch_id FROM context_branches WHERE branch_name='main' AND workspace_id=(SELECT workspace_id FROM workspaces WHERE workspace_alias='code-review')), 'SHARED', CURRENT_TIMESTAMP - INTERVAL '13 days'),
  ((SELECT workspace_id FROM workspaces WHERE workspace_alias='code-review'),'agent-echo',    'CHECKPOINT',   '{"item":"Review payment service PR #312","assignee":"agent-echo","priority":"CRITICAL","required_approvers":2}'::jsonb,                                                          NULL, (SELECT branch_id FROM context_branches WHERE branch_name='main' AND workspace_id=(SELECT workspace_id FROM workspaces WHERE workspace_alias='code-review')), 'SHARED', CURRENT_TIMESTAMP - INTERVAL '5 days'),
  ((SELECT workspace_id FROM workspaces WHERE workspace_alias='devops'),     'agent-foxtrot', 'SUMMARY',      '{"project":"DevOps Pipeline","status":"active","deployments_this_week":12,"rollback_rate":"8.3%","mean_deploy_time":"18 minutes"}'::jsonb,                                       NULL, (SELECT branch_id FROM context_branches WHERE branch_name='main' AND workspace_id=(SELECT workspace_id FROM workspaces WHERE workspace_alias='devops')),     'SHARED', CURRENT_TIMESTAMP - INTERVAL '9 days'),
  ((SELECT workspace_id FROM workspaces WHERE workspace_alias='devops'),     'agent-foxtrot', 'CHECKPOINT',   '{"item":"Set up canary deployment for v2.4","assignee":"agent-foxtrot","priority":"HIGH","canary_percentage":5}'::jsonb,                                                           NULL, (SELECT branch_id FROM context_branches WHERE branch_name='main' AND workspace_id=(SELECT workspace_id FROM workspaces WHERE workspace_alias='devops')),     'SHARED', CURRENT_TIMESTAMP - INTERVAL '3 days')
ON CONFLICT DO NOTHING;

-- ============================================================================
-- 11. ENTITY_EDGES (35 edges)
-- ============================================================================

-- DERIVED_FROM edges
INSERT INTO entity_edges (source_id, source_type, target_id, target_type, edge_type, strength, confidence, metadata, created_at)
SELECT s.entity_id, s.entity_type, t.entity_id, t.entity_type, 'DERIVED_FROM', 0.85, 0.90, '{"reason":"Lesson derived from incident analysis"}'::jsonb, CURRENT_TIMESTAMP - INTERVAL '10 days'
FROM entities s, entities t WHERE s.title = 'Lesson Learned: Over-Engineering Agent State Management' AND t.title = 'Incident Post-Mortem: Cascading Agent Failure'
ON CONFLICT DO NOTHING;

INSERT INTO entity_edges (source_id, source_type, target_id, target_type, edge_type, strength, confidence, metadata, created_at)
SELECT s.entity_id, s.entity_type, t.entity_id, t.entity_type, 'DERIVED_FROM', 0.80, 0.85, '{"reason":"capacity_planning_from_incident"}'::jsonb, CURRENT_TIMESTAMP - INTERVAL '9 days'
FROM entities s, entities t WHERE s.title = 'Infrastructure Capacity Notes' AND t.title = 'Incident Post-Mortem: Database Connection Pool Exhaustion'
ON CONFLICT DO NOTHING;

INSERT INTO entity_edges (source_id, source_type, target_id, target_type, edge_type, strength, confidence, metadata, created_at)
SELECT s.entity_id, s.entity_type, t.entity_id, t.entity_type, 'DERIVED_FROM', 0.75, 0.80, '{"reason":"error_handling_from_patterns"}'::jsonb, CURRENT_TIMESTAMP - INTERVAL '7 days'
FROM entities s, entities t WHERE s.title = 'Error Handling Patterns' AND t.title = 'Microservices Communication Patterns'
ON CONFLICT DO NOTHING;

INSERT INTO entity_edges (source_id, source_type, target_id, target_type, edge_type, strength, confidence, metadata, created_at)
SELECT s.entity_id, s.entity_type, t.entity_id, t.entity_type, 'DERIVED_FROM', 0.70, 0.75, '{"reason":"vector_optimization_from_experience"}'::jsonb, CURRENT_TIMESTAMP - INTERVAL '2 days'
FROM entities s, entities t WHERE s.title = 'Vector Embedding Optimization' AND t.title = 'Incident Post-Mortem: Vector Search Degradation'
ON CONFLICT DO NOTHING;

-- VERSION_OF edges
INSERT INTO entity_edges (source_id, source_type, target_id, target_type, edge_type, strength, confidence, metadata, created_at)
SELECT s.entity_id, s.entity_type, t.entity_id, t.entity_type, 'VERSION_OF', 1.00, 1.00, '{"version":"2.0","change_type":"major"}'::jsonb, CURRENT_TIMESTAMP - INTERVAL '8 days'
FROM entities s, entities t WHERE s.title = 'Code Review Harness' AND t.title = 'Security Scan Harness'
ON CONFLICT DO NOTHING;

INSERT INTO entity_edges (source_id, source_type, target_id, target_type, edge_type, strength, confidence, metadata, created_at)
SELECT s.entity_id, s.entity_type, t.entity_id, t.entity_type, 'VERSION_OF', 1.00, 1.00, '{"version":"1.2","change_type":"minor"}'::jsonb, CURRENT_TIMESTAMP - INTERVAL '5 days'
FROM entities s, entities t WHERE s.title = 'Entity Search API Specification' AND t.title = 'Workspace Isolation Specification'
ON CONFLICT DO NOTHING;

-- EXTRACTED_FROM edges
INSERT INTO entity_edges (source_id, source_type, target_id, target_type, edge_type, strength, confidence, metadata, created_at)
SELECT s.entity_id, s.entity_type, t.entity_id, t.entity_type, 'EXTRACTED_FROM', 0.80, 0.85, '{"extraction_method":"auto","confidence_score":0.85}'::jsonb, CURRENT_TIMESTAMP - INTERVAL '12 days'
FROM entities s, entities t WHERE s.title = 'Web Search and Synthesis' AND t.title = 'Retrieval-Augmented Generation (RAG)'
ON CONFLICT DO NOTHING;

INSERT INTO entity_edges (source_id, source_type, target_id, target_type, edge_type, strength, confidence, metadata, created_at)
SELECT s.entity_id, s.entity_type, t.entity_id, t.entity_type, 'EXTRACTED_FROM', 0.75, 0.80, '{"extraction_method":"auto","confidence_score":0.80}'::jsonb, CURRENT_TIMESTAMP - INTERVAL '11 days'
FROM entities s, entities t WHERE s.title = 'Code Generation and Refactoring' AND t.title = 'Event-Driven Architecture Patterns'
ON CONFLICT DO NOTHING;

INSERT INTO entity_edges (source_id, source_type, target_id, target_type, edge_type, strength, confidence, metadata, created_at)
SELECT s.entity_id, s.entity_type, t.entity_id, t.entity_type, 'EXTRACTED_FROM', 0.70, 0.75, '{"extraction_method":"auto","confidence_score":0.75}'::jsonb, CURRENT_TIMESTAMP - INTERVAL '10 days'
FROM entities s, entities t WHERE s.title = 'Infrastructure Automation' AND t.title = 'CI/CD Pipeline Design Principles'
ON CONFLICT DO NOTHING;

INSERT INTO entity_edges (source_id, source_type, target_id, target_type, edge_type, strength, confidence, metadata, created_at)
SELECT s.entity_id, s.entity_type, t.entity_id, t.entity_type, 'EXTRACTED_FROM', 0.85, 0.90, '{"extraction_method":"auto","confidence_score":0.90}'::jsonb, CURRENT_TIMESTAMP - INTERVAL '9 days'
FROM entities s, entities t WHERE s.title = 'Security Assessment and Remediation' AND t.title = 'OAuth 2.0 and JWT Security Best Practices'
ON CONFLICT DO NOTHING;

INSERT INTO entity_edges (source_id, source_type, target_id, target_type, edge_type, strength, confidence, metadata, created_at)
SELECT s.entity_id, s.entity_type, t.entity_id, t.entity_type, 'EXTRACTED_FROM', 0.65, 0.70, '{"extraction_method":"manual","confidence_score":0.70}'::jsonb, CURRENT_TIMESTAMP - INTERVAL '6 days'
FROM entities s, entities t WHERE s.title = 'Data Analysis and Visualization' AND t.title = 'Data Partitioning Strategies'
ON CONFLICT DO NOTHING;

-- RELATED_TO edges
INSERT INTO entity_edges (source_id, source_type, target_id, target_type, edge_type, strength, confidence, metadata, created_at)
SELECT s.entity_id, s.entity_type, t.entity_id, t.entity_type, 'RELATED_TO', 0.60, 0.70, '{"relation":"both_involve_database_optimization"}'::jsonb, CURRENT_TIMESTAMP - INTERVAL '14 days'
FROM entities s, entities t WHERE s.title = 'Database Performance Troubleshooting' AND t.title = 'PostgreSQL Performance Tuning Best Practices'
ON CONFLICT DO NOTHING;

INSERT INTO entity_edges (source_id, source_type, target_id, target_type, edge_type, strength, confidence, metadata, created_at)
SELECT s.entity_id, s.entity_type, t.entity_id, t.entity_type, 'RELATED_TO', 0.55, 0.65, '{"relation":"both_address_security"}'::jsonb, CURRENT_TIMESTAMP - INTERVAL '13 days'
FROM entities s, entities t WHERE s.title = 'Security Audit Findings 2026' AND t.title = 'OAuth 2.0 and JWT Security Best Practices'
ON CONFLICT DO NOTHING;

INSERT INTO entity_edges (source_id, source_type, target_id, target_type, edge_type, strength, confidence, metadata, created_at)
SELECT s.entity_id, s.entity_type, t.entity_id, t.entity_type, 'RELATED_TO', 0.70, 0.75, '{"relation":"both_involve_distributed_systems"}'::jsonb, CURRENT_TIMESTAMP - INTERVAL '12 days'
FROM entities s, entities t WHERE s.title = 'Event-Driven Architecture Patterns' AND t.title = 'Microservices Communication Patterns'
ON CONFLICT DO NOTHING;

INSERT INTO entity_edges (source_id, source_type, target_id, target_type, edge_type, strength, confidence, metadata, created_at)
SELECT s.entity_id, s.entity_type, t.entity_id, t.entity_type, 'RELATED_TO', 0.50, 0.60, '{"relation":"both_involve_monitoring"}'::jsonb, CURRENT_TIMESTAMP - INTERVAL '11 days'
FROM entities s, entities t WHERE s.title = 'Monitoring Alert Thresholds' AND t.title = 'Observability Trinity: Logs, Metrics, Traces'
ON CONFLICT DO NOTHING;

INSERT INTO entity_edges (source_id, source_type, target_id, target_type, edge_type, strength, confidence, metadata, created_at)
SELECT s.entity_id, s.entity_type, t.entity_id, t.entity_type, 'RELATED_TO', 0.65, 0.70, '{"relation":"both_involve_data_partitioning"}'::jsonb, CURRENT_TIMESTAMP - INTERVAL '10 days'
FROM entities s, entities t WHERE s.title = 'Data Partitioning Strategies' AND t.title = 'Vector Embedding Optimization'
ON CONFLICT DO NOTHING;

INSERT INTO entity_edges (source_id, source_type, target_id, target_type, edge_type, strength, confidence, metadata, created_at)
SELECT s.entity_id, s.entity_type, t.entity_id, t.entity_type, 'RELATED_TO', 0.45, 0.55, '{"relation":"both_involve_deployment"}'::jsonb, CURRENT_TIMESTAMP - INTERVAL '9 days'
FROM entities s, entities t WHERE s.title = 'Deployment Runbook v2.3' AND t.title = 'CI/CD Pipeline Design Principles'
ON CONFLICT DO NOTHING;

INSERT INTO entity_edges (source_id, source_type, target_id, target_type, edge_type, strength, confidence, metadata, created_at)
SELECT s.entity_id, s.entity_type, t.entity_id, t.entity_type, 'RELATED_TO', 0.75, 0.80, '{"relation":"incident_and_capacity_overlap"}'::jsonb, CURRENT_TIMESTAMP - INTERVAL '8 days'
FROM entities s, entities t WHERE s.title = 'Incident Post-Mortem: Database Connection Pool Exhaustion' AND t.title = 'Infrastructure Capacity Notes'
ON CONFLICT DO NOTHING;

INSERT INTO entity_edges (source_id, source_type, target_id, target_type, edge_type, strength, confidence, metadata, created_at)
SELECT s.entity_id, s.entity_type, t.entity_id, t.entity_type, 'RELATED_TO', 0.60, 0.70, '{"relation":"both_involve_agent_coordination"}'::jsonb, CURRENT_TIMESTAMP - INTERVAL '7 days'
FROM entities s, entities t WHERE s.title = 'Agent Coordination Protocols' AND t.title = 'Incident Post-Mortem: Cascading Agent Failure'
ON CONFLICT DO NOTHING;

INSERT INTO entity_edges (source_id, source_type, target_id, target_type, edge_type, strength, confidence, metadata, created_at)
SELECT s.entity_id, s.entity_type, t.entity_id, t.entity_type, 'RELATED_TO', 0.55, 0.65, '{"relation":"code_review_and_security"}'::jsonb, CURRENT_TIMESTAMP - INTERVAL '6 days'
FROM entities s, entities t WHERE s.title = 'Code Review: Auth Module PR #247' AND t.title = 'Security Scan Report: May 2026'
ON CONFLICT DO NOTHING;

INSERT INTO entity_edges (source_id, source_type, target_id, target_type, edge_type, strength, confidence, metadata, created_at)
SELECT s.entity_id, s.entity_type, t.entity_id, t.entity_type, 'RELATED_TO', 0.50, 0.60, '{"relation":"test_results_overlap"}'::jsonb, CURRENT_TIMESTAMP - INTERVAL '5 days'
FROM entities s, entities t WHERE s.title = 'Integration Test Results: Sprint 14' AND t.title = 'API Contract Test Results: v2.4.0'
ON CONFLICT DO NOTHING;

INSERT INTO entity_edges (source_id, source_type, target_id, target_type, edge_type, strength, confidence, metadata, created_at)
SELECT s.entity_id, s.entity_type, t.entity_id, t.entity_type, 'RELATED_TO', 0.70, 0.80, '{"relation":"spec_implementation"}'::jsonb, CURRENT_TIMESTAMP - INTERVAL '15 days'
FROM entities s, entities t WHERE s.title = 'Code Review Harness' AND t.title = 'Entity Search API Specification'
ON CONFLICT DO NOTHING;

INSERT INTO entity_edges (source_id, source_type, target_id, target_type, edge_type, strength, confidence, metadata, created_at)
SELECT s.entity_id, s.entity_type, t.entity_id, t.entity_type, 'RELATED_TO', 0.65, 0.75, '{"relation":"security_framework_alignment"}'::jsonb, CURRENT_TIMESTAMP - INTERVAL '12 days'
FROM entities s, entities t WHERE s.title = 'Security Scan Harness' AND t.title = 'Agent Credential Management Specification'
ON CONFLICT DO NOTHING;

INSERT INTO entity_edges (source_id, source_type, target_id, target_type, edge_type, strength, confidence, metadata, created_at)
SELECT s.entity_id, s.entity_type, t.entity_id, t.entity_type, 'RELATED_TO', 0.80, 0.85, '{"relation":"deployment_verification"}'::jsonb, CURRENT_TIMESTAMP - INTERVAL '8 days'
FROM entities s, entities t WHERE s.title = 'Deployment Verification Harness' AND t.title = 'Deployment Runbook v2.3'
ON CONFLICT DO NOTHING;

INSERT INTO entity_edges (source_id, source_type, target_id, target_type, edge_type, strength, confidence, metadata, created_at)
SELECT s.entity_id, s.entity_type, t.entity_id, t.entity_type, 'RELATED_TO', 0.40, 0.50, '{"relation":"architectural_alignment"}'::jsonb, CURRENT_TIMESTAMP - INTERVAL '10 days'
FROM entities s, entities t WHERE s.title = 'Project Alpha Architecture Decision' AND t.title = 'Workspace Isolation Specification'
ON CONFLICT DO NOTHING;

INSERT INTO entity_edges (source_id, source_type, target_id, target_type, edge_type, strength, confidence, metadata, created_at)
SELECT s.entity_id, s.entity_type, t.entity_id, t.entity_type, 'RELATED_TO', 0.60, 0.70, '{"relation":"versioning_and_isolation"}'::jsonb, CURRENT_TIMESTAMP - INTERVAL '5 days'
FROM entities s, entities t WHERE s.title = 'Entity Versioning Specification' AND t.title = 'Workspace Isolation Specification'
ON CONFLICT DO NOTHING;

INSERT INTO entity_edges (source_id, source_type, target_id, target_type, edge_type, strength, confidence, metadata, created_at)
SELECT s.entity_id, s.entity_type, t.entity_id, t.entity_type, 'RELATED_TO', 0.55, 0.65, '{"relation":"events_and_communication"}'::jsonb, CURRENT_TIMESTAMP - INTERVAL '4 days'
FROM entities s, entities t WHERE s.title = 'Real-time Event Notification Specification' AND t.title = 'Event-Driven Architecture Patterns'
ON CONFLICT DO NOTHING;

INSERT INTO entity_edges (source_id, source_type, target_id, target_type, edge_type, strength, confidence, metadata, created_at)
SELECT s.entity_id, s.entity_type, t.entity_id, t.entity_type, 'RELATED_TO', 0.50, 0.60, '{"relation":"both_reference_vendor_apis"}'::jsonb, CURRENT_TIMESTAMP - INTERVAL '3 days'
FROM entities s, entities t WHERE s.title = 'Vendor API Rate Limits' AND t.title = 'API Design Preferences'
ON CONFLICT DO NOTHING;

-- USES_HARNESS edges
INSERT INTO entity_edges (source_id, source_type, target_id, target_type, edge_type, strength, confidence, metadata, created_at)
SELECT s.entity_id, s.entity_type, t.entity_id, t.entity_type, 'USES_HARNESS', 0.90, 0.95, '{"harness_version":"2.1.0","invocation_count":47}'::jsonb, CURRENT_TIMESTAMP - INTERVAL '7 days'
FROM entities s, entities t WHERE s.title = 'Code Review: Auth Module PR #247' AND t.title = 'Code Review Harness'
ON CONFLICT DO NOTHING;

INSERT INTO entity_edges (source_id, source_type, target_id, target_type, edge_type, strength, confidence, metadata, created_at)
SELECT s.entity_id, s.entity_type, t.entity_id, t.entity_type, 'USES_HARNESS', 0.90, 0.95, '{"harness_version":"3.0.0","invocation_count":23}'::jsonb, CURRENT_TIMESTAMP - INTERVAL '6 days'
FROM entities s, entities t WHERE s.title = 'Security Scan Report: May 2026' AND t.title = 'Security Scan Harness'
ON CONFLICT DO NOTHING;

INSERT INTO entity_edges (source_id, source_type, target_id, target_type, edge_type, strength, confidence, metadata, created_at)
SELECT s.entity_id, s.entity_type, t.entity_id, t.entity_type, 'USES_HARNESS', 0.85, 0.90, '{"harness_version":"1.4.0","invocation_count":156}'::jsonb, CURRENT_TIMESTAMP - INTERVAL '4 days'
FROM entities s, entities t WHERE s.title = 'Data Pipeline Performance Benchmark' AND t.title = 'Data Ingestion Pipeline Harness'
ON CONFLICT DO NOTHING;

INSERT INTO entity_edges (source_id, source_type, target_id, target_type, edge_type, strength, confidence, metadata, created_at)
SELECT s.entity_id, s.entity_type, t.entity_id, t.entity_type, 'USES_HARNESS', 0.90, 0.95, '{"harness_version":"1.2.0","invocation_count":89}'::jsonb, CURRENT_TIMESTAMP - INTERVAL '3 days'
FROM entities s, entities t WHERE s.title = 'Data Analysis and Visualization' AND t.title = 'Knowledge Extraction Harness'
ON CONFLICT DO NOTHING;

-- ============================================================================
-- 12. ENTITY_EMBEDDINGS (25 embeddings using random 1024-dim vectors)
-- ============================================================================
INSERT INTO entity_embeddings (entity_id, entity_type, embedding, embedding_model, embedding_dim, embedded_at)
SELECT
  e.entity_id,
  e.entity_type,
  (SELECT array_agg(random()) FROM generate_series(1, 1024))::vector(1024),
  'text-embedding-3-small',
  1024,
  CURRENT_TIMESTAMP - (random() * INTERVAL '7 days')::interval
FROM entities e
WHERE e.entity_type IN ('KNOWLEDGE', 'MEMORY', 'SKILL')
ORDER BY e.entity_id
LIMIT 25
ON CONFLICT DO NOTHING;

-- ============================================================================
-- 13. COLLAB_GROUPS (3 groups) + COLLAB_GROUP_MEMBERS (8 members)
-- ============================================================================
INSERT INTO collab_groups (group_name, group_type, description, workspace_id, coordinator_agent_id, sharing_policy, status, metadata, created_at, updated_at)
VALUES
  ('Alpha Dev Team',   'PROJECT',  'Core development team for Project Alpha',          (SELECT workspace_id FROM workspaces WHERE workspace_alias='proj-alpha'), 'agent-bravo',   'OPEN',      'ACTIVE', '{"capacity":5,"current_load":"moderate"}'::jsonb, CURRENT_TIMESTAMP - INTERVAL '30 days', CURRENT_TIMESTAMP),
  ('Data Science Pod', 'PROJECT',  'Data analytics and research collaboration group',  (SELECT workspace_id FROM workspaces WHERE workspace_alias='proj-beta'),  'agent-charlie',  'OPEN',      'ACTIVE', '{"capacity":4,"current_load":"high"}'::jsonb,     CURRENT_TIMESTAMP - INTERVAL '25 days', CURRENT_TIMESTAMP),
  ('Platform SRE',     'PIPELINE', 'Site reliability and infrastructure operations',   (SELECT workspace_id FROM workspaces WHERE workspace_alias='devops'),     'agent-foxtrot', 'RESTRICTED','ACTIVE', '{"capacity":3,"current_load":"low"}'::jsonb,      CURRENT_TIMESTAMP - INTERVAL '20 days', CURRENT_TIMESTAMP)
ON CONFLICT DO NOTHING;

INSERT INTO collab_group_members (group_id, agent_id, role, personal_workspace_id, joined_at, status)
SELECT g.group_id, a.agent_id,
  CASE WHEN a.agent_id = g.coordinator_agent_id THEN 'LEAD' WHEN a.agent_role = 'SYSTEM' THEN 'OBSERVER' ELSE 'MEMBER' END,
  NULL,
  CURRENT_TIMESTAMP - (random() * INTERVAL '20 days')::interval,
  'ACTIVE'
FROM collab_groups g
CROSS JOIN agent_registry a
WHERE (g.group_name = 'Alpha Dev Team' AND a.agent_id IN ('agent-bravo', 'agent-alpha', 'agent-echo'))
   OR (g.group_name = 'Data Science Pod' AND a.agent_id IN ('agent-charlie', 'agent-delta'))
   OR (g.group_name = 'Platform SRE' AND a.agent_id IN ('agent-foxtrot', 'agent-golf', 'agent-hotel'))
ON CONFLICT DO NOTHING;

-- ============================================================================
-- 14. TASK_PLANS (5 plans)
-- ============================================================================
INSERT INTO task_plans (agent_id, goal, status, priority, strategy, result_summary, branch_id, created_at, updated_at)
VALUES
  ('agent-alpha',  'Implement authentication module v2 with bcrypt and session management',     'RUNNING', 8, 'SEQUENTIAL', NULL,       (SELECT branch_id FROM context_branches WHERE branch_name='feature/auth-v2'), CURRENT_TIMESTAMP - INTERVAL '7 days',  CURRENT_TIMESTAMP),
  ('agent-charlie','Optimize ETL pipeline JSON parsing - evaluate simdjson library',            'RUNNING', 9, 'SEQUENTIAL', 'Benchmarked simdjson: 25K records/sec vs Jackson 8.5K. 3x improvement confirmed.', (SELECT branch_id FROM context_branches WHERE branch_name='main' AND workspace_id=(SELECT workspace_id FROM workspaces WHERE workspace_alias='proj-beta')), CURRENT_TIMESTAMP - INTERVAL '5 days',  CURRENT_TIMESTAMP - INTERVAL '1 day'),
  ('agent-delta',  'Research RAG optimization techniques for vector search recall improvement', 'SUCCESS', 6, 'EXPLORATORY','Evaluated HNSW vs IVFFlat. HNSW provides 15% better recall at comparable latency.', (SELECT branch_id FROM context_branches WHERE branch_name='main' AND workspace_id=(SELECT workspace_id FROM workspaces WHERE workspace_alias='research')), CURRENT_TIMESTAMP - INTERVAL '10 days', CURRENT_TIMESTAMP - INTERVAL '2 days'),
  ('agent-foxtrot','Set up canary deployment infrastructure for v2.4 release',                  'PENDING', 7, 'SEQUENTIAL', NULL,       (SELECT branch_id FROM context_branches WHERE branch_name='main' AND workspace_id=(SELECT workspace_id FROM workspaces WHERE workspace_alias='devops')), CURRENT_TIMESTAMP - INTERVAL '2 days',  CURRENT_TIMESTAMP),
  ('agent-echo',   'Conduct security audit of payment service and generate remediation plan',   'RUNNING', 9, 'PARALLEL',   'SAST complete, 2 high findings. DAST in progress.', (SELECT branch_id FROM context_branches WHERE branch_name='main' AND workspace_id=(SELECT workspace_id FROM workspaces WHERE workspace_alias='proj-alpha')), CURRENT_TIMESTAMP - INTERVAL '3 days',  CURRENT_TIMESTAMP - INTERVAL '1 day')
ON CONFLICT DO NOTHING;

-- ============================================================================
-- 15. TASK_STEPS (15 steps - 3 per plan)
-- ============================================================================
INSERT INTO task_steps (plan_id, plan_status, step_order, description, tool_name, tool_input, tool_output, status, created_at)
SELECT p.plan_id, 'RUNNING', s.step_order, s.description, s.tool_name, s.tool_input, s.tool_output, s.step_status, s.created_at
FROM task_plans p,
  (SELECT 1 as step_order, 'Analyze current auth module codebase' as description, 'code_search' as tool_name, '{"pattern":"auth","file_type":"ts"}'::jsonb as tool_input, '{"files_found":12}'::jsonb as tool_output, 'SUCCESS' as step_status, CURRENT_TIMESTAMP - INTERVAL '7 days' as created_at
   UNION ALL SELECT 2, 'Design bcrypt integration with existing session layer', 'architect', '{"component":"auth","change":"bcrypt_integration"}'::jsonb, '{"schema_version":"2.0"}'::jsonb, 'SUCCESS', CURRENT_TIMESTAMP - INTERVAL '6 days'
   UNION ALL SELECT 3, 'Implement bcrypt password hashing utility', 'code_gen', '{"spec":"bcrypt_util","language":"typescript"}'::jsonb, NULL::jsonb, 'RUNNING', CURRENT_TIMESTAMP - INTERVAL '5 days'
  ) s
WHERE p.agent_id = 'agent-alpha' AND p.goal LIKE '%auth module v2%'
ON CONFLICT DO NOTHING;

INSERT INTO task_steps (plan_id, plan_status, step_order, description, tool_name, tool_input, tool_output, status, created_at)
SELECT p.plan_id, 'RUNNING', s.step_order, s.description, s.tool_name, s.tool_input, s.tool_output, s.step_status, s.created_at
FROM task_plans p,
  (SELECT 1 as step_order, 'Download and benchmark simdjson library' as description, 'benchmark' as tool_name, '{"library":"simdjson"}'::jsonb as tool_input, '{"throughput":"25K/sec"}'::jsonb as tool_output, 'SUCCESS' as step_status, CURRENT_TIMESTAMP - INTERVAL '5 days' as created_at
   UNION ALL SELECT 2, 'Integrate simdjson into ETL pipeline', 'code_gen', '{"spec":"simdjson_integration"}'::jsonb, NULL::jsonb, 'RUNNING', CURRENT_TIMESTAMP - INTERVAL '4 days'
   UNION ALL SELECT 3, 'Run regression tests on ETL pipeline', 'test_runner', '{"suite":"etl_regression"}'::jsonb, NULL::jsonb, 'PENDING', CURRENT_TIMESTAMP - INTERVAL '3 days'
  ) s
WHERE p.agent_id = 'agent-charlie' AND p.goal LIKE '%Optimize ETL%'
ON CONFLICT DO NOTHING;

INSERT INTO task_steps (plan_id, plan_status, step_order, description, tool_name, tool_input, tool_output, status, created_at)
SELECT p.plan_id, 'SUCCESS', s.step_order, s.description, s.tool_name, s.tool_input, s.tool_output, s.step_status, s.created_at
FROM task_plans p,
  (SELECT 1 as step_order, 'Literature review of RAG optimization methods' as description, 'web_search' as tool_name, '{"query":"RAG optimization"}'::jsonb as tool_input, '{"papers_found":23}'::jsonb as tool_output, 'SUCCESS' as step_status, CURRENT_TIMESTAMP - INTERVAL '10 days' as created_at
   UNION ALL SELECT 2, 'Benchmark HNSW vs IVFFlat index performance', 'benchmark', '{"index_types":["hnsw","ivfflat"]}'::jsonb, '{"hnsw_recall":0.95,"ivfflat_recall":0.82}'::jsonb, 'SUCCESS', CURRENT_TIMESTAMP - INTERVAL '8 days'
   UNION ALL SELECT 3, 'Write research summary with recommendations', 'report_gen', '{"format":"markdown"}'::jsonb, '{"report_id":"RAG-OPT-2026-001"}'::jsonb, 'SUCCESS', CURRENT_TIMESTAMP - INTERVAL '2 days'
  ) s
WHERE p.agent_id = 'agent-delta' AND p.goal LIKE '%RAG optimization%'
ON CONFLICT DO NOTHING;

INSERT INTO task_steps (plan_id, plan_status, step_order, description, tool_name, tool_input, tool_output, status, created_at)
SELECT p.plan_id, 'PENDING', s.step_order, s.description, s.tool_name, s.tool_input, s.tool_output, s.step_status, s.created_at
FROM task_plans p,
  (SELECT 1 as step_order, 'Provision canary deployment infrastructure' as description, 'infra_mgr' as tool_name, '{"action":"provision","canary_percent":5}'::jsonb as tool_input, NULL::jsonb as tool_output, 'PENDING' as step_status, CURRENT_TIMESTAMP - INTERVAL '2 days' as created_at
   UNION ALL SELECT 2, 'Configure monitoring for canary metrics', 'monitor_setup', '{"metrics":["error_rate","latency_p99"]}'::jsonb, NULL::jsonb, 'PENDING', CURRENT_TIMESTAMP - INTERVAL '1 day'
   UNION ALL SELECT 3, 'Execute canary deployment with 5% traffic', 'deploy', '{"strategy":"canary","percent":5}'::jsonb, NULL::jsonb, 'PENDING', CURRENT_TIMESTAMP
  ) s
WHERE p.agent_id = 'agent-foxtrot' AND p.goal LIKE '%canary deployment%'
ON CONFLICT DO NOTHING;

INSERT INTO task_steps (plan_id, plan_status, step_order, description, tool_name, tool_input, tool_output, status, created_at)
SELECT p.plan_id, 'RUNNING', s.step_order, s.description, s.tool_name, s.tool_input, s.tool_output, s.step_status, s.created_at
FROM task_plans p,
  (SELECT 1 as step_order, 'Run SAST scan on payment service' as description, 'security_scan' as tool_name, '{"target":"payment-service","scan_type":"sast"}'::jsonb as tool_input, '{"critical":0,"high":2,"medium":8}'::jsonb as tool_output, 'SUCCESS' as step_status, CURRENT_TIMESTAMP - INTERVAL '3 days' as created_at
   UNION ALL SELECT 2, 'Run DAST scan on payment API endpoints', 'security_scan', '{"target":"payment-api","scan_type":"dast"}'::jsonb, NULL::jsonb, 'RUNNING', CURRENT_TIMESTAMP - INTERVAL '1 day'
   UNION ALL SELECT 3, 'Generate consolidated remediation plan', 'report_gen', '{"format":"markdown"}'::jsonb, NULL::jsonb, 'PENDING', CURRENT_TIMESTAMP
  ) s
WHERE p.agent_id = 'agent-echo' AND p.goal LIKE '%security audit%'
ON CONFLICT DO NOTHING;

-- ============================================================================
-- 16. SYSTEM_CONFIG (10 config entries)
-- ============================================================================
INSERT INTO system_config (config_key, config_value, description, updated_at)
VALUES
  ('max_agents_per_workspace',   '10',                     'Maximum number of agents per workspace',       CURRENT_TIMESTAMP),
  ('default_embedding_model',    'text-embedding-3-small', 'Default model for entity embeddings',         CURRENT_TIMESTAMP),
  ('embedding_dimensions',       '1024',                   'Dimensionality of embedding vectors',          CURRENT_TIMESTAMP),
  ('session_timeout_minutes',    '60',                     'Minutes before agent session marked inactive', CURRENT_TIMESTAMP),
  ('max_retries_per_task',       '3',                      'Maximum retries for failed task step',         CURRENT_TIMESTAMP),
  ('vector_search_top_k',        '5',                      'Default results for vector similarity search', CURRENT_TIMESTAMP),
  ('entity_import_batch_size',   '1000',                   'Records per batch import operation',           CURRENT_TIMESTAMP),
  ('knowledge_review_cycle_days','14',                     'Days between knowledge entity reviews',        CURRENT_TIMESTAMP),
  ('workspace_isolation_default','SHARED',                 'Default isolation mode for new workspaces',    CURRENT_TIMESTAMP),
  ('agent_health_check_interval','30',                     'Seconds between agent health checks',          CURRENT_TIMESTAMP)
ON CONFLICT (config_key) DO NOTHING;

-- ============================================================================
-- 17. TAGS (10 tags) + ENTITY_TAGS (20 mappings)
-- ============================================================================
INSERT INTO tags (tag_name, tag_group, usage_count, created_at)
VALUES
  ('security',       'DOMAIN', 0, CURRENT_TIMESTAMP),
  ('performance',    'DOMAIN', 0, CURRENT_TIMESTAMP),
  ('architecture',   'DOMAIN', 0, CURRENT_TIMESTAMP),
  ('ai-ml',          'DOMAIN', 0, CURRENT_TIMESTAMP),
  ('incident',       'TYPE',   0, CURRENT_TIMESTAMP),
  ('best-practice',  'TYPE',   0, CURRENT_TIMESTAMP),
  ('api',            'DOMAIN', 0, CURRENT_TIMESTAMP),
  ('database',       'DOMAIN', 0, CURRENT_TIMESTAMP),
  ('devops',         'DOMAIN', 0, CURRENT_TIMESTAMP),
  ('lesson-learned', 'TYPE',   0, CURRENT_TIMESTAMP)
ON CONFLICT (tag_name) DO NOTHING;

INSERT INTO entity_tags (entity_id, entity_type, tag_id)
SELECT e.entity_id, e.entity_type, t.tag_id
FROM entities e, tags t
WHERE (e.title = 'Security Audit Findings 2026' AND t.tag_name = 'security')
   OR (e.title = 'OAuth 2.0 and JWT Security Best Practices' AND t.tag_name = 'security')
   OR (e.title = 'Database Performance Troubleshooting' AND t.tag_name = 'performance')
   OR (e.title = 'PostgreSQL Performance Tuning Best Practices' AND t.tag_name = 'database')
   OR (e.title = 'PostgreSQL Performance Tuning Best Practices' AND t.tag_name = 'performance')
   OR (e.title = 'Event-Driven Architecture Patterns' AND t.tag_name = 'architecture')
   OR (e.title = 'Microservices Communication Patterns' AND t.tag_name = 'architecture')
   OR (e.title = 'Retrieval-Augmented Generation (RAG)' AND t.tag_name = 'ai-ml')
   OR (e.title = 'Vector Embedding Optimization' AND t.tag_name = 'ai-ml')
   OR (e.title = 'Incident Post-Mortem: Database Connection Pool Exhaustion' AND t.tag_name = 'incident')
   OR (e.title = 'Incident Post-Mortem: Vector Search Degradation' AND t.tag_name = 'incident')
   OR (e.title = 'Incident Post-Mortem: Cascading Agent Failure' AND t.tag_name = 'incident')
   OR (e.title = 'CI/CD Pipeline Design Principles' AND t.tag_name = 'devops')
   OR (e.title = 'Deployment Runbook v2.3' AND t.tag_name = 'devops')
   OR (e.title = 'Lesson Learned: Premature Microservices Decomposition' AND t.tag_name = 'lesson-learned')
   OR (e.title = 'Lesson Learned: Over-Engineering Agent State Management' AND t.tag_name = 'lesson-learned')
   OR (e.title = 'API Design Preferences' AND t.tag_name = 'api')
   OR (e.title = 'Entity Search API Specification' AND t.tag_name = 'api')
   OR (e.title = 'Data Partitioning Strategies' AND t.tag_name = 'database')
   OR (e.title = 'Agent Coordination Protocols' AND t.tag_name = 'ai-ml')
ON CONFLICT DO NOTHING;

UPDATE tags SET usage_count = (SELECT COUNT(*) FROM entity_tags et WHERE et.tag_id = tags.tag_id);

-- ============================================================================
-- 18. AGENT_CREDENTIALS (3 credentials)
-- ============================================================================
INSERT INTO agent_credentials (agent_id, user_id, credential_type, credential_value, scope, expires_at, is_active, created_at)
VALUES
  ('agent-alpha', 'admin', 'ACCESS_TOKEN', gen_random_uuid()::text, '["entity:read","entity:write","workspace:read","task:read","task:write"]'::jsonb, CURRENT_TIMESTAMP + INTERVAL '90 days', true, CURRENT_TIMESTAMP),
  ('agent-bravo', 'admin', 'ACCESS_TOKEN', gen_random_uuid()::text, '["entity:read","entity:write","workspace:read","workspace:write","task:read","task:write","agent:read"]'::jsonb, CURRENT_TIMESTAMP + INTERVAL '90 days', true, CURRENT_TIMESTAMP),
  ('agent-hotel', 'admin', 'ACCESS_TOKEN', gen_random_uuid()::text, '["entity:read","agent:read","agent:write","credential:read","security:audit"]'::jsonb, CURRENT_TIMESTAMP + INTERVAL '90 days', true, CURRENT_TIMESTAMP)
ON CONFLICT DO NOTHING;

-- ============================================================================
-- 19. AGENT_COLLABORATION (6 collaborations)
-- ============================================================================
INSERT INTO agent_collaboration (source_agent_id, target_agent_id, col_type, entity_id, context, strength, status, created_at)
VALUES
  ('agent-bravo',   'agent-alpha',  'TASK_ROUTING',   NULL, '{"reason":"Alpha assigned auth module task"}'::jsonb,      0.90, 'ACTIVE', CURRENT_TIMESTAMP - INTERVAL '7 days'),
  ('agent-bravo',   'agent-charlie','TASK_ROUTING',   NULL, '{"reason":"Charlie assigned pipeline optimization"}'::jsonb, 0.85, 'ACTIVE', CURRENT_TIMESTAMP - INTERVAL '5 days'),
  ('agent-alpha',   'agent-echo',   'REVIEW',         NULL, '{"reason":"Echo reviewing Alpha auth code"}'::jsonb,      0.80, 'ACTIVE', CURRENT_TIMESTAMP - INTERVAL '4 days'),
  ('agent-charlie', 'agent-delta',  'CONSULTATION',   NULL, '{"reason":"Delta advising on RAG optimization"}'::jsonb,  0.70, 'ACTIVE', CURRENT_TIMESTAMP - INTERVAL '6 days'),
  ('agent-foxtrot', 'agent-golf',   'HANDOFF',        NULL, '{"reason":"Golf taking over monitoring during deploy"}'::jsonb, 0.75, 'ACTIVE', CURRENT_TIMESTAMP - INTERVAL '2 days'),
  ('agent-echo',    'agent-hotel',  'SHARED_CONTEXT', NULL, '{"reason":"Shared security context for auth review"}'::jsonb, 0.85, 'ACTIVE', CURRENT_TIMESTAMP - INTERVAL '3 days')
ON CONFLICT DO NOTHING;

-- ============================================================================
-- 20. AGENT_SESSION (2 active sessions)
-- ============================================================================
INSERT INTO agent_session (agent_id, owner_user_id, workspace_id, predecessor_session_id, branch_id, is_active, context, last_active_at, created_at)
VALUES
  ('agent-alpha', 'admin',    (SELECT workspace_id FROM workspaces WHERE workspace_alias='proj-alpha'), NULL, (SELECT branch_id FROM context_branches WHERE branch_name='feature/auth-v2'), true, '{"current_task":"auth_module_v2","step":3,"progress":"60%"}'::jsonb,  CURRENT_TIMESTAMP - INTERVAL '5 minutes',  CURRENT_TIMESTAMP - INTERVAL '2 hours'),
  ('agent-echo',  'operator', (SELECT workspace_id FROM workspaces WHERE workspace_alias='code-review'), NULL, (SELECT branch_id FROM context_branches WHERE branch_name='main' AND workspace_id=(SELECT workspace_id FROM workspaces WHERE workspace_alias='proj-alpha')), true, '{"current_task":"security_audit","step":2,"progress":"40%"}'::jsonb, CURRENT_TIMESTAMP - INTERVAL '15 minutes', CURRENT_TIMESTAMP - INTERVAL '3 hours')
ON CONFLICT DO NOTHING;

-- ============================================================================
-- SEED DATA COMPLETE
-- ============================================================================
