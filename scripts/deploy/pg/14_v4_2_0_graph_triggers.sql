-- v4.2.0 Graph trigger registration and delivery bindings
CREATE TABLE IF NOT EXISTS graph_triggers (
    trigger_id varchar(128) PRIMARY KEY,
    graph_version_id varchar(128) NOT NULL REFERENCES graph_versions(graph_version_id),
    trigger_kind varchar(32) NOT NULL CHECK (trigger_kind IN ('MANUAL','API','SCHEDULE','DATABASE','EXTERNAL','INTERNAL')),
    config_json text NOT NULL,
    status varchar(32) NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE','DISABLED')),
    actor_id varchar(256) NOT NULL,
    reason varchar(2000) NOT NULL,
    created_at timestamp NOT NULL DEFAULT current_timestamp,
    updated_at timestamp NOT NULL DEFAULT current_timestamp
);
CREATE INDEX IF NOT EXISTS idx_graph_trigger_version
    ON graph_triggers(graph_version_id, status, trigger_kind);
