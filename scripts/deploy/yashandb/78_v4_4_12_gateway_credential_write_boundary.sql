-- Credentials and bearer-token records are written by the authenticated gateway.
-- Independent database identities must never manufacture or alter these records.
DECLARE
  PROCEDURE revoke_one(p VARCHAR2, o VARCHAR2, g VARCHAR2) IS
    not_granted EXCEPTION; PRAGMA EXCEPTION_INIT(not_granted, 2221);
    missing_grantee EXCEPTION; PRAGMA EXCEPTION_INIT(missing_grantee, 2012);
  BEGIN
    EXECUTE IMMEDIATE 'REVOKE '||p||' ON '||o||' FROM '||g;
  EXCEPTION WHEN not_granted OR missing_grantee THEN NULL;
  END;
BEGIN
  FOR g IN (SELECT 'DEEP_SEC_SESSION_ROLE' name FROM DUAL UNION ALL SELECT 'AGENT_API' FROM DUAL UNION ALL SELECT 'PUBLIC' FROM DUAL) LOOP
    FOR p IN (SELECT 'INSERT' name FROM DUAL UNION ALL SELECT 'UPDATE' FROM DUAL UNION ALL SELECT 'DELETE' FROM DUAL) LOOP
      revoke_one(p.name,'CX_AGENT_CREDENTIALS',g.name);
      revoke_one(p.name,'CX_AGENT_ACCESS_TOKENS',g.name);
    END LOOP;
  END LOOP;
END;
/
