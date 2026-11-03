"""503 additive migration/upgrade guards; historical release contracts remain exact."""
import json
import sys

import pytest

from .test_v502_delivery import ROOT, deploy, generator
import build
import migration_runner as runner
import live_db_validator as validator
from product_delivery import acceptance_targets
from lib import task_step_timestamps


@pytest.mark.parametrize('database', ('pg', 'oracle', 'yashandb'))
def test_task_step_times_are_additive_nullable_and_required(database, tmp_path):
    name, sql, facts = generator().render(database, 117)
    assert (deploy(database) / name).read_text() == sql
    assert json.loads((deploy(database) / name).with_suffix('.schema.json').read_text()) == facts
    assert not facts['historical_backfill'] and facts['grants'] == 'UNCHANGED'
    assert all(value == dict(type='TIMESTAMP', nullable=True, default=None) for value in facts['columns'].values())
    assert not any(word in sql.upper() for word in ('UPDATE TASK_STEPS', 'DROP ', 'GRANT ', 'REVOKE '))
    for edition in ('community', 'enterprise'):
        scripts = list(deploy(database).glob('*.sql'))
        assert validator.validate_v503_static_contract(database, scripts, edition)['passed']
        assert not validator.validate_v503_static_contract(database, [p for p in scripts if p.name != name], edition)['passed']
    # A terminal ledger entry alone cannot accept the wrong native schema.
    class Cursor:
        def execute(self, sql): pass
        def fetchall(self): return []
    assert not runner._step_objects_complete(Cursor(), database, deploy(database) / name)
    import shutil
    target = tmp_path / database
    shutil.copytree(deploy(database), target)
    build.generate_deployment_baseline(target, '5.0.3', database)
    assert json.loads((target / 'baseline_v5_0_3.json').read_text())['required_terminal_migration'] == validator.v503_runtime_migration_scripts(database)[-1]
    (target / name).write_text(sql + '\n-- changed\n')
    with pytest.raises(ValueError, match='Task Step timestamps'):
        build.generate_deployment_baseline(target, '5.0.3', database)


@pytest.mark.parametrize('database', ('pg', 'oracle', 'yashandb'))
@pytest.mark.parametrize('fault', (None, 'missing', 'type', 'nullable', 'default', 'duplicate'))
def test_task_step_native_check_rejects_false_historical_timestamps(database, fault):
    data_type = 'timestamp without time zone' if database == 'pg' else 'TIMESTAMP(6)'
    rows = [[name, data_type, 'YES' if database == 'pg' else 'Y', None] for name in task_step_timestamps.COLUMNS]
    if fault == 'missing': rows.pop()
    if fault == 'type': rows[0][1] = 'DATE'
    if fault == 'nullable': rows[0][2] = 'NO'
    if fault == 'default': rows[0][3] = 'CURRENT_TIMESTAMP'
    if fault == 'duplicate': rows.append(list(rows[0]))
    class Cursor:
        def execute(self, sql):
            assert 'task_steps' in sql.lower()
        def fetchall(self): return rows
    assert bool(task_step_timestamps.errors(Cursor(), database)) == bool(fault)


@pytest.mark.parametrize('database',('oracle','pg','yashandb'))
def test_intake_migration_is_generated_and_complete(database):
    name,sql,facts=generator().render(database,111)
    assert (deploy(database)/name).read_text()==sql
    assert json.loads((deploy(database)/name).with_suffix('.schema.json').read_text())==facts
    assert set(facts)=={'CX_KNOWLEDGE_INTAKE'}
    assert validator.validate_v502_schema_manifest(facts)==[]
    for edition in ('community','enterprise'):
        scripts=list(deploy(database).glob('*.sql'))
        assert validator.validate_v503_static_contract(database,scripts,edition)['passed']
        if name in validator.v503_runtime_migration_scripts(database):
            assert not validator.validate_v503_static_contract(database,[p for p in scripts if p.name!=name],edition)['passed']


@pytest.mark.parametrize('database',('oracle','pg','yashandb'))
@pytest.mark.parametrize('number',(112,113,114))
def test_native_write_guards_are_generated_and_required_for_all_products(database,number):
    name,sql,facts=generator().render(database,number)
    assert (deploy(database)/name).read_text()==sql
    assert json.loads((deploy(database)/name).with_suffix('.schema.json').read_text())==facts
    assert {guard['table'] for guard in facts['guards']}=={'ENTITIES','KNOWLEDGE_META','CX_KNOWLEDGE_ACCESS_POLICIES'}
    for edition in ('community','enterprise'):
        scripts=list(deploy(database).glob('*.sql'))
        assert validator.validate_v503_static_contract(database,scripts,edition)['passed']
        if name in validator.v503_runtime_migration_scripts(database):
            assert not validator.validate_v503_static_contract(database,[p for p in scripts if p.name!=name],edition)['passed']


@pytest.mark.parametrize('number',(112,113,114))
def test_oracle_clob_body_changes_cannot_escape_the_native_guard(number):
    _,sql,facts=generator().render('oracle',number)
    entity=next(item for item in facts['guards'] if item['table']=='ENTITIES')
    # UPDATE OF CONTENT is illegal for a CLOB; dropping just CONTENT from that
    # list is also unsafe. The executable trigger must cover all updates.
    assert 'BEFORE INSERT OR DELETE OR UPDATE ON ENTITIES FOR EACH ROW' in sql
    assert entity['columns']==[]
    assert 'UPDATING OR DELETING' in entity['body']
    assert "a.FAMILY='KNOWLEDGE'" in entity['body']


@pytest.mark.parametrize('database',('oracle','pg','yashandb'))
def test_legacy_shared_boundary_is_additive_and_preserves_old_contracts(database):
    _,old,old_facts=generator().render(database,113)
    _,current,facts=generator().render(database,114)
    assert current!=old
    meta=next(row['body'] for row in facts['guards'] if row['table']=='KNOWLEDGE_META')
    assert 'CX_KNOWLEDGE_ACCESS_POLICIES' in meta.upper()
    assert 'VISIBILITY' in meta.upper()
    assert 'PRINCIPAL_PRIVATE' in meta.upper()
    assert 'CX_CONTINUITY_ARTIFACT_REVS' in meta.upper()
    old_meta=next(row['body'] for row in old_facts['guards'] if row['table']=='KNOWLEDGE_META')
    assert 'CX_KNOWLEDGE_ACCESS_POLICIES' not in old_meta.upper()
    if database=='pg':
        assert 'SESSION_USER<>CURRENT_USER' in meta
    elif database=='oracle':
        assert 'ORA_END_USER_CONTEXT.username' in meta
    else:
        assert "SYS_CONTEXT('USERENV','SESSION_USER')" in meta


@pytest.mark.parametrize('target',acceptance_targets(),ids=lambda item:item['key'])
def test_all_seven_targets_select_complete_stable_chain_and_additive_intake(monkeypatch,tmp_path,target):
    def absent(_): raise ValueError('No native database in unit selector test')
    monkeypatch.setattr(runner,'_load_database_config',absent)
    database=target['database']
    names=runner.release_script_names('5.0.3',database,tmp_path/'absent.json',target['edition'].lower())
    tail=[*validator.v502_native_migration_scripts(database),*validator.v503_runtime_migration_scripts(database)]
    assert names[-len(tail):]==tail
    assert len(names)==len(set(names))
    assert build.deployment_terminal('5.0.3',database)==tail[-1]


@pytest.mark.parametrize('problem',('missing','failed','checksum','objects'))
@pytest.mark.parametrize('bad_step',validator.v502_native_migration_scripts('pg'))
def test_every_native_stable_step_is_required_on_declared_upgrade(monkeypatch,bad_step,problem):
    def row(_cursor,_database,path,*,version):
        assert version=='5.0.2'
        if path.name==bad_step and problem=='missing': return None
        return {'status':'FAILED' if path.name==bad_step and problem=='failed' else 'APPLIED',
                'checksum':'changed' if path.name==bad_step and problem=='checksum' else runner._checksum(path)}
    monkeypatch.setattr(runner,'_step_row',row)
    monkeypatch.setattr(runner,'_step_objects_complete',lambda _c,_d,path,**_kw:not(path.name==bad_step and problem=='objects'))
    scripts=[deploy('pg')/name for name in validator.v502_native_migration_scripts('pg')]
    result=runner._v503_predecessor_contract(None,'pg',scripts)
    assert not result['passed']
    assert not result['steps'][bad_step]['passed']


@pytest.mark.parametrize('target',acceptance_targets(),ids=lambda item:item['key'])
def test_declared_upgrade_selects_only_new_steps_without_historical_replay(monkeypatch,tmp_path,target):
    monkeypatch.setattr(runner,'_load_database_config',lambda *_:pytest.fail('No legacy schema probe on declared upgrade'))
    names=runner.release_script_names('5.0.3',target['database'],tmp_path/'config.json',
        target['edition'].lower(),from_version='5.0.2')
    assert names==list(validator.v503_runtime_migration_scripts(target['database']))


@pytest.mark.parametrize('database',('pg','oracle','yashandb'))
def test_incremental_plan_still_checks_all_sibling_predecessor_files(monkeypatch,database):
    seen=[]
    def row(_cursor,_database,path,*,version):
        assert version=='5.0.2'
        seen.append(path.name)
        return {'status':'APPLIED','checksum':runner._checksum(path)}
    monkeypatch.setattr(runner,'_step_row',row)
    monkeypatch.setattr(runner,'_step_objects_complete',lambda *_args,**_kw:True)
    scripts=[deploy(database)/name for name in validator.v503_runtime_migration_scripts(database)]
    result=runner._v503_predecessor_contract(None,database,scripts)
    assert result['passed']
    assert seen==list(validator.v502_native_migration_scripts(database))


def test_yashandb_lob_successor_is_generated_and_protects_content_without_update_of():
    name,sql,facts=generator().render('yashandb',115)
    assert (deploy('yashandb')/name).read_text()==sql
    assert json.loads((deploy('yashandb')/name).with_suffix('.schema.json').read_text())==facts
    assert 'BEFORE INSERT OR DELETE OR UPDATE ON ENTITIES FOR EACH ROW' in sql
    assert all(not guard['columns'] for guard in facts['guards'])
    for edition in ('community','enterprise'):
        scripts=list(deploy('yashandb').glob('*.sql'))
        assert validator.validate_v503_static_contract('yashandb',scripts,edition)['passed']
        assert not validator.validate_v503_static_contract('yashandb',[p for p in scripts if p.name!=name],edition)['passed']


def test_yashandb_body_search_is_additive_and_required_on_both_editions():
    name,sql,facts=generator().render('yashandb',116)
    assert (deploy('yashandb')/name).read_text()==sql
    assert json.loads((deploy('yashandb')/name).with_suffix('.schema.json').read_text())==facts
    assert facts['columns']==['CONTENT'] and facts['existing_title_index']=='PRESERVED'
    for edition in ('community','enterprise'):
        scripts=list(deploy('yashandb').glob('*.sql'))
        assert validator.validate_v503_static_contract('yashandb',scripts,edition)['passed']
        assert not validator.validate_v503_static_contract('yashandb',[p for p in scripts if p.name!=name],edition)['passed']


@pytest.mark.parametrize('status',('APPLIED','FAILED','RUNNING','MISSING'))
def test_v503_handoff_successor_uses_nearest_present_checksum_bound_receipt(monkeypatch,status):
    path=deploy('yashandb')/'94_v4_4_15_handoff_policy.sql'
    seen=[]
    def row(_cursor,_database,_path,*,version):
        seen.append(version)
        if version=='5.0.3':
            return None if status=='MISSING' else {'status':status,'checksum':runner._checksum(path)}
        return {'status':'APPLIED','checksum':runner._checksum(path)}
    monkeypatch.setattr(runner,'_step_row',row)
    assert runner._handoff_policy_applied(None,'yashandb',path,version='5.0.3')==(status in {'APPLIED','MISSING'})
    assert seen==(['5.0.3','5.0.2'] if status=='MISSING' else ['5.0.3'])


def test_native_identity_mismatch_blocks_before_preflight_and_mutation(monkeypatch,tmp_path,capsys):
    class Cursor:
        def __enter__(self):return self
        def __exit__(self,*_):pass
        def execute(self,sql):assert "CON_NAME" in sql
        def fetchone(self):return ('AI_AGENT',)
    class Connection:
        def cursor(self):return Cursor()
        def close(self):pass
    monkeypatch.setattr(sys,'argv',['migration_runner.py','--database','yashandb','--version','5.0.3',
        '--from-version','5.0.2','--yashandb-config',str(tmp_path/'config.json'),
        '--expected-database-name','cxv503devent','--confirm-database-backup'])
    monkeypatch.setattr(runner,'_load_database_config',lambda *_:{})
    monkeypatch.setattr(runner,'_connect_for_preflight',lambda *_:Connection())
    monkeypatch.setattr(runner,'_preflight',lambda *_:pytest.fail('Identity mismatch must stop before preflight'))
    monkeypatch.setattr(runner,'_apply_yashandb',lambda *_:pytest.fail('Identity mismatch must block DDL'))
    assert runner.main()==1
    result=json.loads(capsys.readouterr().out)
    assert not result['passed'] and result['results'][0]['error_type']=='ValueError'
