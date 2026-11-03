"""Native SQL keeps private notes separate from reviewed/shared Knowledge.

Schema Owner operations are the existing trusted control plane. An End User
or independent Agent login cannot publish by updating visibility or mutate an
approved body. No capability default, old SQL or business row is rewritten.
"""
from __future__ import annotations

import re

SCRIPT='112_v5_0_3_native_knowledge_governance.sql'
COLUMNS=('ENTITY_ID','ENTITY_TYPE','TITLE','CONTENT','SUMMARY','CATEGORY','STATUS','OWNED_BY_AGENT','VISIBILITY','WORKSPACE_ID','EXPIRES_AT')
TABLES=(('ENTITIES','CX503_KNOW_ENTITY_GUARD'),
        ('KNOWLEDGE_META','CX503_KNOW_META_GUARD'),
        ('CX_KNOWLEDGE_ACCESS_POLICIES','CX503_KNOW_POLICY_GUARD'))


def render_body_search():
    name='116_v5_0_3_yashandb_knowledge_body_search.sql'
    sql=("-- v5.0.3 native body recall; retain the existing TITLE SEARCH index.\n"
         "DECLARE n NUMBER; BEGIN SELECT COUNT(*) INTO n FROM USER_INDEXES "
         "WHERE INDEX_NAME='CX503_KNOW_BODY_SEARCH'; IF n=0 THEN EXECUTE IMMEDIATE "
         "'CREATE SEARCH INDEX CX503_KNOW_BODY_SEARCH ON ENTITIES(CONTENT)'; END IF; END;\n/\n")
    facts=dict(schema='v503-yashandb-knowledge-body-search/v1',database='yashandb',
               index='CX503_KNOW_BODY_SEARCH',table='ENTITIES',columns=['CONTENT'],index_type='SEARCH',
               existing_title_index='PRESERVED',grants='UNCHANGED')
    return name,sql,facts


def body_search_errors(cursor):
    cursor.execute("SELECT TABLE_NAME,INDEX_TYPE,STATUS FROM USER_INDEXES WHERE INDEX_NAME='CX503_KNOW_BODY_SEARCH'")
    index=cursor.fetchone()
    cursor.execute("SELECT COLUMN_NAME FROM USER_IND_COLUMNS WHERE INDEX_NAME='CX503_KNOW_BODY_SEARCH' ORDER BY COLUMN_POSITION")
    columns=[row[0] for row in cursor.fetchall()]
    return [] if index and tuple(index)==('ENTITIES','SEARCH','VALID') and columns==['CONTENT'] else ['KNOWLEDGE_BODY_SEARCH_INDEX']


def _entity_condition(database):
    n,o=('NEW.','OLD.') if database=='pg' else (':NEW.',':OLD.')
    cast=(lambda value:value+'::text') if database=='pg' else (lambda value:value)
    exists=("EXISTS (SELECT 1 FROM CX_CONTINUITY_ARTIFACT_REVS r JOIN CX_CONTINUITY_ARTIFACTS a "
        "ON a.ARTIFACT_ID=r.ARTIFACT_ID WHERE r.NATIVE_ENTITY_ID="+cast(o+'ENTITY_ID')+" AND a.FAMILY='KNOWLEDGE')")
    shared="EXISTS (SELECT 1 FROM CX_KNOWLEDGE_ACCESS_POLICIES k WHERE k.ENTITY_ID="+cast(o+'ENTITY_ID')+" AND k.STATUS='ACTIVE' AND k.SCOPE_TYPE<>'PRINCIPAL_PRIVATE')"
    return n,o,'('+exists+' OR '+shared+')'


def _pg_body(table):
    if table=='CX_KNOWLEDGE_ACCESS_POLICIES':
        condition='TRUE'
    elif table=='KNOWLEDGE_META':
        condition=("EXISTS (SELECT 1 FROM public.cx_continuity_artifact_revs r JOIN public.cx_continuity_artifacts a "
            "ON a.artifact_id=r.artifact_id WHERE a.family='KNOWLEDGE' AND "
            "((TG_OP<>'INSERT' AND r.native_entity_id=OLD.entity_id::text) OR (TG_OP<>'DELETE' AND r.native_entity_id=NEW.entity_id::text)))")
    else:
        n,o,formal=_entity_condition('pg')
        condition=("(TG_OP='INSERT' AND NEW.ENTITY_TYPE='KNOWLEDGE' AND NEW.VISIBILITY IS DISTINCT FROM 'PRIVATE') OR "
            "(TG_OP='UPDATE' AND (OLD.ENTITY_TYPE='KNOWLEDGE' OR NEW.ENTITY_TYPE='KNOWLEDGE') AND "
            "(NEW.ENTITY_TYPE IS DISTINCT FROM 'KNOWLEDGE' OR NEW.VISIBILITY IS DISTINCT FROM 'PRIVATE' OR "
            "OLD.VISIBILITY IS DISTINCT FROM 'PRIVATE' OR "+formal+")) OR "
            "(TG_OP='DELETE' AND OLD.ENTITY_TYPE='KNOWLEDGE' AND (OLD.VISIBILITY IS DISTINCT FROM 'PRIVATE' OR "+formal+"))")
    return ("BEGIN IF public.current_agent_identity() IS NOT NULL AND ("+condition+
        ") THEN RAISE EXCEPTION 'Shared or reviewed Knowledge requires governed intake' USING ERRCODE='42501'; "
        "END IF; IF TG_OP='DELETE' THEN RETURN OLD; END IF; RETURN NEW; END")


def _native_body(database,table,owner='__CX_SCHEMA_OWNER__'):
    # Oracle End Users share a schema login: SESSION_USER alone cannot detect
    # them. YashanDB binds independent native logins to SESSION_USER.
    declaration='DECLARE native_agent VARCHAR2(128); governed_intake_required EXCEPTION; n NUMBER; '
    if database=='oracle':
        declaration='DECLARE native_agent VARCHAR2(128); n NUMBER; '
        identity="SELECT ORA_END_USER_CONTEXT.username INTO native_agent FROM DUAL;"
        check='native_agent IS NOT NULL'
        deny="RAISE_APPLICATION_ERROR(-20912,'Shared or reviewed Knowledge requires governed intake');"
    else:
        identity="native_agent:=SYS_CONTEXT('USERENV','SESSION_USER');"
        check="native_agent<>'"+owner.replace("'","''")+"'"
        deny='RAISE governed_intake_required;'
    if table=='CX_KNOWLEDGE_ACCESS_POLICIES':
        action=deny
    elif table=='KNOWLEDGE_META':
        action=("SELECT COUNT(*) INTO n FROM CX_CONTINUITY_ARTIFACT_REVS r "
            "JOIN CX_CONTINUITY_ARTIFACTS a ON a.ARTIFACT_ID=r.ARTIFACT_ID WHERE "
            "(r.NATIVE_ENTITY_ID=:OLD.ENTITY_ID OR r.NATIVE_ENTITY_ID=:NEW.ENTITY_ID) AND a.FAMILY='KNOWLEDGE'; "
            "IF n>0 THEN "+deny+' END IF;')
    else:
        action=("IF INSERTING AND :NEW.ENTITY_TYPE='KNOWLEDGE' AND COALESCE(:NEW.VISIBILITY,'?')<>'PRIVATE' THEN "+deny+' END IF; '
            "IF UPDATING AND (:OLD.ENTITY_TYPE='KNOWLEDGE' OR :NEW.ENTITY_TYPE='KNOWLEDGE') THEN "
            "IF COALESCE(:NEW.ENTITY_TYPE,'?')<>'KNOWLEDGE' OR COALESCE(:NEW.VISIBILITY,'?')<>'PRIVATE' OR COALESCE(:OLD.VISIBILITY,'?')<>'PRIVATE' THEN "+deny+' END IF; END IF; '
            "IF (UPDATING OR DELETING) AND :OLD.ENTITY_TYPE='KNOWLEDGE' THEN "
            "SELECT COUNT(*) INTO n FROM CX_CONTINUITY_ARTIFACT_REVS r JOIN CX_CONTINUITY_ARTIFACTS a ON a.ARTIFACT_ID=r.ARTIFACT_ID "
            "WHERE r.NATIVE_ENTITY_ID=:OLD.ENTITY_ID AND a.FAMILY='KNOWLEDGE'; "
            "IF n>0 OR (DELETING AND COALESCE(:OLD.VISIBILITY,'?')<>'PRIVATE') THEN "+deny+' END IF; END IF;')
    return declaration+'BEGIN '+identity+' IF '+check+' THEN '+action+' END IF; END;'


def _legacy_shared_body(database, table, body):
    """Migration 114: protect legacy shared rows without rewriting 112/113."""
    if table == 'CX_KNOWLEDGE_ACCESS_POLICIES':
        return body
    if database == 'pg':
        if table == 'ENTITIES':
            return body  # 112/113 already check legacy visibility and policy.
        predicate = ("EXISTS (SELECT 1 FROM public.entities e WHERE e.entity_type='KNOWLEDGE' AND "
            "((TG_OP<>'INSERT' AND e.entity_id=OLD.entity_id) OR (TG_OP<>'DELETE' AND e.entity_id=NEW.entity_id)) AND "
            "(e.visibility IS DISTINCT FROM 'PRIVATE' OR EXISTS (SELECT 1 FROM public.cx_knowledge_access_policies k "
            "WHERE k.entity_id=e.entity_id::text AND k.status='ACTIVE' AND k.scope_type<>'PRINCIPAL_PRIVATE'))) OR ")
        return body.replace('AND (EXISTS (', 'AND ('+predicate+'EXISTS (', 1)
    if table == 'KNOWLEDGE_META':
        addition=("SELECT COUNT(*) INTO legacy_shared FROM ENTITIES e WHERE e.ENTITY_TYPE='KNOWLEDGE' "
            "AND (e.ENTITY_ID=:OLD.ENTITY_ID OR e.ENTITY_ID=:NEW.ENTITY_ID) "
            "AND (COALESCE(e.VISIBILITY,'?')<>'PRIVATE' OR EXISTS (SELECT 1 FROM CX_KNOWLEDGE_ACCESS_POLICIES k "
            "WHERE k.ENTITY_ID=e.ENTITY_ID AND k.STATUS='ACTIVE' AND k.SCOPE_TYPE<>'PRINCIPAL_PRIVATE')); ")
    else:
        addition=("SELECT COUNT(*) INTO legacy_shared FROM CX_KNOWLEDGE_ACCESS_POLICIES k "
            "WHERE k.ENTITY_ID=:OLD.ENTITY_ID AND k.STATUS='ACTIVE' AND k.SCOPE_TYPE<>'PRINCIPAL_PRIVATE'; ")
    body=body.replace('n NUMBER;', 'n NUMBER; legacy_shared NUMBER;', 1)
    return body.replace('IF n>0', addition+'IF legacy_shared>0 OR n>0', 1)


def render(database, *, authenticated_login=False, legacy_shared=False, all_updates=False):
    if database not in {'pg','oracle','yashandb'}:
        raise ValueError('Unsupported knowledge governance database')
    if all_updates:
        if database!='yashandb':
            raise ValueError('Migration 115 is specific to YashanDB')
        legacy_shared=True
    if legacy_shared:
        authenticated_login=True
    output=['-- v5.0.3 private-note / reviewed Knowledge native write boundary.',
            '-- Generated from lib.knowledge_native_governance; preserve applied bytes.']
    guards=[]
    for table,trigger in TABLES:
        # Oracle rejects a CLOB column (CONTENT) in UPDATE OF (ORA-25006).
        # Fire for every update there; narrowing the list by omitting CONTENT
        # would silently allow direct changes to a reviewed Knowledge body.
        columns=list(COLUMNS) if table=='ENTITIES' and database!='oracle' and not all_updates else []
        events='INSERT OR DELETE OR UPDATE'+(' OF '+','.join(columns) if columns else '')
        if database=='pg':
            function=trigger.lower()
            body=_pg_body(table)
            if authenticated_login:
                body=body.replace('public.current_agent_identity() IS NOT NULL','SESSION_USER<>CURRENT_USER')
            if legacy_shared:
                body=_legacy_shared_body(database,table,body)
            output += [f'CREATE OR REPLACE FUNCTION public.{function}() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public AS $cx503$ {body} $cx503$;',
                f'REVOKE ALL ON FUNCTION public.{function}() FROM PUBLIC, ai_agent_runtime;',
                f'CREATE OR REPLACE TRIGGER {trigger} BEFORE {events} ON public.{table} FOR EACH ROW EXECUTE FUNCTION public.{function}();']
        else:
            function=None;body=_native_body(database,table)
            if legacy_shared:
                body=_legacy_shared_body(database,table,body)
            ddl=f'CREATE OR REPLACE TRIGGER {trigger} BEFORE {events} ON {table} FOR EACH ROW '+body
            if database=='yashandb':
                quoted=ddl.replace("'","''").replace('__CX_SCHEMA_OWNER__',"' || REPLACE(owner_name,'''','''''') || '")
                output.append("DECLARE owner_name VARCHAR2(128); BEGIN SELECT USER INTO owner_name FROM DUAL; EXECUTE IMMEDIATE '"+quoted+"'; END;\n/")
            else:
                output.append(ddl+'\n/')
        guards.append(dict(table=table,trigger=trigger,function=function,body=body,columns=columns))
    if database=='pg':
        output.append('REVOKE ALL ON public.cx_knowledge_access_policies FROM PUBLIC, ai_agent_runtime;')
    filename=('115_v5_0_3_yashandb_lob_knowledge_write.sql' if all_updates else
              '114_v5_0_3_legacy_shared_knowledge_write.sql' if legacy_shared else
              '113_v5_0_3_authenticated_knowledge_write.sql' if authenticated_login else SCRIPT)
    return filename,'\n\n'.join(output)+'\n',dict(schema='v503-native-knowledge-governance/v1',database=database,
        guards=guards,policy_table_native_mutation='DENIED',owner_control_plane='PRESERVED')


def _compact(value):
    value=value.read() if hasattr(value,'read') else str(value)
    return ''.join(part if part.startswith("'") else re.sub(r'\s+','',part).upper()
        for part in re.findall(r"'(?:[^']|'')*'|[^']+",value)).rstrip(';')


def errors(cursor,database, *, authenticated_login=True, legacy_shared=False):
    """Inspect executable guard definitions, identity binding and enablement."""
    failures=[]
    expected=render(database,authenticated_login=authenticated_login,legacy_shared=legacy_shared)[2]
    owner=None
    if database!='pg':
        cursor.execute('SELECT USER FROM DUAL');owner=str(cursor.fetchone()[0])
    for guard in expected['guards']:
        if database=='pg':
            cursor.execute("SELECT t.tgtype,p.prosrc,p.prosecdef,p.proconfig,t.tgenabled,"
                "ARRAY(SELECT upper(a.attname) FROM unnest(t.tgattr::smallint[]) WITH ORDINALITY k(num,ord) "
                "JOIN pg_attribute a ON a.attrelid=t.tgrelid AND a.attnum=k.num ORDER BY k.ord),"
                "NOT EXISTS (SELECT 1 FROM aclexplode(COALESCE(p.proacl,acldefault('f',p.proowner))) acl "
                "WHERE acl.grantee<>p.proowner AND acl.privilege_type='EXECUTE') "
                "FROM pg_trigger t JOIN pg_proc p ON p.oid=t.tgfoid WHERE t.tgrelid=to_regclass(%s) "
                "AND t.tgname=%s AND NOT t.tgisinternal",(guard['table'].lower(),guard['trigger'].lower()))
            row=cursor.fetchone()
            if (not row or row[0]!=31 or _compact(row[1])!=_compact(guard['body']) or not row[2]
                    or row[3]!=['search_path=pg_catalog, public'] or row[4]!='O'
                    or list(row[5])!=guard['columns'] or not row[6]):
                failures.append(guard['trigger']+':EXECUTABLE_GUARD')
        else:
            cursor.execute('SELECT TRIGGER_BODY,STATUS,TRIGGER_TYPE,TRIGGERING_EVENT FROM USER_TRIGGERS '
                'WHERE TABLE_NAME=:table_name AND TRIGGER_NAME=:trigger_name',{'table_name':guard['table'],'trigger_name':guard['trigger']})
            row=cursor.fetchone()
            cursor.execute('SELECT STATUS FROM USER_OBJECTS WHERE OBJECT_TYPE=\'TRIGGER\' AND OBJECT_NAME=:trigger_name',
                {'trigger_name':guard['trigger']})
            compiled=cursor.fetchone()
            body=_native_body(database,guard['table'],owner)
            if legacy_shared:
                body=_legacy_shared_body(database,guard['table'],body)
            if (not row or not compiled or compiled[0]!='VALID' or _compact(row[0])!=_compact(body) or row[1]!='ENABLED'
                    or row[2]!='BEFORE EACH ROW' or set(re.split(r'\s+OR\s+',row[3]))!={'INSERT','DELETE','UPDATE'}):
                failures.append(guard['trigger']+':EXECUTABLE_GUARD')
    if database=='pg':
        cursor.execute("SELECT COUNT(*) FROM pg_class c,LATERAL aclexplode(COALESCE(c.relacl,acldefault('r',c.relowner))) a "
            "WHERE c.oid='public.cx_knowledge_access_policies'::regclass AND a.grantee<>c.relowner")
        if int(cursor.fetchone()[0]):
            failures.append('POLICY_TABLE_NATIVE_GRANTS')
    return failures
