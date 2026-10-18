-- v4.4.2 additive Embedding activation evidence and Graph capability profile.
-- Provider secrets and customer payloads are deliberately absent from this schema.
CREATE TABLE IF NOT EXISTS cx_graph_capability_profiles (
    profile_key varchar(64) PRIMARY KEY,
    profile_version varchar(32) NOT NULL,
    status varchar(24) NOT NULL DEFAULT 'ACTIVE',
    reason varchar(2000) NOT NULL,
    created_by varchar(128) NOT NULL,
    created_at timestamp NOT NULL DEFAULT current_timestamp,
    updated_at timestamp NOT NULL DEFAULT current_timestamp
);
CREATE TABLE IF NOT EXISTS cx_graph_capability_matrix (
    profile_key varchar(64) NOT NULL REFERENCES cx_graph_capability_profiles(profile_key),
    capability_key varchar(64) NOT NULL,
    state varchar(16) NOT NULL CHECK (state IN ('ENABLED','CONTROLLED','DISABLED','UNAVAILABLE')),
    version bigint NOT NULL DEFAULT 1 CHECK (version > 0),
    mandatory char(1) NOT NULL DEFAULT 'N' CHECK (mandatory IN ('Y','N')),
    evidence_ref varchar(256),
    reason varchar(2000) NOT NULL,
    effective_at timestamp NOT NULL DEFAULT current_timestamp,
    updated_by varchar(128) NOT NULL,
    updated_at timestamp NOT NULL DEFAULT current_timestamp,
    PRIMARY KEY (profile_key, capability_key)
);
CREATE TABLE IF NOT EXISTS cx_graph_capability_history (
    history_id varchar(128) PRIMARY KEY,
    profile_key varchar(64) NOT NULL,
    capability_key varchar(64) NOT NULL,
    from_state varchar(16) NOT NULL,
    to_state varchar(16) NOT NULL,
    expected_version bigint NOT NULL,
    evidence_ref varchar(256),
    reason varchar(2000) NOT NULL,
    changed_by varchar(128) NOT NULL,
    created_at timestamp NOT NULL DEFAULT current_timestamp
);
CREATE TABLE IF NOT EXISTS cx_embedding_activation_evidence (
    activation_id varchar(128) PRIMARY KEY,
    profile_id varchar(128) NOT NULL,
    profile_version bigint NOT NULL,
    observed_dimension bigint NOT NULL,
    observed_model varchar(256),
    response_digest varchar(128) NOT NULL,
    probe_status varchar(32) NOT NULL,
    activation_status varchar(32) NOT NULL,
    contract_id varchar(128),
    space_id varchar(128),
    binding_id varchar(128),
    migration_state varchar(32) NOT NULL DEFAULT 'NONE',
    reason varchar(2000) NOT NULL,
    actor varchar(128) NOT NULL,
    created_at timestamp NOT NULL DEFAULT current_timestamp
);
CREATE TABLE IF NOT EXISTS cx_admin_node_targets (
    target_id varchar(128) PRIMARY KEY,
    node_id varchar(256) NOT NULL,
    host_reference varchar(256) NOT NULL,
    ssh_port integer NOT NULL DEFAULT 22,
    os_user varchar(128) NOT NULL DEFAULT 'root',
    deployment_target varchar(128) NOT NULL DEFAULT 'LOCAL',
    ssh_trust_mode varchar(32) NOT NULL,
    public_key_digest varchar(128),
    failure_domain varchar(128),
    status varchar(32) NOT NULL DEFAULT 'CANDIDATE',
    reason varchar(2000) NOT NULL,
    created_by varchar(128) NOT NULL,
    created_at timestamp NOT NULL DEFAULT current_timestamp,
    updated_at timestamp NOT NULL DEFAULT current_timestamp
);
ALTER TABLE cx_admin_node_targets ADD COLUMN IF NOT EXISTS ssh_port integer NOT NULL DEFAULT 22;
ALTER TABLE cx_admin_node_targets ADD COLUMN IF NOT EXISTS os_user varchar(128) NOT NULL DEFAULT 'root';
ALTER TABLE cx_admin_node_targets ADD COLUMN IF NOT EXISTS deployment_target varchar(128) NOT NULL DEFAULT 'LOCAL';
CREATE TABLE IF NOT EXISTS cx_admin_deployment_attempts (
    attempt_id varchar(128) PRIMARY KEY,
    target_id varchar(128) NOT NULL,
    attempt_digest varchar(128) NOT NULL,
    verification_state varchar(32) NOT NULL,
    result_digest varchar(128),
    failure_code varchar(64),
    reason varchar(2000) NOT NULL,
    created_by varchar(128) NOT NULL,
    created_at timestamp NOT NULL DEFAULT current_timestamp
);
CREATE UNIQUE INDEX IF NOT EXISTS uk_cx_graph_active_profile ON cx_graph_capability_profiles(profile_key, status);
CREATE INDEX IF NOT EXISTS idx_cx_graph_matrix_state ON cx_graph_capability_matrix(profile_key,state);
CREATE INDEX IF NOT EXISTS idx_cx_embedding_activation ON cx_embedding_activation_evidence(profile_id,created_at);

INSERT INTO cx_graph_capability_profiles(profile_key,profile_version,status,reason,created_by)
VALUES ('PRODUCTION','4.4.2','ACTIVE','Initial v4.4.2 capability-level production profile','SYSTEM')
ON CONFLICT (profile_key) DO UPDATE SET profile_version=EXCLUDED.profile_version,status='ACTIVE';
INSERT INTO cx_graph_capability_matrix(profile_key,capability_key,state,mandatory,reason,updated_by)
VALUES
 ('PRODUCTION','graph_runtime_core','ENABLED','Y','Database-authoritative runtime core','SYSTEM'),
 ('PRODUCTION','graph_inspection','ENABLED','N','Authorized graph inspection','SYSTEM'),
 ('PRODUCTION','graph_manifest_draft_import','CONTROLLED','N','Signed imports remain Draft','SYSTEM'),
 ('PRODUCTION','graph_slo_readonly','CONTROLLED','N','Read-only SLO evidence','SYSTEM'),
 ('PRODUCTION','graph_checkpoint_fork','CONTROLLED','N','Protected checkpoint fork','SYSTEM'),
 ('PRODUCTION','graph_replay','DISABLED','N','Side effects and compensation evidence incomplete','SYSTEM'),
 ('PRODUCTION','a2a_gateway','DISABLED','N','A2A conformance evidence incomplete','SYSTEM'),
 ('PRODUCTION','otel_export','DISABLED','N','OTLP delivery evidence incomplete','SYSTEM'),
 ('PRODUCTION','graph_dynamic_migration','DISABLED','N','Migration rollback evidence incomplete','SYSTEM'),
 ('PRODUCTION','framework_adapter_execution','DISABLED','N','Framework imports remain non-executable','SYSTEM')
ON CONFLICT (profile_key,capability_key) DO NOTHING;
