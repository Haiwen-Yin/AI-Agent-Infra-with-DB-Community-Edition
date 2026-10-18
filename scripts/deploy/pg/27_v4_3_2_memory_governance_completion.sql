-- v4.3.2 completion: content-addressed evidence, ingestion findings and
-- relational graph projection state.  These facts are additive; AGE remains
-- a rebuildable projection and is never an authorization authority.
CREATE TABLE IF NOT EXISTS cx_memory_version_artifacts (
    link_id varchar(128) PRIMARY KEY,
    version_id varchar(128) NOT NULL REFERENCES cx_memory_versions(version_id),
    artifact_id varchar(128) NOT NULL REFERENCES graph_artifacts(artifact_id),
    relation_type varchar(32) NOT NULL DEFAULT 'SOURCE',
    created_by varchar(128), created_at timestamp NOT NULL DEFAULT current_timestamp,
    UNIQUE(version_id, artifact_id, relation_type)
);
CREATE TABLE IF NOT EXISTS cx_memory_ingestion_findings (
    finding_id varchar(128) PRIMARY KEY,
    version_id varchar(128) NOT NULL REFERENCES cx_memory_versions(version_id),
    finding_type varchar(48) NOT NULL, severity varchar(16) NOT NULL DEFAULT 'LOW',
    content_digest varchar(64) NOT NULL, evidence_json text NOT NULL DEFAULT '{}',
    status varchar(24) NOT NULL DEFAULT 'OPEN', created_at timestamp NOT NULL DEFAULT current_timestamp,
    UNIQUE(version_id, finding_type, content_digest)
);
CREATE TABLE IF NOT EXISTS cx_memory_worker_results (
    result_id varchar(128) PRIMARY KEY, job_item_id varchar(128) NOT NULL REFERENCES cx_memory_job_items(item_id),
    worker_id varchar(256) NOT NULL, fencing_token bigint NOT NULL, input_digest varchar(64) NOT NULL,
    output_digest varchar(64) NOT NULL, schema_version varchar(64) NOT NULL, result_json text NOT NULL,
    validation_state varchar(24) NOT NULL, created_at timestamp NOT NULL DEFAULT current_timestamp,
    UNIQUE(job_item_id, fencing_token, output_digest)
);
ALTER TABLE cx_memory_representations ADD COLUMN IF NOT EXISTS purpose_scope varchar(128) NOT NULL DEFAULT 'RUNTIME_CONTEXT';
ALTER TABLE cx_memory_representations ADD COLUMN IF NOT EXISTS archived_at timestamp;
ALTER TABLE cx_memory_versions ADD COLUMN IF NOT EXISTS expiry_review_at timestamp;
ALTER TABLE cx_memory_versions ADD COLUMN IF NOT EXISTS security_state varchar(24) NOT NULL DEFAULT 'CLEAR';
CREATE INDEX IF NOT EXISTS idx_cx_memory_findings_version ON cx_memory_ingestion_findings(version_id, status, severity);
CREATE INDEX IF NOT EXISTS idx_cx_memory_artifacts_version ON cx_memory_version_artifacts(version_id, artifact_id);
CREATE INDEX IF NOT EXISTS idx_cx_memory_worker_results_item ON cx_memory_worker_results(job_item_id, fencing_token);
