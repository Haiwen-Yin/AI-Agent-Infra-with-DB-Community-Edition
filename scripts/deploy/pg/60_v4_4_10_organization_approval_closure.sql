-- v4.4.10 organization approval closure. Additive so initialized baselines remain upgradeable.
ALTER TABLE approval_requests DROP CONSTRAINT IF EXISTS ck_approval_entity;
ALTER TABLE approval_requests ADD CONSTRAINT ck_approval_entity
  CHECK (entity_type IN ('STEP','LOOP','TOOL','ORGANIZATION_CHANGE'));

CREATE TABLE IF NOT EXISTS cx_agent_relationship_history (
  history_id varchar(128) PRIMARY KEY,
  version_id varchar(128) NOT NULL,
  relationship_id varchar(128) NOT NULL,
  agent_id varchar(128) NOT NULL,
  principal_id varchar(128) NOT NULL,
  relationship_role varchar(32) NOT NULL,
  responsible_organization_id varchar(128),
  operation varchar(16) NOT NULL CHECK (operation IN ('INSERT','UPDATE','END')),
  fact_json text NOT NULL,
  fact_digest varchar(128) NOT NULL,
  actor_principal_id varchar(128) NOT NULL,
  reason varchar(2000) NOT NULL,
  recorded_at timestamp NOT NULL DEFAULT current_timestamp
);
CREATE INDEX IF NOT EXISTS idx_cx_agent_rel_history
  ON cx_agent_relationship_history(agent_id, recorded_at);
