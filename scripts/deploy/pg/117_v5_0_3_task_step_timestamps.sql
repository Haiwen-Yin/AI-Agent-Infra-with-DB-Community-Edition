-- v5.0.3 observed Task Step times; unknown historical times remain NULL.
-- Additive migration: preserve existing rows, grants and historical SQL.
ALTER TABLE TASK_STEPS ADD COLUMN IF NOT EXISTS STARTED_AT TIMESTAMP;
ALTER TABLE TASK_STEPS ADD COLUMN IF NOT EXISTS COMPLETED_AT TIMESTAMP;
