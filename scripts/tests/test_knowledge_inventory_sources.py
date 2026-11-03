"""Inventory bodies, metadata and cursors retain original-source authority."""
import re

import pytest

from lib import knowledge_api,agent_source_sync,cursor_pagination
from lib.continuity_state import ContinuityError
from .test_knowledge_curated import published_source
from .test_v501_context_assets import store,configuration
from .test_continuity_candidates import candidate_db
from .test_continuity_handoff import fixture
from .test_continuity_work import database


@pytest.fixture
def inventory(store,monkeypatch):
    db,_=store
    for name,kind in [('SUMMARY','TEXT'),('CATEGORY','TEXT'),('IMPORTANCE','INTEGER'),
                      ('SOURCE_AGENT','TEXT'),('RETRIEVAL_COUNT','INTEGER'),('CREATED_AT','TEXT'),('WORKSPACE_ID','TEXT')]:
        db.execute('ALTER TABLE ENTITIES ADD COLUMN '+name+' '+kind)
    for name,kind in [('DIFFICULTY','TEXT'),('LAST_REVIEWED','TEXT'),('NEXT_REVIEW','TEXT')]:
        db.execute('ALTER TABLE KNOWLEDGE_META ADD COLUMN '+name+' '+kind)
    db.execute('CREATE TABLE CX_API_CURSORS(CURSOR_ID TEXT PRIMARY KEY,PRINCIPAL_ID TEXT,RESOURCE_KEY TEXT,'
        'FILTER_DIGEST TEXT,SORT_KEY TEXT,PAGE_SIZE INTEGER,POSITION_KEY TEXT,EXPIRES_AT TEXT)')
    db.create_function('TO_CHAR',2,lambda value,_format:value)
    def query(sql,params):
        sql=re.sub(r'OFFSET :off ROWS FETCH NEXT :lim ROWS ONLY','LIMIT :lim OFFSET :off',sql)
        sql=sql.replace('FETCH FIRST :lim ROWS ONLY','LIMIT :lim')
        return [{key.lower():row[key] for key in row.keys()} for row in db.execute(sql,params)]
    monkeypatch.setattr(knowledge_api,'execute_query',query)
    monkeypatch.setattr(knowledge_api.connection,'execute_query',query)
    monkeypatch.setattr(knowledge_api.connection,'execute_query_one',lambda sql,params:next(iter(query(sql,params)),None))
    monkeypatch.setattr(knowledge_api.connection,'execute',lambda sql,params:db.execute(sql,params).rowcount)
    monkeypatch.setattr(cursor_pagination,'_expiry_sql',lambda:"datetime('now','+15 minutes')")
    yield db


@pytest.mark.parametrize('cursor',[False,True])
def test_inventory_reauthorizes_originals_even_for_an_administrator(inventory,cursor):
    db=inventory
    source,_=published_source(db)
    def read():
        return (knowledge_api.search_knowledge_cursor('owner')['items'] if cursor else
            knowledge_api.search_knowledge(principal_id='owner'))
    visible=read()
    assert len(visible)==1 and visible[0]['source_context']['intake']['decision_status']=='PROPOSED'
    agent_source_sync.change_state('owner',source,dict(expected_version=1,status='REVOKED',
        reason='Withdraw the original source',idempotency_key='withdraw'))
    assert read()==[]
    assert db.execute('SELECT COUNT(*) FROM ENTITIES').fetchone()[0]==1


def test_cursor_advances_after_a_filtered_row_and_never_reports_raw_totals(inventory):
    db=inventory
    source,_=published_source(db)
    for number in range(20):
        entity='zz-'+str(number).zfill(2)
        db.execute("INSERT INTO ENTITIES(ENTITY_ID,ENTITY_TYPE,TITLE,CONTENT,STATUS,VISIBILITY) VALUES(?,'KNOWLEDGE','Manual','Body','ACTIVE','PUBLIC')",(entity,))
        db.execute("INSERT INTO KNOWLEDGE_META(ENTITY_ID,ENTITY_TYPE) VALUES(?,'KNOWLEDGE')",(entity,))
    db.commit()
    agent_source_sync.change_state('owner',source,dict(expected_version=1,status='REVOKED',
        reason='Withdraw the original source',idempotency_key='withdraw'))
    first=knowledge_api.search_knowledge_cursor('owner')
    assert len(first['items'])==first['count']==19 and first['has_more']
    assert 'total_items' not in first and first['next_cursor']
    assert all(item['entity_id'].startswith('zz-') for item in first['items'])
    second=knowledge_api.search_knowledge_cursor('owner',cursor=first['next_cursor'])
    assert second['count']==1 and not second['has_more']
    assert set(item['entity_id'] for item in first['items']).isdisjoint(item['entity_id'] for item in second['items'])
    with pytest.raises(cursor_pagination.CursorError):
        knowledge_api.search_knowledge_cursor('agent',cursor=first['next_cursor'])


def test_corrupt_lineage_is_an_error_instead_of_a_successful_empty_inventory(inventory):
    db=inventory
    published_source(db)
    db.execute("UPDATE CX_CANDIDATE_REVIEWS SET CONTENT_DIGEST=?",('0'*64,));db.commit()
    with pytest.raises(ContinuityError,match='integrity'):
        knowledge_api.search_knowledge(principal_id='owner')
