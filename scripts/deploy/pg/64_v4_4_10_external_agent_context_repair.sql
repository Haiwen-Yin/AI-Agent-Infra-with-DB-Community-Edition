-- v4.4.10 PostgreSQL external Agent request-context closure.
-- Gateway operations execute after attaching the dedicated Agent login, so
-- compliance posture reads and Agent-owned evidence writes require explicit
-- RLS policies in addition to table privileges.
DO $cx_optional_compliance_rls$
BEGIN
  IF to_regclass('public.cx_agent_postures') IS NOT NULL THEN
    ALTER TABLE cx_agent_postures ENABLE ROW LEVEL SECURITY;
    ALTER TABLE cx_agent_postures FORCE ROW LEVEL SECURITY;
    DROP POLICY IF EXISTS cx_agent_postures_self ON cx_agent_postures;
    CREATE POLICY cx_agent_postures_self ON cx_agent_postures FOR ALL
      USING (agent_id = public.current_agent_identity())
      WITH CHECK (agent_id = public.current_agent_identity());
  END IF;
  IF to_regclass('public.cx_agent_posture_evidence') IS NOT NULL THEN
    ALTER TABLE cx_agent_posture_evidence ENABLE ROW LEVEL SECURITY;
    ALTER TABLE cx_agent_posture_evidence FORCE ROW LEVEL SECURITY;
    DROP POLICY IF EXISTS cx_agent_posture_evidence_self ON cx_agent_posture_evidence;
    CREATE POLICY cx_agent_posture_evidence_self ON cx_agent_posture_evidence FOR ALL
      USING (agent_id = public.current_agent_identity())
      WITH CHECK (agent_id = public.current_agent_identity());
  END IF;
END
$cx_optional_compliance_rls$;

ALTER TABLE cx_security_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE cx_security_events FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS cx_security_events_agent_insert ON cx_security_events;
CREATE POLICY cx_security_events_agent_insert ON cx_security_events FOR INSERT
  WITH CHECK (principal_id = public.current_agent_identity());
