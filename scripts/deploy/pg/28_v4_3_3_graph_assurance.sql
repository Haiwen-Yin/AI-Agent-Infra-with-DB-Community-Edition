-- v4.3.3 Graph Runtime assurance and Definition supply-chain evidence.
-- Relational facts are authoritative; protocol and telemetry records are
-- bounded projections and cannot authorize or mutate a Graph Run.
CREATE TABLE IF NOT EXISTS graph_assurance_evidence (
    evidence_id varchar(128) PRIMARY KEY, run_id varchar(128) REFERENCES graph_runs(run_id),
    evidence_type varchar(64) NOT NULL, status varchar(32) NOT NULL, actor_id varchar(256),
    detail_json text NOT NULL DEFAULT '{}', created_at timestamp NOT NULL DEFAULT current_timestamp
);
CREATE TABLE IF NOT EXISTS graph_definition_provenance (
    provenance_id varchar(128) PRIMARY KEY, graph_version_id varchar(128) NOT NULL REFERENCES graph_versions(graph_version_id),
    parent_digest varchar(64), publisher_id varchar(256), source_uri varchar(1024),
    format_version varchar(32) NOT NULL, compiler_version varchar(64), document_digest varchar(64) NOT NULL,
    trust_state varchar(32) NOT NULL DEFAULT 'UNTRUSTED_DRAFT', created_at timestamp NOT NULL DEFAULT current_timestamp,
    UNIQUE(graph_version_id), UNIQUE(document_digest, graph_version_id)
);
CREATE TABLE IF NOT EXISTS graph_definition_dependencies (
    dependency_id varchar(128) PRIMARY KEY, graph_version_id varchar(128) NOT NULL REFERENCES graph_versions(graph_version_id),
    dependency_kind varchar(32) NOT NULL, dependency_name varchar(256) NOT NULL, dependency_version varchar(128) NOT NULL,
    dependency_digest varchar(64), created_at timestamp NOT NULL DEFAULT current_timestamp,
    UNIQUE(graph_version_id, dependency_kind, dependency_name, dependency_version, dependency_digest)
);
CREATE TABLE IF NOT EXISTS graph_definition_signatures (
    signature_id varchar(128) PRIMARY KEY, graph_version_id varchar(128) NOT NULL REFERENCES graph_versions(graph_version_id),
    algorithm varchar(32) NOT NULL, key_id varchar(256) NOT NULL, signature_value text NOT NULL,
    status varchar(32) NOT NULL DEFAULT 'UNVERIFIED', verified_at timestamp, created_at timestamp NOT NULL DEFAULT current_timestamp,
    UNIQUE(graph_version_id, key_id)
);
CREATE TABLE IF NOT EXISTS graph_definition_scans (
    scan_id varchar(128) PRIMARY KEY, graph_version_id varchar(128) NOT NULL REFERENCES graph_versions(graph_version_id),
    scan_version varchar(32) NOT NULL, findings_json text NOT NULL DEFAULT '[]', risk_level varchar(16) NOT NULL DEFAULT 'LOW',
    status varchar(32) NOT NULL DEFAULT 'PENDING', created_at timestamp NOT NULL DEFAULT current_timestamp
);
CREATE TABLE IF NOT EXISTS graph_dynamic_proposals (
    proposal_id varchar(128) PRIMARY KEY, source_version_id varchar(128) NOT NULL REFERENCES graph_versions(graph_version_id),
    target_version_id varchar(128) REFERENCES graph_versions(graph_version_id), run_id varchar(128) REFERENCES graph_runs(run_id),
    checkpoint_id varchar(128), operations_json text NOT NULL, state_mapping_json text NOT NULL DEFAULT '{}',
    risk_json text NOT NULL DEFAULT '{}', status varchar(32) NOT NULL DEFAULT 'DRAFT', approval_id varchar(128), expected_version varchar(128),
    actor_id varchar(256) NOT NULL, reason varchar(2000) NOT NULL, created_at timestamp NOT NULL DEFAULT current_timestamp,
    updated_at timestamp NOT NULL DEFAULT current_timestamp
);
CREATE TABLE IF NOT EXISTS graph_protocol_tasks (
    protocol_task_id varchar(256) PRIMARY KEY, protocol_version varchar(32) NOT NULL, run_id varchar(128) NOT NULL REFERENCES graph_runs(run_id),
    principal_id varchar(256) NOT NULL, status varchar(32) NOT NULL, cursor_seq bigint NOT NULL DEFAULT 0,
    created_at timestamp NOT NULL DEFAULT current_timestamp, updated_at timestamp NOT NULL DEFAULT current_timestamp,
    UNIQUE(protocol_version, run_id, principal_id)
);
CREATE TABLE IF NOT EXISTS graph_telemetry_deliveries (
    delivery_id varchar(128) PRIMARY KEY, outbox_id varchar(128) REFERENCES graph_outbox(outbox_id),
    mapping_version varchar(64) NOT NULL, destination_ref varchar(512) NOT NULL, status varchar(32) NOT NULL DEFAULT 'PENDING',
    trace_id varchar(128), span_id varchar(128), last_error varchar(2000), created_at timestamp NOT NULL DEFAULT current_timestamp,
    updated_at timestamp NOT NULL DEFAULT current_timestamp, UNIQUE(outbox_id, destination_ref)
);
CREATE INDEX IF NOT EXISTS idx_graph_assurance_run ON graph_assurance_evidence(run_id, created_at);
CREATE INDEX IF NOT EXISTS idx_graph_dynamic_status ON graph_dynamic_proposals(status, updated_at);
CREATE INDEX IF NOT EXISTS idx_graph_protocol_run ON graph_protocol_tasks(run_id, status);
CREATE INDEX IF NOT EXISTS idx_graph_telemetry_status ON graph_telemetry_deliveries(status, updated_at);
