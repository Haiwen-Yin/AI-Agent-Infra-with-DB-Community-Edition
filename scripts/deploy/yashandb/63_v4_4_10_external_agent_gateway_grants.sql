-- v4.4.10 YashanDB external Agent Gateway privilege closure.
-- YashanDB uses independent users granted DEEP_SEC_SESSION_ROLE; the role is
-- already provisioned by 6_deep_sec_policy.sql. Re-grants are idempotent and
-- keep the Gateway contract explicit for new or repaired baselines.
DECLARE
  v_sql VARCHAR2(4000);
BEGIN
  FOR r IN (
    SELECT TABLE_NAME FROM USER_TABLES WHERE TABLE_NAME IN (
      'CX_AGENT_CREDENTIALS','CX_PRINCIPALS','CX_AGENT_INSTANCES',
      'CX_AGENT_ACCESS_TOKENS','CX_AGENT_POSTURES','CX_AGENT_POSTURE_EVIDENCE',
      'CX_SECURITY_EVENTS','CX_EXTERNAL_DB_ENDPOINTS','CX_AGENT_DELIVERIES',
      'CX_CHANNEL_MEMBERS','CX_CHANNELS','CX_COMPLIANCE_FINDINGS',
      'CX_COMPLIANCE_REMEDIATION_CASES'
    )
  ) LOOP
    v_sql := 'GRANT SELECT, INSERT, UPDATE ON ' || r.TABLE_NAME || ' TO DEEP_SEC_SESSION_ROLE';
    BEGIN EXECUTE IMMEDIATE v_sql; EXCEPTION WHEN OTHERS THEN NULL; END;
  END LOOP;
END;
/

-- Ensure the independent Agent role can establish a session and invoke the
-- existing Gateway-facing lifecycle packages without exposing SYSTEM_CONFIG.
BEGIN
  EXECUTE IMMEDIATE 'GRANT CREATE SESSION TO DEEP_SEC_SESSION_ROLE';
EXCEPTION WHEN OTHERS THEN NULL;
END;
/
