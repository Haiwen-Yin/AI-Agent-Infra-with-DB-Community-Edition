-- v4.3.2 lifecycle safety correction.
-- pg_cron is optional. When installed, remove only the obsolete job that
-- directly mutated legacy Memory rows outside lifecycle governance.
DO $cx_disable_legacy_memory_fusion$
DECLARE
    legacy_job_id bigint;
BEGIN
    IF EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = 'cron') THEN
        FOR legacy_job_id IN
            SELECT jobid FROM cron.job WHERE jobname = 'memory_fusion_job'
        LOOP
            PERFORM cron.unschedule(legacy_job_id);
        END LOOP;
    END IF;
EXCEPTION
    WHEN undefined_table OR undefined_function OR insufficient_privilege THEN
        RAISE NOTICE 'Legacy memory fusion job was not removed: %', SQLERRM;
END;
$cx_disable_legacy_memory_fusion$;
