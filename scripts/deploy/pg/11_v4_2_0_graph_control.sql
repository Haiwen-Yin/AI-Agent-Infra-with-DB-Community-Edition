-- v4.2.0 Graph Engineering control, join, trace and migration evidence
-- Additive upgrade for databases that installed an earlier v4.2.0 runtime
-- draft before legal-hold metadata was finalized.
ALTER TABLE graph_artifacts ALTER COLUMN legal_hold TYPE char(1)
    USING CASE WHEN lower(legal_hold::text) IN ('true','t','y','1') THEN 'Y' ELSE 'N' END;
ALTER TABLE graph_artifacts ADD COLUMN IF NOT EXISTS legal_hold_actor varchar(256);
ALTER TABLE graph_artifacts ADD COLUMN IF NOT EXISTS legal_hold_reason varchar(2000);
ALTER TABLE graph_artifacts ADD COLUMN IF NOT EXISTS legal_hold_at timestamp;
ALTER TABLE graph_artifacts ADD COLUMN IF NOT EXISTS released_by varchar(256);
ALTER TABLE graph_artifacts ADD COLUMN IF NOT EXISTS release_reason varchar(2000);
ALTER TABLE graph_artifacts ADD COLUMN IF NOT EXISTS released_at timestamp;
CREATE TABLE IF NOT EXISTS graph_join_states (
    join_id varchar(128) PRIMARY KEY, run_id varchar(128) NOT NULL REFERENCES graph_runs(run_id) ON DELETE CASCADE,
    node_key varchar(256) NOT NULL, join_key varchar(256) NOT NULL, strategy varchar(32) NOT NULL,
    required_count integer NOT NULL DEFAULT 1, expected_count integer NOT NULL DEFAULT 1,
    accepted_count integer NOT NULL DEFAULT 0, status varchar(32) NOT NULL DEFAULT 'WAITING',
    inputs_json text, reducer_json text, created_at timestamp NOT NULL DEFAULT current_timestamp,
    updated_at timestamp NOT NULL DEFAULT current_timestamp,
    CHECK (status IN ('WAITING','READY','COMMITTED','CANCELLED','DEADLOCKED')),
    UNIQUE (run_id, node_key, join_key)
);
CREATE TABLE IF NOT EXISTS graph_run_branches (
    branch_id varchar(128) PRIMARY KEY, run_id varchar(128) NOT NULL REFERENCES graph_runs(run_id) ON DELETE CASCADE,
    parent_node_run_id varchar(128), branch_key varchar(256) NOT NULL, source_edge_id varchar(128),
    node_key varchar(256), status varchar(32) NOT NULL DEFAULT 'ACTIVE', input_checkpoint_id varchar(128),
    output_checkpoint_id varchar(128), metadata_json text, created_at timestamp NOT NULL DEFAULT current_timestamp,
    updated_at timestamp NOT NULL DEFAULT current_timestamp,
    CHECK (status IN ('ACTIVE','SUCCEEDED','FAILED','CANCELLED','MERGED','REVIEW_REQUIRED')),
    UNIQUE (run_id, branch_key, node_key)
);
CREATE TABLE IF NOT EXISTS graph_wait_subscriptions (
    wait_id varchar(128) PRIMARY KEY, run_id varchar(128) NOT NULL REFERENCES graph_runs(run_id) ON DELETE CASCADE,
    node_run_id varchar(128) NOT NULL UNIQUE, wait_kind varchar(32) NOT NULL, event_type varchar(128),
    correlation_key varchar(256), status varchar(32) NOT NULL DEFAULT 'WAITING', deadline_at timestamp,
    payload_json text, created_at timestamp NOT NULL DEFAULT current_timestamp, resolved_at timestamp,
    CHECK (status IN ('WAITING','RESOLVED','EXPIRED','CANCELLED'))
);
CREATE TABLE IF NOT EXISTS graph_traces (
    trace_id varchar(128) PRIMARY KEY, run_id varchar(128) NOT NULL REFERENCES graph_runs(run_id) ON DELETE CASCADE,
    node_run_id varchar(128), attempt_id varchar(128), transition_id varchar(128), event_type varchar(64) NOT NULL,
    status varchar(32), retry_no integer NOT NULL DEFAULT 0, duration_ms bigint, token_count bigint,
    estimated_cost numeric(30,10), payload_ref varchar(128), detail_json text,
    created_at timestamp NOT NULL DEFAULT current_timestamp
);
CREATE TABLE IF NOT EXISTS graph_run_migrations (
    migration_id varchar(128) PRIMARY KEY, run_id varchar(128) NOT NULL REFERENCES graph_runs(run_id) ON DELETE CASCADE,
    from_version_id varchar(128) NOT NULL, to_version_id varchar(128) NOT NULL, from_plan_id varchar(128) NOT NULL,
    to_plan_id varchar(128) NOT NULL, precheckpoint_id varchar(128), status varchar(32) NOT NULL,
    mapping_json text, actor_id varchar(256) NOT NULL, reason varchar(2000) NOT NULL, error_message varchar(2000),
    created_at timestamp NOT NULL DEFAULT current_timestamp, completed_at timestamp,
    CHECK (status IN ('VALIDATING','APPLIED','FAILED','ROLLED_BACK'))
);
CREATE TABLE IF NOT EXISTS graph_compat_bindings (
    binding_id varchar(128) PRIMARY KEY, legacy_kind varchar(64) NOT NULL,
    legacy_id varchar(256) NOT NULL, graph_id varchar(128) NOT NULL REFERENCES graph_definitions(graph_id),
    graph_version_id varchar(128) REFERENCES graph_versions(graph_version_id),
    graph_run_id varchar(128) REFERENCES graph_runs(run_id),
    status varchar(32) NOT NULL DEFAULT 'ACTIVE', topology_status varchar(32) NOT NULL DEFAULT 'KNOWN',
    read_only char(1) NOT NULL DEFAULT 'N', review_reason varchar(2000), metadata_json text,
    created_at timestamp NOT NULL DEFAULT current_timestamp, updated_at timestamp NOT NULL DEFAULT current_timestamp,
    last_sync_at timestamp, UNIQUE (legacy_kind, legacy_id),
    CHECK (status IN ('ACTIVE','MIGRATED','REVIEW_REQUIRED','READ_ONLY')),
    CHECK (topology_status IN ('KNOWN','REVIEW_REQUIRED','UNKNOWN')),
    CHECK (read_only IN ('Y','N'))
);
CREATE INDEX IF NOT EXISTS idx_graph_join_run ON graph_join_states(run_id, status, updated_at);
CREATE INDEX IF NOT EXISTS idx_graph_branch_run ON graph_run_branches(run_id, status, updated_at);
CREATE INDEX IF NOT EXISTS idx_graph_wait_event ON graph_wait_subscriptions(status, event_type, correlation_key);
CREATE INDEX IF NOT EXISTS idx_graph_trace_run ON graph_traces(run_id, created_at);
CREATE INDEX IF NOT EXISTS idx_graph_migration_run ON graph_run_migrations(run_id, created_at);
CREATE INDEX IF NOT EXISTS idx_graph_compat_graph ON graph_compat_bindings(graph_id, status, updated_at);
CREATE INDEX IF NOT EXISTS idx_graph_compat_run ON graph_compat_bindings(graph_run_id, status);
