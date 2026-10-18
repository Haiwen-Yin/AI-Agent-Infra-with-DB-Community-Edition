-- v4.4.8 platform command registry, governed autonomy, and private knowledge.
CREATE TABLE IF NOT EXISTS cx_platform_commands (
    command_id varchar(128) PRIMARY KEY,
    command_key varchar(64) NOT NULL,
    version integer NOT NULL DEFAULT 1,
    status varchar(24) NOT NULL DEFAULT 'PUBLISHED',
    risk_level varchar(32) NOT NULL,
    execution_mode varchar(32) NOT NULL,
    parameter_schema text NOT NULL DEFAULT '{}',
    target_schema text NOT NULL DEFAULT '{}',
    example_text varchar(1000) NOT NULL,
    localized_metadata text NOT NULL DEFAULT '{}',
    required_action varchar(128) NOT NULL,
    capability_scope varchar(128) NOT NULL,
    resource_scope text NOT NULL DEFAULT '{}',
    domain_policy varchar(32) NOT NULL DEFAULT 'MANAGEMENT_ONLY',
    approval_policy varchar(64) NOT NULL,
    expiry_seconds integer NOT NULL DEFAULT 900,
    idempotency_policy text NOT NULL DEFAULT '{}',
    compensation_contract text NOT NULL DEFAULT '{}',
    evidence_policy text NOT NULL DEFAULT '{}',
    content_digest varchar(64) NOT NULL,
    created_at timestamp NOT NULL DEFAULT current_timestamp,
    UNIQUE (command_key, version),
    CHECK (status IN ('DRAFT','PUBLISHED','DEPRECATED','RETIRED')),
    CHECK (risk_level IN ('READ','SAFE_MAINTENANCE','PROPOSED_CHANGE','HIGH_RISK_CHANGE','EMERGENCY_CONTAINMENT')),
    CHECK (execution_mode IN ('DIRECT_READ','PROPOSAL_ONLY','GOVERNED_EXECUTOR','UNAVAILABLE')),
    CHECK (domain_policy IN ('MANAGEMENT_ONLY','CHANNEL_DOMAIN','ANY_DOMAIN'))
);
CREATE TABLE IF NOT EXISTS cx_platform_command_executors (
    executor_id varchar(128) PRIMARY KEY,
    command_key varchar(64) NOT NULL,
    command_version integer NOT NULL,
    executor_key varchar(128) NOT NULL,
    state varchar(24) NOT NULL DEFAULT 'DISABLED',
    expected_digest varchar(64) NOT NULL,
    rate_limit_per_minute integer NOT NULL DEFAULT 10,
    failure_budget integer NOT NULL DEFAULT 1,
    reason varchar(2000) NOT NULL,
    updated_by varchar(128) NOT NULL,
    updated_at timestamp NOT NULL DEFAULT current_timestamp,
    UNIQUE (command_key, command_version),
    CHECK (state IN ('ENABLED','DISABLED','DEGRADED','UNAVAILABLE'))
);
CREATE TABLE IF NOT EXISTS cx_platform_maintenance_tasks (
    task_id varchar(128) PRIMARY KEY,
    command_id varchar(128) NOT NULL,
    command_instance_id varchar(128),
    task_kind varchar(64) NOT NULL,
    status varchar(32) NOT NULL DEFAULT 'DISCOVERED',
    risk_level varchar(32) NOT NULL,
    autonomous boolean NOT NULL DEFAULT false,
    scope_json text NOT NULL DEFAULT '{}',
    finding_json text NOT NULL DEFAULT '{}',
    plan_json text NOT NULL DEFAULT '{}',
    postflight_json text NOT NULL DEFAULT '{}',
    evidence_json text NOT NULL DEFAULT '{}',
    idempotency_key varchar(256),
    graph_run_id varchar(128),
    security_domain_id varchar(128),
    created_by varchar(128) NOT NULL,
    lease_owner varchar(128),
    lease_expires_at timestamp,
    fencing_token bigint NOT NULL DEFAULT 1,
    created_at timestamp NOT NULL DEFAULT current_timestamp,
    updated_at timestamp NOT NULL DEFAULT current_timestamp,
    UNIQUE (idempotency_key),
    CHECK (status IN ('DISCOVERED','ANALYZED','PROPOSED','AUTHORIZED','EXECUTING','VERIFYING','COMPLETED','VERIFY_FAILED','COMPENSATED','FAILED','CANCELLED','EXPIRED'))
);
ALTER TABLE cx_platform_maintenance_tasks ADD COLUMN IF NOT EXISTS graph_run_id varchar(128);
CREATE TABLE IF NOT EXISTS cx_platform_maintenance_attempts (
    attempt_id varchar(128) PRIMARY KEY,
    task_id varchar(128) NOT NULL,
    attempt_no integer NOT NULL DEFAULT 1,
    status varchar(32) NOT NULL DEFAULT 'PENDING',
    started_at timestamp,
    completed_at timestamp,
    lease_owner varchar(128),
    fencing_token bigint NOT NULL DEFAULT 1,
    output_json text NOT NULL DEFAULT '{}',
    failure_reason varchar(2000),
    created_at timestamp NOT NULL DEFAULT current_timestamp,
    UNIQUE (task_id, attempt_no)
);
CREATE TABLE IF NOT EXISTS cx_platform_safe_autonomy_policies (
    policy_id varchar(64) PRIMARY KEY,
    state varchar(24) NOT NULL DEFAULT 'DISABLED',
    allowed_command_json text NOT NULL DEFAULT '[]',
    resource_scope_json text NOT NULL DEFAULT '{}',
    execution_principal varchar(128),
    rate_limit_per_minute integer NOT NULL DEFAULT 10,
    max_concurrency integer NOT NULL DEFAULT 1,
    failure_budget integer NOT NULL DEFAULT 1,
    evidence_retention_days integer NOT NULL DEFAULT 365,
    version bigint NOT NULL DEFAULT 1,
    reason varchar(2000) NOT NULL,
    updated_by varchar(128) NOT NULL,
    updated_at timestamp NOT NULL DEFAULT current_timestamp,
    CHECK (state IN ('ENABLED','DISABLED','PAUSED'))
);
CREATE TABLE IF NOT EXISTS cx_platform_knowledge (
    knowledge_id varchar(128) PRIMARY KEY,
    knowledge_key varchar(128) NOT NULL,
    version integer NOT NULL DEFAULT 1,
    knowledge_kind varchar(64) NOT NULL,
    audience varchar(64) NOT NULL,
    scope_type varchar(32) NOT NULL,
    security_domain_id varchar(128),
    owner_principal_id varchar(128),
    classification varchar(32) NOT NULL DEFAULT 'RESTRICTED',
    content_json text NOT NULL,
    content_digest varchar(64) NOT NULL,
    signature varchar(256) NOT NULL,
    signature_status varchar(32) NOT NULL DEFAULT 'UNVERIFIED',
    status varchar(24) NOT NULL DEFAULT 'DRAFT',
    valid_from timestamp,
    valid_until timestamp,
    source_manifest_id varchar(128),
    created_by varchar(128) NOT NULL,
    created_at timestamp NOT NULL DEFAULT current_timestamp,
    UNIQUE (knowledge_key, version),
    CHECK (audience IN ('PLATFORM_ADMIN','COMPLIANCE_ADMIN','MANAGEMENT_AGENTS','SECURITY_DOMAIN','PRINCIPAL','PUBLIC')),
    CHECK (scope_type IN ('PLATFORM_GLOBAL','SECURITY_DOMAIN','PRINCIPAL','MANAGEMENT_AGENT','COMPLIANCE_AGENT','PUBLIC')),
    CHECK (signature_status IN ('UNVERIFIED','VERIFIED_BUILTIN','INVALID')),
    CHECK (status IN ('DRAFT','PUBLISHED','SUPERSEDED','REVOKED'))
);
CREATE TABLE IF NOT EXISTS cx_platform_knowledge_chunks (
    chunk_id varchar(128) PRIMARY KEY,
    knowledge_id varchar(128) NOT NULL,
    chunk_no integer NOT NULL,
    chunk_text text NOT NULL,
    chunk_digest varchar(64) NOT NULL,
    representation_json text NOT NULL DEFAULT '{}',
    audience varchar(64) NOT NULL,
    scope_type varchar(32) NOT NULL,
    security_domain_id varchar(128),
    owner_principal_id varchar(128),
    classification varchar(32) NOT NULL,
    status varchar(24) NOT NULL DEFAULT 'ACTIVE',
    UNIQUE (knowledge_id, chunk_no)
);
CREATE TABLE IF NOT EXISTS cx_platform_knowledge_grants (
    grant_id varchar(128) PRIMARY KEY,
    knowledge_id varchar(128) NOT NULL,
    principal_id varchar(128),
    security_domain_id varchar(128),
    grant_scope varchar(32) NOT NULL,
    status varchar(24) NOT NULL DEFAULT 'ACTIVE',
    valid_from timestamp NOT NULL DEFAULT current_timestamp,
    valid_until timestamp,
    granted_by varchar(128) NOT NULL,
    reason varchar(2000) NOT NULL,
    CHECK (grant_scope IN ('MANAGEMENT_CONTEXT','COMPLIANCE_CONTEXT','SECURITY_DOMAIN','PRINCIPAL'))
);
CREATE TABLE IF NOT EXISTS cx_database_isolation_inventory (
    inventory_id varchar(128) PRIMARY KEY,
    object_type varchar(128) NOT NULL,
    object_name varchar(128) NOT NULL,
    scope_keys_json text NOT NULL DEFAULT '[]',
    human_path varchar(512),
    agent_path varchar(512),
    sharing_model varchar(64) NOT NULL,
    derived_inheritance varchar(256) NOT NULL,
    move_policy varchar(64) NOT NULL,
    oracle_enforcement varchar(256) NOT NULL,
    pg_enforcement varchar(256) NOT NULL,
    yashan_enforcement varchar(256) NOT NULL,
    verification_ref varchar(256),
    status varchar(24) NOT NULL DEFAULT 'PENDING',
    version bigint NOT NULL DEFAULT 1,
    reason varchar(2000) NOT NULL,
    updated_by varchar(128) NOT NULL,
    updated_at timestamp NOT NULL DEFAULT current_timestamp,
    UNIQUE (object_type, object_name),
    CHECK (status IN ('PENDING','IMPLEMENTED','EXCEPTION_APPROVED','UNAVAILABLE'))
);
CREATE INDEX IF NOT EXISTS idx_cx_platform_command_key
    ON cx_platform_commands(command_key,status,version DESC);
CREATE INDEX IF NOT EXISTS idx_cx_maintenance_status
    ON cx_platform_maintenance_tasks(status,lease_expires_at,created_at);
CREATE INDEX IF NOT EXISTS idx_cx_platform_knowledge_scope
    ON cx_platform_knowledge(audience,scope_type,status,valid_until);
CREATE INDEX IF NOT EXISTS idx_cx_knowledge_chunk_scope
    ON cx_platform_knowledge_chunks(audience,scope_type,status);

-- Platform private knowledge and command metadata are human/built-in control
-- planes. RLS without an ordinary-agent policy fails closed even if a future
-- migration accidentally grants these tables to ai_agent_runtime.
ALTER TABLE cx_platform_commands ENABLE ROW LEVEL SECURITY;
ALTER TABLE cx_platform_command_executors ENABLE ROW LEVEL SECURITY;
ALTER TABLE cx_platform_maintenance_tasks ENABLE ROW LEVEL SECURITY;
ALTER TABLE cx_platform_maintenance_attempts ENABLE ROW LEVEL SECURITY;
ALTER TABLE cx_platform_safe_autonomy_policies ENABLE ROW LEVEL SECURITY;
ALTER TABLE cx_platform_knowledge ENABLE ROW LEVEL SECURITY;
ALTER TABLE cx_platform_knowledge_chunks ENABLE ROW LEVEL SECURITY;
ALTER TABLE cx_platform_knowledge_grants ENABLE ROW LEVEL SECURITY;
ALTER TABLE cx_database_isolation_inventory ENABLE ROW LEVEL SECURITY;
ALTER TABLE cx_platform_commands FORCE ROW LEVEL SECURITY;
ALTER TABLE cx_platform_command_executors FORCE ROW LEVEL SECURITY;
ALTER TABLE cx_platform_safe_autonomy_policies FORCE ROW LEVEL SECURITY;
ALTER TABLE cx_platform_knowledge FORCE ROW LEVEL SECURITY;
ALTER TABLE cx_platform_knowledge_chunks FORCE ROW LEVEL SECURITY;
ALTER TABLE cx_platform_knowledge_grants FORCE ROW LEVEL SECURITY;
ALTER TABLE cx_database_isolation_inventory FORCE ROW LEVEL SECURITY;

DO $cx_platform_controlplane_revoke$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ai_agent_runtime') THEN
        EXECUTE 'REVOKE ALL PRIVILEGES ON TABLE public.cx_platform_commands, '
            || 'public.cx_platform_command_executors, public.cx_platform_maintenance_tasks, '
            || 'public.cx_platform_maintenance_attempts, public.cx_platform_safe_autonomy_policies, '
            || 'public.cx_platform_knowledge, public.cx_platform_knowledge_chunks, '
            || 'public.cx_platform_knowledge_grants, public.cx_database_isolation_inventory '
            || 'FROM ai_agent_runtime';
    END IF;
END
$cx_platform_controlplane_revoke$;

INSERT INTO cx_platform_safe_autonomy_policies(policy_id,state,reason,updated_by)
VALUES ('DEFAULT','DISABLED','v4.4.8 safe autonomy is disabled by default','SYSTEM_BOOTSTRAP')
ON CONFLICT (policy_id) DO NOTHING;
