-- v4.4.10 governed model gateway, usage ledger, pricing, and wallboard.
CREATE TABLE IF NOT EXISTS cx_model_gateway_credentials (
 credential_id varchar(128) PRIMARY KEY, display_name varchar(160) NOT NULL,
 token_digest varchar(128) NOT NULL UNIQUE, scopes_json text NOT NULL,
 status varchar(24) NOT NULL, expires_at timestamptz, created_by varchar(128) NOT NULL,
 created_at timestamptz DEFAULT CURRENT_TIMESTAMP NOT NULL, revoked_at timestamptz,
 revoked_by varchar(128), revoke_reason varchar(500)
);
CREATE TABLE IF NOT EXISTS cx_model_requests (
 request_id varchar(128) PRIMARY KEY, actor_principal_id varchar(128) NOT NULL,
 agent_id varchar(128), profile_id varchar(128) NOT NULL, model_id varchar(256) NOT NULL,
 status varchar(24) NOT NULL, idempotency_key varchar(160), input_digest varchar(128) NOT NULL,
 error_category varchar(64), created_at timestamptz DEFAULT CURRENT_TIMESTAMP NOT NULL,
 completed_at timestamptz, UNIQUE(actor_principal_id,idempotency_key)
);
CREATE TABLE IF NOT EXISTS cx_model_pricing (
 price_id varchar(128) PRIMARY KEY, pricing_version varchar(64) NOT NULL,
 provider_key varchar(128) NOT NULL, model_id varchar(256) NOT NULL, currency varchar(12) NOT NULL,
 input_per_million numeric(24,12), output_per_million numeric(24,12), cache_per_million numeric(24,12), reasoning_per_million numeric(24,12),
 effective_from timestamptz NOT NULL, effective_to timestamptz, status varchar(24) NOT NULL
);
CREATE TABLE IF NOT EXISTS cx_model_usage (
 usage_id varchar(128) PRIMARY KEY, request_id varchar(128) NOT NULL REFERENCES cx_model_requests(request_id),
 actor_principal_id varchar(128) NOT NULL, agent_id varchar(128), provider_key varchar(128) NOT NULL, model_id varchar(256) NOT NULL,
 prompt_tokens bigint CHECK(prompt_tokens IS NULL OR prompt_tokens>=0), completion_tokens bigint CHECK(completion_tokens IS NULL OR completion_tokens>=0), cached_tokens bigint CHECK(cached_tokens IS NULL OR cached_tokens>=0), reasoning_tokens bigint CHECK(reasoning_tokens IS NULL OR reasoning_tokens>=0), total_tokens bigint CHECK(total_tokens IS NULL OR total_tokens>=0),
 usage_provenance varchar(32) NOT NULL, cost numeric(24,6), currency varchar(12), pricing_version varchar(64), status varchar(24) NOT NULL, latency_ms bigint NOT NULL DEFAULT 0, idempotency_key varchar(160), created_at timestamptz DEFAULT CURRENT_TIMESTAMP NOT NULL, UNIQUE(request_id)
);
CREATE TABLE IF NOT EXISTS cx_wallboard_definitions (
 definition_id varchar(128) PRIMARY KEY, version integer NOT NULL, display_name varchar(160) NOT NULL, config_json text NOT NULL, scope_json text NOT NULL, status varchar(24) NOT NULL, created_by varchar(128) NOT NULL, created_at timestamptz DEFAULT CURRENT_TIMESTAMP NOT NULL, UNIQUE(definition_id,version)
);
CREATE TABLE IF NOT EXISTS cx_model_routing_policies (
 policy_id varchar(128) PRIMARY KEY, agent_id varchar(128), profile_id varchar(128),
 routing_mode varchar(24) NOT NULL DEFAULT 'OPTIONAL', gateway_enabled boolean NOT NULL DEFAULT false,
 direct_allowed boolean NOT NULL DEFAULT true, updated_by varchar(128) NOT NULL,
 updated_at timestamptz DEFAULT CURRENT_TIMESTAMP NOT NULL, reason varchar(500),
 UNIQUE(agent_id,profile_id)
);
CREATE INDEX IF NOT EXISTS idx_model_usage_scope_time ON cx_model_usage(actor_principal_id,created_at);
CREATE INDEX IF NOT EXISTS idx_model_requests_agent_time ON cx_model_requests(agent_id,created_at);
ALTER TABLE cx_model_gateway_credentials ENABLE ROW LEVEL SECURITY;
ALTER TABLE cx_model_gateway_credentials FORCE ROW LEVEL SECURITY;
ALTER TABLE cx_model_requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE cx_model_requests FORCE ROW LEVEL SECURITY;
ALTER TABLE cx_model_usage ENABLE ROW LEVEL SECURITY;
ALTER TABLE cx_model_usage FORCE ROW LEVEL SECURITY;
ALTER TABLE cx_model_pricing ENABLE ROW LEVEL SECURITY;
ALTER TABLE cx_model_pricing FORCE ROW LEVEL SECURITY;
ALTER TABLE cx_wallboard_definitions ENABLE ROW LEVEL SECURITY;
ALTER TABLE cx_wallboard_definitions FORCE ROW LEVEL SECURITY;
ALTER TABLE cx_model_routing_policies ENABLE ROW LEVEL SECURITY;
ALTER TABLE cx_model_routing_policies FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS cx_model_usage_runtime ON cx_model_usage;
CREATE POLICY cx_model_usage_runtime ON cx_model_usage USING (actor_principal_id = current_setting('app.current_principal_id', true));
DROP POLICY IF EXISTS cx_model_requests_runtime ON cx_model_requests;
CREATE POLICY cx_model_requests_runtime ON cx_model_requests USING (actor_principal_id = current_setting('app.current_principal_id', true));
DROP POLICY IF EXISTS cx_model_pricing_runtime ON cx_model_pricing;
CREATE POLICY cx_model_pricing_runtime ON cx_model_pricing USING (true);
DROP POLICY IF EXISTS cx_wallboard_definitions_runtime ON cx_wallboard_definitions;
CREATE POLICY cx_wallboard_definitions_runtime ON cx_wallboard_definitions USING (true);
DROP POLICY IF EXISTS cx_model_routing_runtime ON cx_model_routing_policies;
CREATE POLICY cx_model_routing_runtime ON cx_model_routing_policies USING (updated_by = current_setting('app.current_principal_id', true));
