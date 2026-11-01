"""Explicit authenticated HTTP actions for exact contracts and governed turns."""
from typing import Any

from fastapi import Depends,Query
from pydantic import Field,field_validator

from .continuity_contracts import Contract,Identifier
from .agent_extension_contracts import bounded_json,validate_schema
from . import governed_model_turns as turns,model_output_contracts as contracts


class ExactProbeBody(Contract):
    output_schema: dict[str,Any]
    example: dict[str,Any]
    tool_name: str | None = Field(default=None,min_length=1,max_length=64,pattern=r'^[A-Za-z0-9][A-Za-z0-9_.:-]*$')

    @field_validator('output_schema')
    @classmethod
    def schema_is_bounded(cls,value):
        validate_schema(value,check_value=False)
        return value

    @field_validator('example')
    @classmethod
    def example_is_bounded(cls,value):
        return bounded_json(value,maximum=65536)


class RegisterReadBody(turns.ReadToolRegistration):
    action_id: Identifier


def install(router,prefix,invoke,require_action):
    """The parent supplies its existing session/CSRF and Agent-scope guards."""
    from .edition_features import MODEL_RUNTIME_CONTEXT_ENABLED
    if not MODEL_RUNTIME_CONTEXT_ENABLED:
        return

    @router.get(prefix+'/retrospective-output-contracts/{profile_id}')
    def retrospective_contract(profile_id:Identifier,target_family:str,session=Depends(require_action('platform.manage'))):
        from .continuity_retrospectives import output_directory
        return invoke(output_directory,session,profile_id,target_family)

    @router.post(prefix+'/model-output-contracts/{profile_id}/probes')
    def exact_probe(profile_id:Identifier,body:ExactProbeBody,session=Depends(require_action('agents.operate'))):
        return invoke(contracts.probe_exact,session,profile_id,body.output_schema,body.example,tool_name=body.tool_name)

    @router.post(prefix+'/model-read-tools/approval-requests')
    def registration_approval(body:turns.ReadToolRegistration,session=Depends(require_action('tools.write'))):
        return invoke(turns.request_registration,session,body)

    @router.get(prefix+'/model-read-tools')
    def registrations(security_domain_id:Identifier,after:str='',limit:int=Query(20,ge=1,le=100),session=Depends(require_action('tools.read'))):
        return invoke(turns.list_registrations,session,security_domain_id,after=after,limit=limit)

    @router.post(prefix+'/model-read-tools')
    def registration(body:RegisterReadBody,session=Depends(require_action('tools.write'))):
        return invoke(turns.register_read_tool,session,body.model_dump(mode='json',exclude={'action_id'}),body.action_id)

    @router.get(prefix+'/model-read-tools/{registration_id}/contract')
    def read_contract(registration_id:Identifier,session=Depends(require_action('tools.read'))):
        return invoke(turns.read_registration,session,registration_id)

    @router.post(prefix+'/model-tool-turns')
    def create(body:turns.NewToolTurn,session=Depends(require_action('actions.propose'))):
        return invoke(turns.create_turn,session,body)

    @router.get(prefix+'/model-tool-turns')
    def turn_directory(security_domain_id:Identifier,after:str='',limit:int=Query(20,ge=1,le=100),session=Depends(require_action('workspaces.read'))):
        return invoke(turns.list_turns,session,security_domain_id,after=after,limit=limit)

    @router.get(prefix+'/model-tool-turns/{turn_id}')
    def read(turn_id:Identifier,session=Depends(require_action('workspaces.read'))):
        return invoke(turns.read_turn,session,turn_id)

    @router.post(prefix+'/model-tool-turns/{turn_id}/run')
    def run(turn_id:Identifier,body:Contract,session=Depends(require_action('actions.propose'))):
        return invoke(turns.run_once,session,turn_id,worker_id='model-tool-http-worker')

    @router.post(prefix+'/model-tool-turns/{turn_id}/approval-requests')
    def approval(turn_id:Identifier,body:turns.ToolApprovalRequest,session=Depends(require_action('actions.propose'))):
        return invoke(turns.request_tool_approval,session,turn_id,channel_id=body.channel_id)

    @router.post(prefix+'/model-tool-turns/{turn_id}/admit')
    def admit(turn_id:Identifier,body:Contract,session=Depends(require_action('actions.propose'))):
        return invoke(turns.admit_approved_tool,session,turn_id)
