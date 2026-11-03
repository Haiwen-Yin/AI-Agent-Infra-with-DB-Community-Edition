-- v5.0.3 Oracle explicit child document key; preserve all JSON fields.
-- MEMBER_ID remains the original primary key. No rows or grants change.
DECLARE
    n NUMBER;
    columns_value VARCHAR2(4000);
BEGIN
    SELECT COUNT(*) INTO n FROM USER_CONSTRAINTS
      WHERE TABLE_NAME='COLLAB_GROUP_MEMBERS' AND CONSTRAINT_TYPE='P'
        AND STATUS='ENABLED' AND VALIDATED='VALIDATED';
    SELECT LISTAGG(cc.COLUMN_NAME, ',') WITHIN GROUP (ORDER BY cc.POSITION)
      INTO columns_value FROM USER_CONS_COLUMNS cc JOIN USER_CONSTRAINTS c
        ON c.CONSTRAINT_NAME=cc.CONSTRAINT_NAME
      WHERE c.TABLE_NAME='COLLAB_GROUP_MEMBERS' AND c.CONSTRAINT_TYPE='P';
    IF n<>1 OR columns_value IS NULL OR columns_value<>'MEMBER_ID' THEN
        RAISE_APPLICATION_ERROR(-20918, 'Preserve the original member primary key');
    END IF;
    SELECT COUNT(*) INTO n FROM USER_CONSTRAINTS WHERE CONSTRAINT_NAME='CX503_CGM_DOCUMENT_KEY';
    IF n=0 THEN
        EXECUTE IMMEDIATE 'ALTER TABLE COLLAB_GROUP_MEMBERS ADD CONSTRAINT CX503_CGM_DOCUMENT_KEY UNIQUE (MEMBER_ID,GROUP_ID)';
    ELSE
        SELECT COUNT(*) INTO n FROM USER_CONSTRAINTS
          WHERE CONSTRAINT_NAME='CX503_CGM_DOCUMENT_KEY' AND TABLE_NAME='COLLAB_GROUP_MEMBERS'
            AND CONSTRAINT_TYPE='U' AND STATUS='ENABLED' AND VALIDATED='VALIDATED'
            AND DEFERRABLE='NOT DEFERRABLE';
        SELECT LISTAGG(COLUMN_NAME, ',') WITHIN GROUP (ORDER BY POSITION)
          INTO columns_value FROM USER_CONS_COLUMNS WHERE CONSTRAINT_NAME='CX503_CGM_DOCUMENT_KEY';
        IF n<>1 OR columns_value IS NULL OR columns_value<>'MEMBER_ID,GROUP_ID' THEN
            RAISE_APPLICATION_ERROR(-20918, 'Existing member document key differs');
        END IF;
    END IF;
END;
/
CREATE OR REPLACE JSON RELATIONAL DUALITY VIEW COLLAB_GROUP_DV AS
SELECT JSON {
    '_id'              : g.GROUP_ID,
    'name'             : g.GROUP_NAME WITH UPDATE,
    'type'             : g.GROUP_TYPE WITH UPDATE,
    'description'      : g.DESCRIPTION WITH UPDATE,
    'workspace_id'     : g.WORKSPACE_ID WITH UPDATE,
    'coordinator'      : g.COORDINATOR_AGENT_ID WITH UPDATE,
    'sharing_policy'   : g.SHARING_POLICY WITH UPDATE,
    'status'           : g.STATUS WITH UPDATE,
    'metadata'         : g.METADATA WITH UPDATE,
    'created_at'       : g.CREATED_AT,
    'updated_at'       : g.UPDATED_AT,
    'members' : [
        SELECT JSON {
            'member_id'     : m.MEMBER_ID,
            'group_id'      : m.GROUP_ID,
            'agent_id'      : m.AGENT_ID WITH UPDATE,
            'role'          : m.ROLE WITH UPDATE,
            'workspace_id'  : m.PERSONAL_WORKSPACE_ID WITH UPDATE,
            'joined_at'     : m.JOINED_AT,
            'status'        : m.STATUS WITH UPDATE
        }
        FROM COLLAB_GROUP_MEMBERS m WITH INSERT UPDATE DELETE
        WHERE m.GROUP_ID = g.GROUP_ID
    ]
}
FROM COLLAB_GROUPS g WITH INSERT UPDATE DELETE;
