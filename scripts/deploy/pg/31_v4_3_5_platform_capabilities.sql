-- v4.3.5 database-authoritative platform capability switches.
CREATE TABLE IF NOT EXISTS cx_platform_capabilities (
    capability_key varchar(64) PRIMARY KEY,
    enabled char(1) NOT NULL DEFAULT 'Y' CHECK (enabled IN ('Y','N')),
    mandatory char(1) NOT NULL DEFAULT 'N' CHECK (mandatory IN ('Y','N')),
    version integer NOT NULL DEFAULT 1 CHECK (version > 0),
    updated_by varchar(128),
    update_reason varchar(2000),
    created_at timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS cx_platform_capability_dependencies (
    capability_key varchar(64) NOT NULL REFERENCES cx_platform_capabilities(capability_key),
    depends_on_key varchar(64) NOT NULL REFERENCES cx_platform_capabilities(capability_key),
    PRIMARY KEY (capability_key, depends_on_key),
    CHECK (capability_key <> depends_on_key)
);
CREATE TABLE IF NOT EXISTS cx_platform_capability_history (
    history_id varchar(128) PRIMARY KEY,
    capability_key varchar(64) NOT NULL REFERENCES cx_platform_capabilities(capability_key),
    from_enabled char(1) NOT NULL CHECK (from_enabled IN ('Y','N')),
    to_enabled char(1) NOT NULL CHECK (to_enabled IN ('Y','N')),
    result_version integer NOT NULL CHECK (result_version > 1),
    changed_by varchar(128) NOT NULL,
    reason varchar(2000) NOT NULL,
    created_at timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_cx_platform_cap_enabled ON cx_platform_capabilities(enabled, mandatory);
CREATE INDEX IF NOT EXISTS idx_cx_platform_cap_history ON cx_platform_capability_history(capability_key, created_at);

INSERT INTO cx_platform_capabilities(capability_key,mandatory)
SELECT key, mandatory FROM (VALUES
 ('identity','Y'),('authorization','Y'),('security','Y'),('audit_write','Y'),('agents','Y'),('users','Y'),('platform_config','Y'),
 ('portal','N'),('monitor','N'),('tasks','N'),('workspaces','N'),('knowledge','N'),('memory','N'),('skills','N'),('specs','N'),
 ('branches','N'),('collaboration','N'),('loops','N'),('graph','N'),('channels','N'),('barriers','N'),('approvals','N'),
 ('compliance','N'),('audit_view','N'),('organization','N')) AS seed(key,mandatory)
ON CONFLICT (capability_key) DO NOTHING;

INSERT INTO cx_platform_capability_dependencies(capability_key,depends_on_key)
SELECT capability, dependency FROM (VALUES
 ('branches','tasks'),('branches','workspaces'),('collaboration','agents'),('loops','tasks'),('graph','tasks'),
 ('channels','agents'),('barriers','channels'),('approvals','audit_write'),('compliance','agents'),
 ('compliance','audit_write'),('audit_view','audit_write'),('organization','users'),('organization','agents')) AS seed(capability,dependency)
ON CONFLICT (capability_key,depends_on_key) DO NOTHING;
