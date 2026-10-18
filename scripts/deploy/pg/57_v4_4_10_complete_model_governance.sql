-- v4.4.10 complete model governance: quota, replay, finance, evidence, and wallboard versions.
ALTER TABLE cx_model_requests ADD COLUMN IF NOT EXISTS correlation_id varchar(128);
ALTER TABLE cx_model_requests ADD COLUMN IF NOT EXISTS credential_id varchar(128);

CREATE TABLE IF NOT EXISTS cx_model_quota_policies (
 policy_id varchar(128) PRIMARY KEY, policy_key varchar(128) NOT NULL, version integer NOT NULL,
 scope_type varchar(32) NOT NULL, scope_id varchar(128), metric varchar(16) NOT NULL,
 limit_value numeric(24,6) NOT NULL CHECK(limit_value>=0), currency varchar(12),
 enforcement varchar(16) NOT NULL CHECK(enforcement IN ('HARD','WARN')),
 window_type varchar(16) NOT NULL CHECK(window_type IN ('DAILY','MONTHLY')),
 reservation_value numeric(24,6) NOT NULL CHECK(reservation_value>=0),
 incomplete_policy varchar(24) NOT NULL CHECK(incomplete_policy IN ('CHARGE_RESERVED','RELEASE')),
 effective_from timestamptz NOT NULL, effective_to timestamptz, status varchar(24) NOT NULL,
 created_by varchar(128) NOT NULL, reason varchar(500) NOT NULL, created_at timestamptz DEFAULT CURRENT_TIMESTAMP NOT NULL,
 UNIQUE(policy_key,version)
);
CREATE TABLE IF NOT EXISTS cx_model_quota_reservations (
 reservation_id varchar(128) PRIMARY KEY, request_id varchar(128) NOT NULL, policy_id varchar(128) NOT NULL,
 window_start timestamptz NOT NULL, window_end timestamptz NOT NULL,
 reserved_value numeric(24,6) NOT NULL CHECK(reserved_value>=0), settled_value numeric(24,6),
 status varchar(24) NOT NULL, warning varchar(500), expires_at timestamptz NOT NULL,
 created_at timestamptz DEFAULT CURRENT_TIMESTAMP NOT NULL, updated_at timestamptz DEFAULT CURRENT_TIMESTAMP NOT NULL,
 UNIQUE(request_id,policy_id)
);
CREATE INDEX IF NOT EXISTS idx_model_quota_window ON cx_model_quota_reservations(policy_id,window_start,status);

CREATE TABLE IF NOT EXISTS cx_model_replay_snapshots (
 request_id varchar(128) PRIMARY KEY, response_cipher text NOT NULL, response_digest varchar(128) NOT NULL,
 key_reference varchar(128) NOT NULL, byte_count integer NOT NULL CHECK(byte_count>=0 AND byte_count<=1048576),
 expires_at timestamptz NOT NULL, created_at timestamptz DEFAULT CURRENT_TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS cx_provider_invoice_batches (
 batch_id varchar(128) PRIMARY KEY, provider_key varchar(128) NOT NULL, external_invoice_id varchar(160) NOT NULL,
 source_digest varchar(128) NOT NULL, currency varchar(12) NOT NULL, period_start timestamptz NOT NULL,
 period_end timestamptz NOT NULL, total_amount numeric(24,6) NOT NULL, status varchar(24) NOT NULL,
 imported_by varchar(128) NOT NULL, reason varchar(500) NOT NULL, created_at timestamptz DEFAULT CURRENT_TIMESTAMP NOT NULL,
 UNIQUE(provider_key,external_invoice_id)
);
CREATE TABLE IF NOT EXISTS cx_provider_invoice_lines (
 line_id varchar(128) PRIMARY KEY, batch_id varchar(128) NOT NULL, external_line_id varchar(160) NOT NULL,
 model_id varchar(256), quantity numeric(24,6), amount numeric(24,6) NOT NULL, currency varchar(12) NOT NULL,
 line_digest varchar(128) NOT NULL, created_at timestamptz DEFAULT CURRENT_TIMESTAMP NOT NULL,
 UNIQUE(batch_id,external_line_id)
);
CREATE TABLE IF NOT EXISTS cx_model_reconciliations (
 reconciliation_id varchar(128) PRIMARY KEY, line_id varchar(128) NOT NULL, usage_id varchar(128),
 rule_version varchar(64) NOT NULL, confidence numeric(8,6), invoice_amount numeric(24,6) NOT NULL,
 calculated_amount numeric(24,6), variance_amount numeric(24,6), status varchar(24) NOT NULL,
 created_by varchar(128) NOT NULL, reason varchar(500) NOT NULL, created_at timestamptz DEFAULT CURRENT_TIMESTAMP NOT NULL,
 UNIQUE(line_id,usage_id,rule_version)
);
CREATE TABLE IF NOT EXISTS cx_provider_invoice_corrections (
 correction_id varchar(128) PRIMARY KEY, line_id varchar(128) NOT NULL, prior_correction_id varchar(128),
 amount_delta numeric(24,6) NOT NULL CHECK(amount_delta<>0), currency varchar(12) NOT NULL,
 created_by varchar(128) NOT NULL, reason varchar(500) NOT NULL,
 created_at timestamptz DEFAULT CURRENT_TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS cx_model_allocation_rules (
 rule_id varchar(128) PRIMARY KEY, rule_key varchar(128) NOT NULL, version integer NOT NULL,
 target_type varchar(32) NOT NULL, target_id varchar(128) NOT NULL, percentage numeric(9,6) NOT NULL CHECK(percentage>=0 AND percentage<=100),
 currency varchar(12), effective_from timestamptz NOT NULL, effective_to timestamptz,
 status varchar(24) NOT NULL, created_by varchar(128) NOT NULL, reason varchar(500) NOT NULL,
 created_at timestamptz DEFAULT CURRENT_TIMESTAMP NOT NULL, UNIQUE(rule_key,version,target_type,target_id)
);
CREATE TABLE IF NOT EXISTS cx_model_allocations (
 allocation_id varchar(128) PRIMARY KEY, source_type varchar(16) NOT NULL, source_id varchar(128) NOT NULL,
 rule_id varchar(128) NOT NULL, target_type varchar(32) NOT NULL, target_id varchar(128) NOT NULL,
 amount numeric(24,6) NOT NULL, currency varchar(12) NOT NULL, remainder boolean NOT NULL DEFAULT false,
 created_at timestamptz DEFAULT CURRENT_TIMESTAMP NOT NULL, UNIQUE(source_type,source_id,rule_id,target_type,target_id)
);

CREATE TABLE IF NOT EXISTS cx_model_evidence_adapters (
 adapter_id varchar(128) NOT NULL, display_name varchar(160) NOT NULL, key_version integer NOT NULL,
 verification_key text NOT NULL, scopes_json text NOT NULL, status varchar(24) NOT NULL,
 created_by varchar(128) NOT NULL, created_at timestamptz DEFAULT CURRENT_TIMESTAMP NOT NULL,
 revoked_at timestamptz, revoked_by varchar(128), revoke_reason varchar(500), PRIMARY KEY(adapter_id,key_version)
);
CREATE TABLE IF NOT EXISTS cx_model_evidence_batches (
 batch_id varchar(128) PRIMARY KEY, adapter_id varchar(128) NOT NULL, key_version integer NOT NULL,
 sequence_no bigint NOT NULL CHECK(sequence_no>=0), nonce varchar(128) NOT NULL, payload_digest varchar(128) NOT NULL,
 signature_digest varchar(128) NOT NULL, observed_from timestamptz NOT NULL, observed_to timestamptz NOT NULL,
 provider_key varchar(128), agent_id varchar(128), request_count bigint NOT NULL CHECK(request_count>=0),
 total_tokens bigint, usage_provenance varchar(32) NOT NULL, status varchar(24) NOT NULL,
 correlation_id varchar(128) NOT NULL, created_at timestamptz DEFAULT CURRENT_TIMESTAMP NOT NULL,
 UNIQUE(adapter_id,sequence_no), UNIQUE(adapter_id,nonce)
);
CREATE INDEX IF NOT EXISTS idx_model_evidence_time ON cx_model_evidence_batches(adapter_id,observed_to,status);

CREATE TABLE IF NOT EXISTS cx_wallboard_def_versions (
 version_id varchar(128) PRIMARY KEY, definition_id varchar(128) NOT NULL, version integer NOT NULL,
 display_name varchar(160) NOT NULL, config_json text NOT NULL, scope_json text NOT NULL,
 status varchar(24) NOT NULL, created_by varchar(128) NOT NULL, reason varchar(500) NOT NULL,
 created_at timestamptz DEFAULT CURRENT_TIMESTAMP NOT NULL, UNIQUE(definition_id,version)
);
CREATE TABLE IF NOT EXISTS cx_wallboard_publications (
 publication_id varchar(128) PRIMARY KEY, definition_id varchar(128) NOT NULL, version_id varchar(128) NOT NULL,
 status varchar(24) NOT NULL, published_by varchar(128) NOT NULL, reason varchar(500) NOT NULL,
 current_marker varchar(128), published_at timestamptz DEFAULT CURRENT_TIMESTAMP NOT NULL,
 UNIQUE(current_marker)
);

ALTER TABLE cx_model_quota_policies ENABLE ROW LEVEL SECURITY; ALTER TABLE cx_model_quota_policies FORCE ROW LEVEL SECURITY;
ALTER TABLE cx_model_quota_reservations ENABLE ROW LEVEL SECURITY; ALTER TABLE cx_model_quota_reservations FORCE ROW LEVEL SECURITY;
ALTER TABLE cx_model_replay_snapshots ENABLE ROW LEVEL SECURITY; ALTER TABLE cx_model_replay_snapshots FORCE ROW LEVEL SECURITY;
ALTER TABLE cx_provider_invoice_batches ENABLE ROW LEVEL SECURITY; ALTER TABLE cx_provider_invoice_batches FORCE ROW LEVEL SECURITY;
ALTER TABLE cx_provider_invoice_lines ENABLE ROW LEVEL SECURITY; ALTER TABLE cx_provider_invoice_lines FORCE ROW LEVEL SECURITY;
ALTER TABLE cx_model_reconciliations ENABLE ROW LEVEL SECURITY; ALTER TABLE cx_model_reconciliations FORCE ROW LEVEL SECURITY;
ALTER TABLE cx_provider_invoice_corrections ENABLE ROW LEVEL SECURITY; ALTER TABLE cx_provider_invoice_corrections FORCE ROW LEVEL SECURITY;
ALTER TABLE cx_model_allocation_rules ENABLE ROW LEVEL SECURITY; ALTER TABLE cx_model_allocation_rules FORCE ROW LEVEL SECURITY;
ALTER TABLE cx_model_allocations ENABLE ROW LEVEL SECURITY; ALTER TABLE cx_model_allocations FORCE ROW LEVEL SECURITY;
ALTER TABLE cx_model_evidence_adapters ENABLE ROW LEVEL SECURITY; ALTER TABLE cx_model_evidence_adapters FORCE ROW LEVEL SECURITY;
ALTER TABLE cx_model_evidence_batches ENABLE ROW LEVEL SECURITY; ALTER TABLE cx_model_evidence_batches FORCE ROW LEVEL SECURITY;
ALTER TABLE cx_wallboard_def_versions ENABLE ROW LEVEL SECURITY; ALTER TABLE cx_wallboard_def_versions FORCE ROW LEVEL SECURITY;
ALTER TABLE cx_wallboard_publications ENABLE ROW LEVEL SECURITY; ALTER TABLE cx_wallboard_publications FORCE ROW LEVEL SECURITY;

DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['cx_model_quota_policies','cx_model_quota_reservations','cx_model_replay_snapshots','cx_provider_invoice_batches','cx_provider_invoice_lines','cx_provider_invoice_corrections','cx_model_reconciliations','cx_model_allocation_rules','cx_model_allocations','cx_model_evidence_adapters','cx_wallboard_def_versions','cx_wallboard_publications'] LOOP
  EXECUTE format('DROP POLICY IF EXISTS cx_v410_owner ON %I',t);
  EXECUTE format('CREATE POLICY cx_v410_owner ON %I USING (public.current_agent_identity() IS NULL) WITH CHECK (public.current_agent_identity() IS NULL)',t);
 END LOOP;
END $$;
DROP POLICY IF EXISTS cx_v410_evidence_runtime ON cx_model_evidence_batches;
CREATE POLICY cx_v410_evidence_runtime ON cx_model_evidence_batches
 USING (public.current_agent_identity() IS NULL OR agent_id=public.current_agent_identity())
 WITH CHECK (public.current_agent_identity() IS NULL OR agent_id=public.current_agent_identity());

INSERT INTO cx_platform_capabilities(capability_key,mandatory,enabled) VALUES ('model_finance','N','Y') ON CONFLICT (capability_key) DO NOTHING;
INSERT INTO cx_platform_capabilities(capability_key,mandatory,enabled) VALUES ('external_model_evidence','N','Y') ON CONFLICT (capability_key) DO NOTHING;
