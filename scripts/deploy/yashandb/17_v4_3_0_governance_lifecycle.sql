-- v4.3.0 additive lifecycle, Bridge, notification, Barrier and profile fields.

BEGIN EXECUTE IMMEDIATE 'ALTER TABLE CX_CHANNELS ADD (LIFECYCLE_REASON VARCHAR2(2000))';
EXCEPTION WHEN OTHERS THEN IF ABS(SQLCODE) NOT IN (1430, 2013, 2176) THEN RAISE; END IF; END;
/
BEGIN EXECUTE IMMEDIATE 'ALTER TABLE CX_CHANNELS ADD (DELETION_AFTER TIMESTAMP)';
EXCEPTION WHEN OTHERS THEN IF ABS(SQLCODE) NOT IN (1430, 2013, 2176) THEN RAISE; END IF; END;
/
BEGIN EXECUTE IMMEDIATE 'ALTER TABLE CX_CHANNELS ADD (QUARANTINED_AT TIMESTAMP)';
EXCEPTION WHEN OTHERS THEN IF ABS(SQLCODE) NOT IN (1430, 2013, 2176) THEN RAISE; END IF; END;
/
BEGIN EXECUTE IMMEDIATE 'ALTER TABLE CX_BRIDGES ADD (APPROVAL_REASON VARCHAR2(2000))';
EXCEPTION WHEN OTHERS THEN IF ABS(SQLCODE) NOT IN (1430, 2013, 2176) THEN RAISE; END IF; END;
/
BEGIN EXECUTE IMMEDIATE 'ALTER TABLE CX_BRIDGES ADD (POLICY_VERSION NUMBER(19,0) DEFAULT 1 NOT NULL)';
EXCEPTION WHEN OTHERS THEN IF ABS(SQLCODE) NOT IN (1430, 2013, 2176) THEN RAISE; END IF; END;
/
BEGIN EXECUTE IMMEDIATE 'ALTER TABLE CX_BRIDGE_TRANSFERS ADD (IDEMPOTENCY_KEY VARCHAR2(256))';
EXCEPTION WHEN OTHERS THEN IF ABS(SQLCODE) NOT IN (1430, 2013, 2176) THEN RAISE; END IF; END;
/
BEGIN EXECUTE IMMEDIATE 'ALTER TABLE CX_BRIDGE_TRANSFERS ADD (SOURCE_CLASSIFICATION VARCHAR2(32))';
EXCEPTION WHEN OTHERS THEN IF ABS(SQLCODE) NOT IN (1430, 2013, 2176) THEN RAISE; END IF; END;
/
BEGIN EXECUTE IMMEDIATE 'ALTER TABLE CX_NOTIFICATIONS ADD (NOTIFICATION_LEVEL VARCHAR2(32) DEFAULT ''INFO'' NOT NULL)';
EXCEPTION WHEN OTHERS THEN IF ABS(SQLCODE) NOT IN (1430, 2013, 2176) THEN RAISE; END IF; END;
/
BEGIN EXECUTE IMMEDIATE 'ALTER TABLE CX_NOTIFICATIONS ADD (ACKNOWLEDGED_BY VARCHAR2(128))';
EXCEPTION WHEN OTHERS THEN IF ABS(SQLCODE) NOT IN (1430, 2013, 2176) THEN RAISE; END IF; END;
/
BEGIN EXECUTE IMMEDIATE 'ALTER TABLE CX_NOTIFICATIONS ADD (ESCALATED_AT TIMESTAMP)';
EXCEPTION WHEN OTHERS THEN IF ABS(SQLCODE) NOT IN (1430, 2013, 2176) THEN RAISE; END IF; END;
/
BEGIN EXECUTE IMMEDIATE 'ALTER TABLE CX_BARRIERS ADD (RETRY_COUNT NUMBER(10,0) DEFAULT 0 NOT NULL)';
EXCEPTION WHEN OTHERS THEN IF ABS(SQLCODE) NOT IN (1430, 2013, 2176) THEN RAISE; END IF; END;
/
BEGIN EXECUTE IMMEDIATE 'ALTER TABLE CX_BARRIERS ADD (MAX_RETRIES NUMBER(10,0) DEFAULT 3 NOT NULL)';
EXCEPTION WHEN OTHERS THEN IF ABS(SQLCODE) NOT IN (1430, 2013, 2176) THEN RAISE; END IF; END;
/
BEGIN EXECUTE IMMEDIATE 'ALTER TABLE CX_BARRIERS ADD (LAST_RECOVERY_ACTION VARCHAR2(32))';
EXCEPTION WHEN OTHERS THEN IF ABS(SQLCODE) NOT IN (1430, 2013, 2176) THEN RAISE; END IF; END;
/
BEGIN EXECUTE IMMEDIATE 'ALTER TABLE CX_BARRIERS ADD (RECOVERY_REASON VARCHAR2(2000))';
EXCEPTION WHEN OTHERS THEN IF ABS(SQLCODE) NOT IN (1430, 2013, 2176) THEN RAISE; END IF; END;
/
BEGIN EXECUTE IMMEDIATE 'CREATE UNIQUE INDEX IDX_CX_BRIDGE_TRANSFER_IDEMP ON CX_BRIDGE_TRANSFERS(BRIDGE_ID, IDEMPOTENCY_KEY)';
EXCEPTION WHEN OTHERS THEN IF ABS(SQLCODE) NOT IN (955, 4207, 2043) THEN RAISE; END IF; END;
/

BEGIN EXECUTE IMMEDIATE 'CREATE TABLE CX_CHANNEL_THREADS (
    THREAD_ID VARCHAR2(128) PRIMARY KEY, CHANNEL_ID VARCHAR2(128) NOT NULL,
    PARENT_THREAD_ID VARCHAR2(128), THREAD_TYPE VARCHAR2(32) NOT NULL,
    CLASSIFICATION VARCHAR2(32) NOT NULL, STATUS VARCHAR2(32) DEFAULT ''ACTIVE'' NOT NULL,
    POLICY_JSON CLOB NOT NULL, CREATED_BY VARCHAR2(128) NOT NULL,
    CREATED_AT TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL, UPDATED_AT TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL
)';
EXCEPTION WHEN OTHERS THEN IF ABS(SQLCODE) NOT IN (955, 4207) THEN RAISE; END IF; END;
/

-- YashanDB keeps these canonical JSON payloads in CLOB columns.  The
-- comparison below deliberately avoids Oracle-only whole-LOB comparison:
-- deployments may
-- expose YashanDB's native LOB package surface rather than Oracle's complete
-- comparison API.  Only system-managed templates are synchronized.
DECLARE
    FUNCTION same_clob(p_left CLOB, p_right CLOB) RETURN NUMBER IS
        l_left_length NUMBER;
        l_right_length NUMBER;
        l_offset NUMBER := 1;
        l_chunk_length NUMBER;
        l_left_chunk VARCHAR2(4000);
        l_right_chunk VARCHAR2(4000);
    BEGIN
        IF p_left IS NULL OR p_right IS NULL THEN
            IF p_left IS NULL AND p_right IS NULL THEN
                RETURN 1;
            END IF;
            RETURN 0;
        END IF;

        l_left_length := NVL(LENGTH(p_left), 0);
        l_right_length := NVL(LENGTH(p_right), 0);
        IF l_left_length <> l_right_length THEN
            RETURN 0;
        END IF;

        WHILE l_offset <= l_left_length LOOP
            l_left_chunk := DBMS_LOB.SUBSTR(p_left, 4000, l_offset);
            l_right_chunk := DBMS_LOB.SUBSTR(p_right, 4000, l_offset);
            IF (l_left_chunk <> l_right_chunk)
               OR (l_left_chunk IS NULL AND l_right_chunk IS NOT NULL)
               OR (l_left_chunk IS NOT NULL AND l_right_chunk IS NULL) THEN
                RETURN 0;
            END IF;
            l_chunk_length := NVL(LENGTH(l_left_chunk), 0);
            IF l_chunk_length = 0 THEN
                RETURN 0;
            END IF;
            l_offset := l_offset + l_chunk_length;
        END LOOP;
        RETURN 1;
    END;

    PROCEDURE sync_role(
        p_role_code VARCHAR2, p_display_name VARCHAR2,
        p_permissions CLOB, p_scopes CLOB
    ) IS
        l_display_name CX_ROLE_TEMPLATES.DISPLAY_NAME%TYPE;
        l_permissions CX_ROLE_TEMPLATES.PERMISSIONS_JSON%TYPE;
        l_scopes CX_ROLE_TEMPLATES.DATA_SCOPES_JSON%TYPE;
        l_managed CX_ROLE_TEMPLATES.MANAGED%TYPE;
    BEGIN
        BEGIN
            SELECT DISPLAY_NAME, PERMISSIONS_JSON, DATA_SCOPES_JSON, MANAGED
              INTO l_display_name, l_permissions, l_scopes, l_managed
              FROM CX_ROLE_TEMPLATES
             WHERE ROLE_CODE = p_role_code
               FOR UPDATE;
        EXCEPTION
            WHEN NO_DATA_FOUND THEN
                INSERT INTO CX_ROLE_TEMPLATES
                    (ROLE_CODE, DISPLAY_NAME, PERMISSIONS_JSON, DATA_SCOPES_JSON, VERSION, MANAGED)
                VALUES
                    (p_role_code, p_display_name, p_permissions, p_scopes, 1, 'Y');
                RETURN;
        END;

        IF l_managed = 'Y'
           AND (l_display_name <> p_display_name
                OR same_clob(l_permissions, p_permissions) = 0
                OR same_clob(l_scopes, p_scopes) = 0) THEN
            UPDATE CX_ROLE_TEMPLATES
               SET DISPLAY_NAME = p_display_name,
                   PERMISSIONS_JSON = p_permissions,
                   DATA_SCOPES_JSON = p_scopes,
                   VERSION = NVL(VERSION, 1) + 1,
                   UPDATED_AT = SYSTIMESTAMP
             WHERE ROLE_CODE = p_role_code;
        END IF;
    END;
BEGIN
    sync_role('END_USER', 'End User', '["profile.read","profile.update","agents.enroll","agents.read","channels.read","channels.write","tasks.read","workspaces.read","knowledge.read","memory.read","skills.read","specs.read","branches.read","collab.read","loops.read","graphs.read","notifications.read"]', '["OWNED","ASSIGNED"]');
    sync_role('SYSTEM_ADMIN', 'System Administrator', '["*"]', '["ALL"]');
    sync_role('SECURITY_ADMIN', 'Security Administrator', '["security.*","sessions.revoke","domains.manage","profile.update","users.identity.link","users.security.manage","users.sessions.read","users.delegations.read","users.delegations.manage","agents.claim","channels.bridge","channels.lifecycle","channels.delete","channels.manage_members","channels.quarantine","memory.review","agents.transfer","agents.offboard","barriers.recover","notifications.manage","barriers.create","channels.actions.decide"]', '["SECURITY_DOMAIN"]');
    sync_role('AGENT_MANAGER', 'Agent Manager', '["agents.read","agents.enroll","agents.manage","agents.operate","agents.transfer","agents.offboard","channels.read","channels.create","channels.manage_members","channels.lifecycle","barriers.create","channels.actions.decide","users.read","notifications.manage","profile.update"]', '["ORG_SUBTREE"]');
    sync_role('AUDITOR', 'Auditor', '["audit.read","audit.export","users.read","profile.update"]', '["SECURITY_DOMAIN"]');
    sync_role('APPROVER', 'Approver', '["approvals.read","approvals.decide","channels.actions.decide","barriers.release","barriers.recover","memory.review","profile.update"]', '["ASSIGNED"]');
    sync_role('OPERATOR', 'Operator', '["agents.read","agents.operate","channels.write","barriers.arrive","profile.update"]', '["ASSIGNED"]');
    sync_role('DEVELOPER', 'Developer', '["skills.read","tools.read","graphs.read","barriers.create","profile.update"]', '["OWNED"]');
    sync_role('USER_ADMIN', 'User Administrator', '["users.read","users.read.all","users.approve","users.roles.manage","users.permissions.manage","users.identity.link","users.security.manage","users.sessions.read","users.delegations.read","users.delegations.manage"]', '["ORG_SUBTREE"]');
    sync_role('ROLE_ADMIN', 'Role Administrator', '["users.read","users.roles.manage","users.permissions.manage","users.delegations.read","users.delegations.manage"]', '["ORG_SUBTREE"]');
    sync_role('AGENT', 'Agent', '["channels.read","channels.write","barriers.read","barriers.arrive","actions.propose"]', '["ASSIGNED"]');
END;
/
BEGIN EXECUTE IMMEDIATE 'CREATE INDEX IDX_CX_CHANNEL_THREAD_PARENT ON CX_CHANNEL_THREADS(CHANNEL_ID, PARENT_THREAD_ID, STATUS, UPDATED_AT)';
EXCEPTION WHEN OTHERS THEN IF ABS(SQLCODE) NOT IN (955, 4207, 2043) THEN RAISE; END IF; END;
/
BEGIN EXECUTE IMMEDIATE 'CREATE TABLE CX_CHANNEL_THREAD_MEMBERS (
    THREAD_MEMBER_ID VARCHAR2(128) PRIMARY KEY, THREAD_ID VARCHAR2(128) NOT NULL,
    PRINCIPAL_ID VARCHAR2(128) NOT NULL, MEMBER_ROLE VARCHAR2(32) DEFAULT ''MEMBER'' NOT NULL,
    STATUS VARCHAR2(32) DEFAULT ''ACTIVE'' NOT NULL, VALID_UNTIL TIMESTAMP,
    JOINED_AT TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT UK_CX_CHANNEL_THREAD_MEMBER UNIQUE (THREAD_ID, PRINCIPAL_ID)
)';
EXCEPTION WHEN OTHERS THEN IF ABS(SQLCODE) NOT IN (955, 4207) THEN RAISE; END IF; END;
/
BEGIN EXECUTE IMMEDIATE 'CREATE INDEX IDX_CX_CHANNEL_THREAD_MEMBER ON CX_CHANNEL_THREAD_MEMBERS(THREAD_ID, PRINCIPAL_ID, STATUS, VALID_UNTIL)';
EXCEPTION WHEN OTHERS THEN IF ABS(SQLCODE) NOT IN (955, 4207, 2043) THEN RAISE; END IF; END;
/
BEGIN EXECUTE IMMEDIATE 'CREATE TABLE CX_RUNTIME_PROFILE_CHANGES (
    CHANGE_ID VARCHAR2(128) PRIMARY KEY, REQUESTED_BY VARCHAR2(128) NOT NULL,
    CURRENT_PROFILE VARCHAR2(64) NOT NULL, TARGET_PROFILE VARCHAR2(64) NOT NULL,
    IMPACT_JSON CLOB NOT NULL, STATUS VARCHAR2(32) DEFAULT ''PREFLIGHT'' NOT NULL,
    REASON VARCHAR2(2000) NOT NULL, ACTIVATED_AT TIMESTAMP,
    CREATED_AT TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL
)';
EXCEPTION WHEN OTHERS THEN IF ABS(SQLCODE) NOT IN (955, 4207) THEN RAISE; END IF; END;
/
