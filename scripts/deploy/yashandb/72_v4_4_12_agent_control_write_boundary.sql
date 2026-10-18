-- Principal lifecycle and registry state are control-plane operations.
-- Independent Agents must use authorized platform APIs for these mutations.
DECLARE
  PROCEDURE revoke_write(o VARCHAR2, g VARCHAR2) IS
    not_granted EXCEPTION; PRAGMA EXCEPTION_INIT(not_granted, 2221);
    missing_grantee EXCEPTION; PRAGMA EXCEPTION_INIT(missing_grantee, 2012);
  BEGIN
    EXECUTE IMMEDIATE 'REVOKE INSERT, UPDATE, DELETE ON '||o||' FROM '||g;
  EXCEPTION WHEN not_granted OR missing_grantee THEN NULL;
  END;
BEGIN
  FOR g IN (SELECT 'DEEP_SEC_SESSION_ROLE' name FROM DUAL UNION ALL SELECT 'AGENT_API' FROM DUAL UNION ALL SELECT 'PUBLIC' FROM DUAL) LOOP
    revoke_write('CX_PRINCIPALS',g.name);
    revoke_write('AGENT_REGISTRY',g.name);
  END LOOP;
END;
/
