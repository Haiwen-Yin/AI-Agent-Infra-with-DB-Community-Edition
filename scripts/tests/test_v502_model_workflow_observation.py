"""Authorized read-only workflow observation on the relational SQLite harness.

No native database or model endpoint is contacted by these tests.
"""
import json

import pytest

from lib import governed_model_turns as turns,continuity_retrospectives as retros,model_output_contracts as contracts
from lib import continuity_bindings as bindings,provider_capability_probes as probes,native_runtime
from lib.agent_extension_contracts import validate_schema
from lib.continuity_state import ContinuityError
from .test_v502_governed_model_turns import (governed,runtime,candidate_db,fixture,database,http,new_turn,evidence,TOKEN,TRANSPORT)


@pytest.fixture
def observed(governed,monkeypatch):
    db,source=governed
    turn,registered,_=new_turn(governed)
    # A current Human owner is also an explicit participant in this exact
    # synthetic Handoff source; domain membership alone would not suffice.
    db.execute('ALTER TABLE CX_AGENT_RELATIONSHIPS ADD COLUMN RELATIONSHIP_ID TEXT')
    db.execute("INSERT INTO CX_AGENT_RELATIONSHIPS VALUES('owner','reader','PRIMARY_OWNER','ACTIVE',NULL,'human-owner')")
    db.execute("UPDATE CX_HANDOFFS SET TO_PRINCIPAL_ID='reader'")
    db.commit()
    monkeypatch.setattr(native_runtime,'_call_llm',lambda *args,**kwargs:pytest.fail('Read must not send a model request'))
    return db,turn,registered,source


def test_human_observer_reads_only_authorized_summary_and_answer_without_agent_transport(observed):
    db,turn,_,_=observed
    db.execute("UPDATE CX_MODEL_TOOL_TURNS SET STATUS='SUCCEEDED',ANSWER_CIPHER=:answer,ANSWER_DIGEST=:digest",
        dict(answer=json.dumps({'answer':'Verified synthetic answer'}),digest=turns.digest('Verified synthetic answer')))
    db.commit()
    assert bindings._transport.get() is None
    value=turns.read_turn('reader',turn)
    assert value['observer_only'] is True and value['answer']=='Verified synthetic answer'
    assert value['task_id']=='501' and len(value['stages'])==2
    assert not any(key in json.dumps(value) for key in (TOKEN,'token_digest','question_cipher','fencing_token'))
    assert bindings._transport.get() is None
    listing=turns.list_turns('reader','domain')
    assert listing['items'][0]['turn_id']==turn and 'answer' not in listing['items'][0]
    assert turns.list_registrations('reader','domain')['items'][0]['source']['content_digest']
    assert db.execute('SELECT COUNT(*) FROM EXECUTION_JOBS').fetchone()[0]==0


@pytest.mark.parametrize('change',[
    "UPDATE CX_PRINCIPALS SET STATUS='REVOKED' WHERE PRINCIPAL_ID='reader'",
    "UPDATE CX_PRINCIPALS SET STATUS='REVOKED' WHERE PRINCIPAL_ID='owner'",
    "UPDATE CX_PRINCIPALS SET PRINCIPAL_TYPE='AGENT' WHERE PRINCIPAL_ID='reader'",
    "UPDATE CX_DOMAIN_MEMBERS SET STATUS='REVOKED' WHERE PRINCIPAL_ID='reader'",
    "UPDATE CX_AGENT_RELATIONSHIPS SET STATUS='REVOKED'",
    "UPDATE CX_HANDOFFS SET TO_PRINCIPAL_ID='agent'",
    "UPDATE CX_AGENT_ACCESS_TOKENS SET REVOKED_AT=CURRENT_TIMESTAMP",
    "UPDATE CX_AGENT_ACCESS_TOKENS SET SCOPE_JSON='[\"workspaces.read\"]'",
    "UPDATE CX_AGENT_INSTANCES SET FENCING_TOKEN=2",
    "UPDATE CX_LLM_PROVIDER_PROFILES SET VERSION=2",
    "UPDATE CX_PORTAL_KNOWLEDGE_POLICY SET VERSION=2",
    "UPDATE TOOL_REGISTRY SET TOOL_VERSION='2'",
    "UPDATE CX_HANDOFF_REVISIONS SET CONTENT_DIGEST='changed'",
    "UPDATE CX_ACTION_CARDS SET STATUS='REJECTED'",
])
def test_observer_rechecks_both_current_principals_and_exact_source(observed,change):
    db,turn,_,_=observed
    db.execute(change);db.commit()
    with pytest.raises((PermissionError,ContinuityError)):turns.read_turn('reader',turn)


def test_observer_cannot_restore_or_use_an_agent_transport_or_resume_mutations(observed):
    _,turn,registered,_=observed
    with bindings.authenticated_transport(TRANSPORT):
        with pytest.raises(PermissionError):turns.read_turn('reader',turn)
    for function in (turns.run_once,turns.request_tool_approval,turns.admit_approved_tool):
        with pytest.raises(PermissionError):
            if function is turns.run_once:function('reader',turn,'human-worker')
            else:function('reader',turn)
    assert turns.list_turns('agent','domain')['items']==[]
    assert bindings._transport.get() is None


def test_directories_are_bounded_domain_scoped_and_recheck_each_entry(observed):
    db,turn,registered,_=observed
    with pytest.raises(PermissionError):turns.list_turns('reader','other-domain')
    with pytest.raises(ValueError):turns.list_registrations('reader','domain',limit=101)
    db.execute("UPDATE CX_HANDOFFS SET TO_PRINCIPAL_ID='agent'");db.commit()
    assert turns.list_turns('reader','domain')['items']==[]
    assert turns.list_registrations('reader','domain')['items']==[]


@pytest.mark.parametrize('family',['MEMORY','KNOWLEDGE','EXPERIENCE','SKILL'])
def test_exact_retrospective_directory_has_valid_synthetic_example_and_only_current_matching_probe(governed,monkeypatch,family):
    db,_=governed
    monkeypatch.setattr(probes,'_profile',lambda *args:dict(profile_id='model',version=1,model_id='test-model'))
    monkeypatch.setattr(native_runtime,'_call_llm',lambda *args,**kwargs:pytest.fail('Directory must not probe'))
    evidence(db,'exact-schema',retros._schema(family),capability='STRUCTURED_OUTPUT')
    evidence(db,'generic-schema',probes.PROBE_SCHEMA,capability='STRUCTURED_OUTPUT')
    for name,column,value in [('expired','EXPIRES_AT','2000-01-01'),('old-profile','PROFILE_VERSION',2),
                              ('other-model','MODEL_ID','other'),('other-parameters','PARAMETER_DIGEST','0'*64)]:
        evidence(db,name,retros._schema(family),capability='STRUCTURED_OUTPUT')
        db.execute(f'UPDATE CX_PROVIDER_CAP_PROBES SET {column}=:value WHERE PROBE_ID=:probe',dict(value=value,probe=name))
    db.commit()
    value=retros.output_directory('owner','model',family)
    validate_schema(value['output_schema'],value['example'])
    assert [item['probe_id'] for item in value['items']]==['exact-schema']
    assert value['schema_digest']==contracts.schema_digest(retros._schema(family))
    assert db.execute('SELECT COUNT(*) FROM CX_RETROSPECTIVE_JOBS').fetchone()[0]==0


def test_previous_runtime_refuses_new_read_directories(governed,monkeypatch):
    from lib import edition_features
    monkeypatch.setattr(edition_features,'MODEL_RUNTIME_CONTEXT_ENABLED',False)
    for operation in (lambda:turns.list_turns('owner','domain'),lambda:retros.output_directory('owner','model','MEMORY')):
        with pytest.raises(ValueError):operation()


def test_directory_keyset_reaches_following_turn_without_duplicates(governed):
    first,_,request=new_turn(governed)
    with bindings.authenticated_transport(TRANSPORT):
        second=turns.create_turn('owner',{**request,'idempotency_key':'second-turn'})['turn_id']
        page=turns.list_turns('owner','domain',limit=1)
        following=turns.list_turns('owner','domain',limit=1,after=page['next_after'])
    assert {page['items'][0]['turn_id'],following['items'][0]['turn_id']}=={first,second}
    assert following['next_after'] is None


def test_new_http_read_directories_require_existing_action_guard_and_never_send(http,governed,monkeypatch):
    client,headers=http
    new_turn(governed)
    monkeypatch.setattr(probes,'_profile',lambda *args:dict(profile_id='model',version=1,model_id='test-model'))
    monkeypatch.setattr(native_runtime,'_call_llm',lambda *args,**kwargs:pytest.fail('GET must never dispatch'))
    paths=['/api/extensions/model-tool-turns?security_domain_id=domain',
        '/api/extensions/model-read-tools?security_domain_id=domain',
        '/api/extensions/retrospective-output-contracts/model?target_family=MEMORY']
    for path in paths:
        assert client.get(path).status_code==401
        assert client.get(path,headers={**headers,'x-permission':'other'}).status_code==403
        response=client.get(path,headers=headers)
        assert response.status_code==200
        assert TOKEN not in response.text and 'token_digest' not in response.text
    assert client.get(paths[0]+'&limit=101',headers=headers).status_code==422
