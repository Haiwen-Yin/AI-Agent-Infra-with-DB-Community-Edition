-- v4.3.2: bind a Runtime Memory Snapshot to the live authorization subject.
ALTER TABLE cx_memory_snapshots ADD COLUMN IF NOT EXISTS principal_id varchar(128);
ALTER TABLE cx_memory_snapshots ADD COLUMN IF NOT EXISTS principal_permission_version bigint;
ALTER TABLE cx_memory_snapshots ADD COLUMN IF NOT EXISTS agent_instance_id varchar(128);
ALTER TABLE cx_memory_snapshots ADD COLUMN IF NOT EXISTS agent_fencing_token bigint;
CREATE INDEX IF NOT EXISTS idx_cx_memory_snapshots_subject
  ON cx_memory_snapshots (principal_id, agent_instance_id, state);
