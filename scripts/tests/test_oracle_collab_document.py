"""Preserve the legacy document shape while rejecting an unbound repair."""
import importlib.util
import json
from pathlib import Path

import pytest

from lib import oracle_collab_document as contract, package_layout

ROOT=Path(__file__).resolve().parents[2]


@pytest.fixture
def deployer():
    path=ROOT/'adapters/oracle/deploy_oracle.py'
    if not path.is_file():path=ROOT/'scripts/deploy_oracle.py'
    if not path.is_file():pytest.skip('Oracle deployer is not shipped in this backend product')
    spec=importlib.util.spec_from_file_location('oracle_collab_deployer',path)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize('fault',[None,'other_error','other_view','other_script','missing_repair','changed_repair','changed_manifest','changed_projection'])
def test_fresh_compatibility_never_swallows_an_unrelated_error_or_changed_contract(tmp_path,monkeypatch,fault,deployer):
    name,sql,facts=contract.render()
    (tmp_path/name).write_text(sql)
    (tmp_path/name).with_suffix('.schema.json').write_text(json.dumps(facts))
    statement=contract.VIEW_SQL.replace('CREATE OR REPLACE','CREATE',1).rstrip(';\n')
    script=tmp_path/'1_schema.sql'
    error=RuntimeError('ORA-40609: exact known foreign key projection failure')
    if fault=='other_error':error=RuntimeError('ORA-00942: missing table')
    if fault=='other_view':statement=statement.replace('VIEW COLLAB_GROUP_DV','VIEW KNOWLEDGE_DV')
    if fault=='other_script':script=tmp_path/'other.sql'
    if fault=='missing_repair':(tmp_path/name).unlink()
    if fault=='changed_repair':(tmp_path/name).write_text(sql+'-- changed')
    if fault=='changed_manifest':(tmp_path/name).with_suffix('.schema.json').write_text('{}')
    if fault=='changed_projection':statement=statement.replace("'group_id'", "'Group_ID'")
    called=[]
    monkeypatch.setattr(deployer,'execute_sql_file',lambda connection,path,**kwargs:called.append(path) or True)
    assert deployer.repair_collab_document_key(None,script,statement,error)==(fault is None)
    assert called==([tmp_path/name] if fault is None else [])


@pytest.mark.parametrize('fault',[None,'pk','key','invalid_view','missing_field','changed_json_case'])
def test_native_contract_requires_both_original_key_and_complete_view(fault):
    expected=contract.VIEW_SQL.split(' AS\n',1)[1].rstrip(';\n')
    class Cursor:
        def execute(self,sql,parameters=None):
            if 'USER_CONSTRAINTS' in sql:
                kind=parameters['kind']
                columns='MEMBER_ID' if kind=='P' else 'MEMBER_ID,GROUP_ID'
                if fault==('pk' if kind=='P' else 'key'):columns='GROUP_ID'
                self.result=[('KEY','ENABLED','VALIDATED','NOT DEFERRABLE',columns)]
            elif 'USER_OBJECTS' in sql:self.result=[('INVALID' if fault=='invalid_view' else 'VALID',)]
            else:
                text=expected
                if fault=='missing_field':text=text.replace("'group_id'      : m.GROUP_ID,",'')
                if fault=='changed_json_case':text=text.replace("'group_id'","'Group_id'")
                self.result=[(text,)]
        def fetchall(self):return self.result
    assert bool(contract.errors(Cursor()))==(fault is not None)


def test_selected_oracle_tail_preserves_historical_sql_and_other_backends():
    import live_db_validator as validator
    import migration_runner as runner
    name,sql,facts=contract.render()
    if 'oracle' not in package_layout.databases(ROOT):
        pytest.skip('Oracle deployment SQL is not shipped in this backend product')
    path=package_layout.deployment_dir(ROOT,'oracle')/name
    assert path.read_text()==sql and json.loads(path.with_suffix('.schema.json').read_text())==facts
    assert validator.v503_runtime_migration_scripts('oracle')[-1]==name
    assert name not in validator.v503_runtime_migration_scripts('pg')
    assert name not in validator.v503_runtime_migration_scripts('yashandb')
    legacy=(path.parent/'1_schema.sql').read_text()
    assert "'group_id'      : m.GROUP_ID," in legacy
    assert 'CX503_CGM_DOCUMENT_KEY' not in legacy
    assert not runner._step_objects_complete(None,'pg',path,version='5.0.3')
