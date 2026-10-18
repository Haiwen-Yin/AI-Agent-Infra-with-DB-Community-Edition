-- v4.3.1 authoritative organization governance schema.
-- PostgreSQL 18 / Apache AGE adapter. Relational facts remain authoritative;
-- graph projections must never be used to make an authorization decision.

ALTER TABLE cx_organizations ADD COLUMN IF NOT EXISTS organization_code varchar(128);
ALTER TABLE cx_organizations ADD COLUMN IF NOT EXISTS organization_type varchar(64) NOT NULL DEFAULT 'DEPARTMENT';
ALTER TABLE cx_organizations ADD COLUMN IF NOT EXISTS is_legal_entity boolean NOT NULL DEFAULT false;
ALTER TABLE cx_organizations ADD COLUMN IF NOT EXISTS sort_order bigint NOT NULL DEFAULT 0;
ALTER TABLE cx_organizations ADD COLUMN IF NOT EXISTS responsible_principal_id varchar(128);
ALTER TABLE cx_organizations ADD COLUMN IF NOT EXISTS security_domain_id varchar(128);
ALTER TABLE cx_organizations ADD COLUMN IF NOT EXISTS valid_from timestamp NOT NULL DEFAULT current_timestamp;
ALTER TABLE cx_organizations ADD COLUMN IF NOT EXISTS valid_until timestamp;
ALTER TABLE cx_organizations ADD COLUMN IF NOT EXISTS source_type varchar(32) NOT NULL DEFAULT 'MANUAL';
ALTER TABLE cx_organizations ADD COLUMN IF NOT EXISTS source_connector_id varchar(128);
ALTER TABLE cx_organizations ADD COLUMN IF NOT EXISTS external_object_id varchar(512);
ALTER TABLE cx_organizations ADD COLUMN IF NOT EXISTS row_version bigint NOT NULL DEFAULT 1;
ALTER TABLE cx_organizations ADD COLUMN IF NOT EXISTS updated_at timestamp NOT NULL DEFAULT current_timestamp;
ALTER TABLE cx_organizations ADD COLUMN IF NOT EXISTS updated_by varchar(128);

ALTER TABLE cx_organization_members ADD COLUMN IF NOT EXISTS membership_kind varchar(16) NOT NULL DEFAULT 'PRIMARY';
ALTER TABLE cx_organization_members ADD COLUMN IF NOT EXISTS valid_from timestamp NOT NULL DEFAULT current_timestamp;
ALTER TABLE cx_organization_members ADD COLUMN IF NOT EXISTS source_type varchar(32) NOT NULL DEFAULT 'MANUAL';
ALTER TABLE cx_organization_members ADD COLUMN IF NOT EXISTS source_connector_id varchar(128);
ALTER TABLE cx_organization_members ADD COLUMN IF NOT EXISTS external_object_id varchar(512);
ALTER TABLE cx_organization_members ADD COLUMN IF NOT EXISTS row_version bigint NOT NULL DEFAULT 1;
ALTER TABLE cx_organization_members ADD COLUMN IF NOT EXISTS updated_at timestamp NOT NULL DEFAULT current_timestamp;
ALTER TABLE cx_organization_members ADD COLUMN IF NOT EXISTS updated_by varchar(128);
ALTER TABLE cx_agent_relationships ADD COLUMN IF NOT EXISTS responsible_organization_id varchar(128);

DO $cx_v431_checks$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_cx_org_validity') THEN
        ALTER TABLE cx_organizations ADD CONSTRAINT ck_cx_org_validity
            CHECK (valid_until IS NULL OR valid_until > valid_from);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_cx_org_source') THEN
        ALTER TABLE cx_organizations ADD CONSTRAINT ck_cx_org_source
            CHECK (source_type IN ('MANUAL','CSV','JSON','LDAP','OIDC','SCIM','SYSTEM'));
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_cx_org_member_kind') THEN
        ALTER TABLE cx_organization_members ADD CONSTRAINT ck_cx_org_member_kind
            CHECK (membership_kind IN ('PRIMARY','SECONDARY'));
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_cx_org_member_validity') THEN
        ALTER TABLE cx_organization_members ADD CONSTRAINT ck_cx_org_member_validity
            CHECK (valid_until IS NULL OR valid_until > valid_from);
    END IF;
END
$cx_v431_checks$;

CREATE INDEX IF NOT EXISTS idx_cx_org_parent
    ON cx_organizations(parent_id, status, sort_order, organization_id);
CREATE INDEX IF NOT EXISTS idx_cx_org_code ON cx_organizations(organization_code);
CREATE INDEX IF NOT EXISTS idx_cx_org_external
    ON cx_organizations(source_connector_id, external_object_id);
CREATE INDEX IF NOT EXISTS idx_cx_org_member_principal
    ON cx_organization_members(principal_id, status, membership_kind, valid_until);
CREATE INDEX IF NOT EXISTS idx_cx_org_member_external
    ON cx_organization_members(source_connector_id, external_object_id);
DO $cx_v431_primary_preflight$
BEGIN
    IF EXISTS (
        SELECT 1 FROM cx_organization_members
         WHERE membership_kind = 'PRIMARY' AND status = 'ACTIVE'
         GROUP BY principal_id HAVING COUNT(*) > 1
    ) THEN
        RAISE EXCEPTION 'v4.3.1 organization migration refused: a Human has multiple active primary memberships';
    END IF;
END
$cx_v431_primary_preflight$;
CREATE UNIQUE INDEX IF NOT EXISTS idx_cx_org_active_primary
    ON cx_organization_members(principal_id)
    WHERE membership_kind = 'PRIMARY' AND status = 'ACTIVE';

CREATE TABLE IF NOT EXISTS cx_reporting_relationships (
    relationship_id varchar(128) PRIMARY KEY,
    principal_id varchar(128) NOT NULL,
    manager_principal_id varchar(128) NOT NULL,
    relationship_type varchar(32) NOT NULL
        CHECK (relationship_type IN ('DIRECT','DOTTED','PROJECT_LEAD')),
    valid_from timestamp NOT NULL DEFAULT current_timestamp,
    valid_until timestamp,
    source_type varchar(32) NOT NULL DEFAULT 'MANUAL',
    source_connector_id varchar(128),
    external_object_id varchar(512),
    status varchar(32) NOT NULL DEFAULT 'ACTIVE',
    row_version bigint NOT NULL DEFAULT 1,
    created_at timestamp NOT NULL DEFAULT current_timestamp,
    updated_at timestamp NOT NULL DEFAULT current_timestamp,
    updated_by varchar(128),
    CHECK (principal_id <> manager_principal_id),
    CHECK (valid_until IS NULL OR valid_until > valid_from)
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_cx_reporting_active_direct
    ON cx_reporting_relationships(principal_id)
    WHERE relationship_type = 'DIRECT' AND status = 'ACTIVE';
CREATE INDEX IF NOT EXISTS idx_cx_reporting_manager
    ON cx_reporting_relationships(manager_principal_id, relationship_type, status, valid_until);
CREATE INDEX IF NOT EXISTS idx_cx_reporting_external
    ON cx_reporting_relationships(source_connector_id, external_object_id);

CREATE TABLE IF NOT EXISTS cx_organization_closure (
    ancestor_id varchar(128) NOT NULL,
    descendant_id varchar(128) NOT NULL,
    depth integer NOT NULL CHECK (depth >= 0),
    updated_at timestamp NOT NULL DEFAULT current_timestamp,
    PRIMARY KEY (ancestor_id, descendant_id),
    CHECK ((depth = 0 AND ancestor_id = descendant_id)
        OR (depth > 0 AND ancestor_id <> descendant_id))
);
CREATE INDEX IF NOT EXISTS idx_cx_org_closure_desc
    ON cx_organization_closure(descendant_id, depth, ancestor_id);
CREATE INDEX IF NOT EXISTS idx_cx_org_closure_ancestor
    ON cx_organization_closure(ancestor_id, depth, descendant_id);

CREATE TABLE IF NOT EXISTS cx_organization_versions (
    version_id varchar(128) PRIMARY KEY,
    version_number bigint NOT NULL UNIQUE,
    parent_version_id varchar(128),
    change_set_id varchar(128),
    status varchar(32) NOT NULL DEFAULT 'CURRENT',
    effective_at timestamp NOT NULL DEFAULT current_timestamp,
    content_digest varchar(128),
    reason varchar(2000) NOT NULL,
    created_by varchar(128) NOT NULL,
    created_at timestamp NOT NULL DEFAULT current_timestamp
);
CREATE INDEX IF NOT EXISTS idx_cx_org_version_effective
    ON cx_organization_versions(effective_at, version_number);

CREATE TABLE IF NOT EXISTS cx_organization_unit_history (
    history_id varchar(128) PRIMARY KEY,
    version_id varchar(128) NOT NULL,
    organization_id varchar(128) NOT NULL,
    operation varchar(16) NOT NULL CHECK (operation IN ('INSERT','UPDATE','RETIRE')),
    valid_from timestamp NOT NULL,
    valid_until timestamp,
    fact_json text NOT NULL,
    fact_digest varchar(128) NOT NULL,
    actor_principal_id varchar(128) NOT NULL,
    reason varchar(2000) NOT NULL,
    recorded_at timestamp NOT NULL DEFAULT current_timestamp
);
CREATE INDEX IF NOT EXISTS idx_cx_org_unit_history
    ON cx_organization_unit_history(organization_id, valid_from, recorded_at);

CREATE TABLE IF NOT EXISTS cx_organization_member_history (
    history_id varchar(128) PRIMARY KEY,
    version_id varchar(128) NOT NULL,
    membership_id varchar(128) NOT NULL,
    principal_id varchar(128) NOT NULL,
    organization_id varchar(128) NOT NULL,
    operation varchar(16) NOT NULL CHECK (operation IN ('INSERT','UPDATE','END')),
    valid_from timestamp NOT NULL,
    valid_until timestamp,
    fact_json text NOT NULL,
    fact_digest varchar(128) NOT NULL,
    actor_principal_id varchar(128) NOT NULL,
    reason varchar(2000) NOT NULL,
    recorded_at timestamp NOT NULL DEFAULT current_timestamp
);
CREATE INDEX IF NOT EXISTS idx_cx_org_member_history
    ON cx_organization_member_history(principal_id, valid_from, recorded_at);

CREATE TABLE IF NOT EXISTS cx_reporting_history (
    history_id varchar(128) PRIMARY KEY,
    version_id varchar(128) NOT NULL,
    relationship_id varchar(128) NOT NULL,
    principal_id varchar(128) NOT NULL,
    manager_principal_id varchar(128) NOT NULL,
    operation varchar(16) NOT NULL CHECK (operation IN ('INSERT','UPDATE','END')),
    valid_from timestamp NOT NULL,
    valid_until timestamp,
    fact_json text NOT NULL,
    fact_digest varchar(128) NOT NULL,
    actor_principal_id varchar(128) NOT NULL,
    reason varchar(2000) NOT NULL,
    recorded_at timestamp NOT NULL DEFAULT current_timestamp
);
CREATE INDEX IF NOT EXISTS idx_cx_reporting_history
    ON cx_reporting_history(principal_id, valid_from, recorded_at);

CREATE TABLE IF NOT EXISTS cx_org_changesets (
    change_set_id varchar(128) PRIMARY KEY,
    base_version_id varchar(128) NOT NULL,
    author_principal_id varchar(128) NOT NULL,
    status varchar(32) NOT NULL DEFAULT 'DRAFT',
    reason varchar(2000) NOT NULL,
    risk_level varchar(16) NOT NULL DEFAULT 'LOW'
        CHECK (risk_level IN ('LOW','MEDIUM','HIGH','CRITICAL')),
    policy_snapshot text,
    validation_json text,
    impact_json text,
    action_card_id varchar(128),
    scheduled_for timestamp,
    submitted_at timestamp,
    published_at timestamp,
    outcome_json text,
    idempotency_key varchar(256) NOT NULL UNIQUE,
    row_version bigint NOT NULL DEFAULT 1,
    created_at timestamp NOT NULL DEFAULT current_timestamp,
    updated_at timestamp NOT NULL DEFAULT current_timestamp
);
ALTER TABLE cx_org_changesets ADD COLUMN IF NOT EXISTS validation_json text;
CREATE INDEX IF NOT EXISTS idx_cx_org_changeset_state
    ON cx_org_changesets(status, scheduled_for, updated_at);

CREATE TABLE IF NOT EXISTS cx_org_change_operations (
    operation_id varchar(128) PRIMARY KEY,
    change_set_id varchar(128) NOT NULL,
    sequence_number integer NOT NULL CHECK (sequence_number > 0),
    operation_type varchar(64) NOT NULL,
    target_type varchar(32) NOT NULL,
    target_id varchar(128),
    expected_row_version bigint,
    command_json text NOT NULL,
    before_digest varchar(128),
    after_digest varchar(128) NOT NULL,
    status varchar(32) NOT NULL DEFAULT 'ACTIVE',
    created_at timestamp NOT NULL DEFAULT current_timestamp,
    UNIQUE (change_set_id, sequence_number)
);
CREATE INDEX IF NOT EXISTS idx_cx_org_change_target
    ON cx_org_change_operations(target_type, target_id, status);

CREATE TABLE IF NOT EXISTS cx_directory_sync_batches (
    sync_batch_id varchar(128) PRIMARY KEY,
    connector_id varchar(128) NOT NULL,
    connector_type varchar(16) NOT NULL CHECK (connector_type IN ('CSV','JSON','LDAP','OIDC','SCIM')),
    source_digest varchar(128) NOT NULL,
    status varchar(32) NOT NULL DEFAULT 'STAGING',
    requested_by varchar(128) NOT NULL,
    change_set_id varchar(128),
    total_records bigint NOT NULL DEFAULT 0,
    accepted_records bigint NOT NULL DEFAULT 0,
    conflict_records bigint NOT NULL DEFAULT 0,
    error_records bigint NOT NULL DEFAULT 0,
    started_at timestamp NOT NULL DEFAULT current_timestamp,
    completed_at timestamp,
    summary_json text
);
CREATE INDEX IF NOT EXISTS idx_cx_directory_batch
    ON cx_directory_sync_batches(connector_id, status, started_at);

CREATE TABLE IF NOT EXISTS cx_directory_source_records (
    source_record_id varchar(128) PRIMARY KEY,
    sync_batch_id varchar(128) NOT NULL,
    connector_id varchar(128) NOT NULL,
    external_object_id varchar(512) NOT NULL,
    object_type varchar(32) NOT NULL,
    source_digest varchar(128) NOT NULL,
    normalized_json text NOT NULL,
    status varchar(32) NOT NULL DEFAULT 'STAGED',
    error_json text,
    created_at timestamp NOT NULL DEFAULT current_timestamp,
    UNIQUE (sync_batch_id, connector_id, external_object_id, object_type)
);
CREATE INDEX IF NOT EXISTS idx_cx_directory_source_key
    ON cx_directory_source_records(connector_id, object_type, external_object_id);

CREATE TABLE IF NOT EXISTS cx_directory_conflicts (
    conflict_id varchar(128) PRIMARY KEY,
    sync_batch_id varchar(128) NOT NULL,
    source_record_id varchar(128),
    object_type varchar(32) NOT NULL,
    object_id varchar(128),
    field_name varchar(128) NOT NULL,
    authority_source varchar(32) NOT NULL,
    source_digest varchar(128),
    platform_digest varchar(128),
    risk_level varchar(16) NOT NULL DEFAULT 'MEDIUM',
    status varchar(32) NOT NULL DEFAULT 'OPEN',
    resolution varchar(32),
    resolution_reason varchar(2000),
    resolved_by varchar(128),
    override_until timestamp,
    created_at timestamp NOT NULL DEFAULT current_timestamp,
    resolved_at timestamp
);
CREATE INDEX IF NOT EXISTS idx_cx_directory_conflict
    ON cx_directory_conflicts(sync_batch_id, status, risk_level);
CREATE INDEX IF NOT EXISTS idx_cx_directory_conflict_object
    ON cx_directory_conflicts(object_type, object_id, status);

CREATE TABLE IF NOT EXISTS cx_org_lifecycle_cases (
    lifecycle_case_id varchar(128) PRIMARY KEY,
    subject_type varchar(16) NOT NULL CHECK (subject_type IN ('PERSON','ORGANIZATION')),
    subject_id varchar(128) NOT NULL,
    lifecycle_type varchar(32) NOT NULL CHECK (lifecycle_type IN ('DEPARTURE','RETIREMENT')),
    source_type varchar(32) NOT NULL,
    source_reference_id varchar(128),
    status varchar(32) NOT NULL DEFAULT 'PENDING',
    reason varchar(2000) NOT NULL,
    inventory_json text,
    due_at timestamp,
    cancelled_at timestamp,
    completed_at timestamp,
    row_version bigint NOT NULL DEFAULT 1,
    created_by varchar(128) NOT NULL,
    created_at timestamp NOT NULL DEFAULT current_timestamp,
    updated_at timestamp NOT NULL DEFAULT current_timestamp
);
CREATE INDEX IF NOT EXISTS idx_cx_org_lifecycle_subject
    ON cx_org_lifecycle_cases(subject_type, subject_id, status);
CREATE INDEX IF NOT EXISTS idx_cx_org_lifecycle_queue
    ON cx_org_lifecycle_cases(status, due_at, updated_at);

CREATE TABLE IF NOT EXISTS cx_org_dispositions (
    disposition_id varchar(128) PRIMARY KEY,
    lifecycle_case_id varchar(128),
    change_set_id varchar(128),
    subject_type varchar(32) NOT NULL,
    subject_id varchar(128) NOT NULL,
    disposition_type varchar(32) NOT NULL,
    target_principal_id varchar(128),
    target_organization_id varchar(128),
    status varchar(32) NOT NULL DEFAULT 'PENDING',
    reason varchar(2000) NOT NULL,
    decision_json text,
    decided_by varchar(128),
    decided_at timestamp,
    created_at timestamp NOT NULL DEFAULT current_timestamp
);
CREATE INDEX IF NOT EXISTS idx_cx_org_disposition_queue
    ON cx_org_dispositions(status, subject_type, subject_id);
CREATE INDEX IF NOT EXISTS idx_cx_org_disposition_case
    ON cx_org_dispositions(lifecycle_case_id, change_set_id);

-- The v4.3.0 Oracle-compatible index shape constrained every active role.
-- PostgreSQL already used the intended partial index, but recreate it so an
-- early draft database is corrected as well.
DROP INDEX IF EXISTS idx_cx_agent_primary_owner;
CREATE UNIQUE INDEX idx_cx_agent_primary_owner
    ON cx_agent_relationships(agent_id)
    WHERE relationship_role = 'PRIMARY_OWNER' AND status = 'ACTIVE';
CREATE INDEX IF NOT EXISTS idx_cx_agent_relationship_principal
    ON cx_agent_relationships(principal_id, relationship_role, status, agent_id);
CREATE INDEX IF NOT EXISTS idx_cx_agent_relationship_org
    ON cx_agent_relationships(responsible_organization_id, relationship_role, status, agent_id);

-- A cyclic hierarchy cannot produce an authoritative closure. Fail the
-- migration explicitly so readiness remains false instead of adopting a
-- truncated graph.
DO $cx_v431_cycle_preflight$
BEGIN
    IF EXISTS (
        WITH RECURSIVE parent_walk AS (
            SELECT organization_id AS start_id,
                   parent_id AS current_id,
                   ARRAY[organization_id]::varchar[] AS visited,
                   false AS cycle
              FROM cx_organizations
            UNION ALL
            SELECT w.start_id,
                   parent.parent_id,
                   w.visited || parent.organization_id,
                   parent.organization_id = ANY(w.visited)
              FROM parent_walk w
              JOIN cx_organizations parent ON parent.organization_id = w.current_id
             WHERE NOT w.cycle
        )
        SELECT 1 FROM parent_walk WHERE cycle
    ) THEN
        RAISE EXCEPTION 'v4.3.1 organization migration refused: hierarchy contains a cycle';
    END IF;
END
$cx_v431_cycle_preflight$;

-- Backfill the complete current closure. Broken parents are retained as roots
-- and are reported separately by readiness/preflight validation.
DELETE FROM cx_organization_closure;
WITH RECURSIVE organization_paths AS (
    SELECT organization_id AS ancestor_id,
           organization_id AS descendant_id,
           0 AS depth,
           ARRAY[organization_id]::varchar[] AS visited
      FROM cx_organizations
    UNION ALL
    SELECT p.ancestor_id,
           child.organization_id,
           p.depth + 1,
           p.visited || child.organization_id
      FROM organization_paths p
      JOIN cx_organizations child ON child.parent_id = p.descendant_id
     WHERE NOT child.organization_id = ANY(p.visited)
       AND p.depth < 10000
)
INSERT INTO cx_organization_closure(ancestor_id, descendant_id, depth)
SELECT ancestor_id, descendant_id, MIN(depth)
  FROM organization_paths
 GROUP BY ancestor_id, descendant_id
ON CONFLICT (ancestor_id, descendant_id) DO UPDATE
SET depth = EXCLUDED.depth, updated_at = current_timestamp;

-- Only one unambiguous, current manager fact between active Human Principals
-- is promoted. Other legacy values remain untouched for later review.
WITH provable AS (
    SELECT m.principal_id,
           MIN(m.membership_id) AS membership_id,
           MIN(m.manager_principal_id) AS manager_principal_id
      FROM cx_organization_members m
      JOIN cx_principals p ON p.principal_id = m.principal_id
                          AND p.principal_type = 'HUMAN' AND p.status = 'ACTIVE'
      JOIN cx_principals mgr ON mgr.principal_id = m.manager_principal_id
                            AND mgr.principal_type = 'HUMAN' AND mgr.status = 'ACTIVE'
     WHERE m.manager_principal_id IS NOT NULL
       AND m.manager_principal_id <> m.principal_id
       AND m.status = 'ACTIVE'
       AND (m.valid_until IS NULL OR m.valid_until > current_timestamp)
     GROUP BY m.principal_id
    HAVING COUNT(DISTINCT m.manager_principal_id) = 1
)
INSERT INTO cx_reporting_relationships(
    relationship_id, principal_id, manager_principal_id, relationship_type,
    source_type, status, updated_by)
SELECT 'V431-RPT-' || substr(membership_id, 1, 119), principal_id,
       manager_principal_id, 'DIRECT', 'SYSTEM', 'ACTIVE', 'MIGRATION_V4_3_1'
  FROM provable
ON CONFLICT DO NOTHING;

INSERT INTO cx_organization_versions(
    version_id, version_number, status, reason, created_by)
SELECT 'V431-BASELINE', 1, 'CURRENT',
       'v4.3.1 baseline adopted from current organization facts', 'MIGRATION_V4_3_1'
WHERE NOT EXISTS (SELECT 1 FROM cx_organization_versions);

-- These are Human control-plane tables. RLS is enabled without Agent policies,
-- matching the existing v4.3 owner/service access pattern. Do not FORCE RLS:
-- the Human API currently uses the schema owner. Runtime access is explicitly
-- revoked below so accidental inherited grants cannot expose these facts.
ALTER TABLE cx_reporting_relationships ENABLE ROW LEVEL SECURITY;
ALTER TABLE cx_organization_closure ENABLE ROW LEVEL SECURITY;
ALTER TABLE cx_organization_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE cx_organization_unit_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE cx_organization_member_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE cx_reporting_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE cx_org_changesets ENABLE ROW LEVEL SECURITY;
ALTER TABLE cx_org_change_operations ENABLE ROW LEVEL SECURITY;
ALTER TABLE cx_directory_sync_batches ENABLE ROW LEVEL SECURITY;
ALTER TABLE cx_directory_source_records ENABLE ROW LEVEL SECURITY;
ALTER TABLE cx_directory_conflicts ENABLE ROW LEVEL SECURITY;
ALTER TABLE cx_org_lifecycle_cases ENABLE ROW LEVEL SECURITY;
ALTER TABLE cx_org_dispositions ENABLE ROW LEVEL SECURITY;

DO $cx_v431_runtime_revoke$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ai_agent_runtime') THEN
        EXECUTE 'REVOKE ALL PRIVILEGES ON TABLE '
            || 'public.cx_reporting_relationships, public.cx_organization_closure, '
            || 'public.cx_organization_versions, public.cx_organization_unit_history, '
            || 'public.cx_organization_member_history, public.cx_reporting_history, '
            || 'public.cx_org_changesets, public.cx_org_change_operations, '
            || 'public.cx_directory_sync_batches, public.cx_directory_source_records, '
            || 'public.cx_directory_conflicts, public.cx_org_lifecycle_cases, '
            || 'public.cx_org_dispositions FROM ai_agent_runtime';
    END IF;
END
$cx_v431_runtime_revoke$;

-- Synchronize only system-managed role templates. Edition/profile capability
-- checks remain mandatory even when an administrator role names an Enterprise
-- organization action.
INSERT INTO cx_role_templates
    (role_code, display_name, permissions_json, data_scopes_json)
SELECT role_code, display_name, permissions_json, data_scopes_json
  FROM (VALUES
    ('END_USER', 'End User',
     '["profile.read","profile.update","agents.enroll","agents.read","channels.read","channels.write","tasks.read","workspaces.read","knowledge.read","memory.read","skills.read","specs.read","branches.read","collab.read","loops.read","graphs.read","notifications.read","organizations.read"]',
     '["OWNED","ASSIGNED"]'),
    ('SYSTEM_ADMIN', 'System Administrator', '["*"]', '["ALL"]'),
    ('SECURITY_ADMIN', 'Security Administrator',
     '["security.*","sessions.revoke","domains.manage","profile.update","users.identity.link","users.security.manage","users.sessions.read","users.delegations.read","users.delegations.manage","agents.claim","channels.bridge","channels.lifecycle","channels.delete","channels.manage_members","channels.quarantine","memory.review","agents.transfer","agents.offboard","barriers.recover","notifications.manage","barriers.create","channels.actions.decide","organizations.read","organizations.changes.approve","organizations.emergency"]',
     '["SECURITY_DOMAIN"]'),
    ('AGENT_MANAGER', 'Agent Manager',
     '["agents.read","agents.enroll","agents.manage","agents.operate","agents.transfer","agents.offboard","channels.read","channels.create","channels.manage_members","channels.lifecycle","barriers.create","channels.actions.decide","users.read","notifications.manage","profile.update","organizations.read","organizations.agent_relationships.read"]',
     '["ORG_SUBTREE"]'),
    ('ORG_MANAGER', 'Organization Manager',
     '["organizations.read","organizations.manage","organizations.people.read","organizations.agents.read","organizations.anomalies.read","organizations.changes.create","organizations.changes.write","organizations.changes.submit","organizations.history.read","organizations.members.manage","organizations.reporting.manage","organizations.sync.manage","agents.read","users.read","profile.update"]',
     '["ORG_SUBTREE"]'),
    ('USER_ADMIN', 'User Administrator',
     '["users.read","users.read.all","users.approve","users.roles.manage","users.permissions.manage","users.identity.link","users.security.manage","users.sessions.read","users.delegations.read","users.delegations.manage","organizations.read","organizations.members.manage","organizations.reporting.manage","organizations.sync.manage"]',
     '["ORG_SUBTREE"]'),
    ('APPROVER', 'Approver',
     '["approvals.read","approvals.decide","channels.actions.decide","barriers.release","barriers.recover","memory.review","profile.update","organizations.read","organizations.changes.approve"]',
     '["ASSIGNED"]'),
    ('AUDITOR', 'Auditor',
     '["audit.read","audit.export","users.read","profile.update","organizations.read","organizations.history.read","organizations.export"]',
     '["SECURITY_DOMAIN"]')
  ) AS desired(role_code, display_name, permissions_json, data_scopes_json)
 WHERE true
ON CONFLICT (role_code) DO UPDATE
SET display_name = EXCLUDED.display_name,
    permissions_json = EXCLUDED.permissions_json,
    data_scopes_json = EXCLUDED.data_scopes_json,
    version = cx_role_templates.version + 1,
    updated_at = current_timestamp
WHERE cx_role_templates.managed
  AND (cx_role_templates.display_name,
       cx_role_templates.permissions_json,
       cx_role_templates.data_scopes_json)
      IS DISTINCT FROM
      (EXCLUDED.display_name, EXCLUDED.permissions_json, EXCLUDED.data_scopes_json);
