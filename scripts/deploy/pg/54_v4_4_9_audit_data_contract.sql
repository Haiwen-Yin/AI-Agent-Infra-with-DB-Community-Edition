-- v4.4.9 Enterprise audit-page contract alignment.
-- PostgreSQL's historical base schema carried WORKSPACE_CONTEXT_AUDIT but
-- omitted the cross-entity CONTEXT_AUDIT_LOG consumed by audit_api.py.
CREATE TABLE IF NOT EXISTS context_audit_log (
    audit_id varchar(64) PRIMARY KEY,
    entity_id varchar(128) NOT NULL,
    entity_type varchar(64) NOT NULL,
    audit_type varchar(32) NOT NULL,
    rule_id varchar(128),
    similarity_score numeric(8,6),
    threshold_score numeric(8,6),
    violation_detail text,
    agent_id varchar(128),
    session_id varchar(128),
    workspace_id varchar(128),
    resolution_status varchar(32) NOT NULL DEFAULT 'OPEN',
    resolved_by varchar(128),
    resolved_at timestamp,
    created_at timestamp NOT NULL DEFAULT current_timestamp,
    CHECK (audit_type IN ('RULE_VIOLATION','CONTEXT_SIMILARITY','IDLE_PATTERN','ACCESS_ANOMALY','DATA_LEAK')),
    CHECK (resolution_status IN ('OPEN','ACKNOWLEDGED','RESOLVED','FALSE_POSITIVE','ESCALATED'))
);
CREATE INDEX IF NOT EXISTS idx_context_audit_status
    ON context_audit_log(resolution_status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_context_audit_type
    ON context_audit_log(audit_type, created_at DESC);
