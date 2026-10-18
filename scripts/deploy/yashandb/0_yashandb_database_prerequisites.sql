-- YashanDB 23.5 v4.4.10 application-owner prerequisites.
-- Run as the database administrator in the dedicated application PDB.
-- Replace the default owner before execution.
WHENEVER SQLERROR EXIT SQL.SQLCODE
DEFINE SCHEMA_OWNER = CX_AGENT_OWNER

SELECT SYS_CONTEXT('USERENV', 'CON_NAME') AS TARGET_PDB FROM DUAL;

-- The release baseline creates schema objects and DBMS_SCHEDULER jobs before
-- handing control to native management Agents. Grant these directly so the
-- live preflight can prove the bounded Owner contract without a DBA role.
GRANT CREATE SESSION, CREATE TABLE, CREATE VIEW, CREATE SEQUENCE,
      CREATE PROCEDURE, CREATE TRIGGER, CREATE TYPE, CREATE JOB
  TO &&SCHEMA_OWNER;

-- Business Agents receive independent database users. The bounded application
-- Owner creates those users and rotates only their credentials; it does not
-- receive DBA, SYSDBA, or unrestricted object privileges.
GRANT CREATE USER TO &&SCHEMA_OWNER;
GRANT ALTER USER TO &&SCHEMA_OWNER;

DECLARE
    v_count NUMBER;
BEGIN
    SELECT COUNT(*) INTO v_count
      FROM DBA_ROLES
     WHERE ROLE = 'DEEP_SEC_SESSION_ROLE';
    IF v_count = 0 THEN
        EXECUTE IMMEDIATE 'CREATE ROLE DEEP_SEC_SESSION_ROLE';
    END IF;
END;
/
GRANT CREATE SESSION TO DEEP_SEC_SESSION_ROLE;
-- Independent Agent sessions resolve business objects in the Owner schema.
GRANT ALTER SESSION TO DEEP_SEC_SESSION_ROLE;
GRANT DEEP_SEC_SESSION_ROLE TO &&SCHEMA_OWNER WITH ADMIN OPTION;

SELECT PRIVILEGE
  FROM DBA_SYS_PRIVS
 WHERE GRANTEE = UPPER('&&SCHEMA_OWNER')
   AND PRIVILEGE IN (
       'CREATE SESSION', 'CREATE TABLE', 'CREATE VIEW', 'CREATE SEQUENCE',
       'CREATE PROCEDURE', 'CREATE TRIGGER', 'CREATE TYPE', 'CREATE JOB',
       'CREATE USER', 'ALTER USER'
   )
 ORDER BY PRIVILEGE;

SELECT GRANTED_ROLE, ADMIN_OPTION
  FROM DBA_ROLE_PRIVS
 WHERE GRANTEE = UPPER('&&SCHEMA_OWNER')
   AND GRANTED_ROLE = 'DEEP_SEC_SESSION_ROLE';

PROMPT YashanDB application-owner prerequisites completed.
