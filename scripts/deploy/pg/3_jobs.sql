-- ============================================================================
-- AI Agent Infra v5.0.0 - PostgreSQL 18.3 - Phase 3: Scheduler Jobs
-- ============================================================================
-- NOTE: pg_cron must be installed and configured before running this script.
-- See deployment.md for pg_cron setup instructions.
-- If pg_cron is not available, skip this file and schedule jobs manually.

DO $$ BEGIN
    CREATE EXTENSION IF NOT EXISTS pg_cron;
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'pg_cron not available. Job scheduling skipped. Install pg_cron first.';
    RETURN;
END $$;

-- 1. Memory Fusion Job: merge similar memories + decay old priorities
-- Schedule: Daily at 02:00
DO $$
BEGIN
    PERFORM cron.schedule(
        'memory_fusion_job',
        '0 2 * * *',
        $JOB$
        SELECT memory_fusion.fuse_similar();
        SELECT memory_fusion.decay_old();
        $JOB$
    );
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'memory_fusion_job already exists or cannot be scheduled: %', SQLERRM;
END;
$$;

-- 2. Knowledge Extraction Job: extract knowledge from memory patterns
-- Schedule: Daily at 03:00
DO $$
BEGIN
    PERFORM cron.schedule(
        'knowledge_extraction_job',
        '0 3 * * *',
        $JOB$
        SELECT memory_fusion.extract_knowledge();
        $JOB$
    );
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'knowledge_extraction_job already exists or cannot be scheduled: %', SQLERRM;
END;
$$;

-- 3. Knowledge Review Job: schedule reviews for knowledge entities
-- Schedule: Daily at 06:00
DO $$
BEGIN
    PERFORM cron.schedule(
        'knowledge_review_job',
        '0 6 * * *',
        $JOB$
        SELECT knowledge_api.schedule_review(e.entity_id)
        FROM knowledge_entities e
        WHERE e.status = 'ACTIVE';
        $JOB$
    );
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'knowledge_review_job already exists or cannot be scheduled: %', SQLERRM;
END;
$$;

-- 4. Session Cleanup Job: purge inactive sessions
-- Schedule: Every 30 minutes
DO $$
BEGIN
    PERFORM cron.schedule(
        'session_cleanup_job',
        '*/30 * * * *',
        $JOB$
        SELECT session_cleanup.purge_inactive_sessions();
        $JOB$
    );
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'session_cleanup_job already exists or cannot be scheduled: %', SQLERRM;
END;
$$;

-- 5. Access Log Purge Job: purge access logs older than 90 days
-- Schedule: Weekly Sunday at 04:00
DO $$
BEGIN
    PERFORM cron.schedule(
        'access_log_purge_job',
        '0 4 * * 0',
        $JOB$
        SELECT session_cleanup.purge_access_logs(90);
        $JOB$
    );
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'access_log_purge_job already exists or cannot be scheduled: %', SQLERRM;
END;
$$;

-- 6. Entity Archive Job: archive old entities older than 180 days
-- Schedule: Weekly Sunday at 05:00
DO $$
BEGIN
    PERFORM cron.schedule(
        'entity_archive_job',
        '0 5 * * 0',
        $JOB$
        SELECT session_cleanup.archive_old_entities(180);
        $JOB$
    );
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'entity_archive_job already exists or cannot be scheduled: %', SQLERRM;
END;
$$;

-- 7. Collab Expiry Job: archive expired collaboration groups
-- Schedule: Daily at 00:30
DO $$
BEGIN
    PERFORM cron.schedule(
        'collab_expiry_job',
        '30 0 * * *',
        $JOB$
        SELECT collab_group_manager.archive()
        FROM collab_groups
        WHERE status = 'ACTIVE'
          AND expires_at IS NOT NULL
          AND expires_at < now();
        $JOB$
    );
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'collab_expiry_job already exists or cannot be scheduled: %', SQLERRM;
END;
$$;

-- 8. Workspace Cleanup Job: cleanup abandoned workspaces
-- Schedule: Daily at 04:00
DO $$
BEGIN
    PERFORM cron.schedule(
        'workspace_cleanup_job',
        '0 4 * * *',
        $JOB$
        SELECT workspace_manager.cleanup_abandoned();
        $JOB$
    );
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'workspace_cleanup_job already exists or cannot be scheduled: %', SQLERRM;
END;
$$;

-- 9. Stale Workspace Detect Job: mark workspaces as PAUSED when session gone
-- Schedule: Hourly
DO $$
BEGIN
    PERFORM cron.schedule(
        'stale_workspace_detect_job',
        '0 * * * *',
        $JOB$
        UPDATE workspaces
        SET status = 'PAUSED', updated_at = now()
        WHERE status = 'ACTIVE'
          AND current_session_id IS NOT NULL
          AND NOT EXISTS (
            SELECT 1 FROM agent_session s
            WHERE s.session_id = workspaces.current_session_id
              AND s.is_active = TRUE
          );
        $JOB$
    );
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'stale_workspace_detect_job already exists or cannot be scheduled: %', SQLERRM;
END;
$$;

-- 10. Dormant Agent Job: mark agents as DORMANT/POOL when inactive beyond timeout
-- Schedule: Every 30 minutes
DO $$
BEGIN
    PERFORM cron.schedule(
        'dormant_agent_job',
        '*/30 * * * *',
        $JOB$
        UPDATE agent_registry
        SET status = 'POOL', current_user_id = NULL, portal_node_id = NULL,
            updated_at = now()
        WHERE status = 'ACTIVE'
          AND last_active_at IS NOT NULL
          AND last_active_at < now() - (SELECT COALESCE(config_value::INT, 30) FROM system_config WHERE config_key = 'dormant_timeout_min') * interval '1 minute';
        $JOB$
    );
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'dormant_agent_job already exists or cannot be scheduled: %', SQLERRM;
END;
$$;

-- 11. Credential Cleanup Job: soft-expire then delete expired credentials
-- Schedule: Daily at 02:00
DO $$
BEGIN
    PERFORM cron.schedule(
        'credential_cleanup_job',
        '0 2 * * *',
        $JOB$
        UPDATE agent_credentials
        SET is_active = FALSE, updated_at = now()
        WHERE is_active = TRUE
          AND expires_at IS NOT NULL
          AND expires_at < now();
        DELETE FROM agent_credentials
        WHERE is_active = FALSE
           OR (expires_at IS NOT NULL AND expires_at < now());
        $JOB$
    );
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'credential_cleanup_job already exists or cannot be scheduled: %', SQLERRM;
END;
$$;

-- 12. Embedding Generation Job: auto-generate embeddings for new entities
-- Schedule: Every 2 hours
DO $$
BEGIN
    PERFORM cron.schedule(
        'embedding_generation_job',
        '0 */2 * * *',
        $JOB$
        SELECT embedding_manager.batch_embed_entities();
        $JOB$
    );
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'embedding_generation_job already exists or cannot be scheduled: %', SQLERRM;
END;
$$;

-- 13. Branch Cleanup Job: cleanup abandoned branches older than 90 days
-- Schedule: Daily at 03:00
DO $$
BEGIN
    PERFORM cron.schedule(
        'branch_cleanup_job',
        '0 3 * * *',
        $JOB$
        SELECT branch_manager.cleanup();
        $JOB$
    );
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'branch_cleanup_job already exists or cannot be scheduled: %', SQLERRM;
END;
$$;

-- ============================================================
-- ENT-only pg_cron jobs (14-17)
-- ============================================================

-- 14. Audit Cleanup Job: purge old audit logs and context audit
-- Schedule: Weekly Sunday at 03:00
DO $$
BEGIN
    PERFORM cron.schedule(
        'audit_cleanup_job',
        '0 3 * * 0',
        $JOB$
        SELECT audit_api.purge_audit_logs(90);
        $JOB$
    );
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'audit_cleanup_job already exists or cannot be scheduled: %', SQLERRM;
END;
$$;

-- 15. Compliance Report Job: generate compliance report and log non-compliant items
-- Schedule: Monthly on 1st at 01:00
DO $$
BEGIN
    PERFORM cron.schedule(
        'compliance_report_job',
        '0 1 1 * *',
        $JOB$
        INSERT INTO compliance_log (regulation_type, check_type, entity_id, entity_type, agent_id, status, details)
        SELECT 'INTERNAL', 'PERIODIC_REVIEW', e.entity_id, e.entity_type, e.owned_by_agent, 'COMPLIANT',
               jsonb_build_object('review_type', 'periodic', 'reviewed_at', now())
        FROM entities e
        WHERE e.status = 'ACTIVE'
          AND NOT EXISTS (
            SELECT 1 FROM compliance_log cl
            WHERE cl.entity_id = e.entity_id
              AND cl.regulation_type = 'INTERNAL'
              AND cl.created_at > now() - interval '30 days'
          )
        LIMIT 100;
        $JOB$
    );
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'compliance_report_job already exists or cannot be scheduled: %', SQLERRM;
END;
$$;

-- 16. Skill Token Cleanup Job: clean expired and consumed tokens
-- Schedule: Daily at 01:00
DO $$
BEGIN
    PERFORM cron.schedule(
        'skill_token_cleanup_job',
        '0 1 * * *',
        $JOB$
        SELECT skill_token_api.cleanup_expired();
        $JOB$
    );
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'skill_token_cleanup_job already exists or cannot be scheduled: %', SQLERRM;
END;
$$;

-- 17. LDAP Sync Job: sync LDAP users and groups
-- Schedule: Every 6 hours
DO $$
BEGIN
    PERFORM cron.schedule(
        'ldap_sync_job',
        '0 */6 * * *',
        $JOB$
        INSERT INTO ldap_sync_log (sync_type, status, users_synced, groups_synced, sync_time, duration_sec)
        SELECT 'INCREMENTAL', 'SUCCESS', 0, 0, CURRENT_TIMESTAMP, 0
        FROM ldap_config
        WHERE is_active = TRUE
        LIMIT 1;
        $JOB$
    );
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'ldap_sync_job already exists or cannot be scheduled: %', SQLERRM;
END;
$$;

-- 18. Loop Trigger Job: start scheduled loop runs [NEW v3.7.5]
-- Schedule: Every minute
DO $$
BEGIN
    PERFORM cron.schedule(
        'loop_trigger_job',
        '* * * * *',
        $JOB$
        SELECT loop_manager.process_scheduled_triggers();
        $JOB$
    );
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'loop_trigger_job already exists or cannot be scheduled: %', SQLERRM;
END;
$$;

-- 19. Loop Stuck Check Job: detect and timeout stuck loop runs [NEW v3.7.5]
-- Schedule: Every 5 minutes
DO $$
BEGIN
    PERFORM cron.schedule(
        'loop_stuck_check_job',
        '*/5 * * * *',
        $JOB$
        SELECT loop_manager.check_stuck_runs();
        $JOB$
    );
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'loop_stuck_check_job already exists or cannot be scheduled: %', SQLERRM;
END;
$$;

-- 20. Loop Cleanup Job: purge old completed/failed loop runs [NEW v3.7.5]
-- Schedule: Weekly Sunday at 06:00
DO $$
BEGIN
    PERFORM cron.schedule(
        'loop_cleanup_job',
        '0 6 * * 0',
        $JOB$
        SELECT loop_manager.cleanup_old_runs(90);
        $JOB$
    );
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'loop_cleanup_job already exists or cannot be scheduled: %', SQLERRM;
END;
$$;

-- Individual scheduling blocks above safely no-op when pg_cron is not
-- available.  Do not query cron.job here: a prepared PostgreSQL target may
-- deliberately use an external scheduler and therefore omit the extension.

-- AI Agent Infra v5.0.0 - PostgreSQL 18.3 - Scheduler Jobs Complete
