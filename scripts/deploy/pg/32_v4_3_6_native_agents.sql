-- v4.3.6 platform-native Agent bootstrap, provisioning, LLM and runtime contracts.
INSERT INTO cx_platform_capabilities(capability_key,mandatory)
VALUES ('agent_provisioning','N')
ON CONFLICT (capability_key) DO NOTHING;
INSERT INTO cx_platform_capability_dependencies(capability_key,depends_on_key)
VALUES ('agent_provisioning','agents'),('agent_provisioning','audit_write')
ON CONFLICT (capability_key,depends_on_key) DO NOTHING;
CREATE TABLE IF NOT EXISTS cx_native_bootstrap (
    bootstrap_key varchar(64) PRIMARY KEY,
    bootstrap_version varchar(32) NOT NULL,
    status varchar(32) NOT NULL,
    started_at timestamp NOT NULL DEFAULT current_timestamp,
    completed_at timestamp,
    updated_at timestamp NOT NULL DEFAULT current_timestamp
);
CREATE TABLE IF NOT EXISTS cx_agent_templates (
    template_id varchar(128) PRIMARY KEY,
    template_key varchar(128) NOT NULL UNIQUE,
    display_name varchar(256) NOT NULL,
    template_kind varchar(64) NOT NULL,
    content_json text NOT NULL,
    content_digest varchar(64) NOT NULL,
    locked_fields_json text NOT NULL,
    status varchar(32) NOT NULL DEFAULT 'DRAFT',
    managed char(1) NOT NULL DEFAULT 'N',
    created_by varchar(128) NOT NULL,
    created_at timestamp NOT NULL DEFAULT current_timestamp,
    updated_at timestamp NOT NULL DEFAULT current_timestamp
);
CREATE TABLE IF NOT EXISTS cx_native_manifests (
    manifest_id varchar(128) PRIMARY KEY,
    manifest_key varchar(128) NOT NULL,
    version integer NOT NULL DEFAULT 1,
    manifest_kind varchar(32) NOT NULL,
    content_json text NOT NULL,
    content_digest varchar(64) NOT NULL,
    signature varchar(256) NOT NULL,
    signature_status varchar(32) NOT NULL DEFAULT 'UNVERIFIED',
    status varchar(32) NOT NULL DEFAULT 'DRAFT',
    managed char(1) NOT NULL DEFAULT 'N',
    created_by varchar(128) NOT NULL,
    created_at timestamp NOT NULL DEFAULT current_timestamp,
    updated_at timestamp NOT NULL DEFAULT current_timestamp,
    UNIQUE (manifest_key, version)
);
CREATE TABLE IF NOT EXISTS cx_native_agents (
    agent_id varchar(128) PRIMARY KEY,
    source varchar(32) NOT NULL,
    agent_kind varchar(64) NOT NULL,
    template_id varchar(128),
    owner_principal_id varchar(128),
    status varchar(32) NOT NULL,
    activation_state varchar(32) NOT NULL,
    llm_profile_id varchar(128),
    deployment_target_id varchar(128),
    security_domain_id varchar(128) NOT NULL DEFAULT 'DEFAULT',
    is_protected char(1) NOT NULL DEFAULT 'N',
    created_by varchar(128) NOT NULL,
    created_at timestamp NOT NULL DEFAULT current_timestamp,
    updated_at timestamp NOT NULL DEFAULT current_timestamp
);
CREATE INDEX IF NOT EXISTS idx_cx_native_agents_state ON cx_native_agents(status, activation_state);
CREATE TABLE IF NOT EXISTS cx_llm_provider_profiles (
    profile_id varchar(128) PRIMARY KEY,
    profile_key varchar(128) NOT NULL UNIQUE,
    provider_url varchar(512) NOT NULL,
    model_id varchar(256) NOT NULL,
    api_key_cipher text,
    secret_present char(1) NOT NULL DEFAULT 'N',
    health_state varchar(32) NOT NULL DEFAULT 'UNKNOWN',
    status varchar(32) NOT NULL DEFAULT 'ACTIVE',
    version bigint NOT NULL DEFAULT 1,
    approved_for_json text NOT NULL DEFAULT '[]',
    updated_by varchar(128),
    update_reason varchar(2000),
    created_at timestamp NOT NULL DEFAULT current_timestamp,
    updated_at timestamp NOT NULL DEFAULT current_timestamp
);
CREATE TABLE IF NOT EXISTS cx_deployment_targets (
    target_id varchar(128) PRIMARY KEY,
    target_key varchar(128) NOT NULL UNIQUE,
    target_type varchar(64) NOT NULL,
    config_json text NOT NULL,
    status varchar(32) NOT NULL DEFAULT 'ACTIVE',
    managed char(1) NOT NULL DEFAULT 'N',
    created_by varchar(128) NOT NULL,
    created_at timestamp NOT NULL DEFAULT current_timestamp,
    updated_at timestamp NOT NULL DEFAULT current_timestamp
);
CREATE TABLE IF NOT EXISTS cx_native_provision_requests (
    request_id varchar(128) PRIMARY KEY,
    agent_name varchar(256) NOT NULL,
    applicant_principal_id varchar(128) NOT NULL,
    owner_principal_id varchar(128) NOT NULL,
    template_key varchar(128) NOT NULL,
    llm_profile_id varchar(128),
    deployment_target_id varchar(128),
    isolation_level varchar(32) NOT NULL,
    classification varchar(32) NOT NULL,
    purpose varchar(2000) NOT NULL,
    reason varchar(2000) NOT NULL,
    status varchar(32) NOT NULL DEFAULT 'APPROVAL_PENDING',
    decided_by varchar(128),
    decision_reason varchar(2000),
    decided_at timestamp,
    created_at timestamp NOT NULL DEFAULT current_timestamp,
    updated_at timestamp NOT NULL DEFAULT current_timestamp
);
CREATE INDEX IF NOT EXISTS idx_cx_native_request_status ON cx_native_provision_requests(status, created_at);
CREATE TABLE IF NOT EXISTS cx_runtime_workers (
    worker_id varchar(128) PRIMARY KEY,
    node_id varchar(128) NOT NULL,
    target_type varchar(64) NOT NULL,
    status varchar(32) NOT NULL DEFAULT 'ONLINE',
    capabilities_json text NOT NULL DEFAULT '{}',
    lease_expires_at timestamp,
    fencing_token bigint NOT NULL DEFAULT 1,
    last_seen_at timestamp NOT NULL DEFAULT current_timestamp,
    created_at timestamp NOT NULL DEFAULT current_timestamp,
    updated_at timestamp NOT NULL DEFAULT current_timestamp
);
CREATE TABLE IF NOT EXISTS cx_runtime_executions (
    execution_id varchar(128) PRIMARY KEY,
    agent_id varchar(128) NOT NULL,
    target_id varchar(128),
    isolation_level varchar(32) NOT NULL,
    status varchar(32) NOT NULL DEFAULT 'PENDING',
    worker_id varchar(128),
    node_id varchar(128),
    context_digest varchar(64),
    workspace_ref varchar(256),
    token_digest varchar(128),
    input_json text NOT NULL DEFAULT '{}',
    output_json text,
    lease_expires_at timestamp,
    fencing_token bigint NOT NULL DEFAULT 1,
    failure_reason varchar(2000),
    started_at timestamp,
    completed_at timestamp,
    created_at timestamp NOT NULL DEFAULT current_timestamp,
    updated_at timestamp NOT NULL DEFAULT current_timestamp
);
CREATE INDEX IF NOT EXISTS idx_cx_runtime_exec_lease ON cx_runtime_executions(status, lease_expires_at, created_at);
CREATE TABLE IF NOT EXISTS cx_external_agent_policy (
    policy_key varchar(64) PRIMARY KEY,
    state varchar(32) NOT NULL DEFAULT 'ENABLED',
    version bigint NOT NULL DEFAULT 1,
    updated_by varchar(128),
    reason varchar(2000) NOT NULL,
    updated_at timestamp NOT NULL DEFAULT current_timestamp
);
CREATE TABLE IF NOT EXISTS cx_external_agent_policy_history (
    history_id varchar(128) PRIMARY KEY,
    policy_key varchar(64) NOT NULL,
    from_state varchar(32) NOT NULL,
    to_state varchar(32) NOT NULL,
    result_version bigint NOT NULL,
    changed_by varchar(128) NOT NULL,
    reason varchar(2000) NOT NULL,
    created_at timestamp NOT NULL DEFAULT current_timestamp
);
INSERT INTO cx_external_agent_policy(policy_key,state,version,updated_by,reason)
VALUES ('external_agent_registration','ENABLED',1,'SYSTEM_BOOTSTRAP','preserve existing Skill-first registration')
ON CONFLICT (policy_key) DO NOTHING;
