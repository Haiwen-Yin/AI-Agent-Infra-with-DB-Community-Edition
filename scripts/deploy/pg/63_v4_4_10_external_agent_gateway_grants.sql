-- v4.4.10 PostgreSQL external Agent Gateway privilege closure.
-- Dedicated Agent logins use ai_agent_runtime plus the existing RLS identity
-- boundary. Keep this migration additive and idempotent.
DO $cx_gateway_grants$
DECLARE
  table_name text;
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ai_agent_runtime') THEN
    FOREACH table_name IN ARRAY ARRAY[
      'cx_agent_credentials','cx_principals','cx_agent_instances',
      'cx_agent_access_tokens','cx_agent_postures','cx_agent_posture_evidence',
      'cx_security_events','cx_external_db_endpoints','cx_agent_deliveries',
      'cx_channel_members','cx_channels','cx_compliance_findings',
      'cx_compliance_remediation_cases'
    ] LOOP
      IF to_regclass('public.' || table_name) IS NOT NULL THEN
        EXECUTE format('GRANT SELECT, INSERT, UPDATE ON TABLE public.%I TO ai_agent_runtime', table_name);
      END IF;
    END LOOP;
  END IF;
END
$cx_gateway_grants$;

-- Gateway reads must remain scoped by the already-installed RLS policies.
DO $cx_gateway_rls$
DECLARE
  table_name text;
BEGIN
  FOREACH table_name IN ARRAY ARRAY[
    'cx_agent_credentials','cx_agent_instances','cx_agent_access_tokens',
    'cx_agent_postures','cx_agent_posture_evidence','cx_security_events'
  ] LOOP
    IF to_regclass('public.' || table_name) IS NOT NULL THEN
      EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', table_name);
      EXECUTE format('ALTER TABLE public.%I FORCE ROW LEVEL SECURITY', table_name);
    END IF;
  END LOOP;
END
$cx_gateway_rls$;
