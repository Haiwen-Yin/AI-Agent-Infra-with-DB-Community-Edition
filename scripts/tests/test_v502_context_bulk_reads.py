"""Original final501 serial reads versus current bounded relational reads.

SQLite is an offline relational harness. These measurements include every SQL
statement through real current policy helpers; they are not vendor acceptance.
"""
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime,timedelta,timezone
import json
from pathlib import Path
import re
import socket
from types import SimpleNamespace
import urllib.request

import pytest

from lib import connection,identity_api,continuity_work as work,continuity_sources as sources
from lib import context_selection as selection,continuity_assembly as assembly,memory_lifecycle as memory,agent_assets as assets
from lib import product_identity
from lib.continuity_contracts import SourceRef
from lib.continuity_state import ContinuityConflict
from .test_v501_context_assets import store,context
from .test_continuity_candidates import candidate_db
from .test_continuity_handoff import fixture
from .test_continuity_work import database
from . import v502_serial_context_reference as reference

ROOT=Path(__file__).resolve().parents[2]
CANONICAL_ACCESS=identity_api.effective_access
CANONICAL_VISIBLE=identity_api._agent_visible_to
CANONICAL_AUDIT=identity_api._audit_tx


@pytest.fixture
def relational(store,monkeypatch):
    if not (ROOT/'adapters').is_dir():pytest.skip('Preserved original501 source comparison belongs to the checkout; native reference has a separate opt-in harness')
    db,_=store
    monkeypatch.setattr(socket,'create_connection',lambda *a,**k:pytest.fail('Offline relational contract cannot connect'))
    monkeypatch.setattr(urllib.request,'urlopen',lambda *a,**k:pytest.fail('Offline relational contract cannot send HTTP'))
    db.executescript('''
        ALTER TABLE CX_MEMORY_FAMILIES ADD COLUMN WORKSPACE_ID TEXT;
        ALTER TABLE CX_MEMORY_FAMILIES ADD COLUMN LEGACY_ENTITY_ID TEXT;
        ALTER TABLE CX_MEMORY_VERSIONS ADD COLUMN VALID_FROM TIMESTAMP;
        ALTER TABLE CX_MEMORY_REPRESENTATIONS ADD COLUMN VALIDATION_STATE TEXT DEFAULT 'VALID';
        ALTER TABLE CX_MEMORY_REPRESENTATIONS ADD COLUMN INDEX_STATE TEXT DEFAULT 'HOT';
        ALTER TABLE CX_MEMORY_REPRESENTATIONS ADD COLUMN CREATED_AT TIMESTAMP DEFAULT '2026-10-20 00:00:00';
        ALTER TABLE CX_MEMORY_REPRESENTATIONS ADD COLUMN GENERATOR_VERSION TEXT;
        CREATE TABLE CX_USER_ROLES(PRINCIPAL_ID TEXT,ROLE_CODE TEXT,STATUS TEXT,VALID_UNTIL TIMESTAMP);
        CREATE TABLE CX_ROLE_TEMPLATES(ROLE_CODE TEXT,PERMISSIONS_JSON TEXT,DATA_SCOPES_JSON TEXT);
        CREATE TABLE CX_USER_PERMISSION_OVERRIDES(PRINCIPAL_ID TEXT,RESOURCE_ACTION TEXT,EFFECT TEXT,DATA_SCOPE TEXT,
            SECURITY_DOMAIN_ID TEXT,REASON TEXT,GRANTED_BY TEXT,VALID_UNTIL TIMESTAMP,CREATED_AT TIMESTAMP);
        CREATE TABLE CX_DELEGATIONS(DELEGATION_ID TEXT,GRANTOR_PRINCIPAL_ID TEXT,GRANTEE_PRINCIPAL_ID TEXT,
            PERMISSIONS_JSON TEXT,DATA_SCOPE TEXT,STATUS TEXT,VALID_UNTIL TIMESTAMP,CREATED_AT TIMESTAMP);
        CREATE TABLE CX_SECURITY_EVENTS(EVENT_ID TEXT PRIMARY KEY,PRINCIPAL_ID TEXT,ACTOR_TYPE TEXT,ACTION_NAME TEXT,
            RESOURCE_TYPE TEXT,RESOURCE_ID TEXT,OUTCOME TEXT,REASON TEXT,DETAIL_JSON TEXT);
    ''')
    permissions=json.dumps(['workspaces.*','memory.read','agents.read','agents.operate'])
    db.execute('INSERT INTO CX_ROLE_TEMPLATES VALUES(?,?,?)',('BULK_OWNER',permissions,'["ALL"]'))
    db.execute('INSERT INTO CX_ROLE_TEMPLATES VALUES(?,?,?)',('BULK_AGENT',permissions,'["ASSIGNED"]'))
    db.executemany('INSERT INTO CX_USER_ROLES VALUES(?,?,?,NULL)',[('owner','BULK_OWNER','ACTIVE'),('agent','BULK_AGENT','ACTIVE')])
    db.commit();calls=[];active=[];hooks=[]
    class Tx:
        def query(self,sql,params=None):
            params=params or {};calls.append(dict(method='query',sql=sql,params=dict(params)))
            for hook in list(hooks):hook(sql,params)
            sql=sql.replace(' FOR UPDATE','')
            sql=sql.replace("CURRENT_TIMESTAMP AT TIME ZONE 'UTC'",'CURRENT_TIMESTAMP')
            sql=re.sub(r'FETCH FIRST (:\w+) ROWS ONLY',r'LIMIT \1',sql)
            return [{key.lower():row[key] for key in row.keys()} for row in db.execute(sql,params)]
        def query_one(self,sql,params=None):
            rows=self.query(sql,params);return rows[0] if rows else None
        def execute(self,sql,params):
            calls.append(dict(method='execute',sql=sql,params=dict(params)))
            return db.execute(sql.replace(' FOR UPDATE',''),params).rowcount
        def execute_many(self,sql,rows):
            rows=list(rows);calls.append(dict(method='execute_many',sql=sql,rows=len(rows)))
            return db.executemany(sql,rows).rowcount
    def transaction(callback):
        tx=Tx();active.append(tx)
        try:
            result=callback(tx);db.commit();return result
        except BaseException:
            db.rollback();raise
        finally:active.pop()
    query=lambda sql,params=None:(active[-1] if active else Tx()).query(sql,params)
    one=lambda sql,params=None:(active[-1] if active else Tx()).query_one(sql,params)
    for module in (connection,memory):
        monkeypatch.setattr(module,'execute_transaction_callback',transaction)
        monkeypatch.setattr(module,'execute_query',query)
        monkeypatch.setattr(module,'execute_query_one',one)
        monkeypatch.setattr(module,'execute',lambda sql,params:(active[-1] if active else Tx()).execute(sql,params))
    monkeypatch.setattr(identity_api,'effective_access',CANONICAL_ACCESS)
    monkeypatch.setattr(identity_api,'_agent_visible_to',CANONICAL_VISIBLE)
    monkeypatch.setattr(identity_api,'_audit_tx',CANONICAL_AUDIT)
    monkeypatch.setattr(product_identity,'read_manifest',lambda:dict(version='5.0.2',delivery_product=dict(key='unified-community')))
    monkeypatch.setattr(connection,'DATABASE_DIALECT','pg')
    from product_delivery import acceptance_targets
    entry=next(item for item in acceptance_targets() if item['key']=='unified-community-pg')
    value=reference.describe(ROOT,entry)
    with reference.load(value) as old:
        yield SimpleNamespace(db=db,calls=calls,tx=Tx,transaction=transaction,old=old,reference=value,hooks=hooks)


def memories(state,count,*,owner='owner'):
    result=[]
    for index in range(count):
        item=memory.create_family(dict(title=f'Frozen cube fact {index:03}',content=f'The approved sample {index} contains exactly 23 blue cubes.',
            memory_type='FACT',memory_scope='AGENT_MEMORY',classification='INTERNAL',security_domain_id='domain',
            owner_principal_id=owner,reason='Explicit offline relational fixture'),actor='owner')
        digest=state.db.execute('SELECT CONTENT_DIGEST FROM CX_MEMORY_VERSIONS WHERE VERSION_ID=?',(item['version_id'],)).fetchone()[0]
        result.append(dict(family='MEMORY',entity_id=item['family_id'],revision_id=item['version_id'],content_digest=digest))
    return result


def stable(record):
    result={key:record[key] for key in ('status','content_digest','request_id','purpose','policy_version','retrieval_policy',
        'token_budget','entry_limit','item_count','text','token_count_method')}
    for key in ('items','representations'):
        result[key]=[{name:value for name,value in row.items() if name!='assembly_id'} for row in record[key]]
    result['budget']={name:value for name,value in record['budget'].items() if name!='assembly_id'}
    return result


def measured(state,operation):
    state.calls.clear();result=operation();calls=deepcopy(state.calls)
    return result,dict(reads=sum(item['method']=='query' for item in calls),
        writes=sum(item['method']!='query' for item in calls),total=len(calls),calls=calls)


def equivalent_unenveloped_context(actual,old):
    # These fixtures are ordinary, noncandidate Memory. V5.0.3 names its new
    # rendering policy explicitly, while all original bytes, budgets, digests,
    # item order and representation receipts must remain exactly equivalent.
    prefix='ASSET_' if old['retrieval_policy'].startswith('ASSET_') else ''
    assert old['retrieval_policy']==prefix+'QUERY_METADATA_BUDGET_V1'
    assert actual['retrieval_policy']==prefix+'QUERY_METADATA_BUDGET_SOURCE_CONTEXT_V2'
    return dict(actual,retrieval_policy=old['retrieval_policy'])==old


@pytest.mark.parametrize('count',[1,8,32])
def test_original501_prepare_and_consumption_have_exact_outputs_and_current_read_counts(relational,count,record_property):
    state=relational;frozen=memories(state,count)
    value=context(sources=frozen,query_text='cube',context_window=131072,token_budget=120000,entry_limit=100)
    def run(module,key):
        built=module.assemble('owner',dict(value,idempotency_key=key))
        return stable(module.read_assembly('owner',built['assembly_id']))
    old,serial=measured(state,lambda:run(state.old.continuity_assembly,'original501'))
    actual,batch=measured(state,lambda:run(assembly,'current502'))
    assert equivalent_unenveloped_context(actual,old) and actual['item_count']==count
    assert [item['entity_id'] for item in actual['items']]==[item['entity_id'] for item in frozen]
    if count==32:assert batch['reads']<serial['reads'] and batch['total']<serial['total']
    assert all(len(item.get('params',{}))<=100 for item in batch['calls'])
    record_property('original501_reference',json.dumps(state.reference,sort_keys=True))
    for kind,value in [('serial',serial),('batch',batch)]:
        for field in ('reads','writes','total'):record_property(kind+'_'+field,value[field])


@pytest.mark.parametrize('count',[1,8,32])
@pytest.mark.parametrize('purpose',['RUNTIME_CONTEXT','AUDIT'])
def test_original501_representation_preference_order_duplicates_and_budget_are_equivalent(relational,count,purpose,record_property):
    state=relational;frozen=memories(state,count)
    for index,source in enumerate(frozen):
        representation=memory.create_representation(source['revision_id'],'SHORT_SUMMARY',f'brief cube {index}')
        state.db.execute("UPDATE CX_MEMORY_REPRESENTATIONS SET CREATED_AT='2026-10-21 01:00:00' WHERE REPRESENTATION_ID=?",(representation,))
    state.db.commit();versions=[source['revision_id'] for source in frozen]
    old,serial=measured(state,lambda:state.old.memory_lifecycle.select_representations('owner',versions,purpose=purpose,token_budget=30))
    actual,batch=measured(state,lambda:memory.select_representations('owner',versions,purpose=purpose,token_budget=30))
    assert actual==old
    if count==32:assert batch['reads']<serial['reads']
    record_property('serial_reads',serial['reads']);record_property('batch_reads',batch['reads'])


@pytest.mark.parametrize('count',[1,8,32])
def test_original501_snapshot_member_order_and_per_version_representation_limit_are_equivalent(relational,count):
    state=relational;memories(state,count)
    old=state.old.memory_lifecycle._select_snapshot_members(state.tx(),token_budget=37)
    actual=memory._select_snapshot_members(state.tx(),token_budget=37)
    assert actual==old


def bindings(state,count,*,policy='PINNED'):
    frozen=memories(state,count)
    identifiers=[assets.bind('owner',dict(security_domain_id='domain',agent_id='agent',source=source,
        purpose='Frozen exact fixture input',resolution_policy=policy,reason='Authorized relational binding',
        idempotency_key='binding-'+str(index)))['binding_id'] for index,source in enumerate(frozen)]
    return frozen,identifiers


@pytest.mark.parametrize('count',[2,16,80])
def test_original501_assets_directory_assembly_and_consumption_have_exact_outputs(relational,count,record_property):
    state=relational;frozen,identifiers=bindings(state,count)
    value=context(context_window=131072,token_budget=120000,entry_limit=100)
    def run(asset_module,assembly_module,key):
        directory=asset_module.list_bindings('owner','domain','agent',limit=100)
        built=asset_module.assemble('owner',identifiers,dict(value,idempotency_key=key))
        return dict(directory=directory,assembly=stable(assembly_module.read_assembly('owner',built['assembly_id'])))
    old,serial=measured(state,lambda:run(state.old.agent_assets,state.old.continuity_assembly,'asset-original501'))
    actual,batch=measured(state,lambda:run(assets,assembly,'asset-current502'))
    assert actual['directory']==old['directory']
    assert equivalent_unenveloped_context(actual['assembly'],old['assembly']) and actual['assembly']['item_count']==count
    assert [item['entity_id'] for item in actual['assembly']['items']]==[item['entity_id'] for item in frozen]
    assert len(actual['directory']['items'])==count
    if count==80:assert batch['reads']<serial['reads'] and batch['total']<serial['total']
    assert all(len(item.get('params',{}))<=100 for item in batch['calls'])
    for kind,counts in [('serial',serial),('batch',batch)]:
        for field in ('reads','writes','total'):record_property(kind+'_'+field,counts[field])


def once(state,predicate,operation):
    def hook(sql,params):
        if predicate(sql,params):
            state.hooks.remove(hook);operation()
    state.hooks.append(hook)


@pytest.mark.parametrize('mutation',[
    "UPDATE CX_PRINCIPALS SET PERMISSION_VERSION=PERMISSION_VERSION+1 WHERE PRINCIPAL_ID='owner'",
    "UPDATE CX_PRINCIPALS SET STATUS='SUSPENDED' WHERE PRINCIPAL_ID='owner'",
    "UPDATE CX_SECURITY_DOMAINS SET STATUS='REVOKED' WHERE SECURITY_DOMAIN_ID='domain'",
    "UPDATE CX_DOMAIN_MEMBERS SET STATUS='REVOKED' WHERE PRINCIPAL_ID='owner'",
    "UPDATE CX_MEMORY_VERSIONS SET LIFECYCLE_STATE='UNAVAILABLE' WHERE VERSION_ID=:version",
    "UPDATE CX_MEMORY_VERSIONS SET OWNER_PRINCIPAL_ID='agent' WHERE VERSION_ID=:version",
    "UPDATE CX_MEMORY_VERSIONS SET VALID_UNTIL='2000-01-01' WHERE VERSION_ID=:version",
    "UPDATE CX_MEMORY_TIME_FACTS SET APPLIES_UNTIL='2000-01-01' WHERE VERSION_ID=:version",
])
def test_bulk_body_read_rejects_current_authority_change_in_same_transaction(relational,mutation):
    state=relational;frozen=memories(state,2)
    # Time evidence is created through the original API, then adversarially
    # altered by a trusted in-transaction callback at the body boundary.
    assert state.db.execute('SELECT COUNT(*) FROM CX_MEMORY_TIME_FACTS WHERE VERSION_ID=?',
        (frozen[0]['revision_id'],)).fetchone()[0]==1
    once(state,lambda sql,p:'SELECT * FROM CX_MEMORY_VERSIONS WHERE VERSION_ID IN' in sql,
        lambda:state.db.execute(mutation,dict(version=frozen[0]['revision_id'])))
    with pytest.raises((PermissionError,ContinuityConflict)):
        state.transaction(lambda tx:sources.resolve_many(tx,'owner','domain',frozen))


@pytest.mark.parametrize('route',['serial','bulk'])
def test_body_permission_expiry_without_version_change_preserves_original_denial(relational,route):
    state=relational;frozen=memories(state,2)
    once(state,lambda sql,p:'SELECT * FROM CX_MEMORY_VERSIONS WHERE VERSION_ID' in sql,
        lambda:state.db.execute("UPDATE CX_ROLE_TEMPLATES SET PERMISSIONS_JSON='[\"workspaces.*\"]' WHERE ROLE_CODE='BULK_OWNER'"))
    with pytest.raises(PermissionError):
        state.transaction(lambda tx:[state.old.continuity_sources.resolve(tx,'owner','domain',item) for item in frozen]
            if route=='serial' else sources.resolve_many(tx,'owner','domain',frozen))


@pytest.mark.parametrize('route',['serial','bulk'])
@pytest.mark.parametrize('kind',['role','override'])
def test_body_authority_natural_expiry_rechecks_original_current_policy(relational,route,kind):
    state=relational;frozen=memories(state,2);clock=[datetime(2030,1,1)]
    state.db.create_function('current_timestamp',0,lambda:clock[0].isoformat(sep=' '))
    if kind=='role':
        state.db.execute("UPDATE CX_USER_ROLES SET VALID_UNTIL='2030-01-01 00:00:02' WHERE PRINCIPAL_ID='owner'")
        state.db.execute("INSERT INTO CX_ROLE_TEMPLATES VALUES('END_USER','[\"workspaces.*\"]','[\"OWNED\"]')")
    else:
        state.db.execute("UPDATE CX_ROLE_TEMPLATES SET PERMISSIONS_JSON='[\"workspaces.*\"]' WHERE ROLE_CODE='BULK_OWNER'")
        state.db.execute("INSERT INTO CX_USER_PERMISSION_OVERRIDES(PRINCIPAL_ID,RESOURCE_ACTION,EFFECT,DATA_SCOPE,VALID_UNTIL) "
            "VALUES('owner','memory.read','ALLOW','ALL','2030-01-01 00:00:02')")
    state.db.commit()
    assert identity_api.effective_access('owner','memory.read')['decision']=='ALLOW'
    once(state,lambda sql,p:'SELECT * FROM CX_MEMORY_VERSIONS WHERE VERSION_ID' in sql,
        lambda:clock.__setitem__(0,clock[0]+timedelta(seconds=3)))
    with pytest.raises(PermissionError):
        state.transaction(lambda tx:[state.old.continuity_sources.resolve(tx,'owner','domain',item) for item in frozen]
            if route=='serial' else sources.resolve_many(tx,'owner','domain',frozen))


@pytest.mark.parametrize('field,changed',[
    ('VERSION_ID','other'),('REPRESENTATION_TYPE','SOURCE'),('TOKEN_COUNT',9999),
    ('CONTENT_DIGEST','0'*64),('VALIDATION_STATE','INVALID'),('INDEX_STATE','COLD')])
def test_selected_representation_is_bound_to_exact_current_metadata(relational,field,changed):
    state=relational;frozen=memories(state,2)
    identifier=memory.create_representation(frozen[0]['revision_id'],'SHORT_SUMMARY','Bound short cube fact')
    state.db.commit()
    if field=='VERSION_ID':changed=frozen[1]['revision_id']
    once(state,lambda sql,p:'SELECT REPRESENTATION_ID,VERSION_ID,REPRESENTATION_TYPE,TOKEN_COUNT,CONTENT_DIGEST,BODY_TEXT' in sql,
        lambda:state.db.execute('UPDATE CX_MEMORY_REPRESENTATIONS SET '+field+'=? WHERE REPRESENTATION_ID=?',(changed,identifier)))
    with pytest.raises(memory.MemoryLifecycleError):memory.select_representations('owner',[frozen[0]['revision_id']])


def test_unauthorized_versions_never_enter_bulk_body_query_and_owned_assigned_remain_current(relational):
    state=relational;frozen=memories(state,2)
    state.db.execute("UPDATE CX_ROLE_TEMPLATES SET DATA_SCOPES_JSON='[\"OWNED\"]' WHERE ROLE_CODE='BULK_OWNER'")
    state.db.execute('UPDATE CX_MEMORY_VERSIONS SET OWNER_PRINCIPAL_ID=? WHERE VERSION_ID=?',('agent',frozen[1]['revision_id']))
    state.db.commit();state.calls.clear()
    result=state.transaction(lambda tx:sources.resolve_many(tx,'owner','domain',frozen,omit_denied=True))
    assert result[0] and result[1] is None
    bodies=[call for call in state.calls if 'SELECT * FROM CX_MEMORY_VERSIONS WHERE VERSION_ID IN' in call.get('sql','')]
    assert len(bodies)==1 and list(bodies[0]['params'].values())==[frozen[0]['revision_id']]
    # ASSIGNED follows the original reader's explicit domain-member rule.
    assert state.transaction(lambda tx:sources.resolve_many(tx,'agent','domain',frozen))
    state.db.execute("UPDATE CX_DOMAIN_MEMBERS SET STATUS='REVOKED' WHERE PRINCIPAL_ID='agent'");state.db.commit()
    with pytest.raises(PermissionError):state.transaction(lambda tx:sources.resolve_many(tx,'agent','domain',frozen))


def test_consumption_uses_a_new_transaction_and_does_not_reuse_prepare_permissions(relational):
    state=relational;frozen=memories(state,8)
    prepared=assembly.assemble('owner',context(sources=frozen))
    assert assembly.read_assembly('owner',prepared['assembly_id'])['item_count']==8
    state.db.execute("UPDATE CX_ROLE_TEMPLATES SET PERMISSIONS_JSON='[]' WHERE ROLE_CODE='BULK_OWNER'");state.db.commit()
    state.calls.clear()
    with pytest.raises(PermissionError):assembly.read_assembly('owner',prepared['assembly_id'])
    assert not any('SELECT * FROM CX_MEMORY_VERSIONS WHERE VERSION_ID IN' in call.get('sql','') for call in state.calls)


@pytest.mark.parametrize('reverse',[False,True])
def test_actor_domain_authorization_precedes_sorted_family_then_version_locks(relational,reverse):
    state=relational;frozen=memories(state,8)
    if reverse:frozen.reverse()
    state.calls.clear()
    state.transaction(lambda tx:sources.resolve_many(tx,'owner','domain',frozen))
    calls=state.calls
    domain=next(index for index,item in enumerate(calls) if 'FROM CX_DOMAIN_MEMBERS' in item.get('sql',''))
    family=next(index for index,item in enumerate(calls) if item.get('sql','').startswith('SELECT FAMILY_ID FROM CX_MEMORY_FAMILIES'))
    version=next(index for index,item in enumerate(calls) if 'BATCH_REVISION_ID' in item.get('sql',''))
    assert domain<family<version
    for item in calls:
        if 'FOR UPDATE' in item.get('sql','') and ' IN (' in item['sql']:
            assert 'ORDER BY' in item['sql']
            values=[value for key,value in item['params'].items() if key.startswith('cx_bulk_')]
            assert values==sorted(values)


def test_asset_dual_actor_authorization_precedes_business_roots_and_revocation_rechecks(relational):
    state=relational;_frozen,identifiers=bindings(state,2)
    state.calls.clear();assert assets.load_many('owner',identifiers)
    calls=state.calls
    locked=next(index for index,item in enumerate(calls) if 'FROM CX_AGENT_ASSET_BINDINGS WHERE BINDING_ID IN' in item.get('sql','') and 'FOR UPDATE' in item['sql'])
    for actor in ('owner','agent'):
        assert any(index<locked and 'FROM CX_DOMAIN_MEMBERS' in item.get('sql','') and item['params'].get('actor')==actor
            for index,item in enumerate(calls))
    prepared=assets.assemble('owner',identifiers,context())
    assets.change_state('owner',identifiers[0],dict(expected_version=1,status='REVOKED',reason='Revoke exact fixture',idempotency_key='revoke-exact'))
    with pytest.raises(PermissionError):assembly.read_assembly('owner',prepared['assembly_id'])


def test_asset_recipient_and_directory_permissions_are_rechecked_after_source_loading(relational):
    state=relational;_frozen,identifiers=bindings(state,2)
    once(state,lambda sql,p:'SELECT * FROM CX_MEMORY_VERSIONS WHERE VERSION_ID IN' in sql,
        lambda:state.db.execute("UPDATE CX_ROLE_TEMPLATES SET PERMISSIONS_JSON='[\"workspaces.*\",\"memory.read\"]' WHERE ROLE_CODE='BULK_OWNER'"))
    with pytest.raises(PermissionError):assets.load_many('owner',identifiers)


def test_bulk_reads_chunk_all_actual_bindings_and_preserve_requested_order(relational):
    state=relational;frozen=memories(state,105);frozen.reverse()
    state.calls.clear();result=state.transaction(lambda tx:sources.resolve_many(tx,'owner','domain',frozen))
    assert [item['source'] for item in result]==frozen
    assert all(len(item.get('params',{}))<=100 for item in state.calls)
    bodies=[item for item in state.calls if 'SELECT * FROM CX_MEMORY_VERSIONS WHERE VERSION_ID IN' in item.get('sql','')]
    assert [len(item['params']) for item in bodies]==[100,5]


def test_memory_cycle_guards_are_identical_for_serial_and_bulk_readers(relational):
    state=relational;frozen=memories(state,2)
    key=tuple(frozen[0][name] for name in ('family','entity_id','revision_id'))
    token=sources._resolving.set((key,))
    try:
        with pytest.raises(Exception) as error:state.transaction(lambda tx:sources.resolve_many(tx,'owner','domain',frozen))
        assert error.value.code=='CYCLIC_SOURCE'
    finally:sources._resolving.reset(token)


def test_current_asset_policy_keeps_original_resolution_and_exact_source_revalidation(relational):
    state=relational;frozen,identifiers=bindings(state,2,policy='CURRENT')
    original=state.old.agent_assets.load('owner',identifiers[0])
    assert assets.load('owner',identifiers[0])==original
    source=frozen[0]
    memory.create_successor(source['entity_id'],source['revision_id'],dict(title='Current replacement cube',content='Exactly 24 blue cubes.',
        memory_type='FACT',memory_scope='AGENT_MEMORY',classification='INTERNAL',security_domain_id='domain',owner_principal_id='owner',
        reason='Explicit fixture successor'),actor='owner')
    loaded=assets.load('owner',identifiers[0]);old=state.old.agent_assets.load('owner',identifiers[0])
    assert loaded==old and loaded['source']['revision_id']!=source['revision_id']


def test_original_reference_private_imports_use_all_five_unchanged_serial_modules(relational):
    import sys
    state=relational;old=state.old
    assert old.continuity_assembly.context_selection is old.context_selection
    assert old.continuity_assembly.resolve.__module__==old.continuity_sources.__name__
    assert old.continuity_sources.resolve is not sources.resolve
    assert not hasattr(old.continuity_sources,'resolve_many')
    assert not hasattr(old.agent_assets,'load_many')
    assert not hasattr(old.memory_lifecycle,'_representation_metadata')
    assert sys.modules['lib.continuity_assembly'] is assembly
    names={name for name in sys.modules if name.startswith('_cx501_read_reference_')}
    with reference.load(state.reference) as second:
        assert second.continuity_assembly.context_selection is second.context_selection
        assert second.continuity_assembly is not old.continuity_assembly
    assert {name for name in sys.modules if name.startswith('_cx501_read_reference_')}==names


@pytest.mark.parametrize('change',['source-hash','archive-hash','wrong-product','wrong-backend','path-escape'])
def test_original_reference_refuses_changed_or_other_product_sources(relational,change):
    state=relational;value=deepcopy(state.reference)
    if change=='source-hash':value['files']['continuity_sources']['sha256']='0'*64
    elif change=='archive-hash':value['archive']['sha256']='0'*64
    elif change=='wrong-product':value['product']='oracle-enterprise'
    elif change=='wrong-backend':value['database']='oracle'
    else:value['files']['continuity_sources']['path']=str(ROOT/'../outside.py')
    with pytest.raises(ValueError):
        with reference.load(value):pytest.fail('Changed reference must be rejected before import')


def test_representation_family_and_digest_deduplication_and_ambiguous_order_use_true501(relational):
    state=relational;frozen=memories(state,3)
    for source in frozen:
        memory.create_representation(source['revision_id'],'SHORT_SUMMARY','Same bounded summary')
        memory.create_representation(source['revision_id'],'ATOMIC_FACT','Alternative cube')
    # Equal timestamps deliberately exercise the original per-version query;
    # do not invent a new tie breaker at a selection/limit boundary.
    state.db.execute("UPDATE CX_MEMORY_REPRESENTATIONS SET CREATED_AT='2026-10-21 12:00:00'")
    state.db.execute("UPDATE CX_MEMORY_REPRESENTATIONS SET CONTENT_DIGEST='same-summary' WHERE REPRESENTATION_TYPE='SHORT_SUMMARY'")
    state.db.execute('UPDATE CX_MEMORY_VERSIONS SET FAMILY_ID=? WHERE VERSION_ID=?',(frozen[0]['entity_id'],frozen[2]['revision_id']))
    state.db.commit();versions=[item['revision_id'] for item in frozen]
    for budget in (0,4,10,100):
        expected=state.old.memory_lifecycle.select_representations('owner',versions,token_budget=budget)
        state.calls.clear();actual=memory.select_representations('owner',versions,token_budget=budget)
        assert actual==expected
        assert len({row['family_id'] for row in actual})==len(actual)
        assert any('FETCH FIRST :lim ROWS ONLY' in row.get('sql','') for row in state.calls)


def test_metadata_detects_applicability_change_after_authorized_selection(relational):
    state=relational;frozen=memories(state,2)
    observations=[]
    def hook(sql,params):
        if 'SELECT VERSION_ID FROM CX_MEMORY_TIME_FACTS WHERE VERSION_ID=' in sql:
            observations.append(1)
        if len(observations)==2 and 'SELECT FAMILY_ID FROM CX_MEMORY_FAMILIES WHERE FAMILY_ID IN' in sql:
            state.hooks.remove(hook)
            state.db.execute("UPDATE CX_MEMORY_TIME_FACTS SET APPLIES_UNTIL='2000-01-01' WHERE VERSION_ID=?",(frozen[0]['revision_id'],))
    state.hooks.append(hook)
    with pytest.raises(ContinuityConflict):state.transaction(lambda tx:selection.metadata_many(tx,'owner','domain',frozen))


def test_metadata_policy_snapshot_rechecks_role_inputs_without_a_version_increment(relational):
    state=relational;frozen=memories(state,2)
    once(state,lambda sql,p:'SELECT VERSION_ID FROM CX_MEMORY_TIME_FACTS WHERE VERSION_ID=' in sql,
        lambda:state.db.execute("UPDATE CX_ROLE_TEMPLATES SET PERMISSIONS_JSON='[\"workspaces.*\"]' WHERE ROLE_CODE='BULK_OWNER'"))
    with pytest.raises(PermissionError):state.transaction(lambda tx:selection.metadata_many(tx,'owner','domain',frozen))


def test_source_integrity_and_mandatory_failure_leave_no_partial_assembly(relational):
    state=relational;frozen=memories(state,2)
    for module in (state.old.continuity_assembly,assembly):
        with pytest.raises(ContinuityConflict) as failure:
            module.assemble('owner',context(mandatory_sources=frozen,token_budget=1,context_window=1000))
        assert failure.value.code=='MANDATORY_CONTEXT_EXCEEDS_BUDGET'
        assert state.db.execute('SELECT COUNT(*) FROM CX_CONTEXT_ASSEMBLIES').fetchone()[0]==0
    state.db.execute("UPDATE CX_MEMORY_VERSIONS SET BODY_TEXT='Modified without exact digest' WHERE VERSION_ID=?",(frozen[0]['revision_id'],));state.db.commit()
    with pytest.raises(Exception) as failure:assembly.assemble('owner',context(sources=frozen))
    assert failure.value.code=='INTEGRITY_ERROR'
    assert state.db.execute('SELECT COUNT(*) FROM CX_CONTEXT_ASSEMBLIES').fetchone()[0]==0


def test_bulk_locators_do_not_replace_rich_family_original_resolver(relational,caplog):
    import logging
    state=relational
    row=state.db.execute('SELECT HANDOFF_ID,REVISION_NO,CONTENT_DIGEST FROM CX_HANDOFF_REVISIONS LIMIT 1').fetchone()
    source=dict(family='HANDOFF',entity_id=row[0],revision_id=str(row[1]),content_digest=row[2])
    with caplog.at_level(logging.DEBUG,logger='lib.continuity_sources'):
        expected=state.transaction(lambda tx:state.old.continuity_sources.resolve(tx,'owner','domain',source))
        actual=state.transaction(lambda tx:sources.resolve_many(tx,'owner','domain',[source]))
    assert actual==[expected] and 'serial_fallback' in caplog.text
