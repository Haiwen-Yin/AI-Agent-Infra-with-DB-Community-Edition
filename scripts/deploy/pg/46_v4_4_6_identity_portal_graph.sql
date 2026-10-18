-- v4.4.6 configurable Human registration, external identity transactions,
-- Portal connection/page leases, and Graph capability posture.
ALTER TABLE cx_human_identities ADD COLUMN IF NOT EXISTS mobile varchar(64);
ALTER TABLE cx_registration_requests ADD COLUMN IF NOT EXISTS mobile varchar(64);
ALTER TABLE cx_registration_requests ADD COLUMN IF NOT EXISTS registration_token_id varchar(128);
ALTER TABLE cx_registration_requests ADD COLUMN IF NOT EXISTS policy_version bigint;

CREATE TABLE IF NOT EXISTS cx_human_profiles (
    principal_id varchar(128) PRIMARY KEY,
    display_name varchar(256) NOT NULL,
    email varchar(320),
    mobile varchar(64),
    remediation_state varchar(32) NOT NULL DEFAULT 'CLEAR',
    remediation_due_at timestamp,
    version bigint NOT NULL DEFAULT 1,
    updated_by varchar(128),
    updated_at timestamp NOT NULL DEFAULT current_timestamp
);
CREATE TABLE IF NOT EXISTS cx_registration_field_policies (
    policy_id varchar(128) PRIMARY KEY,
    field_key varchar(64) NOT NULL,
    registration_context varchar(32) NOT NULL,
    field_state varchar(16) NOT NULL,
    visible boolean NOT NULL DEFAULT true,
    mutable_after_activation boolean NOT NULL DEFAULT true,
    validator_key varchar(128) NOT NULL,
    normalization_key varchar(128) NOT NULL,
    version bigint NOT NULL DEFAULT 1,
    reason varchar(2000) NOT NULL,
    updated_by varchar(128) NOT NULL,
    updated_at timestamp NOT NULL DEFAULT current_timestamp,
    UNIQUE(field_key, registration_context),
    CHECK (field_state IN ('REQUIRED','OPTIONAL','DISABLED'))
);
CREATE TABLE IF NOT EXISTS cx_identity_platform_policies (
    policy_key varchar(128) PRIMARY KEY,
    policy_value varchar(4000) NOT NULL,
    version bigint NOT NULL DEFAULT 1,
    reason varchar(2000) NOT NULL,
    updated_by varchar(128),
    updated_at timestamp NOT NULL DEFAULT current_timestamp
);
CREATE TABLE IF NOT EXISTS cx_human_registration_tokens (
    token_id varchar(128) PRIMARY KEY,
    token_digest varchar(128) NOT NULL UNIQUE,
    purpose varchar(32) NOT NULL DEFAULT 'HUMAN_REGISTRATION',
    sponsor_principal_id varchar(128) NOT NULL,
    intended_constraints_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    expires_at timestamp NOT NULL,
    max_uses integer NOT NULL DEFAULT 1,
    used_count integer NOT NULL DEFAULT 0,
    revoked_at timestamp,
    created_at timestamp NOT NULL DEFAULT current_timestamp,
    reason varchar(2000) NOT NULL,
    CHECK (purpose = 'HUMAN_REGISTRATION'),
    CHECK (max_uses = 1),
    CHECK (used_count >= 0 AND used_count <= max_uses)
);
CREATE TABLE IF NOT EXISTS cx_identity_providers (
    provider_id varchar(128) PRIMARY KEY,
    provider_key varchar(128) NOT NULL UNIQUE,
    adapter_type varchar(128) NOT NULL,
    protocol_type varchar(64) NOT NULL,
    issuer varchar(512),
    tenant_reference varchar(256),
    endpoints_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    redirect_allowlist_json jsonb NOT NULL DEFAULT '[]'::jsonb,
    scopes_json jsonb NOT NULL DEFAULT '[]'::jsonb,
    credential_reference varchar(256),
    attribute_mapping_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    registration_policy varchar(32) NOT NULL DEFAULT 'APPROVAL',
    capability_status varchar(24) NOT NULL DEFAULT 'UNAVAILABLE',
    version bigint NOT NULL DEFAULT 1,
    status varchar(24) NOT NULL DEFAULT 'DISABLED',
    updated_by varchar(128),
    updated_at timestamp NOT NULL DEFAULT current_timestamp
);
CREATE TABLE IF NOT EXISTS cx_external_identity_bindings (
    binding_id varchar(128) PRIMARY KEY,
    principal_id varchar(128) NOT NULL,
    provider_id varchar(128) NOT NULL,
    provider_tenant varchar(256) NOT NULL,
    provider_subject varchar(512) NOT NULL,
    provider_global_subject varchar(512),
    claims_digest varchar(128) NOT NULL,
    claims_snapshot_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    status varchar(24) NOT NULL DEFAULT 'PENDING',
    version bigint NOT NULL DEFAULT 1,
    first_login_at timestamp,
    last_login_at timestamp,
    created_at timestamp NOT NULL DEFAULT current_timestamp,
    UNIQUE(provider_id, provider_tenant, provider_subject)
);
CREATE TABLE IF NOT EXISTS cx_external_login_transactions (
    transaction_id varchar(128) PRIMARY KEY,
    transaction_digest varchar(128) NOT NULL UNIQUE,
    provider_id varchar(128) NOT NULL,
    entry varchar(16) NOT NULL,
    state_digest varchar(128) NOT NULL,
    nonce_digest varchar(128) NOT NULL,
    pkce_reference varchar(256),
    qr_reference varchar(512),
    expires_at timestamp NOT NULL,
    status varchar(24) NOT NULL DEFAULT 'STARTED',
    attempts integer NOT NULL DEFAULT 0,
    callback_digest varchar(128),
    failure_code varchar(128),
    consumed_at timestamp,
    created_at timestamp NOT NULL DEFAULT current_timestamp,
    CHECK (entry IN ('PORTAL','APP'))
);
CREATE TABLE IF NOT EXISTS cx_portal_connection_policies (
    principal_id varchar(128) PRIMARY KEY,
    max_connections integer NOT NULL DEFAULT 1,
    version bigint NOT NULL DEFAULT 1,
    reason varchar(2000) NOT NULL,
    updated_by varchar(128) NOT NULL,
    updated_at timestamp NOT NULL DEFAULT current_timestamp,
    CHECK (max_connections BETWEEN 1 AND 32)
);
CREATE TABLE IF NOT EXISTS cx_portal_connections (
    connection_id varchar(128) PRIMARY KEY,
    principal_id varchar(128) NOT NULL,
    session_digest varchar(128) NOT NULL UNIQUE,
    client_instance_digest varchar(128) NOT NULL,
    node_id varchar(128) NOT NULL,
    status varchar(24) NOT NULL DEFAULT 'ACTIVE',
    fencing_token bigint NOT NULL DEFAULT 1,
    lease_expires_at timestamp NOT NULL,
    last_heartbeat_at timestamp NOT NULL DEFAULT current_timestamp,
    created_at timestamp NOT NULL DEFAULT current_timestamp,
    released_at timestamp,
    release_reason varchar(1000)
);
CREATE INDEX IF NOT EXISTS idx_cx_portal_conn_principal ON cx_portal_connections(principal_id, status, lease_expires_at);
CREATE TABLE IF NOT EXISTS cx_portal_page_leases (
    lease_id varchar(128) PRIMARY KEY,
    connection_id varchar(128) NOT NULL UNIQUE,
    session_digest varchar(128) NOT NULL UNIQUE,
    page_instance_digest varchar(128) NOT NULL,
    fencing_token bigint NOT NULL DEFAULT 1,
    status varchar(24) NOT NULL DEFAULT 'ACTIVE',
    lease_expires_at timestamp NOT NULL,
    last_heartbeat_at timestamp NOT NULL DEFAULT current_timestamp,
    created_at timestamp NOT NULL DEFAULT current_timestamp
);
CREATE TABLE IF NOT EXISTS cx_graph_capability_posture (
    capability_key varchar(128) PRIMARY KEY,
    posture varchar(24) NOT NULL,
    evidence_id varchar(256),
    implementation_version varchar(64),
    limitation_text varchar(2000),
    edition_scope varchar(64) NOT NULL DEFAULT 'ALL',
    updated_at timestamp NOT NULL DEFAULT current_timestamp,
    CHECK (posture IN ('PRODUCTION','CONTROLLED','DISABLED','UNAVAILABLE'))
);

INSERT INTO cx_identity_platform_policies(policy_key, policy_value, reason)
VALUES ('human_registration_token_required','false','v4.4.6 default preserves existing registration behavior')
ON CONFLICT (policy_key) DO NOTHING;
INSERT INTO cx_identity_platform_policies(policy_key, policy_value, reason)
VALUES ('portal_connection_platform_max','8','v4.4.6 bounded Portal concurrency')
ON CONFLICT (policy_key) DO NOTHING;
INSERT INTO cx_registration_field_policies(policy_id,field_key,registration_context,field_state,validator_key,normalization_key,reason,updated_by)
VALUES ('RFP-DISPLAY-SELF','display_name','SELF','REQUIRED','DISPLAY_NAME','TRIM','v4.4.6 default','SYSTEM')
ON CONFLICT (field_key,registration_context) DO NOTHING;
INSERT INTO cx_registration_field_policies(policy_id,field_key,registration_context,field_state,validator_key,normalization_key,reason,updated_by)
VALUES ('RFP-EMAIL-SELF','email','SELF','OPTIONAL','EMAIL','EMAIL_LOWER','v4.4.6 default','SYSTEM')
ON CONFLICT (field_key,registration_context) DO NOTHING;
INSERT INTO cx_registration_field_policies(policy_id,field_key,registration_context,field_state,validator_key,normalization_key,reason,updated_by)
VALUES ('RFP-MOBILE-SELF','mobile','SELF','OPTIONAL','MOBILE','E164','v4.4.6 default','SYSTEM')
ON CONFLICT (field_key,registration_context) DO NOTHING;
INSERT INTO cx_graph_capability_posture(capability_key,posture,limitation_text)
VALUES ('graph-runtime','CONTROLLED','v4.4.6 evidence gate pending') ON CONFLICT (capability_key) DO NOTHING;
INSERT INTO cx_graph_capability_posture(capability_key,posture,limitation_text)
VALUES ('dynamic-graph','CONTROLLED','Requires governed Draft and migration evidence') ON CONFLICT (capability_key) DO NOTHING;
INSERT INTO cx_graph_capability_posture(capability_key,posture,limitation_text)
VALUES ('a2a','DISABLED','Enable only after current conformance evidence') ON CONFLICT (capability_key) DO NOTHING;
INSERT INTO cx_graph_capability_posture(capability_key,posture,limitation_text)
VALUES ('mcp','CONTROLLED','Protocol metadata is not an authority grant') ON CONFLICT (capability_key) DO NOTHING;
INSERT INTO cx_graph_capability_posture(capability_key,posture,limitation_text)
VALUES ('otlp','DISABLED','Enable only after redaction and Collector evidence') ON CONFLICT (capability_key) DO NOTHING;
INSERT INTO cx_graph_capability_posture(capability_key,posture,limitation_text)
VALUES ('evaluation','CONTROLLED','Recommendations require governed review') ON CONFLICT (capability_key) DO NOTHING;
