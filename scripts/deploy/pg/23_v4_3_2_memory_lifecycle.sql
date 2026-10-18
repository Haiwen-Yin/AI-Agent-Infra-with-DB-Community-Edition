-- v4.3.2 Versioned Memory Lifecycle.  Relational facts remain authoritative;
-- Apache AGE projections consume CX_MEMORY_PROJECTION_OUTBOX asynchronously.

CREATE TABLE IF NOT EXISTS cx_memory_families (
    family_id varchar(128) PRIMARY KEY,
    legacy_entity_id varchar(128) UNIQUE,
    current_version_id varchar(128),
    family_state varchar(24) NOT NULL DEFAULT 'ACTIVE',
    owner_principal_id varchar(128), workspace_id varchar(128),
    security_domain_id varchar(128), classification varchar(32) NOT NULL DEFAULT 'INTERNAL',
    created_at timestamp NOT NULL DEFAULT current_timestamp,
    updated_at timestamp NOT NULL DEFAULT current_timestamp,
    row_version bigint NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS cx_memory_versions (
    version_id varchar(128) PRIMARY KEY,
    family_id varchar(128) NOT NULL REFERENCES cx_memory_families(family_id),
    version_number integer NOT NULL,
    legacy_entity_id varchar(128), title varchar(500) NOT NULL, body_text text,
    content_digest varchar(64) NOT NULL, memory_type varchar(32) NOT NULL DEFAULT 'EPISODIC',
    memory_scope varchar(32) NOT NULL DEFAULT 'AGENT_MEMORY', lifecycle_state varchar(24) NOT NULL DEFAULT 'ACTIVE',
    classification varchar(32) NOT NULL DEFAULT 'INTERNAL', source_ref varchar(256), source_digest varchar(64),
    owner_principal_id varchar(128), owner_agent_id varchar(128), workspace_id varchar(128), security_domain_id varchar(128),
    valid_from timestamp NOT NULL DEFAULT current_timestamp, valid_until timestamp, policy_version varchar(64) NOT NULL DEFAULT 'v4.3.2',
    created_by varchar(128), reason text, metadata_json text NOT NULL DEFAULT '{}', created_at timestamp NOT NULL DEFAULT current_timestamp,
    CONSTRAINT cx_memory_versions_family_number_uk UNIQUE (family_id, version_number),
    CONSTRAINT cx_memory_versions_state_ck CHECK (lifecycle_state IN ('CANDIDATE','ACTIVE','STALE','CONFLICTED','SUPERSEDED','EXPIRED','MIGRATED','ARCHIVED','QUARANTINED','UNAVAILABLE')),
    CONSTRAINT cx_memory_versions_type_ck CHECK (memory_type IN ('EPISODIC','FACT','PREFERENCE','DECISION','PROCEDURAL','EXPERIENCE')),
    CONSTRAINT cx_memory_versions_scope_ck CHECK (memory_scope IN ('RUNTIME_CONTEXT','CHANNEL_MEMORY','AGENT_MEMORY','WORKSPACE_MEMORY','ENTERPRISE_KNOWLEDGE'))
);
DO $cx_memory_current_fk$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'cx_memory_families_current_fk') THEN
    ALTER TABLE cx_memory_families ADD CONSTRAINT cx_memory_families_current_fk
      FOREIGN KEY (current_version_id) REFERENCES cx_memory_versions(version_id) DEFERRABLE INITIALLY DEFERRED;
  END IF;
END $cx_memory_current_fk$;

CREATE TABLE IF NOT EXISTS cx_memory_representations (
    representation_id varchar(128) PRIMARY KEY, version_id varchar(128) NOT NULL REFERENCES cx_memory_versions(version_id),
    representation_type varchar(32) NOT NULL, body_text text, content_digest varchar(64) NOT NULL, token_count integer NOT NULL DEFAULT 0,
    generation_method varchar(32) NOT NULL DEFAULT 'DETERMINISTIC', generator_version varchar(128), validation_state varchar(24) NOT NULL DEFAULT 'VALID',
    source_version_ids_json text NOT NULL DEFAULT '[]', index_state varchar(24) NOT NULL DEFAULT 'HOT', created_at timestamp NOT NULL DEFAULT current_timestamp,
    CONSTRAINT cx_memory_repr_type_ck CHECK (representation_type IN ('SOURCE','ATOMIC_FACT','SHORT_SUMMARY','STANDARD_SUMMARY','TOPIC_SUMMARY','CHAIN_SUMMARY'))
);
CREATE TABLE IF NOT EXISTS cx_memory_relations (
    relation_id varchar(128) PRIMARY KEY, source_version_id varchar(128) NOT NULL REFERENCES cx_memory_versions(version_id),
    target_version_id varchar(128) NOT NULL REFERENCES cx_memory_versions(version_id), relation_type varchar(32) NOT NULL,
    relation_state varchar(24) NOT NULL DEFAULT 'ACTIVE', deterministic boolean NOT NULL DEFAULT false, confidence numeric(5,4),
    method varchar(128), evidence_json text NOT NULL DEFAULT '{}', rule_version varchar(128), created_by varchar(128), created_at timestamp NOT NULL DEFAULT current_timestamp,
    CONSTRAINT cx_memory_relation_distinct_ck CHECK (source_version_id <> target_version_id)
);
CREATE TABLE IF NOT EXISTS cx_memory_snapshots (
    snapshot_id varchar(128) PRIMARY KEY, run_id varchar(128) NOT NULL, snapshot_version integer NOT NULL DEFAULT 1,
    purpose varchar(128) NOT NULL DEFAULT 'RUNTIME_CONTEXT', policy_version varchar(64) NOT NULL, query_digest varchar(64) NOT NULL,
    snapshot_digest varchar(64) NOT NULL, state varchar(24) NOT NULL DEFAULT 'ACTIVE', created_by varchar(128), reason text,
    idempotency_key varchar(128), created_at timestamp NOT NULL DEFAULT current_timestamp,
    CONSTRAINT cx_memory_snapshot_idempotency_uk UNIQUE (run_id, idempotency_key)
);
CREATE TABLE IF NOT EXISTS cx_memory_snapshot_members (
    snapshot_id varchar(128) NOT NULL REFERENCES cx_memory_snapshots(snapshot_id), family_id varchar(128) NOT NULL REFERENCES cx_memory_families(family_id),
    version_id varchar(128) NOT NULL REFERENCES cx_memory_versions(version_id), representation_id varchar(128) REFERENCES cx_memory_representations(representation_id),
    selection_rank integer NOT NULL DEFAULT 0, selected_tokens integer NOT NULL DEFAULT 0,
    PRIMARY KEY (snapshot_id, family_id)
);
CREATE TABLE IF NOT EXISTS cx_memory_policies (
    policy_id varchar(128) PRIMARY KEY, policy_name varchar(128) NOT NULL UNIQUE, policy_version varchar(64) NOT NULL,
    policy_json text NOT NULL, status varchar(24) NOT NULL DEFAULT 'ACTIVE', created_by varchar(128), created_at timestamp NOT NULL DEFAULT current_timestamp, updated_at timestamp NOT NULL DEFAULT current_timestamp
);
CREATE TABLE IF NOT EXISTS cx_memory_jobs (
    job_id varchar(128) PRIMARY KEY, job_type varchar(32) NOT NULL, status varchar(24) NOT NULL DEFAULT 'QUEUED', scope_json text NOT NULL DEFAULT '{}',
    dry_run boolean NOT NULL DEFAULT true, policy_version varchar(64) NOT NULL, requested_by varchar(128), reason text, idempotency_key varchar(128) UNIQUE,
    lease_owner varchar(128), lease_expires_at timestamp, fencing_token bigint NOT NULL DEFAULT 0, checkpoint_json text NOT NULL DEFAULT '{}',
    created_at timestamp NOT NULL DEFAULT current_timestamp, updated_at timestamp NOT NULL DEFAULT current_timestamp
);
CREATE TABLE IF NOT EXISTS cx_memory_job_items (
    item_id varchar(128) PRIMARY KEY, job_id varchar(128) NOT NULL REFERENCES cx_memory_jobs(job_id), subject_version_id varchar(128) REFERENCES cx_memory_versions(version_id),
    status varchar(24) NOT NULL DEFAULT 'QUEUED', attempt_count integer NOT NULL DEFAULT 0, lease_owner varchar(128), lease_expires_at timestamp, fencing_token bigint NOT NULL DEFAULT 0,
    input_digest varchar(64), result_json text NOT NULL DEFAULT '{}', error_code varchar(64), created_at timestamp NOT NULL DEFAULT current_timestamp, updated_at timestamp NOT NULL DEFAULT current_timestamp
);
CREATE TABLE IF NOT EXISTS cx_memory_usage_events (
    usage_event_id varchar(128) PRIMARY KEY, version_id varchar(128) NOT NULL REFERENCES cx_memory_versions(version_id),
    event_type varchar(32) NOT NULL, principal_id varchar(128), agent_id varchar(128), run_id varchar(128), purpose varchar(128),
    outcome varchar(32), value_numeric numeric(12,4), idempotency_key varchar(128), metadata_json text NOT NULL DEFAULT '{}', created_at timestamp NOT NULL DEFAULT current_timestamp,
    CONSTRAINT cx_memory_usage_idempotency_uk UNIQUE (version_id, idempotency_key)
);
CREATE TABLE IF NOT EXISTS cx_memory_candidates (
    candidate_id varchar(128) PRIMARY KEY, candidate_type varchar(32) NOT NULL, source_version_id varchar(128) REFERENCES cx_memory_versions(version_id),
    target_version_id varchar(128) REFERENCES cx_memory_versions(version_id), proposed_json text NOT NULL, confidence numeric(5,4), status varchar(24) NOT NULL DEFAULT 'PENDING',
    policy_result varchar(24) NOT NULL DEFAULT 'REVIEW', created_by varchar(128), reason text, idempotency_key varchar(128) UNIQUE, created_at timestamp NOT NULL DEFAULT current_timestamp, updated_at timestamp NOT NULL DEFAULT current_timestamp
);
CREATE TABLE IF NOT EXISTS cx_memory_reviews (
    review_id varchar(128) PRIMARY KEY, candidate_id varchar(128) NOT NULL REFERENCES cx_memory_candidates(candidate_id), reviewer_principal_id varchar(128) NOT NULL,
    decision varchar(24) NOT NULL, reason text NOT NULL, created_at timestamp NOT NULL DEFAULT current_timestamp
);
CREATE TABLE IF NOT EXISTS cx_memory_projection_outbox (
    outbox_id varchar(128) PRIMARY KEY, aggregate_type varchar(32) NOT NULL, aggregate_id varchar(128) NOT NULL, event_type varchar(32) NOT NULL,
    payload_json text NOT NULL, status varchar(24) NOT NULL DEFAULT 'PENDING', attempts integer NOT NULL DEFAULT 0, available_at timestamp NOT NULL DEFAULT current_timestamp,
    lease_owner varchar(128), lease_expires_at timestamp, fencing_token bigint NOT NULL DEFAULT 0, created_at timestamp NOT NULL DEFAULT current_timestamp, processed_at timestamp
);

CREATE INDEX IF NOT EXISTS idx_cx_memory_versions_current ON cx_memory_versions (family_id, lifecycle_state, valid_until);
CREATE INDEX IF NOT EXISTS idx_cx_memory_versions_scope ON cx_memory_versions (memory_scope, workspace_id, owner_agent_id, classification);
CREATE INDEX IF NOT EXISTS idx_cx_memory_relations_source ON cx_memory_relations (source_version_id, relation_state, relation_type);
CREATE INDEX IF NOT EXISTS idx_cx_memory_relations_target ON cx_memory_relations (target_version_id, relation_state, relation_type);
CREATE INDEX IF NOT EXISTS idx_cx_memory_jobs_claim ON cx_memory_jobs (status, lease_expires_at, created_at);
CREATE INDEX IF NOT EXISTS idx_cx_memory_outbox_claim ON cx_memory_projection_outbox (status, available_at, lease_expires_at);

-- Rerunnable adoption. Existing identity and payload remain untouched.
INSERT INTO cx_memory_families (family_id, legacy_entity_id, family_state, owner_principal_id, workspace_id, classification)
SELECT 'MF-' || e.entity_id::text, e.entity_id::text, 'ACTIVE', e.owned_by_agent, e.workspace_id::text, 'INTERNAL'
  FROM entities e WHERE e.entity_type = 'MEMORY'
ON CONFLICT (legacy_entity_id) DO NOTHING;
INSERT INTO cx_memory_versions (version_id, family_id, version_number, legacy_entity_id, title, body_text, content_digest, memory_type, memory_scope, lifecycle_state, owner_agent_id, workspace_id, created_by, reason)
SELECT 'MV-' || e.entity_id::text || '-1', 'MF-' || e.entity_id::text, 1, e.entity_id::text, e.title, e.content,
       md5(coalesce(e.content, '') || '|' || coalesce(e.summary, '') || '|' || coalesce(e.updated_at::text, '')),
       CASE WHEN upper(coalesce(e.category, '')) = 'DECISION' THEN 'DECISION' WHEN upper(coalesce(e.category, '')) = 'PREFERENCE' THEN 'PREFERENCE' ELSE 'EPISODIC' END,
       CASE WHEN e.workspace_id IS NOT NULL THEN 'WORKSPACE_MEMORY' WHEN e.visibility IN ('SHARED','PUBLIC') THEN 'AGENT_MEMORY' ELSE 'AGENT_MEMORY' END,
       CASE WHEN e.status = 'ACTIVE' THEN 'ACTIVE' ELSE 'STALE' END, e.owned_by_agent, e.workspace_id::text, e.source_agent, 'v4.3.1 adoption'
  FROM entities e WHERE e.entity_type = 'MEMORY'
ON CONFLICT (family_id, version_number) DO NOTHING;
UPDATE cx_memory_families f SET current_version_id = v.version_id, updated_at = current_timestamp
  FROM cx_memory_versions v WHERE f.family_id = v.family_id AND v.version_number = 1 AND f.current_version_id IS NULL;
INSERT INTO cx_memory_representations (representation_id, version_id, representation_type, body_text, content_digest, token_count, source_version_ids_json)
SELECT 'MR-' || v.version_id, v.version_id, 'SOURCE', v.body_text, v.content_digest, greatest(0, length(coalesce(v.body_text, '')) / 4), '[]'
  FROM cx_memory_versions v
ON CONFLICT (representation_id) DO NOTHING;
INSERT INTO cx_memory_policies (policy_id, policy_name, policy_version, policy_json, created_by)
VALUES ('MEMPOL-DEFAULT', 'default', 'v4.3.2', '{"max_chain_nodes":100,"max_hops":3,"max_candidates":50,"auto_archive_days":90,"llm_enabled":false}', 'MIGRATION_V4_3_2')
ON CONFLICT (policy_name) DO NOTHING;
