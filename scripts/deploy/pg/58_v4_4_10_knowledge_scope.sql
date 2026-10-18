-- v4.4.10 fresh-baseline knowledge visibility policy.
CREATE TABLE IF NOT EXISTS cx_knowledge_access_policies (
    policy_id varchar(128) PRIMARY KEY,
    entity_id varchar(128) NOT NULL,
    scope_type varchar(32) NOT NULL CHECK (scope_type IN ('PUBLIC_COMPANY','ORGANIZATION_SUBTREE','ORGANIZATION_LEVEL','PRINCIPAL_PRIVATE')),
    organization_id varchar(128), principal_id varchar(128), hierarchy_depth integer,
    status varchar(16) NOT NULL DEFAULT 'ACTIVE', valid_from timestamp NOT NULL DEFAULT current_timestamp,
    valid_until timestamp, reason varchar(2000) NOT NULL DEFAULT 'initial policy',
    created_by varchar(128) NOT NULL, created_at timestamp NOT NULL DEFAULT current_timestamp,
    updated_at timestamp NOT NULL DEFAULT current_timestamp,
    CHECK ((scope_type='PUBLIC_COMPANY' AND organization_id IS NULL AND principal_id IS NULL)
       OR (scope_type='ORGANIZATION_SUBTREE' AND organization_id IS NOT NULL AND principal_id IS NULL)
       OR (scope_type='ORGANIZATION_LEVEL' AND organization_id IS NOT NULL AND hierarchy_depth IS NOT NULL AND principal_id IS NULL)
       OR (scope_type='PRINCIPAL_PRIVATE' AND principal_id IS NOT NULL AND organization_id IS NULL)),
    CHECK (valid_until IS NULL OR valid_until > valid_from)
);
CREATE INDEX IF NOT EXISTS idx_cx_kap_entity ON cx_knowledge_access_policies(entity_id,status,valid_until);
CREATE INDEX IF NOT EXISTS idx_cx_kap_org ON cx_knowledge_access_policies(organization_id,scope_type,status);
