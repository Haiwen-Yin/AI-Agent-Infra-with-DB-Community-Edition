-- Repair absent constraints as well as nondeferrable early-development ones.
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid='task_steps'::regclass
                 AND conname='fk_step_plan' AND condeferrable) THEN
    ALTER TABLE task_steps DROP CONSTRAINT IF EXISTS fk_step_plan;
    ALTER TABLE task_steps ADD CONSTRAINT fk_step_plan FOREIGN KEY(plan_id,plan_status)
      REFERENCES task_plans(plan_id,status) DEFERRABLE INITIALLY IMMEDIATE;
  END IF;
  ALTER TABLE task_steps VALIDATE CONSTRAINT fk_step_plan;
END $$;
UPDATE cx_task_migration_control SET state='VERIFIED',version=version+1,
 updated_by=current_user,reason='Task foreign key validated; status updates share one transaction',
 updated_at=CURRENT_TIMESTAMP WHERE migration_key='TASK_STEPS' AND state<>'VERIFIED';
