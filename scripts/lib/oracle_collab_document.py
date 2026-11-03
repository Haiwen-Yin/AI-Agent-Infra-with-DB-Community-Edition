"""Oracle's explicit child document key preserves the existing JSON projection."""
from __future__ import annotations

import hashlib
import re

SCRIPT = '118_v5_0_3_oracle_collab_document_key.sql'
KEY = 'CX503_CGM_DOCUMENT_KEY'

KEY_SQL = """DECLARE
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
"""

VIEW_SQL = """CREATE OR REPLACE JSON RELATIONAL DUALITY VIEW COLLAB_GROUP_DV AS
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
"""


def render():
    sql = ('-- v5.0.3 Oracle explicit child document key; preserve all JSON fields.\n'
           '-- MEMBER_ID remains the original primary key. No rows or grants change.\n'
           + KEY_SQL + VIEW_SQL)
    return SCRIPT, sql, dict(schema='v503-oracle-collab-document-key/v1', database='oracle',
        table='COLLAB_GROUP_MEMBERS', primary_key=['MEMBER_ID'], unique_key=KEY,
        unique_columns=['MEMBER_ID','GROUP_ID'], view='COLLAB_GROUP_DV',
        view_sql_sha256=hashlib.sha256(VIEW_SQL.encode()).hexdigest(),
        data_mutation=False, grants_changed=False, json_fields='PRESERVED')


def sql_identity(text):
    """Ignore SQL presentation while retaining the exact case of JSON keys."""
    return ''.join(token if token.startswith("'") else re.sub(r'\s+', '', token).upper()
        for token in re.split(r"('(?:''|[^'])*')", text.strip().rstrip(';')))


def errors(cursor):
    failures=[]
    for kind,name,columns in [('P',None,'MEMBER_ID'),('U',KEY,'MEMBER_ID,GROUP_ID')]:
        cursor.execute("SELECT c.CONSTRAINT_NAME,c.STATUS,c.VALIDATED,c.DEFERRABLE,"
            "LISTAGG(cc.COLUMN_NAME,',') WITHIN GROUP (ORDER BY cc.POSITION) "
            "FROM USER_CONSTRAINTS c JOIN USER_CONS_COLUMNS cc ON cc.CONSTRAINT_NAME=c.CONSTRAINT_NAME "
            "WHERE c.TABLE_NAME='COLLAB_GROUP_MEMBERS' AND c.CONSTRAINT_TYPE=:kind "
            "AND (:name IS NULL OR c.CONSTRAINT_NAME=:name) "
            "GROUP BY c.CONSTRAINT_NAME,c.STATUS,c.VALIDATED,c.DEFERRABLE",dict(kind=kind,name=name))
        rows=cursor.fetchall()
        if len(rows)!=1 or tuple(rows[0][1:])!=('ENABLED','VALIDATED','NOT DEFERRABLE',columns):
            failures.append('MEMBER_PRIMARY_KEY' if kind=='P' else 'MEMBER_DOCUMENT_KEY')
    cursor.execute("SELECT STATUS FROM USER_OBJECTS WHERE OBJECT_NAME='COLLAB_GROUP_DV' AND OBJECT_TYPE='VIEW'")
    if cursor.fetchall()!=[('VALID',)]:failures.append('COLLAB_VIEW_STATUS')
    cursor.execute("SELECT TEXT FROM USER_VIEWS WHERE VIEW_NAME='COLLAB_GROUP_DV'")
    rows=cursor.fetchall()
    text=rows[0][0] if len(rows)==1 else ''
    if hasattr(text,'read'):text=text.read()
    expected=VIEW_SQL.split(' AS\n',1)[1]
    if sql_identity(text)!=sql_identity(expected):failures.append('COLLAB_VIEW_DEFINITION')
    return failures
