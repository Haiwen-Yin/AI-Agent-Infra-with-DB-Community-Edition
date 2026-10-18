-- v4.2.1 Graph Engineering - persistent Node Executor registry

CREATE TABLE IF NOT EXISTS graph_executor_registry (
    executor_id varchar(128) PRIMARY KEY,
    executor_name varchar(128) NOT NULL,
    executor_version varchar(64) NOT NULL,
    executor_kind varchar(32) NOT NULL CHECK (executor_kind IN ('CONTROL','WORKER','WAIT')),
    node_types_json text NOT NULL,
    side_effect_classes_json text NOT NULL,
    manifest_json text NOT NULL,
    status varchar(32) NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE','DISABLED','DEPRECATED')),
    actor_id varchar(256) NOT NULL,
    status_reason varchar(2000),
    status_changed_by varchar(256),
    status_changed_at timestamp,
    created_at timestamp NOT NULL DEFAULT current_timestamp,
    updated_at timestamp NOT NULL DEFAULT current_timestamp,
    UNIQUE (executor_name, executor_version)
);

CREATE INDEX IF NOT EXISTS idx_graph_executor_lookup
    ON graph_executor_registry (executor_name, executor_version, status);

CREATE TABLE IF NOT EXISTS graph_governance_events (
    event_id varchar(128) PRIMARY KEY,
    run_id varchar(128),
    artifact_id varchar(128),
    event_type varchar(64) NOT NULL,
    actor_id varchar(256) NOT NULL,
    reason varchar(2000) NOT NULL,
    detail_json text,
    created_at timestamp NOT NULL DEFAULT current_timestamp
);

CREATE INDEX IF NOT EXISTS idx_graph_gov_events_run
    ON graph_governance_events (run_id, created_at);
CREATE INDEX IF NOT EXISTS idx_graph_gov_events_artifact
    ON graph_governance_events (artifact_id, created_at);

ALTER TABLE graph_executor_registry ADD COLUMN IF NOT EXISTS status_reason varchar(2000);
ALTER TABLE graph_executor_registry ADD COLUMN IF NOT EXISTS status_changed_by varchar(256);
ALTER TABLE graph_executor_registry ADD COLUMN IF NOT EXISTS status_changed_at timestamp;

-- Delivery retry metadata is additive so existing v4.2.0 Inbox/Outbox rows
-- remain readable and can be retried after an interrupted deployment.
ALTER TABLE graph_inbox ADD COLUMN IF NOT EXISTS attempts integer DEFAULT 0 NOT NULL;
ALTER TABLE graph_inbox ADD COLUMN IF NOT EXISTS available_at timestamp DEFAULT current_timestamp NOT NULL;
ALTER TABLE graph_outbox ADD COLUMN IF NOT EXISTS max_attempts integer DEFAULT 5 NOT NULL;
ALTER TABLE graph_attempts ADD COLUMN IF NOT EXISTS completion_digest varchar(128);
ALTER TABLE graph_attempts ADD COLUMN IF NOT EXISTS effect_idempotency_key varchar(256);

CREATE INDEX IF NOT EXISTS idx_graph_inbox_available
    ON graph_inbox (status, available_at, received_at);
