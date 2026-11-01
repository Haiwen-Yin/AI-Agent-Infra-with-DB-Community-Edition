"""Exact-package native Context equivalence and current-source authority.

All queries, authorization, audit, transactions and driver calls are real. The
serial reference is the unchanged same-product final501 archive's read code.
Normal isolated domain/Agent fixtures and their immutable evidence are retained.
"""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
from time import perf_counter
from types import SimpleNamespace

import pytest

from lib import connection, identity_api, security_domain_api as domains
from lib import continuity_assembly as assembly, continuity_work as work
from lib import continuity_handoff as handoff, continuity_publications as publications
from lib import continuity_sources, context_selection
from lib import memory_lifecycle as memory,agent_assets as assets
from .test_v502_business_committed_live import business
from . import v502_serial_context_reference as serial_reference

pytestmark = pytest.mark.skipif(os.environ.get('CX_V502_NATIVE_CONTEXT_LIVE') != '1',
    reason='explicit exact classified v5.0.2 native Context acceptance required')


@pytest.fixture
def context_business(business):
    state = SimpleNamespace(**vars(business), target_domain=business.key + '_CTX')
    domains.create_domain(state.actor, state.target_domain, state.target_domain, 'INTERNAL',
                          state.reason, state.actor, state.reason)
    grant=identity_api.assign_permission_override(state.actor,state.agent,'memory.read','ALLOW','OWNED',state.reason)
    state.grants.append(grant['override_id'])
    try:
        yield state
    finally:
        domains.set_domain_status(state.actor, state.target_domain, 'REVOKED', state.reason)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(',', ':'), default=str).encode()).hexdigest()


def evidence(case, value, *, initial=False):
    directory = Path(os.environ['CX_V502_NATIVE_CONTEXT_EVIDENCE']).resolve()
    assert directory == Path(__file__).resolve().parent.parent / 'context-observations'
    directory.mkdir(mode=0o700, exist_ok=True)
    path = directory / (case + '.json')
    with path.open('x' if initial else 'w') as stream:
        path.chmod(0o600)
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2, default=str)
        stream.write('\n')


def sources(state, count, *, published=False):
    result, grants = [], []
    for index in range(count):
        key = state.key + '_' + str(index)
        created = work.create_work(state.actor, dict(security_domain_id=state.domain,
            owner_principal_id=state.actor, reason=state.reason, idempotency_key=key + '_WORK',
            content=dict(objective='原生上下文固定任务 ' + str(index), constraints=['Preserve exact source authority.'],
                criteria=[dict(criterion_id='one', description='Exact evidence', verification='Native database reads')])))
        offered = handoff.offer(state.actor, created['work_contract_id'], dict(expected_work_version=1,
            recipient_principal_id=state.agent, kind='HUMAN_TO_AGENT',
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1), reason=state.reason,
            idempotency_key=key + '_HANDOFF', content=dict(summary='固定上下文来源 ' + str(index),
                next_actions=[dict(action_id='one', description='Read exact approved input ' + str(index),
                    responsible_principal_id=state.agent, acceptance='No source substitution.',
                    prerequisites=['Keep original revision and digest.'])])))
        record = handoff.read_handoff(state.actor, offered['handoff_id'])
        source = dict(family='HANDOFF', entity_id=offered['handoff_id'],
                      revision_id=str(record['revision_no']), content_digest=record['content_digest'])
        result.append(source)
        if published:
            grant = publish(state, source, key + '_PUB')
            grants.append(grant['publication_id'])
    return result, grants


def memory_sources(state,count):
    frozen=[]
    for index in range(count):
        item=memory.create_family(dict(title='原生固定方块事实 '+str(index),
            content='The approved isolated sample '+str(index)+' contains exactly 23 blue cubes.',
            memory_type='FACT',memory_scope='AGENT_MEMORY',classification='INTERNAL',
            security_domain_id=state.domain,owner_principal_id=state.agent,reason=state.reason),actor=state.actor)
        row=connection.execute_query_one('SELECT CONTENT_DIGEST FROM CX_MEMORY_VERSIONS WHERE VERSION_ID=:version',
            {'version':item['version_id']})
        frozen.append(dict(family='MEMORY',entity_id=item['family_id'],revision_id=item['version_id'],content_digest=row['content_digest']))
    return frozen


def original_reference():
    return serial_reference.load(json.loads(os.environ['CX_V502_ORIGINAL501_READ_REFERENCE']))


def publish(state, source, key):
    return publications.publish(state.actor, dict(source=source,
        target_security_domain_id=state.target_domain, purpose=state.reason, classification='INTERNAL',
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1), reason=state.reason, idempotency_key=key))


def request(state, frozen_sources, key, *, published=False):
    value = dict(request_id=state.key + '_REQUEST',
        security_domain_id=state.target_domain if published else state.domain,
        purpose=state.reason, sources=frozen_sources, token_budget=131072,
        byte_budget=1048576, entry_limit=100, ttl_seconds=3600, idempotency_key=state.key + '_' + key)
    # Planned metadata selection preserves its established same-domain scope.
    # Explicit cross-domain publications use the existing exact-source path.
    if not published:
        value['context_window'] = 131072
    return value


@contextmanager
def driver_observations(monkeypatch):
    """Observe DB-API execute/executemany without changing SQL or bindings."""
    calls = []
    original = connection.get_connection_for_agent

    def sql_text(raw, sql):
        # psycopg2.execute_values renders its real multi-row statement as
        # bytes. Decode only the observation; forward the original object.
        if isinstance(sql, (bytes, bytearray, memoryview)):
            encoding = getattr(getattr(raw, 'connection', None), 'encoding', None) or 'utf-8'
            if encoding == 'SQL_ASCII':
                encoding = 'ascii'
            else:
                from codecs import lookup
                try:
                    lookup(encoding)
                except LookupError:
                    # PostgreSQL uses some names absent from Python's aliases.
                    # This branch is reached only for a driver-encoded SQL value.
                    from psycopg2.extensions import encodings
                    encoding = encodings[encoding]
            sql = bytes(sql).decode(encoding, errors='backslashreplace')
        return ' '.join(sql.split())

    class Cursor:
        def __init__(self, raw): self.raw = raw
        def __getattribute__(self, name):
            if name == 'executemany':
                raw = object.__getattribute__(self, 'raw')
                if not callable(getattr(raw, name, None)):
                    return getattr(raw, name)
            return object.__getattribute__(self, name)
        def __getattr__(self, name): return getattr(self.raw, name)
        def __enter__(self): self.raw.__enter__(); return self
        def __exit__(self, *args): return self.raw.__exit__(*args)
        def execute(self, sql, *args, **kwargs):
            bindings=args[0] if args else kwargs.get('parameters',kwargs.get('vars'))
            observed = dict(method='execute', sql=sql_text(self.raw, sql), rows=1,
                bind_count=len(bindings) if isinstance(bindings,(dict,list,tuple)) else 0)
            calls.append(observed)
            result = self.raw.execute(sql, *args, **kwargs)
            affected = getattr(self.raw, 'rowcount', None)
            if type(affected) is int and affected >= 0:
                observed['affected_rows'] = affected
            return result
        def executemany(self, sql, values, *args, **kwargs):
            calls.append(dict(method='executemany', sql=sql_text(self.raw, sql), rows=len(values),
                bind_count=max((len(row) for row in values),default=0)))
            return self.raw.executemany(sql, values, *args, **kwargs)

    class Session:
        def __init__(self, raw): self.raw = raw
        def __getattr__(self, name): return getattr(self.raw, name)
        def cursor(self, *args, **kwargs): return Cursor(self.raw.cursor(*args, **kwargs))

    @contextmanager
    def observed(*args, **kwargs):
        with original(*args, **kwargs) as session:
            yield Session(session)

    with monkeypatch.context() as patch:
        patch.setattr(connection, 'get_connection_for_agent', observed)
        yield calls


def stable(record):
    result = {name:record[name] for name in ('status', 'content_digest', 'request_id', 'purpose',
        'policy_version', 'retrieval_policy', 'token_budget', 'entry_limit', 'item_count', 'text', 'token_count_method')}
    for name in ('items', 'representations'):
        result[name] = [{key:value for key,value in row.items() if key != 'assembly_id'} for row in record[name]]
    result['budget'] = {key:value for key,value in record['budget'].items() if key != 'assembly_id'}
    return result


def write_calls(calls, table, method):
    return [row for row in calls if row['method'] == method and row['sql'].startswith('INSERT INTO ' + table + '(')]


def assert_batch_write(calls, table, count):
    writes = write_calls(calls, table, 'execute') + write_calls(calls, table, 'executemany')
    assert len(writes) == 1
    if writes[0]['method'] == 'execute':
        # PG's actual optimized path is execute_values -> cursor.execute(bytes).
        # Keep that DB-API method visible and verify its actual affected rows.
        assert connection.DATABASE_DIALECT in {'pg', 'postgresql'}
        assert writes[0]['affected_rows'] == count
    else:
        assert writes[0]['rows'] == count
    return writes


def equivalence(state, monkeypatch, record_property, count, case):
    frozen, grants = memory_sources(state, count),[]
    payloads = connection.execute_transaction_callback(lambda tx:[
        continuity_sources.resolve(tx, state.actor, state.domain, source, purpose=state.reason)['text']
        for source in frozen])
    counter, count_method = context_selection.counter('')
    frozen_text = '\n\n'.join(payloads)
    frozen_tokens = sum(counter(text) for text in payloads) + (count - 1) * counter('\n\n')
    classification = Path(os.environ['CX_RELEASE_TEST_CLASSIFICATION'])
    observation = dict(schema='chuanxu-v502-native-context-observation/v1', case=case, phase='FROZEN',
        database=connection.DATABASE_DIALECT, source_domain=state.domain, target_domain=state.domain,
        actor=state.actor, sources=frozen, publication_ids=grants, source_sha256=digest(frozen),
        classification_sha256=hashlib.sha256(classification.read_bytes()).hexdigest(),
        input_bytes=len(frozen_text.encode('utf-8')), input_tokens=frozen_tokens, count_method=count_method,
        frozen_content_sha256=hashlib.sha256(frozen_text.encode('utf-8')).hexdigest(),
        count=count, token_budget=131072, context_window=131072, byte_budget=1048576,
        input_optimization='IDENTICAL_FROZEN_INPUT', provider_cache_evidence=False, model_requests=0)
    evidence(case, observation, initial=True)
    with original_reference() as old:
        observation['serial_reference']=old.identity
        with driver_observations(monkeypatch) as serial_calls:
            started = perf_counter()
            before = old.continuity_assembly.assemble(state.actor, request(state, frozen, 'SERIAL'))
            serial = old.continuity_assembly.read_assembly(state.actor, before['assembly_id'])
            serial_elapsed = perf_counter() - started
    with driver_observations(monkeypatch) as batch_calls:
        started = perf_counter()
        after = assembly.assemble(state.actor, request(state, frozen, 'BATCH'))
        batched = assembly.read_assembly(state.actor, after['assembly_id'])
        batch_elapsed = perf_counter() - started
    assert serial['item_count'] == batched['item_count'] == count
    assert serial['text'] == frozen_text
    assert before['content_digest'] == after['content_digest']
    assert before['rendered_tokens'] == after['rendered_tokens'] == frozen_tokens
    assert serial['token_count_method'] == batched['token_count_method'] == count_method
    assert stable(serial) == stable(batched)
    assert [row['entity_id'] for row in batched['items']] == [row['entity_id'] for row in frozen]
    for table in ('CX_CONTEXT_ASSEMBLY_ITEMS', 'CX_CONTEXT_REPRESENTATIONS'):
        assert len(write_calls(serial_calls, table, 'execute')) == count
        assert not write_calls(serial_calls, table, 'executemany')
        assert_batch_write(batch_calls, table, count)
    serial_reads=sum(row['sql'].startswith('SELECT ') for row in serial_calls)
    batch_reads=sum(row['sql'].startswith('SELECT ') for row in batch_calls)
    assert all(row['bind_count']<=100 for row in batch_calls)
    if count == 32:
        assert batch_reads<serial_reads and len(batch_calls)<len(serial_calls)
    assert len([row for row in batch_calls if 'FROM CX_CONTEXT_ITEM_GRANTS WHERE ASSEMBLY_ID=' in row['sql']]) == 1
    observed = connection.execute_query('SELECT ITEM_NO,PUBLICATION_ID FROM CX_CONTEXT_ITEM_GRANTS '
        'WHERE ASSEMBLY_ID=:assembly ORDER BY ITEM_NO', {'assembly':after['assembly_id']})
    assert [row['publication_id'] for row in observed] == grants
    observation.update(phase='COMPLETED', serial_assembly=before['assembly_id'], batch_assembly=after['assembly_id'],
        exact_selection_sha256=digest(stable(batched)), content_sha256=after['content_digest'],
        input_bytes=len(batched['text'].encode('utf-8')), input_tokens=after['rendered_tokens'],
        count_method=after['token_count_method'], serial_driver_calls=serial_calls, batch_driver_calls=batch_calls,
        serial_driver_call_count=len(serial_calls), batch_driver_call_count=len(batch_calls),
        serial_read_calls=serial_reads,batch_read_calls=batch_reads,
        serial_observed_seconds=serial_elapsed, batch_observed_seconds=batch_elapsed,
        performance_threshold_applied=False, driver_measurement='DBAPI_CALLS_NOT_NETWORK_PACKETS')
    evidence(case, observation)
    for name in ('source_sha256', 'exact_selection_sha256', 'input_bytes', 'input_tokens', 'count_method',
                 'serial_driver_call_count', 'batch_driver_call_count', 'serial_read_calls','batch_read_calls',
                 'serial_observed_seconds', 'batch_observed_seconds'):
        record_property(name, observation[name])


def test_native_context_1_source_exact_equivalence(context_business, monkeypatch, record_property):
    equivalence(context_business, monkeypatch, record_property, 1, 'test_native_context_1_source_exact_equivalence')


def test_native_context_8_sources_exact_equivalence(context_business, monkeypatch, record_property):
    equivalence(context_business, monkeypatch, record_property, 8, 'test_native_context_8_sources_exact_equivalence')


def test_native_context_32_sources_exact_equivalence(context_business, monkeypatch, record_property):
    equivalence(context_business, monkeypatch, record_property, 32, 'test_native_context_32_sources_exact_equivalence')


def asset_equivalence(state,monkeypatch,record_property,count,case):
    frozen=memory_sources(state,count)
    identifiers=[assets.bind(state.actor,dict(security_domain_id=state.domain,agent_id=state.agent,source=source,
        purpose=state.reason,reason=state.reason,idempotency_key=state.key+'_ASSET_'+str(index)))['binding_id']
        for index,source in enumerate(frozen)]
    observation=dict(schema='chuanxu-v502-native-context-observation/v1',case=case,phase='FROZEN',
        sources=frozen,binding_ids=identifiers,count=count,model_requests=0)
    evidence(case,observation,initial=True)
    def run(asset_module,assembly_module,key):
        directory=asset_module.list_bindings(state.actor,state.domain,state.agent,limit=100)
        built=asset_module.assemble(state.actor,identifiers,request(state,[] ,key))
        return dict(directory=directory,assembly=stable(assembly_module.read_assembly(state.actor,built['assembly_id'])))
    with original_reference() as old:
        observation['serial_reference']=old.identity
        with driver_observations(monkeypatch) as serial_calls:
            serial=run(old.agent_assets,old.continuity_assembly,'ASSET_SERIAL')
    with driver_observations(monkeypatch) as batch_calls:
        batch=run(assets,assembly,'ASSET_BATCH')
    assert all(row['bind_count']<=100 for row in batch_calls)
    assert serial==batch and batch['assembly']['item_count']==count and len(batch['directory']['items'])==count
    assert [row['entity_id'] for row in batch['assembly']['items']]==[row['entity_id'] for row in frozen]
    counts=dict(serial_read_calls=sum(row['sql'].startswith('SELECT ') for row in serial_calls),
        batch_read_calls=sum(row['sql'].startswith('SELECT ') for row in batch_calls),
        serial_driver_call_count=len(serial_calls),batch_driver_call_count=len(batch_calls))
    if count==80:
        assert counts['batch_read_calls']<counts['serial_read_calls']
        assert counts['batch_driver_call_count']<counts['serial_driver_call_count']
    observation.update(phase='COMPLETED',serial_driver_calls=serial_calls,batch_driver_calls=batch_calls,
        exact_selection_sha256=digest(batch),**counts)
    evidence(case,observation)
    for name,value in counts.items():record_property(name,value)


def test_native_context_2_assets_exact_equivalence(context_business,monkeypatch,record_property):
    asset_equivalence(context_business,monkeypatch,record_property,2,'test_native_context_2_assets_exact_equivalence')


def test_native_context_16_assets_exact_equivalence(context_business,monkeypatch,record_property):
    asset_equivalence(context_business,monkeypatch,record_property,16,'test_native_context_16_assets_exact_equivalence')


def test_native_context_80_assets_exact_equivalence(context_business,monkeypatch,record_property):
    asset_equivalence(context_business,monkeypatch,record_property,80,'test_native_context_80_assets_exact_equivalence')


def representation_equivalence(state,monkeypatch,record_property,count,case):
    frozen=memory_sources(state,count);versions=[source['revision_id'] for source in frozen]
    for index,version in enumerate(versions):
        memory.create_representation(version,'SHORT_SUMMARY','Approved cube '+str(index))
    observation=dict(schema='chuanxu-v502-native-context-observation/v1',case=case,phase='FROZEN',
        sources=frozen,count=count,model_requests=0)
    evidence(case,observation,initial=True)
    def run(module):
        representations={purpose:module.select_representations(state.actor,versions,purpose=purpose,token_budget=131072)
            for purpose in ('RUNTIME_CONTEXT','AUDIT')}
        members=connection.execute_transaction_callback(lambda tx:module._select_snapshot_members(tx,limit=count,token_budget=100000))
        return dict(representations=representations,members=members)
    with original_reference() as old:
        observation['serial_reference']=old.identity
        with driver_observations(monkeypatch) as serial_calls:serial=run(old.memory_lifecycle)
    with driver_observations(monkeypatch) as batch_calls:batch=run(memory)
    assert all(row['bind_count']<=100 for row in batch_calls)
    assert serial==batch
    assert all(len(items)==count for items in batch['representations'].values())
    assert len(batch['members'])==count
    counts=dict(serial_read_calls=sum(row['sql'].startswith('SELECT ') for row in serial_calls),
        batch_read_calls=sum(row['sql'].startswith('SELECT ') for row in batch_calls),
        serial_driver_call_count=len(serial_calls),batch_driver_call_count=len(batch_calls))
    if count==32:assert counts['batch_read_calls']<counts['serial_read_calls']
    observation.update(phase='COMPLETED',serial_driver_calls=serial_calls,batch_driver_calls=batch_calls,
        exact_selection_sha256=digest(batch),selected=batch,**counts)
    evidence(case,observation)
    for name,value in counts.items():record_property(name,value)


def test_native_context_1_representation_snapshot_exact_equivalence(context_business,monkeypatch,record_property):
    representation_equivalence(context_business,monkeypatch,record_property,1,'test_native_context_1_representation_snapshot_exact_equivalence')


def test_native_context_8_representations_snapshot_exact_equivalence(context_business,monkeypatch,record_property):
    representation_equivalence(context_business,monkeypatch,record_property,8,'test_native_context_8_representations_snapshot_exact_equivalence')


def test_native_context_32_representations_snapshot_exact_equivalence(context_business,monkeypatch,record_property):
    representation_equivalence(context_business,monkeypatch,record_property,32,'test_native_context_32_representations_snapshot_exact_equivalence')


def test_native_context_revoked_original_publication_cannot_borrow_replacement(context_business, record_property):
    state = context_business
    case = 'test_native_context_revoked_original_publication_cannot_borrow_replacement'
    frozen, grants = sources(state, 1, published=True)
    observation = dict(schema='chuanxu-v502-native-context-observation/v1', case=case, phase='FROZEN',
        sources=frozen, original_publication=grants[0], model_requests=0)
    evidence(case, observation, initial=True)
    prepared = assembly.assemble(state.actor, request(state, frozen, 'ORIGINAL', published=True))
    assert assembly.read_assembly(state.actor, prepared['assembly_id'])['item_count'] == 1
    publications.revoke(state.actor, grants[0], dict(expected_version=1,
        reason=state.reason, idempotency_key=state.key + '_REVOKE'))
    with pytest.raises(PermissionError):
        assembly.read_assembly(state.actor, prepared['assembly_id'])
    replacement = publish(state, frozen[0], state.key + '_REPLACEMENT')
    fresh = assembly.assemble(state.actor, request(state, frozen, 'FRESH', published=True))
    assert assembly.read_assembly(state.actor, fresh['assembly_id'])['item_count'] == 1
    with pytest.raises(PermissionError):
        assembly.read_assembly(state.actor, prepared['assembly_id'])
    original = connection.execute_query_one('SELECT PUBLICATION_ID FROM CX_CONTEXT_ITEM_GRANTS WHERE ASSEMBLY_ID=:assembly',
                                            {'assembly':prepared['assembly_id']})
    current = connection.execute_query_one('SELECT PUBLICATION_ID FROM CX_CONTEXT_ITEM_GRANTS WHERE ASSEMBLY_ID=:assembly',
                                           {'assembly':fresh['assembly_id']})
    assert original['publication_id'] == grants[0]
    assert current['publication_id'] == replacement['publication_id'] != grants[0]
    observation.update(phase='COMPLETED', original_assembly=prepared['assembly_id'], fresh_assembly=fresh['assembly_id'],
        replacement_publication=replacement['publication_id'], revoked_original_denied=True)
    evidence(case, observation)
    record_property('original_publication', grants[0])
    record_property('replacement_publication', replacement['publication_id'])


def test_native_context_audit_failure_rolls_back_real_item_and_grant_batches(context_business, monkeypatch, record_property):
    state = context_business
    case = 'test_native_context_audit_failure_rolls_back_real_item_and_grant_batches'
    frozen, grants = sources(state, 8, published=True)
    observation = dict(schema='chuanxu-v502-native-context-observation/v1', case=case, phase='FROZEN',
        sources=frozen, publication_ids=grants, model_requests=0)
    evidence(case, observation, initial=True)
    original_audit, attempted = identity_api._audit_tx, []

    def fail_after_real_audit(tx, principal, action, resource_type, resource, outcome, reason):
        result = original_audit(tx, principal, action, resource_type, resource, outcome, reason)
        if principal == state.actor and action == 'CONTEXT_PREPARED':
            attempted.append(resource)
            raise RuntimeError('Explicit native Context audit-boundary fault after real batch and audit writes')
        return result

    with driver_observations(monkeypatch) as calls:
        with monkeypatch.context() as patch:
            patch.setattr(identity_api, '_audit_tx', fail_after_real_audit)
            with pytest.raises(RuntimeError, match='audit-boundary fault'):
                assembly.assemble(state.actor, request(state, frozen, 'ROLLBACK', published=True))
    assert len(attempted) == 1
    for table in ('CX_CONTEXT_ASSEMBLY_ITEMS', 'CX_CONTEXT_ITEM_GRANTS'):
        assert_batch_write(calls, table, 8)
    resource = attempted[0]
    counts = {}
    for table in ('CX_CONTEXT_ASSEMBLIES', 'CX_CONTEXT_ASSEMBLY_ITEMS', 'CX_CONTEXT_ITEM_GRANTS',
                  'CX_CONTEXT_BUDGETS', 'CX_CONTEXT_REPRESENTATIONS', 'CX_CONTEXT_INPUT_USES'):
        row = connection.execute_query_one('SELECT COUNT(*) AS N FROM ' + table + ' WHERE ASSEMBLY_ID=:assembly',
                                           {'assembly':resource})
        counts[table] = int(row['n'])
    row = connection.execute_query_one('SELECT COUNT(*) AS N FROM CX_SECURITY_EVENTS '
        "WHERE ACTION_NAME='CONTEXT_PREPARED' AND RESOURCE_ID=:assembly", {'assembly':resource})
    counts['CX_SECURITY_EVENTS'] = int(row['n'])
    assert set(counts.values()) == {0}
    observation.update(phase='COMPLETED', rolled_back_assembly=resource, observed_driver_calls=calls,
                       post_rollback_counts=counts, real_audit_written_before_fault=True)
    evidence(case, observation)
    record_property('rolled_back_assembly', resource)
    record_property('post_rollback_counts', json.dumps(counts, sort_keys=True))
