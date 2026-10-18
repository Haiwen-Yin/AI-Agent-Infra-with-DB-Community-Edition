-- v4.3.0 security lifecycle: identity linking, MFA, delegation, Agent
-- ownership review, instance containment, content evidence and connectors.

ALTER TABLE cx_principals ADD COLUMN IF NOT EXISTS mfa_required boolean NOT NULL DEFAULT false;
ALTER TABLE cx_human_identities ADD COLUMN IF NOT EXISTS failed_login_count integer NOT NULL DEFAULT 0;
ALTER TABLE cx_human_identities ADD COLUMN IF NOT EXISTS locked_until timestamp;
ALTER TABLE cx_human_identities ADD COLUMN IF NOT EXISTS user_id varchar(128);
ALTER TABLE cx_enrollment_grants ADD COLUMN IF NOT EXISTS agent_id varchar(128);

CREATE TABLE IF NOT EXISTS cx_mfa_factors (
    factor_id varchar(128) PRIMARY KEY, principal_id varchar(128) NOT NULL,
    factor_type varchar(32) NOT NULL, secret_ciphertext text,
    credential_ref varchar(512), status varchar(32) NOT NULL DEFAULT 'PENDING',
    verified_at timestamp, last_used_at timestamp, created_at timestamp NOT NULL DEFAULT current_timestamp
);
CREATE TABLE IF NOT EXISTS cx_mfa_recovery_codes (
    code_id varchar(128) PRIMARY KEY, principal_id varchar(128) NOT NULL,
    code_digest varchar(128) NOT NULL UNIQUE, status varchar(32) NOT NULL DEFAULT 'ACTIVE',
    used_at timestamp, created_at timestamp NOT NULL DEFAULT current_timestamp
);
CREATE TABLE IF NOT EXISTS cx_password_reset_tokens (
    token_id varchar(128) PRIMARY KEY, principal_id varchar(128) NOT NULL,
    token_digest varchar(128) NOT NULL UNIQUE, purpose varchar(32) NOT NULL,
    expires_at timestamp NOT NULL, consumed_at timestamp, created_at timestamp NOT NULL DEFAULT current_timestamp
);
CREATE TABLE IF NOT EXISTS cx_identity_link_audit (
    link_event_id varchar(128) PRIMARY KEY, identity_id varchar(128),
    principal_id varchar(128) NOT NULL, actor_principal_id varchar(128) NOT NULL,
    provider varchar(256) NOT NULL, subject_digest varchar(128) NOT NULL,
    reason varchar(2000) NOT NULL, outcome varchar(32) NOT NULL,
    created_at timestamp NOT NULL DEFAULT current_timestamp
);
CREATE TABLE IF NOT EXISTS cx_delegations (
    delegation_id varchar(128) PRIMARY KEY, grantor_principal_id varchar(128) NOT NULL,
    grantee_principal_id varchar(128) NOT NULL, permissions_json text NOT NULL,
    data_scope varchar(32) NOT NULL, valid_until timestamp, reason varchar(2000) NOT NULL,
    status varchar(32) NOT NULL DEFAULT 'ACTIVE', version bigint NOT NULL DEFAULT 1,
    created_at timestamp NOT NULL DEFAULT current_timestamp, revoked_at timestamp
);
CREATE TABLE IF NOT EXISTS cx_agent_quotas (
    quota_id varchar(128) PRIMARY KEY, scope_type varchar(32) NOT NULL,
    scope_id varchar(128) NOT NULL, environment varchar(64) NOT NULL,
    max_agents bigint NOT NULL DEFAULT 0, used_agents bigint NOT NULL DEFAULT 0,
    max_active_instances bigint NOT NULL DEFAULT 0, used_active_instances bigint NOT NULL DEFAULT 0,
    status varchar(32) NOT NULL DEFAULT 'ACTIVE', updated_at timestamp NOT NULL DEFAULT current_timestamp,
    UNIQUE(scope_type, scope_id, environment)
);
CREATE TABLE IF NOT EXISTS cx_agent_ownership_history (
    history_id varchar(128) PRIMARY KEY, agent_id varchar(128) NOT NULL,
    old_owner_principal_id varchar(128), new_owner_principal_id varchar(128),
    actor_principal_id varchar(128) NOT NULL, policy_version bigint,
    credential_rotated boolean NOT NULL DEFAULT false, grants_reevaluated boolean NOT NULL DEFAULT false,
    reason varchar(2000) NOT NULL, created_at timestamp NOT NULL DEFAULT current_timestamp
);
CREATE TABLE IF NOT EXISTS cx_agent_legacy_reviews (
    review_id varchar(128) PRIMARY KEY, agent_id varchar(128) NOT NULL,
    classification varchar(32) NOT NULL, evidence_json text NOT NULL,
    status varchar(32) NOT NULL DEFAULT 'OPEN', claimed_by varchar(128),
    claim_reason varchar(2000), decided_at timestamp, created_at timestamp NOT NULL DEFAULT current_timestamp
);
CREATE TABLE IF NOT EXISTS cx_agent_derived_objects (
    derived_object_id varchar(128) PRIMARY KEY, agent_id varchar(128) NOT NULL,
    instance_id varchar(128), object_type varchar(64) NOT NULL, object_id varchar(128) NOT NULL,
    status varchar(32) NOT NULL DEFAULT 'ACTIVE', created_at timestamp NOT NULL DEFAULT current_timestamp,
    revoked_at timestamp, revoke_reason varchar(2000)
);
CREATE TABLE IF NOT EXISTS cx_channel_deletion_evidence (
    evidence_id varchar(128) PRIMARY KEY, channel_id varchar(128) NOT NULL,
    actor_principal_id varchar(128) NOT NULL, from_status varchar(32) NOT NULL,
    to_status varchar(32) NOT NULL, reference_count bigint NOT NULL DEFAULT 0,
    reason varchar(2000) NOT NULL, detail_json text NOT NULL,
    created_at timestamp NOT NULL DEFAULT current_timestamp
);
CREATE TABLE IF NOT EXISTS cx_memory_artifact_links (
    link_id varchar(128) PRIMARY KEY, candidate_id varchar(128) NOT NULL,
    artifact_id varchar(128) NOT NULL, destination_scope varchar(32) NOT NULL,
    status varchar(32) NOT NULL DEFAULT 'ACTIVE', created_at timestamp NOT NULL DEFAULT current_timestamp
);
CREATE TABLE IF NOT EXISTS cx_bridge_connectors (
    connector_id varchar(128) PRIMARY KEY, bridge_id varchar(128) NOT NULL,
    connector_mode varchar(32) NOT NULL, endpoint_ref varchar(512) NOT NULL,
    metadata_only boolean NOT NULL DEFAULT true, status varchar(32) NOT NULL DEFAULT 'ACTIVE',
    reason varchar(2000) NOT NULL, created_at timestamp NOT NULL DEFAULT current_timestamp
);

CREATE INDEX IF NOT EXISTS idx_cx_mfa_principal ON cx_mfa_factors(principal_id, status);
CREATE INDEX IF NOT EXISTS idx_cx_reset_active ON cx_password_reset_tokens(token_digest, expires_at, consumed_at);
CREATE INDEX IF NOT EXISTS idx_cx_agent_review_status ON cx_agent_legacy_reviews(status, classification, created_at);
CREATE INDEX IF NOT EXISTS idx_cx_derived_agent ON cx_agent_derived_objects(agent_id, instance_id, status);
CREATE INDEX IF NOT EXISTS idx_cx_enrollment_agent ON cx_enrollment_grants(agent_id, status);

ALTER TABLE cx_mfa_factors ENABLE ROW LEVEL SECURITY;
ALTER TABLE cx_mfa_recovery_codes ENABLE ROW LEVEL SECURITY;
ALTER TABLE cx_password_reset_tokens ENABLE ROW LEVEL SECURITY;
ALTER TABLE cx_delegations ENABLE ROW LEVEL SECURITY;
ALTER TABLE cx_agent_legacy_reviews ENABLE ROW LEVEL SECURITY;
ALTER TABLE cx_agent_derived_objects ENABLE ROW LEVEL SECURITY;
ALTER TABLE cx_mfa_factors FORCE ROW LEVEL SECURITY;
ALTER TABLE cx_mfa_recovery_codes FORCE ROW LEVEL SECURITY;
ALTER TABLE cx_password_reset_tokens FORCE ROW LEVEL SECURITY;
ALTER TABLE cx_delegations FORCE ROW LEVEL SECURITY;
ALTER TABLE cx_agent_legacy_reviews FORCE ROW LEVEL SECURITY;
ALTER TABLE cx_agent_derived_objects FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS cx_mfa_factor_owner ON cx_mfa_factors;
CREATE POLICY cx_mfa_factor_owner ON cx_mfa_factors USING (principal_id = public.current_agent_identity()) WITH CHECK (principal_id = public.current_agent_identity());
DROP POLICY IF EXISTS cx_mfa_recovery_owner ON cx_mfa_recovery_codes;
CREATE POLICY cx_mfa_recovery_owner ON cx_mfa_recovery_codes USING (principal_id = public.current_agent_identity()) WITH CHECK (principal_id = public.current_agent_identity());
DROP POLICY IF EXISTS cx_reset_owner ON cx_password_reset_tokens;
CREATE POLICY cx_reset_owner ON cx_password_reset_tokens USING (principal_id = public.current_agent_identity()) WITH CHECK (principal_id = public.current_agent_identity());
DROP POLICY IF EXISTS cx_delegation_member ON cx_delegations;
CREATE POLICY cx_delegation_member ON cx_delegations USING (grantor_principal_id = public.current_agent_identity() OR grantee_principal_id = public.current_agent_identity()) WITH CHECK (grantor_principal_id = public.current_agent_identity());
DROP POLICY IF EXISTS cx_legacy_review_scope ON cx_agent_legacy_reviews;
CREATE POLICY cx_legacy_review_scope ON cx_agent_legacy_reviews USING (EXISTS (SELECT 1 FROM public.cx_agent_relationships r WHERE r.agent_id = cx_agent_legacy_reviews.agent_id AND r.principal_id = public.current_agent_identity() AND r.status = 'ACTIVE')) WITH CHECK (true);
DROP POLICY IF EXISTS cx_derived_instance_scope ON cx_agent_derived_objects;
CREATE POLICY cx_derived_instance_scope ON cx_agent_derived_objects USING (agent_id = public.current_agent_identity() OR EXISTS (SELECT 1 FROM public.cx_agent_relationships r WHERE r.agent_id = cx_agent_derived_objects.agent_id AND r.principal_id = public.current_agent_identity() AND r.status = 'ACTIVE')) WITH CHECK (agent_id = public.current_agent_identity());
