-- v4.3.7 deterministic bootstrap deployment and Embedding governance.
INSERT INTO cx_platform_capabilities(capability_key,mandatory)
VALUES ('deployment_governance','Y'),('embedding_governance','Y'),('embedding_managed_worker','N')
ON CONFLICT (capability_key) DO NOTHING;
INSERT INTO cx_platform_capability_dependencies(capability_key,depends_on_key)
VALUES ('deployment_governance','audit_write'),('embedding_governance','agents'),
       ('embedding_governance','audit_write'),('embedding_managed_worker','embedding_governance')
ON CONFLICT (capability_key,depends_on_key) DO NOTHING;

CREATE TABLE IF NOT EXISTS cx_deployment_runs (
    run_id varchar(128) PRIMARY KEY,
    run_mode varchar(32) NOT NULL,
    database_dialect varchar(32) NOT NULL,
    edition varchar(32) NOT NULL,
    package_version varchar(32) NOT NULL,
    status varchar(64) NOT NULL,
    readiness_json text NOT NULL DEFAULT '{}',
    plan_digest varchar(64) NOT NULL,
    journal_digest varchar(128),
    deployment_agent_id varchar(128),
    current_step varchar(128),
    failure_code varchar(128),
    failure_detail varchar(2000),
    created_by varchar(128) NOT NULL,
    created_at timestamp NOT NULL DEFAULT current_timestamp,
    updated_at timestamp NOT NULL DEFAULT current_timestamp,
    completed_at timestamp
);
CREATE INDEX IF NOT EXISTS idx_cx_deployment_runs_status ON cx_deployment_runs(status, created_at);
CREATE TABLE IF NOT EXISTS cx_deployment_steps (
    step_id varchar(128) PRIMARY KEY,
    run_id varchar(128) NOT NULL,
    step_key varchar(128) NOT NULL,
    step_order integer NOT NULL,
    status varchar(64) NOT NULL,
    action_digest varchar(64) NOT NULL,
    result_json text NOT NULL DEFAULT '{}',
    error_code varchar(128),
    retry_class varchar(64) NOT NULL DEFAULT 'RETRYABLE',
    attempt_count integer NOT NULL DEFAULT 0,
    started_at timestamp,
    completed_at timestamp,
    created_at timestamp NOT NULL DEFAULT current_timestamp,
    updated_at timestamp NOT NULL DEFAULT current_timestamp,
    UNIQUE(run_id, step_key)
);
CREATE TABLE IF NOT EXISTS cx_deployment_evidence (
    evidence_id varchar(128) PRIMARY KEY,
    run_id varchar(128) NOT NULL,
    evidence_type varchar(64) NOT NULL,
    payload_json text NOT NULL,
    payload_digest varchar(64) NOT NULL,
    status varchar(32) NOT NULL DEFAULT 'RECORDED',
    created_at timestamp NOT NULL DEFAULT current_timestamp
);
CREATE INDEX IF NOT EXISTS idx_cx_deployment_evidence_run ON cx_deployment_evidence(run_id, created_at);
CREATE TABLE IF NOT EXISTS cx_deployment_leases (
    lease_key varchar(128) PRIMARY KEY,
    run_id varchar(128) NOT NULL,
    node_id varchar(128) NOT NULL,
    fencing_token bigint NOT NULL DEFAULT 1,
    lease_expires_at timestamp NOT NULL,
    status varchar(32) NOT NULL DEFAULT 'ACTIVE',
    updated_at timestamp NOT NULL DEFAULT current_timestamp
);

CREATE TABLE IF NOT EXISTS cx_embedding_profiles (
    profile_id varchar(128) PRIMARY KEY,
    profile_key varchar(128) NOT NULL UNIQUE,
    provider_url varchar(512),
    model_id varchar(256) NOT NULL,
    model_fingerprint varchar(256),
    api_key_cipher text,
    secret_reference varchar(512),
    execution_mode varchar(32) NOT NULL,
    dimension integer NOT NULL DEFAULT 0,
    distance_metric varchar(32) NOT NULL DEFAULT 'COSINE',
    normalize_vectors char(1) NOT NULL DEFAULT 'Y',
    preprocessing_json text NOT NULL DEFAULT '{}',
    modalities_json text NOT NULL DEFAULT '["TEXT"]',
    status varchar(32) NOT NULL DEFAULT 'DRAFT',
    health_state varchar(32) NOT NULL DEFAULT 'UNKNOWN',
    version bigint NOT NULL DEFAULT 1,
    updated_by varchar(128),
    update_reason varchar(2000),
    created_at timestamp NOT NULL DEFAULT current_timestamp,
    updated_at timestamp NOT NULL DEFAULT current_timestamp
);
CREATE TABLE IF NOT EXISTS cx_embedding_contracts (
    contract_id varchar(128) PRIMARY KEY,
    profile_id varchar(128) NOT NULL,
    contract_version bigint NOT NULL,
    provider_identity varchar(512),
    model_fingerprint varchar(256),
    dimension integer NOT NULL,
    distance_metric varchar(32) NOT NULL,
    normalize_vectors char(1) NOT NULL,
    preprocessing_json text NOT NULL,
    modalities_json text NOT NULL,
    execution_mode varchar(32) NOT NULL,
    status varchar(32) NOT NULL DEFAULT 'DRAFT',
    contract_digest varchar(64) NOT NULL,
    created_by varchar(128) NOT NULL,
    created_at timestamp NOT NULL DEFAULT current_timestamp,
    UNIQUE(profile_id, contract_version)
);
CREATE TABLE IF NOT EXISTS cx_embedding_spaces (
    space_id varchar(128) PRIMARY KEY,
    space_key varchar(128) NOT NULL UNIQUE,
    contract_id varchar(128),
    status varchar(32) NOT NULL DEFAULT 'DRAFT',
    is_default char(1) NOT NULL DEFAULT 'N',
    write_enabled char(1) NOT NULL DEFAULT 'N',
    validation_state varchar(32) NOT NULL DEFAULT 'UNVERIFIED',
    physical_ref varchar(256),
    created_by varchar(128) NOT NULL,
    reason varchar(2000),
    created_at timestamp NOT NULL DEFAULT current_timestamp,
    updated_at timestamp NOT NULL DEFAULT current_timestamp
);
CREATE TABLE IF NOT EXISTS cx_embedding_bindings (
    binding_id varchar(128) PRIMARY KEY,
    binding_scope varchar(32) NOT NULL,
    binding_subject_id varchar(128) NOT NULL,
    profile_id varchar(128),
    space_id varchar(128),
    status varchar(32) NOT NULL DEFAULT 'ACTIVE',
    version bigint NOT NULL DEFAULT 1,
    approved_by varchar(128),
    reason varchar(2000) NOT NULL,
    created_at timestamp NOT NULL DEFAULT current_timestamp,
    updated_at timestamp NOT NULL DEFAULT current_timestamp,
    UNIQUE(binding_scope, binding_subject_id)
);
CREATE TABLE IF NOT EXISTS cx_embedding_probes (
    probe_id varchar(128) PRIMARY KEY,
    profile_id varchar(128) NOT NULL,
    probe_scope varchar(32) NOT NULL,
    status varchar(32) NOT NULL,
    observed_dimension integer,
    observed_model varchar(256),
    observed_fingerprint varchar(256),
    result_json text NOT NULL DEFAULT '{}',
    error_code varchar(128),
    created_by varchar(128) NOT NULL,
    created_at timestamp NOT NULL DEFAULT current_timestamp
);
CREATE TABLE IF NOT EXISTS cx_embedding_jobs (
    job_id varchar(128) PRIMARY KEY,
    job_kind varchar(32) NOT NULL,
    source_space_id varchar(128),
    target_space_id varchar(128),
    status varchar(32) NOT NULL DEFAULT 'PENDING',
    requested_by varchar(128) NOT NULL,
    reason varchar(2000) NOT NULL,
    idempotency_key varchar(128) NOT NULL UNIQUE,
    input_json text NOT NULL DEFAULT '{}',
    result_json text NOT NULL DEFAULT '{}',
    worker_id varchar(128),
    lease_expires_at timestamp,
    fencing_token bigint NOT NULL DEFAULT 1,
    created_at timestamp NOT NULL DEFAULT current_timestamp,
    updated_at timestamp NOT NULL DEFAULT current_timestamp,
    completed_at timestamp
);
CREATE TABLE IF NOT EXISTS cx_embedding_history (
    history_id varchar(128) PRIMARY KEY,
    object_type varchar(32) NOT NULL,
    object_id varchar(128) NOT NULL,
    action varchar(64) NOT NULL,
    from_version bigint,
    to_version bigint,
    actor varchar(128) NOT NULL,
    reason varchar(2000) NOT NULL,
    detail_json text NOT NULL DEFAULT '{}',
    created_at timestamp NOT NULL DEFAULT current_timestamp
);

ALTER TABLE entity_embeddings ADD COLUMN IF NOT EXISTS embedding_space_id varchar(128) NOT NULL DEFAULT 'LEGACY_DEFAULT';
ALTER TABLE entity_embeddings ADD COLUMN IF NOT EXISTS embedding_profile_id varchar(128);
ALTER TABLE entity_embeddings ADD COLUMN IF NOT EXISTS embedding_contract_id varchar(128);
ALTER TABLE entity_embeddings ADD COLUMN IF NOT EXISTS content_digest varchar(64);
ALTER TABLE entity_embeddings ADD COLUMN IF NOT EXISTS source_mode varchar(32) NOT NULL DEFAULT 'LEGACY';
ALTER TABLE entity_embeddings ADD COLUMN IF NOT EXISTS validation_status varchar(32) NOT NULL DEFAULT 'UNVERIFIED';
ALTER TABLE entity_embeddings DROP CONSTRAINT IF EXISTS pk_entity_embeddings;
ALTER TABLE entity_embeddings ADD CONSTRAINT pk_entity_embeddings PRIMARY KEY (entity_id, entity_type, embedding_space_id);
CREATE INDEX IF NOT EXISTS idx_ee_space_contract ON entity_embeddings(embedding_space_id, embedding_contract_id);

INSERT INTO cx_embedding_spaces(space_id,space_key,status,is_default,write_enabled,validation_state,created_by,reason)
VALUES ('SPACE_LEGACY_DEFAULT','LEGACY_DEFAULT','ARCHIVED','N','N','UNVERIFIED','SYSTEM_MIGRATION','v4.3.7 adoption of existing vectors')
ON CONFLICT (space_key) DO NOTHING;
