-- v4.4.11 durable runtime execution admission evidence.
ALTER TABLE cx_runtime_executions ADD COLUMN IF NOT EXISTS isolation_evidence_json text;
ALTER TABLE cx_runtime_executions ADD COLUMN IF NOT EXISTS isolation_evidence_ref varchar(512);
ALTER TABLE cx_runtime_executions ADD COLUMN IF NOT EXISTS isolation_admitted_at timestamp;
