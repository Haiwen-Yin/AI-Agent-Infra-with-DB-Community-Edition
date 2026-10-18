-- v4.4.4 Agent Pool host-node onboarding completion.
CREATE TABLE IF NOT EXISTS cx_agent_pool_node_onboardings (
  onboarding_id varchar(128) PRIMARY KEY,
  node_id varchar(128) NOT NULL,
  integration_kind varchar(32) NOT NULL,
  token_digest varchar(128) NOT NULL,
  status varchar(32) NOT NULL,
  expires_at timestamp NOT NULL,
  checked_in_at timestamp,
  last_heartbeat_at timestamp,
  runtime_version varchar(128),
  result_json text NOT NULL,
  created_by varchar(128) NOT NULL,
  reason varchar(2000) NOT NULL,
  created_at timestamp NOT NULL DEFAULT current_timestamp,
  updated_at timestamp NOT NULL DEFAULT current_timestamp
);
CREATE INDEX IF NOT EXISTS idx_cx_pool_onboarding_node ON cx_agent_pool_node_onboardings(node_id,status,expires_at);
