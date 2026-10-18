-- v4.4.10 external Agent Embedding execution declaration and Contract evidence.
-- Older PostgreSQL baselines use agent_registry; keep a compatibility table
-- for the registration API rather than assuming an unqualified legacy name.
CREATE TABLE IF NOT EXISTS agent_registrations (
  agent_id varchar(128) PRIMARY KEY,
  owner_ref varchar(256) NOT NULL DEFAULT 'platform',
  runtime varchar(128) NOT NULL DEFAULT 'external',
  environment varchar(128) NOT NULL DEFAULT 'unknown',
  capabilities_json jsonb,
  status varchar(32) NOT NULL DEFAULT 'ACTIVE',
  registered_at timestamp NOT NULL DEFAULT current_timestamp,
  updated_at timestamp NOT NULL DEFAULT current_timestamp
);
ALTER TABLE agent_registrations ADD COLUMN IF NOT EXISTS embedding_mode varchar(24) NOT NULL DEFAULT 'PLATFORM_MANAGED';
ALTER TABLE agent_registrations ADD COLUMN IF NOT EXISTS embedding_model_id varchar(256);
ALTER TABLE agent_registrations ADD COLUMN IF NOT EXISTS embedding_fingerprint varchar(256);
ALTER TABLE agent_registrations ADD COLUMN IF NOT EXISTS embedding_dimension integer;
ALTER TABLE agent_registrations ADD COLUMN IF NOT EXISTS embedding_distance_metric varchar(32) NOT NULL DEFAULT 'COSINE';
ALTER TABLE agent_registrations ADD COLUMN IF NOT EXISTS embedding_normalize char(1) NOT NULL DEFAULT 'Y';
