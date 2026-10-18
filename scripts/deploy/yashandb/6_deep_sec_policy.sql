-- ============================================================
-- AI Agent Infra v4.0.1 - YashanDB Enterprise identity isolation
-- ============================================================
-- YashanDB does not implement Oracle 26ai END USER / DATA GRANT syntax.
-- Business Agents therefore use independent database users and a centrally
-- managed least-privilege role. The Owner credential is never a fallback.

DEFINE SCHEMA_OWNER = 'AIADMIN'
DEFINE AGENT_ROLE = 'DEEP_SEC_SESSION_ROLE'

PROMPT Granting business-table access to the independent Agent role

DECLARE
    v_sql VARCHAR2(4000);
BEGIN
    FOR r IN (
        SELECT TABLE_NAME
        FROM USER_TABLES
        WHERE TABLE_NAME NOT IN (
            'SYSTEM_CONFIG', 'SYSTEM_USERS', 'AGENT_CREDENTIALS',
            'AGENT_PERMISSION_LOG', 'ENTITY_ACCESS_LOG', 'CONTEXT_AUDIT_LOG',
            'CONTEXT_AUDIT_RULES', 'EXECUTION_AUDIT', 'APPROVAL_REQUESTS',
            'LDAP_CONFIG', 'LDAP_SYNC_LOG', 'SKILL_ACCESS_TOKEN'
        )
    ) LOOP
        v_sql := 'GRANT SELECT, INSERT, UPDATE, DELETE ON ' || r.TABLE_NAME ||
                 ' TO &&AGENT_ROLE';
        EXECUTE IMMEDIATE v_sql;
    END LOOP;
END;
/

GRANT EXECUTE ON MEMORY_FUSION_ENGINE TO &&AGENT_ROLE;
GRANT EXECUTE ON KNOWLEDGE_BASE_API TO &&AGENT_ROLE;
GRANT EXECUTE ON AGENT_PERMISSION_MANAGER TO &&AGENT_ROLE;
GRANT EXECUTE ON SESSION_CLEANUP TO &&AGENT_ROLE;
GRANT EXECUTE ON WORKSPACE_MANAGER TO &&AGENT_ROLE;
GRANT EXECUTE ON SPEC_MANAGER TO &&AGENT_ROLE;
GRANT EXECUTE ON COLLAB_GROUP_MANAGER TO &&AGENT_ROLE;
GRANT EXECUTE ON EMBEDDING_MANAGER TO &&AGENT_ROLE;
GRANT EXECUTE ON SKILL_MANAGER TO &&AGENT_ROLE;
GRANT EXECUTE ON CONTEXT_AUDIT_MANAGER TO &&AGENT_ROLE;
GRANT EXECUTE ON BRANCH_MANAGER TO &&AGENT_ROLE;
GRANT EXECUTE ON TRACE_MANAGER TO &&AGENT_ROLE;
GRANT EXECUTE ON MONITOR_MANAGER TO &&AGENT_ROLE;

PROMPT Creating compatibility lifecycle package for independent users

CREATE OR REPLACE PACKAGE END_USER_MANAGER AS
    FUNCTION create_end_user(
        p_agent_id VARCHAR2,
        p_eu_name VARCHAR2,
        p_password VARCHAR2 DEFAULT NULL
    ) RETURN VARCHAR2;
    PROCEDURE drop_end_user(p_agent_id VARCHAR2, p_eu_name VARCHAR2);
    FUNCTION get_password(p_agent_id VARCHAR2) RETURN VARCHAR2;
    FUNCTION ensure_end_user(p_agent_id VARCHAR2) RETURN VARCHAR2;
END END_USER_MANAGER;
/

CREATE OR REPLACE PACKAGE BODY END_USER_MANAGER AS
    FUNCTION generate_password RETURN VARCHAR2 IS
    BEGIN
        RETURN RAWTOHEX(SYS_GUID()) || RAWTOHEX(SYS_GUID());
    END generate_password;

    FUNCTION get_password(p_agent_id VARCHAR2) RETURN VARCHAR2 IS
        v_pwd VARCHAR2(128);
    BEGIN
        SELECT CONFIG_VALUE INTO v_pwd
        FROM SYSTEM_CONFIG
        WHERE CONFIG_KEY = 'end_user_pwd.' || p_agent_id;
        RETURN v_pwd;
    EXCEPTION
        WHEN NO_DATA_FOUND THEN RETURN NULL;
    END get_password;

    FUNCTION create_end_user(
        p_agent_id VARCHAR2,
        p_eu_name VARCHAR2,
        p_password VARCHAR2 DEFAULT NULL
    ) RETURN VARCHAR2 IS
        v_pwd VARCHAR2(128);
        v_count NUMBER;
    BEGIN
        v_pwd := get_password(p_agent_id);
        IF v_pwd IS NOT NULL THEN RETURN v_pwd; END IF;
        v_pwd := COALESCE(p_password, generate_password());
        SELECT COUNT(*) INTO v_count FROM ALL_USERS WHERE USERNAME = UPPER(p_eu_name);
        IF v_count = 0 THEN
            EXECUTE IMMEDIATE 'CREATE USER "' || p_eu_name || '" IDENTIFIED BY "' || v_pwd || '"';
        ELSE
            EXECUTE IMMEDIATE 'ALTER USER "' || p_eu_name || '" IDENTIFIED BY "' || v_pwd || '"';
        END IF;
        EXECUTE IMMEDIATE 'GRANT &&AGENT_ROLE TO "' || p_eu_name || '"';
        MERGE INTO SYSTEM_CONFIG sc
        USING (SELECT 'end_user_pwd.' || p_agent_id AS k, v_pwd AS v FROM DUAL) src
        ON (sc.CONFIG_KEY = src.k)
        WHEN MATCHED THEN UPDATE SET CONFIG_VALUE = src.v, UPDATED_AT = SYSTIMESTAMP
        WHEN NOT MATCHED THEN INSERT (CONFIG_KEY, CONFIG_VALUE, DESCRIPTION)
            VALUES (src.k, src.v, 'Independent YashanDB login for Agent ' || p_agent_id);
        COMMIT;
        RETURN v_pwd;
    END create_end_user;

    PROCEDURE drop_end_user(p_agent_id VARCHAR2, p_eu_name VARCHAR2) IS
    BEGIN
        EXECUTE IMMEDIATE 'DROP USER "' || p_eu_name || '" CASCADE';
        DELETE FROM SYSTEM_CONFIG WHERE CONFIG_KEY = 'end_user_pwd.' || p_agent_id;
        COMMIT;
    EXCEPTION
        WHEN OTHERS THEN NULL;
    END drop_end_user;

    FUNCTION ensure_end_user(p_agent_id VARCHAR2) RETURN VARCHAR2 IS
        v_name VARCHAR2(128);
    BEGIN
        v_name := 'AIA_' || SUBSTR(UPPER(REPLACE(p_agent_id, '-', '_')), 1, 24);
        RETURN create_end_user(p_agent_id, v_name);
    END ensure_end_user;
END END_USER_MANAGER;
/

DECLARE
    v_count NUMBER;
BEGIN
    SELECT COUNT(*) INTO v_count FROM ALL_USERS WHERE USERNAME = 'AGENT_API';
    IF v_count > 0 THEN
        EXECUTE IMMEDIATE 'GRANT EXECUTE ON END_USER_MANAGER TO AGENT_API';
    END IF;
END;
/

PROMPT YashanDB independent Business Agent isolation configured
