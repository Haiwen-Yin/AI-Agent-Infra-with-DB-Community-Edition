"""Private-note failures must roll back data, context, policy and audit together.

SQLite exercises service transaction boundaries; native parity has its own
explicitly classified integration checks.
"""
import sqlite3

import pytest

from lib import knowledge_api as knowledge


@pytest.mark.parametrize('database', ('pg', 'oracle', 'yashandb'))
@pytest.mark.parametrize('case', ('unknown', 'suspended', 'denied', 'metadata', 'audit', 'success', 'owner_legacy'))
def test_private_note_creation_commits_all_or_preserves_no_partial_rows(monkeypatch, database, case):
    db=sqlite3.connect(':memory:');db.row_factory=sqlite3.Row
    identifier='INTEGER PRIMARY KEY' if database=='pg' else 'TEXT PRIMARY KEY'
    db.executescript('CREATE TABLE CX_PRINCIPALS(PRINCIPAL_ID TEXT PRIMARY KEY,STATUS TEXT);'
        "INSERT INTO CX_PRINCIPALS VALUES('agent','ACTIVE');"+
        'CREATE TABLE ENTITIES(ENTITY_ID '+identifier+',ENTITY_TYPE TEXT,TITLE TEXT,CONTENT TEXT,SUMMARY TEXT,'
        'CATEGORY TEXT,IMPORTANCE INTEGER,STATUS TEXT,OWNED_BY_AGENT TEXT,SOURCE_AGENT TEXT,VISIBILITY TEXT,WORKSPACE_ID TEXT);'
        'CREATE TABLE KNOWLEDGE_META(ENTITY_ID TEXT PRIMARY KEY,ENTITY_TYPE TEXT,DOMAIN TEXT,TOPIC TEXT,'
        "DIFFICULTY TEXT CHECK(DIFFICULTY IN ('BEGINNER','INTERMEDIATE')),REVIEW_COUNT INTEGER,NEXT_REVIEW TEXT);"
        'CREATE TABLE CX_KNOWLEDGE_CONTEXTS(CONTEXT_ID TEXT,ENTITY_ID TEXT,AGENT_ID TEXT,PRINCIPAL_ID TEXT,'
        'ORGANIZATION_ID TEXT,ORGANIZATION_CHAIN_JSON TEXT,RESPONSIBLE_GROUPS_JSON TEXT,EXECUTION_GROUPS_JSON TEXT,'
        'SHARING_SCOPE TEXT,GRAPH_SNAPSHOT_DIGEST TEXT,REASON TEXT);'
        'CREATE TABLE CX_KNOWLEDGE_ACCESS_POLICIES(POLICY_ID TEXT,ENTITY_ID TEXT,SCOPE_TYPE TEXT,'
        "ORGANIZATION_ID TEXT,PRINCIPAL_ID TEXT,HIERARCHY_DEPTH INTEGER,REASON TEXT,CREATED_BY TEXT,STATUS TEXT DEFAULT 'ACTIVE',UPDATED_AT TEXT);"
        'CREATE TABLE NOTE_AUDIT(ACTOR TEXT,ACTION TEXT,ENTITY_ID TEXT);')
    if case=='suspended':db.execute("UPDATE CX_PRINCIPALS SET STATUS='SUSPENDED'")
    db.commit()

    class Transaction:
        def execute(self,sql,params=None):
            sql=sql.replace(' FOR UPDATE','').replace("CURRENT_TIMESTAMP + INTERVAL '7 days'",'CURRENT_TIMESTAMP').replace('CURRENT_TIMESTAMP + 7','CURRENT_TIMESTAMP')
            return db.execute(sql,params or {})
        def query_one(self,sql,params=None):
            if sql.endswith(' RETURNING ENTITY_ID'):
                # The host's older SQLite has no RETURNING clause. Native PG
                # checks execute the real clause; this fixture tests rollback.
                cursor=self.execute(sql.removesuffix(' RETURNING ENTITY_ID'),params)
                return {'entity_id':cursor.lastrowid}
            row=self.execute(sql,params).fetchone()
            return {key.lower():value for key,value in dict(row).items()} if row else None

    def callback(action):
        with db:
            return action(Transaction())

    def audit(tx,actor,action,_kind,entity,*_args):
        tx.execute('INSERT INTO NOTE_AUDIT VALUES(:actor,:action,:entity)',dict(actor=actor,action=action,entity=entity))
        if case=='audit':raise RuntimeError('Audit persistence failed')

    monkeypatch.setattr(knowledge,'DATABASE_DIALECT',database)
    monkeypatch.setattr(knowledge.connection,'DATABASE_DIALECT',database)
    monkeypatch.setattr(knowledge.connection,'execute_transaction_callback',callback)
    monkeypatch.setattr(knowledge.identity_api,'effective_access',lambda *_:{'decision':'DENY' if case=='denied' else 'ALLOW','scopes':['OWNED']})
    monkeypatch.setattr(knowledge.identity_api,'_audit_tx',audit)
    monkeypatch.setattr(knowledge,'knowledge_access_predicate',lambda *_:'1=1')
    monkeypatch.setattr(knowledge,'get_agent_knowledge_context',lambda _,**kw:dict(agent_id='agent',principal_id='human',
        organization_id=None,organization_chain=[],responsible_groups=[],execution_groups=[]))
    def forbidden(*_a,**_kw):pytest.fail('Atomic note creation used a separately committing writer')
    monkeypatch.setattr(knowledge,'execute',forbidden)
    monkeypatch.setattr(knowledge,'execute_insert_returning_id',forbidden)
    options=dict(owned_by_agent=None if case=='owner_legacy' else 'unknown' if case=='unknown' else 'agent',
                 difficulty='INVALID' if case=='metadata' else 'BEGINNER')
    tables=('ENTITIES','KNOWLEDGE_META','CX_KNOWLEDGE_CONTEXTS','CX_KNOWLEDGE_ACCESS_POLICIES','NOTE_AUDIT')
    try:
        if case in {'success','owner_legacy'}:
            entity=knowledge.create_knowledge('Private note','Preserve exact content',**options)
            assert db.execute('SELECT CONTENT FROM ENTITIES WHERE ENTITY_ID=?',(entity,)).fetchone()[0]=='Preserve exact content'
            expected=(1,1,0,0,0) if case=='owner_legacy' else (1,1,1,1,1)
            assert tuple(db.execute('SELECT COUNT(*) FROM '+table).fetchone()[0] for table in tables)==expected
            if case=='success':
                assert db.execute('SELECT PRINCIPAL_ID FROM CX_KNOWLEDGE_ACCESS_POLICIES').fetchone()[0]=='agent'
        else:
            with pytest.raises((PermissionError,sqlite3.IntegrityError,RuntimeError)):
                knowledge.create_knowledge('Private note','Preserve exact content',**options)
            assert all(db.execute('SELECT COUNT(*) FROM '+table).fetchone()[0]==0 for table in tables)
    finally:
        db.close()
