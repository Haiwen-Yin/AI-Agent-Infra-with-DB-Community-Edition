-- AI Agent Infra v4.1.0 PostgreSQL registration objects (all editions)
-- Enterprise governance objects are deployed separately by
-- 8_v4_1_0_governance.sql.

CREATE TABLE IF NOT EXISTS agent_registrations (
    agent_id VARCHAR(128) PRIMARY KEY,
    owner_ref VARCHAR(256) NOT NULL,
    runtime VARCHAR(128) NOT NULL,
    environment VARCHAR(128) NOT NULL,
    node_id VARCHAR(128),
    capabilities_json JSONB,
    credential_version VARCHAR(64) NOT NULL,
    credential_hash VARCHAR(128) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'ACTIVE'
        CHECK (status IN ('ACTIVE','DISABLED','REVOKED','EXPIRED','DUPLICATE_CONFLICT')),
    registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    last_seen_at TIMESTAMP,
    expires_at TIMESTAMP,
    idempotency_key VARCHAR(160) NOT NULL UNIQUE,
    created_by VARCHAR(256) NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_ar_gov_status ON agent_registrations(status, updated_at);
CREATE INDEX IF NOT EXISTS idx_ar_gov_last_seen ON agent_registrations(last_seen_at);
