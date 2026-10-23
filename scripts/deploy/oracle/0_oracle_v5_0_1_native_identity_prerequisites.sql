-- v5.0.1+ dedicated-PDB administrator prerequisite, separate from Owner migrations.
-- Set BOTH definitions to the exact approved application PDB and bounded Owner.
-- Run as SYSDBA in that PDB. Never run in CDB$ROOT or PDB$SEED.
-- This does not lock accounts, grant dictionary access, or terminate sessions.
WHENEVER SQLERROR EXIT SQL.SQLCODE
SET VERIFY OFF
SET SERVEROUTPUT ON
DEFINE TARGET_PDB = 'REPLACE_WITH_APPLICATION_PDB'
DEFINE SCHEMA_OWNER = 'AIADMIN'

DECLARE
    v_pdb VARCHAR2(128);
    v_owner VARCHAR2(128) := UPPER('&&SCHEMA_OWNER');
    v_count NUMBER;
    v_columns NUMBER;
    v_expected_columns NUMBER;
    v_definition VARCHAR2(32767);
    v_read_only VARCHAR2(16);
    unsafe_native_status_prerequisite EXCEPTION;
    PROCEDURE refuse(p_reason VARCHAR2) IS
    BEGIN
        DBMS_OUTPUT.PUT_LINE('Native identity prerequisite refused: ' || p_reason);
        RAISE unsafe_native_status_prerequisite;
    END;
BEGIN
    SELECT SYS_CONTEXT('USERENV','CON_NAME') INTO v_pdb FROM DUAL;
    IF SYS_CONTEXT('USERENV','SESSION_USER') <> 'SYS' THEN
        refuse('SYS administrator context is required');
    END IF;
    IF v_pdb IS NULL OR UPPER(v_pdb) IN ('CDB$ROOT','PDB$SEED')
       OR UPPER(v_pdb) <> UPPER('&&TARGET_PDB') THEN
        refuse('connected PDB does not match the explicit TARGET_PDB');
    END IF;
    IF NOT REGEXP_LIKE(v_owner, '^[A-Z][A-Z0-9_]{0,127}$')
       OR v_owner IN ('SYS','SYSTEM','PDBADMIN','PUBLIC','AGENT_API') THEN
        refuse('SCHEMA_OWNER must be the approved bounded application Owner');
    END IF;
    SELECT COUNT(*) INTO v_count FROM DBA_USERS WHERE USERNAME=v_owner;
    IF v_count <> 1 THEN
        refuse('the exact application Owner does not exist in this PDB');
    END IF;
    SELECT COUNT(*) INTO v_count FROM DBA_OBJECTS
      WHERE OWNER='SYS' AND OBJECT_NAME='CX_AGENT_ACCOUNT_STATUS';
    IF v_count = 0 THEN
        EXECUTE IMMEDIATE 'CREATE VIEW SYS.CX_AGENT_ACCOUNT_STATUS AS '
          || 'SELECT USERNAME, ACCOUNT_STATUS FROM SYS.DBA_END_USERS WITH READ ONLY';
    ELSE
        IF v_count <> 1 THEN
            refuse('multiple existing SYS objects; no replacement is attempted');
        END IF;
        SELECT COUNT(*) INTO v_count FROM DBA_OBJECTS
          WHERE OWNER='SYS' AND OBJECT_NAME='CX_AGENT_ACCOUNT_STATUS'
            AND OBJECT_TYPE='VIEW' AND STATUS='VALID';
        IF v_count <> 1 THEN
            refuse('unknown or invalid existing SYS status object; no replacement is attempted');
        END IF;
    END IF;
    SELECT TEXT, READ_ONLY INTO v_definition, v_read_only FROM DBA_VIEWS
      WHERE OWNER='SYS' AND VIEW_NAME='CX_AGENT_ACCOUNT_STATUS';
    v_definition := REGEXP_REPLACE(UPPER(v_definition), '[[:space:]"]', '');
    IF v_definition IS NULL OR v_read_only IS NULL
       OR v_definition NOT IN ('SELECTUSERNAME,ACCOUNT_STATUSFROMSYS.DBA_END_USERS',
                            'SELECTUSERNAME,ACCOUNT_STATUSFROMSYS.DBA_END_USERSWITHREADONLY')
       OR UPPER(v_read_only) NOT IN ('Y','YES','TRUE') THEN
        refuse('existing SYS view definition or READ ONLY boundary is not exact');
    END IF;
    SELECT COUNT(*), SUM(CASE WHEN COLUMN_NAME IN ('USERNAME','ACCOUNT_STATUS') THEN 1 ELSE 0 END)
      INTO v_columns, v_expected_columns FROM DBA_TAB_COLUMNS
      WHERE OWNER='SYS' AND TABLE_NAME='CX_AGENT_ACCOUNT_STATUS';
    IF v_columns <> 2 OR v_expected_columns <> 2 THEN
        refuse('SYS view must expose exactly USERNAME and ACCOUNT_STATUS');
    END IF;
    SELECT COUNT(*) INTO v_count FROM DBA_TAB_PRIVS
      WHERE OWNER='SYS' AND TABLE_NAME='CX_AGENT_ACCOUNT_STATUS'
        AND (GRANTEE<>v_owner OR PRIVILEGE<>'SELECT' OR GRANTABLE NOT IN ('N','NO'));
    IF v_count <> 0 THEN
        refuse('unexpected existing object grant; no permission repair is attempted');
    END IF;
    EXECUTE IMMEDIATE 'GRANT SELECT ON SYS.CX_AGENT_ACCOUNT_STATUS TO "' || v_owner || '"';
    DBMS_OUTPUT.PUT_LINE('Native identity status prerequisite verified in PDB ' || v_pdb);
END;
/
-- Rerun the package-bound bootstrap verify/preflight as the bounded Owner.
