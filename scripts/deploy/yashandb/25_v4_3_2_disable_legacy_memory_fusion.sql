-- v4.3.2 lifecycle safety correction.
-- The pre-v4.3.2 scheduler mutates legacy Memory rows directly, bypassing
-- immutable versions, review candidates, snapshots, and lifecycle audit.
-- Remove it rather than silently changing its action; governed durable jobs
-- are the only supported automation path after this migration.
DECLARE
    legacy_job_count NUMBER := 0;
BEGIN
    SELECT COUNT(*) INTO legacy_job_count
      FROM USER_SCHEDULER_JOBS
     WHERE JOB_NAME = 'MEMORY_FUSION_JOB';
    IF legacy_job_count > 0 THEN
        DBMS_SCHEDULER.DROP_JOB('MEMORY_FUSION_JOB', FALSE);
    END IF;
EXCEPTION
    WHEN OTHERS THEN
        -- A concurrent scheduler cleanup may remove the job after the check.
        IF legacy_job_count > 0 THEN RAISE; END IF;
END;
/
