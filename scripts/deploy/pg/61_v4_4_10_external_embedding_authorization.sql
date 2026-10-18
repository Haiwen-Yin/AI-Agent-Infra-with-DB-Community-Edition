-- v4.4.10 external Agent Embedding authorization. External access is deny-by-default in the service.
CREATE TABLE IF NOT EXISTS cx_embedding_access_grants (
  grant_id varchar(128) PRIMARY KEY,
  grant_key varchar(64) UNIQUE NOT NULL,
  subject_type varchar(32) NOT NULL CHECK (subject_type IN ('AGENT','TEMPLATE','ORGANIZATION','SECURITY_DOMAIN')),
  subject_id varchar(128) NOT NULL,
  effect varchar(16) NOT NULL CHECK (effect IN ('ALLOW','DENY')),
  allowed_profile_id varchar(128),
  max_batch_size integer NOT NULL DEFAULT 1 CHECK (max_batch_size BETWEEN 1 AND 16),
  max_input_chars integer NOT NULL DEFAULT 16000 CHECK (max_input_chars BETWEEN 1 AND 64000),
  valid_from timestamp,
  valid_until timestamp,
  status varchar(24) NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE','REVOKED')),
  version bigint NOT NULL DEFAULT 1,
  approved_by varchar(128) NOT NULL,
  reason varchar(2000) NOT NULL,
  created_at timestamp NOT NULL DEFAULT current_timestamp,
  updated_at timestamp NOT NULL DEFAULT current_timestamp,
  CHECK (valid_until IS NULL OR valid_from IS NULL OR valid_until > valid_from)
);
CREATE INDEX IF NOT EXISTS idx_cx_eag_subject
  ON cx_embedding_access_grants(subject_type,subject_id,status,valid_until);
CREATE INDEX IF NOT EXISTS idx_cx_eag_profile
  ON cx_embedding_access_grants(allowed_profile_id,status);

ALTER TABLE cx_embedding_access_grants ENABLE ROW LEVEL SECURITY;
ALTER TABLE cx_embedding_access_grants FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS cx_embedding_access_grants_owner ON cx_embedding_access_grants;
CREATE POLICY cx_embedding_access_grants_owner ON cx_embedding_access_grants
  USING (public.current_agent_identity() IS NULL)
  WITH CHECK (public.current_agent_identity() IS NULL);
