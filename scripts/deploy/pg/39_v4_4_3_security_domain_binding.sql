-- v4.4.3 governed Security Domain administration and legacy collaboration-group binding.
-- A collaboration group is not an authorization boundary; its members remain draft candidates only.
CREATE TABLE IF NOT EXISTS cx_domain_governance (
    security_domain_id varchar(128) PRIMARY KEY REFERENCES cx_security_domains(security_domain_id),
    owner_principal_id varchar(128) NOT NULL,
    reason varchar(2000) NOT NULL,
    updated_by varchar(128) NOT NULL,
    updated_at timestamp NOT NULL DEFAULT current_timestamp
);
CREATE TABLE IF NOT EXISTS cx_domain_bindings (
    binding_id varchar(128) PRIMARY KEY,
    security_domain_id varchar(128) NOT NULL REFERENCES cx_security_domains(security_domain_id),
    binding_type varchar(32) NOT NULL CHECK (binding_type IN ('CHANNEL','LEGACY_COLLAB_GROUP')),
    target_id varchar(128) NOT NULL,
    status varchar(32) NOT NULL DEFAULT 'DRAFT' CHECK (status IN ('DRAFT','ACTIVE','SUSPENDED','REVOKED','SUPERSEDED')),
    reason varchar(2000) NOT NULL,
    approval_ref varchar(256),
    created_by varchar(128) NOT NULL,
    created_at timestamp NOT NULL DEFAULT current_timestamp,
    updated_at timestamp NOT NULL DEFAULT current_timestamp
);
CREATE UNIQUE INDEX IF NOT EXISTS uk_cx_domain_binding_active_group
    ON cx_domain_bindings(target_id) WHERE binding_type='LEGACY_COLLAB_GROUP' AND status='ACTIVE';
CREATE UNIQUE INDEX IF NOT EXISTS uk_cx_domain_binding_active_target
    ON cx_domain_bindings(security_domain_id,binding_type,target_id) WHERE status='ACTIVE';
CREATE INDEX IF NOT EXISTS idx_cx_domain_bindings_domain ON cx_domain_bindings(security_domain_id,status,created_at);
CREATE TABLE IF NOT EXISTS cx_domain_conversion_drafts (
    draft_id varchar(128) PRIMARY KEY,
    source_group_id varchar(128) NOT NULL,
    proposed_domain_id varchar(128) NOT NULL,
    domain_name varchar(256) NOT NULL,
    classification varchar(32) NOT NULL,
    purpose varchar(1000) NOT NULL,
    owner_principal_id varchar(128) NOT NULL,
    snapshot_json text NOT NULL,
    status varchar(32) NOT NULL DEFAULT 'DRAFT' CHECK (status IN ('DRAFT','REVIEW','APPROVED','APPLIED','REJECTED','EXPIRED','FAILED')),
    reason varchar(2000) NOT NULL,
    approval_ref varchar(256),
    created_by varchar(128) NOT NULL,
    applied_by varchar(128),
    applied_at timestamp,
    created_at timestamp NOT NULL DEFAULT current_timestamp,
    updated_at timestamp NOT NULL DEFAULT current_timestamp
);
CREATE INDEX IF NOT EXISTS idx_cx_domain_conversion_group ON cx_domain_conversion_drafts(source_group_id,status,created_at);
CREATE TABLE IF NOT EXISTS cx_domain_draft_members (
    draft_member_id varchar(128) PRIMARY KEY,
    draft_id varchar(128) NOT NULL REFERENCES cx_domain_conversion_drafts(draft_id),
    principal_id varchar(128) NOT NULL,
    principal_type varchar(16) NOT NULL CHECK (principal_type IN ('HUMAN','AGENT')),
    membership_tier varchar(32) NOT NULL DEFAULT 'MEMBER',
    valid_until timestamp,
    decision varchar(32) NOT NULL DEFAULT 'PENDING' CHECK (decision IN ('PENDING','CONFIRMED','REJECTED')),
    reviewed_by varchar(128),
    reviewed_at timestamp,
    review_reason varchar(2000),
    UNIQUE(draft_id,principal_id)
);
CREATE INDEX IF NOT EXISTS idx_cx_domain_draft_members ON cx_domain_draft_members(draft_id,decision,principal_type);
-- Runtime Agents access governed collaboration only through the Gateway and
-- receive no direct read/write path to administration, drafts, or bindings.
REVOKE ALL ON TABLE cx_domain_governance, cx_domain_bindings, cx_domain_conversion_drafts, cx_domain_draft_members FROM ai_agent_runtime;
INSERT INTO cx_platform_capabilities(capability_key,enabled,mandatory,version,updated_by,update_reason)
VALUES ('security_domains','Y','Y',1,'SYSTEM','Security Domain governance is a mandatory zero-trust boundary')
ON CONFLICT (capability_key) DO NOTHING;
INSERT INTO cx_platform_capability_dependencies(capability_key,depends_on_key)
VALUES ('security_domains','identity'),('security_domains','authorization'),('security_domains','audit_write'),('security_domains','channels')
ON CONFLICT (capability_key,depends_on_key) DO NOTHING;
