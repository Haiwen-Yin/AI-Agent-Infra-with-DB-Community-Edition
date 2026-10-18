-- v4.4.15 task status transition contract.  Keep the composite FK, but allow
-- one transaction to move the parent and child status together.
DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname='fk_step_plan') THEN
    ALTER TABLE task_steps DROP CONSTRAINT fk_step_plan;
    ALTER TABLE task_steps ADD CONSTRAINT fk_step_plan FOREIGN KEY (plan_id, plan_status)
      REFERENCES task_plans(plan_id, status) DEFERRABLE INITIALLY IMMEDIATE;
  END IF;
END $$;
