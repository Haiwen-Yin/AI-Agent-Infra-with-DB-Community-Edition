-- v4.3.0 Human Principal, Agent Enrollment, governed Channel and Barrier core.
-- PostgreSQL 18 / Apache AGE adapter.  JSON payloads are intentionally kept
-- as text at this boundary so the portable service can use one canonical form.

-- Some v4.2 baselines contain agent_db_identity but not the function created
-- by the original v4.0.1 migration.  Define the dependency here as well so
-- the v4.3 identity/Channel migration is self-contained and resumable.
CREATE TABLE IF NOT EXISTS public.agent_db_identity (
    role_name name PRIMARY KEY,
    agent_id varchar(64) NOT NULL UNIQUE
);
REVOKE ALL ON public.agent_db_identity FROM PUBLIC;

CREATE OR REPLACE FUNCTION public.current_agent_identity() RETURNS text
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public AS $$
    SELECT COALESCE(
        (SELECT identity.agent_id::text FROM public.agent_db_identity identity
          WHERE identity.role_name = current_user),
        current_setting('app.current_agent_id', true)
    )
$$;

CREATE TABLE IF NOT EXISTS cx_principals (
    principal_id varchar(128) PRIMARY KEY,
    principal_type varchar(16) NOT NULL CHECK (principal_type IN ('HUMAN','AGENT','SERVICE')),
    status varchar(32) NOT NULL DEFAULT 'ACTIVE',
    permission_version bigint NOT NULL DEFAULT 1,
    created_at timestamp NOT NULL DEFAULT current_timestamp,
    updated_at timestamp NOT NULL DEFAULT current_timestamp
);
CREATE INDEX IF NOT EXISTS idx_cx_principal_type ON cx_principals (principal_type, status);

CREATE TABLE IF NOT EXISTS cx_human_identities (
    identity_id varchar(128) PRIMARY KEY,
    principal_id varchar(128) NOT NULL,
    identity_type varchar(16) NOT NULL CHECK (identity_type IN ('LOCAL','LDAP','OIDC')),
    provider varchar(256) NOT NULL DEFAULT 'LOCAL',
    subject_key varchar(512) NOT NULL,
    username varchar(128),
    email varchar(320),
    password_hash text,
    password_version varchar(32),
    status varchar(32) NOT NULL DEFAULT 'ACTIVE',
    last_login_at timestamp,
    created_at timestamp NOT NULL DEFAULT current_timestamp,
    updated_at timestamp NOT NULL DEFAULT current_timestamp,
    UNIQUE (identity_type, provider, subject_key)
);
CREATE INDEX IF NOT EXISTS idx_cx_identity_principal ON cx_human_identities (principal_id, status);
CREATE UNIQUE INDEX IF NOT EXISTS idx_cx_identity_username ON cx_human_identities (lower(username)) WHERE username IS NOT NULL;

CREATE TABLE IF NOT EXISTS cx_registration_requests (
    request_id varchar(128) PRIMARY KEY,
    username varchar(128) NOT NULL,
    email varchar(320),
    password_hash text NOT NULL,
    auth_source varchar(16) NOT NULL DEFAULT 'LOCAL',
    registration_mode varchar(32) NOT NULL DEFAULT 'APPROVAL',
    status varchar(32) NOT NULL DEFAULT 'PENDING',
    decision_by varchar(128),
    decision_reason varchar(2000),
    created_at timestamp NOT NULL DEFAULT current_timestamp,
    decided_at timestamp
);
CREATE INDEX IF NOT EXISTS idx_cx_registration_status ON cx_registration_requests (status, created_at);

CREATE TABLE IF NOT EXISTS cx_web_sessions (
    session_digest varchar(128) PRIMARY KEY,
    principal_id varchar(128) NOT NULL,
    user_id varchar(128),
    auth_method varchar(32) NOT NULL,
    mfa_level varchar(32) NOT NULL DEFAULT 'NONE',
    node_id varchar(128) NOT NULL,
    client_summary varchar(1000),
    permission_version bigint NOT NULL DEFAULT 1,
    csrf_digest varchar(128) NOT NULL,
    expires_at timestamp NOT NULL,
    last_seen_at timestamp NOT NULL DEFAULT current_timestamp,
    revoked_at timestamp,
    revoke_reason varchar(1000),
    created_at timestamp NOT NULL DEFAULT current_timestamp
);
CREATE INDEX IF NOT EXISTS idx_cx_session_principal ON cx_web_sessions (principal_id, revoked_at, expires_at);

CREATE TABLE IF NOT EXISTS cx_role_templates (
    role_code varchar(64) PRIMARY KEY,
    display_name varchar(256) NOT NULL,
    permissions_json text NOT NULL,
    data_scopes_json text NOT NULL,
    version bigint NOT NULL DEFAULT 1,
    managed boolean NOT NULL DEFAULT true,
    updated_at timestamp NOT NULL DEFAULT current_timestamp
);
CREATE TABLE IF NOT EXISTS cx_user_roles (
    user_role_id varchar(128) PRIMARY KEY,
    principal_id varchar(128) NOT NULL,
    role_code varchar(64) NOT NULL,
    source varchar(32) NOT NULL DEFAULT 'DIRECT',
    valid_from timestamp NOT NULL DEFAULT current_timestamp,
    valid_until timestamp,
    granted_by varchar(128),
    status varchar(32) NOT NULL DEFAULT 'ACTIVE'
);
CREATE INDEX IF NOT EXISTS idx_cx_user_roles ON cx_user_roles (principal_id, status, valid_until);
CREATE TABLE IF NOT EXISTS cx_user_permission_overrides (
    override_id varchar(128) PRIMARY KEY,
    principal_id varchar(128) NOT NULL,
    resource_action varchar(256) NOT NULL,
    effect varchar(16) NOT NULL CHECK (effect IN ('ALLOW','DENY')),
    data_scope varchar(32) NOT NULL DEFAULT 'NONE',
    security_domain_id varchar(128),
    valid_until timestamp,
    reason varchar(2000) NOT NULL,
    granted_by varchar(128) NOT NULL,
    created_at timestamp NOT NULL DEFAULT current_timestamp
);
CREATE INDEX IF NOT EXISTS idx_cx_permission_override ON cx_user_permission_overrides (principal_id, resource_action, valid_until);

CREATE TABLE IF NOT EXISTS cx_organizations (
    organization_id varchar(128) PRIMARY KEY,
    parent_id varchar(128),
    organization_name varchar(256) NOT NULL,
    status varchar(32) NOT NULL DEFAULT 'ACTIVE',
    created_at timestamp NOT NULL DEFAULT current_timestamp
);
CREATE TABLE IF NOT EXISTS cx_organization_members (
    membership_id varchar(128) PRIMARY KEY,
    organization_id varchar(128) NOT NULL,
    principal_id varchar(128) NOT NULL,
    membership_role varchar(64) NOT NULL DEFAULT 'MEMBER',
    manager_principal_id varchar(128),
    valid_until timestamp,
    status varchar(32) NOT NULL DEFAULT 'ACTIVE',
    UNIQUE (organization_id, principal_id)
);
ALTER TABLE cx_organization_members ADD COLUMN IF NOT EXISTS manager_principal_id varchar(128);
CREATE TABLE IF NOT EXISTS cx_responsible_groups (
    group_id varchar(128) PRIMARY KEY,
    group_name varchar(256) NOT NULL,
    security_domain_id varchar(128),
    parent_group_id varchar(128),
    status varchar(32) NOT NULL DEFAULT 'ACTIVE',
    created_at timestamp NOT NULL DEFAULT current_timestamp
);
CREATE TABLE IF NOT EXISTS cx_responsible_group_members (
    group_id varchar(128) NOT NULL,
    principal_id varchar(128) NOT NULL,
    member_role varchar(64) NOT NULL DEFAULT 'MEMBER',
    status varchar(32) NOT NULL DEFAULT 'ACTIVE',
    created_at timestamp NOT NULL DEFAULT current_timestamp,
    PRIMARY KEY (group_id, principal_id)
);
CREATE TABLE IF NOT EXISTS cx_security_domains (
    security_domain_id varchar(128) PRIMARY KEY,
    domain_name varchar(256) NOT NULL,
    classification varchar(32) NOT NULL DEFAULT 'INTERNAL',
    purpose varchar(1000),
    status varchar(32) NOT NULL DEFAULT 'ACTIVE',
    created_at timestamp NOT NULL DEFAULT current_timestamp
);
CREATE TABLE IF NOT EXISTS cx_domain_members (
    membership_id varchar(128) PRIMARY KEY,
    security_domain_id varchar(128) NOT NULL,
    principal_id varchar(128) NOT NULL,
    membership_tier varchar(32) NOT NULL DEFAULT 'MEMBER',
    valid_until timestamp,
    status varchar(32) NOT NULL DEFAULT 'ACTIVE',
    UNIQUE (security_domain_id, principal_id)
);

CREATE TABLE IF NOT EXISTS cx_enrollment_grants (
    grant_id varchar(128) PRIMARY KEY,
    sponsor_principal_id varchar(128) NOT NULL,
    owner_principal_id varchar(128) NOT NULL,
    responsible_group_id varchar(128),
    security_domain_id varchar(128),
    environment varchar(64) NOT NULL,
    runtime varchar(128) NOT NULL,
    agent_name varchar(256),
    node_constraint varchar(256),
    public_key_constraint text,
    risk_tier varchar(32) NOT NULL DEFAULT 'STANDARD',
    quota_key varchar(256),
    policy_snapshot text NOT NULL,
    status varchar(32) NOT NULL DEFAULT 'ACTIVE',
    expires_at timestamp NOT NULL,
    max_uses integer NOT NULL DEFAULT 1,
    used_count integer NOT NULL DEFAULT 0,
    created_at timestamp NOT NULL DEFAULT current_timestamp
);
CREATE TABLE IF NOT EXISTS cx_enrollment_tokens (
    token_id varchar(128) PRIMARY KEY,
    grant_id varchar(128) NOT NULL,
    token_digest varchar(128) NOT NULL UNIQUE,
    purpose varchar(32) NOT NULL DEFAULT 'AGENT_ENROLLMENT',
    expires_at timestamp NOT NULL,
    consumed_at timestamp,
    consumed_agent_id varchar(128),
    created_at timestamp NOT NULL DEFAULT current_timestamp
);
CREATE INDEX IF NOT EXISTS idx_cx_enrollment_token_active ON cx_enrollment_tokens (token_digest, expires_at, consumed_at);
CREATE TABLE IF NOT EXISTS cx_agent_relationships (
    relationship_id varchar(128) PRIMARY KEY,
    agent_id varchar(128) NOT NULL,
    principal_id varchar(128) NOT NULL,
    relationship_role varchar(32) NOT NULL CHECK (relationship_role IN ('SPONSOR','PRIMARY_OWNER','OPERATOR','VIEWER')),
    responsible_group_id varchar(128),
    status varchar(32) NOT NULL DEFAULT 'ACTIVE',
    created_at timestamp NOT NULL DEFAULT current_timestamp,
    ended_at timestamp
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_cx_agent_primary_owner ON cx_agent_relationships(agent_id) WHERE relationship_role = 'PRIMARY_OWNER' AND status = 'ACTIVE';
CREATE TABLE IF NOT EXISTS cx_agent_credentials (
    credential_id varchar(128) PRIMARY KEY,
    agent_id varchar(128) NOT NULL,
    credential_type varchar(32) NOT NULL CHECK (credential_type IN ('ED25519','CLIENT_SECRET','MTLS')),
    public_key text,
    secret_digest varchar(128),
    key_version integer NOT NULL DEFAULT 1,
    status varchar(32) NOT NULL DEFAULT 'ACTIVE',
    expires_at timestamp,
    created_at timestamp NOT NULL DEFAULT current_timestamp,
    revoked_at timestamp
);
CREATE TABLE IF NOT EXISTS cx_agent_access_tokens (
    token_digest varchar(128) PRIMARY KEY,
    agent_id varchar(128) NOT NULL,
    instance_id varchar(128) NOT NULL,
    scope_json text NOT NULL,
    lease_digest varchar(128),
    fencing_token bigint,
    expires_at timestamp NOT NULL,
    revoked_at timestamp,
    created_at timestamp NOT NULL DEFAULT current_timestamp
);
CREATE INDEX IF NOT EXISTS idx_cx_agent_access_token ON cx_agent_access_tokens(agent_id, instance_id, expires_at, revoked_at);

CREATE TABLE IF NOT EXISTS cx_channels (
    channel_id varchar(128) PRIMARY KEY,
    channel_name varchar(256) NOT NULL,
    security_domain_id varchar(128) NOT NULL,
    classification varchar(32) NOT NULL DEFAULT 'INTERNAL',
    channel_type varchar(32) NOT NULL DEFAULT 'TEAM',
    status varchar(32) NOT NULL DEFAULT 'ACTIVE',
    retention_until timestamp,
    legal_hold boolean NOT NULL DEFAULT false,
    metadata_json text,
    created_by varchar(128) NOT NULL,
    created_at timestamp NOT NULL DEFAULT current_timestamp,
    updated_at timestamp NOT NULL DEFAULT current_timestamp
);
CREATE INDEX IF NOT EXISTS idx_cx_channel_domain ON cx_channels (security_domain_id, status, updated_at);
CREATE TABLE IF NOT EXISTS cx_channel_members (
    member_id varchar(128) PRIMARY KEY,
    channel_id varchar(128) NOT NULL,
    principal_id varchar(128) NOT NULL,
    member_role varchar(32) NOT NULL DEFAULT 'MEMBER',
    joined_at timestamp NOT NULL DEFAULT current_timestamp,
    valid_until timestamp,
    status varchar(32) NOT NULL DEFAULT 'ACTIVE',
    UNIQUE (channel_id, principal_id)
);
CREATE TABLE IF NOT EXISTS cx_channel_messages (
    message_id varchar(128) PRIMARY KEY,
    channel_id varchar(128) NOT NULL,
    thread_type varchar(32) NOT NULL DEFAULT 'CHANNEL',
    thread_id varchar(128),
    principal_id varchar(128) NOT NULL,
    body_text text NOT NULL,
    body_classification varchar(32) NOT NULL DEFAULT 'INTERNAL',
    message_type varchar(32) NOT NULL DEFAULT 'TEXT',
    reference_json text,
    created_at timestamp NOT NULL DEFAULT current_timestamp,
    redacted_at timestamp
);
CREATE INDEX IF NOT EXISTS idx_cx_channel_message_cursor ON cx_channel_messages (channel_id, created_at, message_id);

CREATE TABLE IF NOT EXISTS cx_barriers (
    barrier_id varchar(128) PRIMARY KEY,
    channel_id varchar(128),
    run_id varchar(128),
    node_key varchar(128) NOT NULL,
    policy_json text NOT NULL,
    participant_snapshot text NOT NULL,
    status varchar(32) NOT NULL DEFAULT 'WAITING',
    policy_version bigint NOT NULL DEFAULT 1,
    checkpoint_id varchar(128),
    released_by varchar(128),
    released_at timestamp,
    timeout_at timestamp,
    created_at timestamp NOT NULL DEFAULT current_timestamp,
    created_by varchar(128),
    updated_at timestamp NOT NULL DEFAULT current_timestamp
);
CREATE INDEX IF NOT EXISTS idx_cx_barrier_status ON cx_barriers (status, timeout_at, updated_at);
CREATE TABLE IF NOT EXISTS cx_barrier_arrivals (
    arrival_id varchar(128) PRIMARY KEY,
    barrier_id varchar(128) NOT NULL,
    principal_id varchar(128) NOT NULL,
    participant_role varchar(64) NOT NULL,
    report_digest varchar(128) NOT NULL,
    report_json text NOT NULL,
    idempotency_key varchar(256),
    status varchar(32) NOT NULL DEFAULT 'ACCEPTED',
    created_at timestamp NOT NULL DEFAULT current_timestamp,
    UNIQUE (barrier_id, principal_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_cx_barrier_arrival_idemp ON cx_barrier_arrivals (barrier_id, principal_id, idempotency_key);
CREATE TABLE IF NOT EXISTS cx_action_cards (
    action_id varchar(128) PRIMARY KEY,
    channel_id varchar(128) NOT NULL,
    proposed_by varchar(128) NOT NULL,
    action_type varchar(64) NOT NULL,
    version integer NOT NULL DEFAULT 1,
    payload_json text NOT NULL,
    status varchar(32) NOT NULL DEFAULT 'PROPOSED',
    reason varchar(2000) NOT NULL,
    idempotency_key varchar(256) NOT NULL UNIQUE,
    decided_by varchar(128),
    decided_at timestamp,
    created_at timestamp NOT NULL DEFAULT current_timestamp
);
CREATE TABLE IF NOT EXISTS cx_notifications (
    notification_id varchar(128) PRIMARY KEY,
    principal_id varchar(128) NOT NULL,
    notification_type varchar(64) NOT NULL,
    dedupe_key varchar(256) NOT NULL,
    payload_json text NOT NULL,
    acknowledged_at timestamp,
    deadline_at timestamp,
    created_at timestamp NOT NULL DEFAULT current_timestamp,
    UNIQUE (principal_id, dedupe_key)
);
CREATE TABLE IF NOT EXISTS cx_security_events (
    event_id varchar(128) PRIMARY KEY,
    principal_id varchar(128),
    actor_type varchar(16) NOT NULL,
    action_name varchar(128) NOT NULL,
    resource_type varchar(64),
    resource_id varchar(128),
    outcome varchar(32) NOT NULL,
    reason varchar(2000),
    detail_json text,
    created_at timestamp NOT NULL DEFAULT current_timestamp
);
CREATE INDEX IF NOT EXISTS idx_cx_security_event_time ON cx_security_events (created_at, action_name, outcome);
CREATE TABLE IF NOT EXISTS cx_bridges (
    bridge_id varchar(128) PRIMARY KEY,
    source_domain_id varchar(128) NOT NULL,
    target_domain_id varchar(128) NOT NULL,
    channel_id varchar(128),
    transfer_mode varchar(32) NOT NULL CHECK (transfer_mode IN ('REFERENCE','REDACTED_COPY','SUMMARY','ARTIFACT','FULL_COPY')),
    purpose varchar(2000) NOT NULL,
    classification varchar(32) NOT NULL,
    recipient_snapshot text NOT NULL,
    status varchar(32) NOT NULL DEFAULT 'PENDING',
    expires_at timestamp NOT NULL,
    approved_by varchar(128),
    created_by varchar(128) NOT NULL,
    created_at timestamp NOT NULL DEFAULT current_timestamp
);

CREATE TABLE IF NOT EXISTS cx_agent_instances (
    instance_id varchar(128) PRIMARY KEY,
    agent_id varchar(128) NOT NULL,
    channel_id varchar(128), security_domain_id varchar(128), run_id varchar(128),
    classification varchar(32) NOT NULL DEFAULT 'INTERNAL', node_id varchar(128),
    status varchar(32) NOT NULL DEFAULT 'ACTIVE', fencing_token bigint NOT NULL DEFAULT 1,
    last_seen_at timestamp NOT NULL DEFAULT current_timestamp,
    lease_expires_at timestamp NOT NULL DEFAULT (current_timestamp + interval '5 minutes'),
    revoked_at timestamp,
    revoke_reason varchar(1000), created_at timestamp NOT NULL DEFAULT current_timestamp,
    updated_at timestamp NOT NULL DEFAULT current_timestamp
);
CREATE INDEX IF NOT EXISTS idx_cx_agent_instance_scope ON cx_agent_instances (agent_id, channel_id, security_domain_id, status);
CREATE TABLE IF NOT EXISTS cx_agent_deliveries (
    delivery_id varchar(128) PRIMARY KEY, event_type varchar(64) NOT NULL,
    channel_id varchar(128), message_id varchar(128), agent_id varchar(128) NOT NULL,
    instance_id varchar(128) NOT NULL, payload_json text NOT NULL, idempotency_key varchar(256) NOT NULL,
    status varchar(32) NOT NULL DEFAULT 'PENDING', visibility_until timestamp,
    attempt_count integer NOT NULL DEFAULT 0, max_attempts integer NOT NULL DEFAULT 5,
    claimed_by varchar(128), claim_token_digest varchar(128), claimed_at timestamp,
    fencing_token bigint, acked_at timestamp, failure_reason varchar(2000), dead_letter_at timestamp,
    created_at timestamp NOT NULL DEFAULT current_timestamp, updated_at timestamp NOT NULL DEFAULT current_timestamp,
    UNIQUE (agent_id, idempotency_key)
);
CREATE INDEX IF NOT EXISTS idx_cx_delivery_claim ON cx_agent_deliveries (instance_id, status, visibility_until, created_at);

-- These additive guards also upgrade a database that already applied an early
-- v4.3.0 draft.  The service will not use an unbound claim or lease.
ALTER TABLE cx_agent_instances
    ADD COLUMN IF NOT EXISTS lease_expires_at timestamp;
ALTER TABLE cx_agent_instances
    ALTER COLUMN lease_expires_at SET DEFAULT (current_timestamp + interval '5 minutes');
UPDATE cx_agent_instances
   SET lease_expires_at = COALESCE(lease_expires_at, last_seen_at + interval '5 minutes')
 WHERE lease_expires_at IS NULL;
ALTER TABLE cx_agent_deliveries ADD COLUMN IF NOT EXISTS claim_token_digest varchar(128);
ALTER TABLE cx_agent_deliveries ADD COLUMN IF NOT EXISTS claimed_at timestamp;
ALTER TABLE cx_agent_deliveries ADD COLUMN IF NOT EXISTS fencing_token bigint;
ALTER TABLE cx_agent_access_tokens ADD COLUMN IF NOT EXISTS fencing_token bigint;
ALTER TABLE cx_barriers ADD COLUMN IF NOT EXISTS created_by varchar(128);
CREATE INDEX IF NOT EXISTS idx_cx_delivery_claim_token ON cx_agent_deliveries (claim_token_digest);
CREATE TABLE IF NOT EXISTS cx_channel_memory_candidates (
    candidate_id varchar(128) PRIMARY KEY, channel_id varchar(128) NOT NULL,
    security_domain_id varchar(128) NOT NULL, proposed_by varchar(128) NOT NULL,
    content_json text NOT NULL, classification varchar(32) NOT NULL, destination_scope varchar(32) NOT NULL,
    provenance_json text NOT NULL, status varchar(32) NOT NULL DEFAULT 'PROPOSED',
    reviewed_by varchar(128), review_reason varchar(2000), created_at timestamp NOT NULL DEFAULT current_timestamp,
    reviewed_at timestamp
);
CREATE TABLE IF NOT EXISTS cx_bridge_transfers (
    transfer_id varchar(128) PRIMARY KEY, bridge_id varchar(128) NOT NULL,
    source_object_type varchar(64) NOT NULL, source_object_id varchar(128) NOT NULL,
    target_object_id varchar(128), payload_digest varchar(128), status varchar(32) NOT NULL DEFAULT 'PENDING',
    created_by varchar(128) NOT NULL, created_at timestamp NOT NULL DEFAULT current_timestamp,
    delivered_at timestamp, quarantined_at timestamp, reason varchar(2000)
);

INSERT INTO cx_role_templates(role_code, display_name, permissions_json, data_scopes_json)
VALUES ('END_USER', 'End User', '["profile.read","profile.update","agents.enroll","agents.read","channels.read","channels.write","tasks.read","workspaces.read","knowledge.read","memory.read","skills.read","specs.read","branches.read","collab.read","loops.read","graphs.read","notifications.read"]', '["OWNED","ASSIGNED"]')
ON CONFLICT (role_code) DO NOTHING;
UPDATE cx_role_templates
   SET display_name = 'End User',
       permissions_json = '["profile.read","profile.update","agents.enroll","agents.read","channels.read","channels.write","tasks.read","workspaces.read","knowledge.read","memory.read","skills.read","specs.read","branches.read","collab.read","loops.read","graphs.read","notifications.read"]',
       data_scopes_json = '["OWNED","ASSIGNED"]',
       version = version + 1,
       updated_at = current_timestamp
 WHERE role_code = 'END_USER'
   AND (permissions_json NOT LIKE '%"agents.enroll"%'
        OR permissions_json NOT LIKE '%"channels.read"%'
        OR data_scopes_json NOT LIKE '%"ASSIGNED"%');
INSERT INTO cx_role_templates(role_code, display_name, permissions_json, data_scopes_json)
VALUES ('SYSTEM_ADMIN', 'System Administrator', '["*"]', '["ALL"]')
ON CONFLICT (role_code) DO NOTHING;
INSERT INTO cx_role_templates(role_code, display_name, permissions_json, data_scopes_json)
VALUES ('SECURITY_ADMIN', 'Security Administrator', '["security.*","sessions.revoke","domains.manage","channels.bridge"]', '["SECURITY_DOMAIN"]')
ON CONFLICT (role_code) DO NOTHING;
INSERT INTO cx_role_templates(role_code, display_name, permissions_json, data_scopes_json)
VALUES ('AGENT_MANAGER', 'Agent Manager', '["agents.read","agents.enroll","agents.manage","agents.operate","channels.read","channels.manage_members","users.read"]', '["ORG_SUBTREE"]')
ON CONFLICT (role_code) DO NOTHING;
UPDATE cx_role_templates
   SET permissions_json = '["agents.read","agents.enroll","agents.manage","agents.operate","channels.read","channels.manage_members","users.read"]',
       version = version + 1,
       updated_at = current_timestamp
 WHERE role_code = 'AGENT_MANAGER' AND permissions_json LIKE '%"agents.*"%';
INSERT INTO cx_role_templates(role_code, display_name, permissions_json, data_scopes_json)
VALUES ('AUDITOR', 'Auditor', '["audit.read","audit.export","users.read"]', '["SECURITY_DOMAIN"]')
ON CONFLICT (role_code) DO NOTHING;
INSERT INTO cx_role_templates(role_code, display_name, permissions_json, data_scopes_json)
VALUES ('APPROVER', 'Approver', '["approvals.read","approvals.decide","channels.actions.decide","barriers.release","users.read"]', '["ASSIGNED"]')
ON CONFLICT (role_code) DO NOTHING;
INSERT INTO cx_role_templates(role_code, display_name, permissions_json, data_scopes_json)
VALUES ('OPERATOR', 'Operator', '["agents.read","agents.operate","channels.write","barriers.arrive"]', '["ASSIGNED"]')
ON CONFLICT (role_code) DO NOTHING;
INSERT INTO cx_role_templates(role_code, display_name, permissions_json, data_scopes_json)
VALUES ('DEVELOPER', 'Developer', '["skills.read","tools.read","graphs.read","barriers.create"]', '["OWNED"]')
ON CONFLICT (role_code) DO NOTHING;
INSERT INTO cx_role_templates(role_code, display_name, permissions_json, data_scopes_json)
VALUES ('USER_ADMIN', 'User Administrator', '["users.read","users.approve","users.roles.manage","users.permissions.manage"]', '["ORG_SUBTREE"]')
ON CONFLICT (role_code) DO NOTHING;
INSERT INTO cx_role_templates(role_code, display_name, permissions_json, data_scopes_json)
VALUES ('ROLE_ADMIN', 'Role Administrator', '["users.read","users.roles.manage","users.permissions.manage"]', '["ORG_SUBTREE"]')
ON CONFLICT (role_code) DO NOTHING;
INSERT INTO cx_security_domains(security_domain_id, domain_name, classification, purpose, status)
VALUES ('DEFAULT', 'Default Security Domain', 'INTERNAL', 'Bootstrap domain; replace with an organization-specific domain before production', 'ACTIVE')
ON CONFLICT (security_domain_id) DO NOTHING;

-- Business Agents run with NOBYPASSRLS roles.  These policies keep the new
-- control plane fail-closed while the Schema Owner retains the administration
-- and migration view through the normal PostgreSQL owner bypass behavior.
CREATE OR REPLACE FUNCTION public.cx_agent_channel_member(p_channel_id varchar, p_principal_id varchar)
RETURNS boolean
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $cx_agent_channel_member$
    SELECT p_principal_id = public.current_agent_identity()
       AND EXISTS (
           SELECT 1 FROM public.cx_channel_members m
           WHERE m.channel_id = p_channel_id
             AND m.principal_id = p_principal_id
             AND m.status = 'ACTIVE'
             AND (m.valid_until IS NULL OR m.valid_until > current_timestamp)
       )
$cx_agent_channel_member$;

REVOKE ALL ON FUNCTION public.cx_agent_channel_member(varchar, varchar) FROM PUBLIC;

ALTER TABLE cx_principals ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS cx_principals_agent_self ON cx_principals;
CREATE POLICY cx_principals_agent_self ON cx_principals FOR SELECT
    USING (principal_id = public.current_agent_identity());

ALTER TABLE cx_human_identities ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS cx_human_identities_agent_none ON cx_human_identities;

ALTER TABLE cx_registration_requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE cx_web_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE cx_role_templates ENABLE ROW LEVEL SECURITY;
ALTER TABLE cx_user_roles ENABLE ROW LEVEL SECURITY;
ALTER TABLE cx_user_permission_overrides ENABLE ROW LEVEL SECURITY;
ALTER TABLE cx_organizations ENABLE ROW LEVEL SECURITY;
ALTER TABLE cx_organization_members ENABLE ROW LEVEL SECURITY;
ALTER TABLE cx_security_domains ENABLE ROW LEVEL SECURITY;
ALTER TABLE cx_domain_members ENABLE ROW LEVEL SECURITY;
ALTER TABLE cx_enrollment_grants ENABLE ROW LEVEL SECURITY;
ALTER TABLE cx_enrollment_tokens ENABLE ROW LEVEL SECURITY;

ALTER TABLE cx_agent_relationships ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS cx_agent_relationships_self ON cx_agent_relationships;
CREATE POLICY cx_agent_relationships_self ON cx_agent_relationships FOR SELECT
    USING (agent_id = public.current_agent_identity() OR principal_id = public.current_agent_identity());

ALTER TABLE cx_agent_credentials ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS cx_agent_credentials_self ON cx_agent_credentials;
CREATE POLICY cx_agent_credentials_self ON cx_agent_credentials FOR SELECT
    USING (agent_id = public.current_agent_identity());

ALTER TABLE cx_agent_access_tokens ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS cx_agent_access_tokens_self ON cx_agent_access_tokens;
CREATE POLICY cx_agent_access_tokens_self ON cx_agent_access_tokens FOR ALL
    USING (agent_id = public.current_agent_identity())
    WITH CHECK (agent_id = public.current_agent_identity());

ALTER TABLE cx_agent_instances ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS cx_agent_instances_self ON cx_agent_instances;
CREATE POLICY cx_agent_instances_self ON cx_agent_instances FOR ALL
    USING (agent_id = public.current_agent_identity())
    WITH CHECK (agent_id = public.current_agent_identity());

ALTER TABLE cx_agent_deliveries ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS cx_agent_deliveries_self ON cx_agent_deliveries;
CREATE POLICY cx_agent_deliveries_self ON cx_agent_deliveries FOR ALL
    USING (agent_id = public.current_agent_identity())
    WITH CHECK (agent_id = public.current_agent_identity());

ALTER TABLE cx_channels ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS cx_channels_member ON cx_channels;
CREATE POLICY cx_channels_member ON cx_channels FOR SELECT
    USING (public.cx_agent_channel_member(channel_id, public.current_agent_identity()));

ALTER TABLE cx_channel_members ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS cx_channel_members_member ON cx_channel_members;
CREATE POLICY cx_channel_members_member ON cx_channel_members FOR SELECT
    USING (public.cx_agent_channel_member(channel_id, public.current_agent_identity()));

ALTER TABLE cx_channel_messages ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS cx_channel_messages_member ON cx_channel_messages;
DROP POLICY IF EXISTS cx_channel_messages_agent_insert ON cx_channel_messages;
CREATE POLICY cx_channel_messages_member ON cx_channel_messages FOR SELECT
    USING (public.cx_agent_channel_member(channel_id, public.current_agent_identity()));
CREATE POLICY cx_channel_messages_agent_insert ON cx_channel_messages FOR INSERT
    WITH CHECK (principal_id = public.current_agent_identity()
        AND public.cx_agent_channel_member(channel_id, public.current_agent_identity()));

ALTER TABLE cx_barriers ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS cx_barriers_member ON cx_barriers;
CREATE POLICY cx_barriers_member ON cx_barriers FOR SELECT
    USING ((channel_id IS NOT NULL AND public.cx_agent_channel_member(channel_id, public.current_agent_identity()))
        OR (channel_id IS NULL AND created_by = public.current_agent_identity()));

ALTER TABLE cx_barrier_arrivals ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS cx_barrier_arrivals_member ON cx_barrier_arrivals;
DROP POLICY IF EXISTS cx_barrier_arrivals_agent_insert ON cx_barrier_arrivals;
CREATE POLICY cx_barrier_arrivals_member ON cx_barrier_arrivals FOR SELECT
    USING (EXISTS (
        SELECT 1 FROM cx_barriers b
        WHERE b.barrier_id = cx_barrier_arrivals.barrier_id
          AND ((b.channel_id IS NOT NULL
                AND public.cx_agent_channel_member(b.channel_id, public.current_agent_identity()))
               OR (b.channel_id IS NULL
                   AND b.created_by = public.current_agent_identity()))
    ));
CREATE POLICY cx_barrier_arrivals_agent_insert ON cx_barrier_arrivals FOR INSERT
    WITH CHECK (principal_id = public.current_agent_identity()
        AND EXISTS (
            SELECT 1 FROM cx_barriers b
            WHERE b.barrier_id = cx_barrier_arrivals.barrier_id
              AND ((b.channel_id IS NOT NULL
                    AND public.cx_agent_channel_member(b.channel_id, public.current_agent_identity()))
                   OR (b.channel_id IS NULL
                       AND b.created_by = public.current_agent_identity()))
        ));

ALTER TABLE cx_action_cards ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS cx_action_cards_member ON cx_action_cards;
DROP POLICY IF EXISTS cx_action_cards_agent_insert ON cx_action_cards;
CREATE POLICY cx_action_cards_member ON cx_action_cards FOR SELECT
    USING (public.cx_agent_channel_member(channel_id, public.current_agent_identity()));
CREATE POLICY cx_action_cards_agent_insert ON cx_action_cards FOR INSERT
    WITH CHECK (proposed_by = public.current_agent_identity()
        AND public.cx_agent_channel_member(channel_id, public.current_agent_identity()));

ALTER TABLE cx_notifications ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS cx_notifications_self ON cx_notifications;
CREATE POLICY cx_notifications_self ON cx_notifications FOR SELECT
    USING (principal_id = public.current_agent_identity());

ALTER TABLE cx_security_events ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS cx_security_events_self ON cx_security_events;
CREATE POLICY cx_security_events_self ON cx_security_events FOR SELECT
    USING (principal_id = public.current_agent_identity());
DROP POLICY IF EXISTS cx_security_events_agent_insert ON cx_security_events;
CREATE POLICY cx_security_events_agent_insert ON cx_security_events FOR INSERT
    WITH CHECK (principal_id = public.current_agent_identity());

ALTER TABLE cx_bridges ENABLE ROW LEVEL SECURITY;
ALTER TABLE cx_channel_memory_candidates ENABLE ROW LEVEL SECURITY;
ALTER TABLE cx_bridge_transfers ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS cx_channel_memory_candidates_member ON cx_channel_memory_candidates;
CREATE POLICY cx_channel_memory_candidates_member ON cx_channel_memory_candidates FOR SELECT
    USING (public.cx_agent_channel_member(channel_id, public.current_agent_identity()));
DROP POLICY IF EXISTS cx_channel_memory_candidates_agent_insert ON cx_channel_memory_candidates;
CREATE POLICY cx_channel_memory_candidates_agent_insert ON cx_channel_memory_candidates FOR INSERT
    WITH CHECK (proposed_by = public.current_agent_identity()
        AND public.cx_agent_channel_member(channel_id, public.current_agent_identity()));

-- Cross-domain Bridge rows and runtime profile changes are human control-plane
-- objects.  RLS is enabled without an Agent policy so a NOBYPASSRLS runtime
-- role fails closed even if a future grant accidentally exposes the table.
DO $cx_agent_grants$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ai_agent_runtime') THEN
        EXECUTE 'GRANT USAGE ON SCHEMA public TO ai_agent_runtime';
        EXECUTE 'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE '
            || 'public.cx_principals, public.cx_human_identities, public.cx_agent_relationships, '
            || 'public.cx_agent_credentials, public.cx_agent_access_tokens, public.cx_agent_instances, '
            || 'public.cx_agent_deliveries, public.cx_channels, public.cx_channel_members, '
            || 'public.cx_channel_messages, public.cx_barriers, public.cx_barrier_arrivals, '
            || 'public.cx_action_cards, public.cx_notifications, public.cx_security_events, '
            || 'public.cx_channel_memory_candidates TO ai_agent_runtime';
        EXECUTE 'GRANT EXECUTE ON FUNCTION public.cx_agent_channel_member(varchar, varchar) TO ai_agent_runtime';
    END IF;
END
$cx_agent_grants$;
