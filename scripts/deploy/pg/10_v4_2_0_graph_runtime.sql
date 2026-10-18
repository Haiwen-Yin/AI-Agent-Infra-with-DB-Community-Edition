-- v4.2.0 Graph Runtime state, worker, event, and evidence tables
CREATE TABLE IF NOT EXISTS graph_runs (
    run_id varchar(128) PRIMARY KEY, graph_version_id varchar(128) NOT NULL, plan_id varchar(128) NOT NULL,
    status varchar(32) NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING','RUNNING','WAITING','PAUSED','SUCCEEDED','FAILED','CANCELLED','MIGRATING','REVIEW_REQUIRED')),
    actor_id varchar(256) NOT NULL, idempotency_key varchar(256), input_state_json text, current_checkpoint_id varchar(128), budget_json text, budget_usage_json text,
    error_code varchar(128), error_message varchar(2000), created_at timestamp NOT NULL DEFAULT current_timestamp, updated_at timestamp NOT NULL DEFAULT current_timestamp, completed_at timestamp,
    UNIQUE (graph_version_id, idempotency_key)
);
CREATE TABLE IF NOT EXISTS graph_node_runs (
    node_run_id varchar(128) PRIMARY KEY, run_id varchar(128) NOT NULL REFERENCES graph_runs(run_id) ON DELETE CASCADE, node_key varchar(256) NOT NULL,
    status varchar(32) NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING','READY','RUNNING','WAITING','SUCCEEDED','FAILED','CANCELLED','SKIPPED','REVIEW_REQUIRED')),
    branch_key varchar(256), join_key varchar(256), iteration_no integer NOT NULL DEFAULT 0, input_checkpoint_id varchar(128), output_checkpoint_id varchar(128), created_at timestamp NOT NULL DEFAULT current_timestamp, updated_at timestamp NOT NULL DEFAULT current_timestamp,
    UNIQUE (run_id, node_key, iteration_no, branch_key)
);
CREATE TABLE IF NOT EXISTS graph_ready_nodes (
    ready_id varchar(128) PRIMARY KEY, node_run_id varchar(128) NOT NULL REFERENCES graph_node_runs(node_run_id) ON DELETE CASCADE, run_id varchar(128) NOT NULL REFERENCES graph_runs(run_id) ON DELETE CASCADE,
    node_key varchar(256) NOT NULL, status varchar(32) NOT NULL DEFAULT 'READY' CHECK (status IN ('READY','CLAIMED','WAITING','DONE','CANCELLED')), priority integer NOT NULL DEFAULT 5, available_at timestamp NOT NULL DEFAULT current_timestamp, deadline_at timestamp, required_capability_json text, resource_class varchar(128), claimed_at timestamp, created_at timestamp NOT NULL DEFAULT current_timestamp
);
CREATE TABLE IF NOT EXISTS graph_attempts (
    attempt_id varchar(128) PRIMARY KEY, node_run_id varchar(128) NOT NULL REFERENCES graph_node_runs(node_run_id) ON DELETE CASCADE, run_id varchar(128) NOT NULL REFERENCES graph_runs(run_id) ON DELETE CASCADE, worker_id varchar(256), status varchar(32) NOT NULL DEFAULT 'CLAIMED' CHECK (status IN ('CLAIMED','RUNNING','WAITING','SUCCEEDED','FAILED','CANCELLED','STALE','REVIEW_REQUIRED')), fencing_token bigint NOT NULL, lease_token_hash varchar(128), lease_expires_at timestamp, input_state_json text, output_state_json text, result_artifact_id varchar(128), idempotency_key varchar(256), effect_idempotency_key varchar(256), error_code varchar(128), error_message varchar(2000), started_at timestamp NOT NULL DEFAULT current_timestamp, completed_at timestamp, UNIQUE (node_run_id, idempotency_key)
);
CREATE TABLE IF NOT EXISTS graph_state_events (
    event_id varchar(128) PRIMARY KEY, run_id varchar(128) NOT NULL REFERENCES graph_runs(run_id) ON DELETE CASCADE, seq_no bigint NOT NULL, checkpoint_id varchar(128), prior_checkpoint_id varchar(128), source_attempt_id varchar(128), delta_json text NOT NULL, reducer_json text, state_hash varchar(128) NOT NULL, created_at timestamp NOT NULL DEFAULT current_timestamp, UNIQUE (run_id, seq_no)
);
CREATE TABLE IF NOT EXISTS graph_checkpoints (
    checkpoint_id varchar(128) PRIMARY KEY, run_id varchar(128) NOT NULL REFERENCES graph_runs(run_id) ON DELETE CASCADE, seq_no bigint NOT NULL, parent_checkpoint_id varchar(128), state_json text NOT NULL, state_hash varchar(128) NOT NULL, snapshot_kind varchar(32) NOT NULL DEFAULT 'DELTA' CHECK (snapshot_kind IN ('DELTA','FULL','FORK','MIGRATION','INTERVENTION')), branch_id varchar(128), actor_id varchar(256) NOT NULL, created_at timestamp NOT NULL DEFAULT current_timestamp
);
CREATE TABLE IF NOT EXISTS graph_transitions (
    transition_id varchar(128) PRIMARY KEY, run_id varchar(128) NOT NULL REFERENCES graph_runs(run_id) ON DELETE CASCADE, node_run_id varchar(128), attempt_id varchar(128), edge_id varchar(128), from_node_key varchar(256), to_node_key varchar(256), transition_type varchar(64) NOT NULL, status varchar(32) NOT NULL, checkpoint_id varchar(128), state_event_id varchar(128), fencing_token bigint, evidence_json text, actor_id varchar(256) NOT NULL, reason varchar(2000), created_at timestamp NOT NULL DEFAULT current_timestamp, UNIQUE (attempt_id)
);
CREATE TABLE IF NOT EXISTS graph_artifacts (
    artifact_id varchar(128) PRIMARY KEY, content_hash varchar(128) NOT NULL UNIQUE, media_type varchar(256), content_size bigint NOT NULL, storage_uri varchar(2048), content_blob bytea, owner_ref varchar(256) NOT NULL, classification varchar(64) NOT NULL DEFAULT 'INTERNAL', encryption_key_ref varchar(256), retention_until timestamp, legal_hold char(1) NOT NULL DEFAULT 'N', legal_hold_actor varchar(256), legal_hold_reason varchar(2000), legal_hold_at timestamp, released_by varchar(256), release_reason varchar(2000), released_at timestamp, created_at timestamp NOT NULL DEFAULT current_timestamp, CHECK (legal_hold IN ('Y','N'))
);
CREATE TABLE IF NOT EXISTS graph_workers (
    worker_id varchar(256) PRIMARY KEY, agent_id varchar(128), runtime varchar(128) NOT NULL, capability_json text, status varchar(32) NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE','DISABLED','REVOKED','DRAINING')), last_heartbeat_at timestamp, node_id varchar(256), created_at timestamp NOT NULL DEFAULT current_timestamp
);
CREATE TABLE IF NOT EXISTS graph_lease_tokens (
    lease_id varchar(128) PRIMARY KEY, attempt_id varchar(128) NOT NULL UNIQUE, worker_id varchar(256) NOT NULL, token_hash varchar(128) NOT NULL, fencing_token bigint NOT NULL, operations_json text NOT NULL, scope_json text NOT NULL, expires_at timestamp NOT NULL, revoked_at timestamp, created_at timestamp NOT NULL DEFAULT current_timestamp
);
CREATE TABLE IF NOT EXISTS graph_inbox (
    inbox_id varchar(128) PRIMARY KEY, source_ref varchar(256) NOT NULL, event_type varchar(128) NOT NULL, schema_version varchar(64) NOT NULL, idempotency_key varchar(256) NOT NULL, authentication_json text, payload_json text NOT NULL, status varchar(32) NOT NULL DEFAULT 'RECEIVED' CHECK (status IN ('RECEIVED','PROCESSING','PROCESSED','DUPLICATE','DEAD_LETTER')), received_at timestamp NOT NULL DEFAULT current_timestamp, processed_at timestamp, error_message varchar(2000), UNIQUE (source_ref, idempotency_key)
);
CREATE TABLE IF NOT EXISTS graph_outbox (
    outbox_id varchar(128) PRIMARY KEY, run_id varchar(128), event_type varchar(128) NOT NULL, idempotency_key varchar(256) NOT NULL, payload_json text NOT NULL, status varchar(32) NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING','DISPATCHING','SENT','DEAD_LETTER')), attempts integer NOT NULL DEFAULT 0, available_at timestamp NOT NULL DEFAULT current_timestamp, last_error varchar(2000), created_at timestamp NOT NULL DEFAULT current_timestamp, sent_at timestamp, UNIQUE (event_type, idempotency_key)
);
CREATE TABLE IF NOT EXISTS graph_evaluations (
    evaluation_id varchar(128) PRIMARY KEY, run_id varchar(128) NOT NULL REFERENCES graph_runs(run_id) ON DELETE CASCADE, node_run_id varchar(128), evaluator_name varchar(128) NOT NULL, evaluator_version varchar(64) NOT NULL, level_name varchar(32) NOT NULL, input_json text, result_json text, route_decision varchar(64), created_at timestamp NOT NULL DEFAULT current_timestamp
);
CREATE TABLE IF NOT EXISTS graph_interventions (
    intervention_id varchar(128) PRIMARY KEY, run_id varchar(128) NOT NULL REFERENCES graph_runs(run_id) ON DELETE CASCADE, node_run_id varchar(128), action_name varchar(64) NOT NULL, actor_id varchar(256) NOT NULL, reason varchar(2000) NOT NULL, evidence_json text, status varchar(32) NOT NULL DEFAULT 'APPLIED', created_at timestamp NOT NULL DEFAULT current_timestamp
);
CREATE INDEX IF NOT EXISTS idx_graph_run_status ON graph_runs(status, updated_at);
CREATE INDEX IF NOT EXISTS idx_graph_ready_claim ON graph_ready_nodes(status, available_at, priority);
CREATE INDEX IF NOT EXISTS idx_graph_attempt_lease ON graph_attempts(status, lease_expires_at);
CREATE INDEX IF NOT EXISTS idx_graph_state_run ON graph_state_events(run_id, seq_no);
CREATE INDEX IF NOT EXISTS idx_graph_transition_run ON graph_transitions(run_id, created_at);
CREATE INDEX IF NOT EXISTS idx_graph_inbox_status ON graph_inbox(status, received_at);
CREATE INDEX IF NOT EXISTS idx_graph_outbox_status ON graph_outbox(status, available_at);
