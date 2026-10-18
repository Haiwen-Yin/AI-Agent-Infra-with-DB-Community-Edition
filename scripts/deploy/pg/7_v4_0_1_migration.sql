-- AI Agent Infra v4.0.1 PostgreSQL migration
BEGIN;

CREATE TABLE IF NOT EXISTS ai_schema_migrations (
    version varchar(32) PRIMARY KEY,
    checksum varchar(64) NOT NULL,
    applied_at timestamp DEFAULT CURRENT_TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS agent_db_identity (
    role_name name PRIMARY KEY,
    agent_id varchar(64) NOT NULL UNIQUE REFERENCES agent_registry(agent_id) ON DELETE CASCADE
);
REVOKE ALL ON agent_db_identity FROM PUBLIC;

CREATE OR REPLACE FUNCTION current_agent_identity() RETURNS text
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public AS $$
    SELECT COALESCE(
        (SELECT identity.agent_id::text FROM public.agent_db_identity identity
          WHERE identity.role_name = current_user),
        current_setting('app.current_agent_id', true)
    )
$$;

DO $$
DECLARE p record;
DECLARE new_qual text;
DECLARE new_check text;
BEGIN
    FOR p IN SELECT * FROM pg_policies WHERE schemaname = 'public'
             AND (qual LIKE '%app.current_agent_id%' OR with_check LIKE '%app.current_agent_id%')
    LOOP
        new_qual := replace(p.qual, 'current_setting(''app.current_agent_id''::text, true)',
                           'public.current_agent_identity()');
        new_check := replace(p.with_check, 'current_setting(''app.current_agent_id''::text, true)',
                            'public.current_agent_identity()');
        EXECUTE format('ALTER POLICY %I ON %I.%I%s%s', p.policyname, p.schemaname, p.tablename,
            CASE WHEN new_qual IS NOT NULL THEN format(' USING (%s)', new_qual) ELSE '' END,
            CASE WHEN new_check IS NOT NULL THEN format(' WITH CHECK (%s)', new_check) ELSE '' END);
    END LOOP;
END $$;

CREATE TABLE IF NOT EXISTS execution_jobs (
    job_id varchar(64) PRIMARY KEY,
    job_type varchar(32) NOT NULL,
    status varchar(24) NOT NULL,
    agent_id varchar(64) NOT NULL,
    payload_json jsonb NOT NULL,
    result_json jsonb,
    error_message varchar(2000),
    idempotency_key varchar(128) NOT NULL UNIQUE,
    attempt_count integer DEFAULT 0 NOT NULL,
    max_attempts integer DEFAULT 3 NOT NULL,
    lease_token varchar(128),
    lease_owner varchar(128),
    lease_until timestamp,
    requires_approval char(1) DEFAULT 'Y' NOT NULL,
    approved_by varchar(64),
    approved_at timestamp,
    cancel_requested char(1) DEFAULT 'N' NOT NULL,
    created_at timestamp DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp DEFAULT CURRENT_TIMESTAMP NOT NULL,
    completed_at timestamp,
    CHECK (status IN ('WAITING_APPROVAL','PENDING','RUNNING','RETRY','SUCCEEDED','FAILED','CANCELLED','REJECTED'))
);
CREATE INDEX IF NOT EXISTS idx_execution_jobs_claim ON execution_jobs(status, created_at);
CREATE INDEX IF NOT EXISTS idx_execution_jobs_lease ON execution_jobs(status, lease_until);

CREATE TABLE IF NOT EXISTS execution_attempts (
    attempt_id varchar(64) PRIMARY KEY,
    job_id varchar(64) NOT NULL REFERENCES execution_jobs(job_id) ON DELETE CASCADE,
    attempt_number integer NOT NULL,
    lease_token varchar(128) NOT NULL,
    worker_id varchar(128) NOT NULL,
    status varchar(24) NOT NULL,
    result_json jsonb,
    error_message varchar(2000),
    started_at timestamp DEFAULT CURRENT_TIMESTAMP NOT NULL,
    completed_at timestamp,
    UNIQUE(job_id, attempt_number)
);

CREATE TABLE IF NOT EXISTS execution_policies (
    policy_id varchar(64) PRIMARY KEY,
    policy_name varchar(128) NOT NULL UNIQUE,
    job_type varchar(32),
    policy_json jsonb NOT NULL,
    enabled char(1) DEFAULT 'Y' NOT NULL,
    created_at timestamp DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp DEFAULT CURRENT_TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS execution_artifacts (
    artifact_id varchar(64) PRIMARY KEY,
    job_id varchar(64) NOT NULL REFERENCES execution_jobs(job_id) ON DELETE CASCADE,
    artifact_type varchar(32) NOT NULL,
    artifact_uri varchar(1000) NOT NULL,
    content_hash varchar(64) NOT NULL,
    size_bytes bigint NOT NULL,
    created_at timestamp DEFAULT CURRENT_TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS execution_audit (
    audit_id varchar(64) PRIMARY KEY,
    job_id varchar(64) NOT NULL REFERENCES execution_jobs(job_id) ON DELETE CASCADE,
    action_type varchar(32) NOT NULL,
    actor_id varchar(128) NOT NULL,
    detail_json jsonb,
    created_at timestamp DEFAULT CURRENT_TIMESTAMP NOT NULL
);

ALTER TABLE approval_requests ADD COLUMN IF NOT EXISTS sla_deadline timestamp;
ALTER TABLE approval_requests ADD COLUMN IF NOT EXISTS sla_escalate_to varchar(64);
ALTER TABLE harness_meta ADD COLUMN IF NOT EXISTS parent_template_id varchar(64);
ALTER TABLE entity_embeddings ADD COLUMN IF NOT EXISTS embedding_version integer DEFAULT 1 NOT NULL;

CREATE TABLE IF NOT EXISTS event_dead_letter (
    dead_letter_id varchar(64) PRIMARY KEY, original_event_id varchar(64),
    agent_id varchar(64), event_type varchar(128), event_payload text,
    failure_reason varchar(4000), retry_count integer DEFAULT 0,
    max_retries integer DEFAULT 5, status varchar(32) DEFAULT 'PENDING',
    first_failed_at timestamp DEFAULT CURRENT_TIMESTAMP, last_retry_at timestamp,
    created_at timestamp DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_edl_status ON event_dead_letter(status);
CREATE INDEX IF NOT EXISTS idx_edl_agent ON event_dead_letter(agent_id);

CREATE TABLE IF NOT EXISTS dag_execution_log (
    log_id varchar(64) PRIMARY KEY, plan_id varchar(64), step_id varchar(64),
    agent_id varchar(64), execution_status varchar(32), started_at timestamp,
    completed_at timestamp, duration_ms numeric, error_message text,
    retry_count integer DEFAULT 0, created_at timestamp DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_del_plan ON dag_execution_log(plan_id);
CREATE INDEX IF NOT EXISTS idx_del_step ON dag_execution_log(step_id);

CREATE TABLE IF NOT EXISTS alert_rules (
    rule_id varchar(64) PRIMARY KEY, rule_name varchar(255) NOT NULL,
    agent_id varchar(128), metric_name varchar(128) NOT NULL,
    operator varchar(8) NOT NULL, threshold numeric NOT NULL,
    action varchar(64) NOT NULL, action_config jsonb,
    enabled char(1) DEFAULT 'Y', cooldown_minutes integer DEFAULT 30,
    last_triggered_at timestamp, created_at timestamp DEFAULT CURRENT_TIMESTAMP
);

-- Replace the v4.0.0 standalone Skill catalog with the shared Entity extension contract.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
         WHERE table_schema = current_schema() AND table_name = 'skill_meta'
           AND column_name = 'skill_id'
    ) AND to_regclass('public.skill_meta_legacy_v400') IS NULL THEN
        ALTER TABLE skill_meta RENAME TO skill_meta_legacy_v400;
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS skill_meta (
    entity_id bigint NOT NULL,
    entity_type varchar(32) DEFAULT 'SKILL' NOT NULL,
    skill_name varchar(256) NOT NULL,
    skill_version varchar(32) DEFAULT '1.0.0' NOT NULL,
    skill_type varchar(32) DEFAULT 'CUSTOM' NOT NULL,
    skill_format varchar(32) DEFAULT 'TEXT' NOT NULL,
    text_content text,
    resource_uri varchar(2048), resource_checksum varchar(128),
    runtime varchar(32) DEFAULT 'PYTHON' NOT NULL,
    parameters jsonb, dependencies jsonb,
    skill_status varchar(32) DEFAULT 'ACTIVE' NOT NULL,
    resource_filename varchar(512), resource_size bigint,
    resource_mime_type varchar(128), resource_server_host varchar(512),
    skill_description text,
    PRIMARY KEY (entity_id, entity_type),
    FOREIGN KEY (entity_id, entity_type) REFERENCES entities(entity_id, entity_type) ON DELETE CASCADE,
    UNIQUE (skill_name, skill_version)
);
ALTER TABLE skill_meta ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS skm_agent_isolation ON skill_meta;
CREATE POLICY skm_agent_isolation ON skill_meta USING (
    EXISTS (SELECT 1 FROM entities e WHERE e.entity_id = skill_meta.entity_id
      AND (e.visibility IN ('SHARED','PUBLIC') OR e.owned_by_agent = public.current_agent_identity()))
);

DO $$
DECLARE
    old record;
    new_entity_id bigint;
BEGIN
    IF to_regclass('public.skill_meta_legacy_v400') IS NOT NULL THEN
        FOR old IN SELECT * FROM skill_meta_legacy_v400 ORDER BY skill_id LOOP
            IF NOT EXISTS (
                SELECT 1 FROM skill_meta sm
                 WHERE sm.skill_name = old.skill_name
                   AND sm.skill_version = old.skill_version
            ) THEN
                INSERT INTO entities (
                    entity_type, title, category, status, owned_by_agent, visibility
                ) VALUES (
                    'SKILL', old.skill_name, old.category,
                    CASE old.status WHEN 'DEPRECATED' THEN 'ARCHIVED' ELSE old.status END,
                    old.owned_by_agent, old.visibility
                ) RETURNING entity_id INTO new_entity_id;

                INSERT INTO skill_meta (
                    entity_id, skill_name, skill_version, skill_type,
                    skill_description, resource_uri, dependencies, skill_status
                ) VALUES (
                    new_entity_id, old.skill_name, old.skill_version, old.skill_type,
                    old.description, old.resource_path, old.dependencies, old.status
                );
            END IF;
        END LOOP;
    END IF;
END $$;

INSERT INTO ai_schema_migrations(version, checksum)
VALUES ('4.0.1', 'embedded-v4.0.1')
ON CONFLICT (version) DO UPDATE SET checksum = EXCLUDED.checksum;

COMMIT;
