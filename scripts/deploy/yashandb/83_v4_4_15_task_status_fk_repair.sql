-- v4.4.15 task status transition marker. Runtime updates child PLAN_STATUS
-- before the parent status and preserves existing native constraints.
COMMENT ON TABLE TASK_STEPS IS 'v4.4.15 task status transition contract';
