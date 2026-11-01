"""Existing Gateway machine-authenticated peer routes; no foreign sessions."""
import json
from typing import Any

from fastapi import Depends,HTTPException,Request
from fastapi.responses import JSONResponse,StreamingResponse

from . import model_coordinator as coordinator,model_coordinator_common as common,model_dispatch
from . import model_coordinator_origin as origin
from . import model_coordinator_observations as observations
from .continuity_contracts import Contract,Identifier
from .continuity_state import ContinuityError
from .model_coordinator_contracts import CoordinatorBinding,CoordinatorRoute,OriginEnvelope,ReceiptReconciliation
from .model_results import ModelResultError


def install(app,*,schema_owner_context,require_action):
    from .edition_features import MODEL_RUNTIME_CONTEXT_ENABLED
    if not MODEL_RUNTIME_CONTEXT_ENABLED:return

    def token(request):
        value=request.headers.get('Authorization','')
        if not value.startswith('Bearer cxgw_'):raise HTTPException(401,detail='An enrolled Gateway machine credential is required')
        return value[7:]

    def failure(exc):
        observation=getattr(exc,'coordinator_observation',None)
        headers={observations.HEADER:observations.encode(observation)} if observation else {}
        if isinstance(exc,model_dispatch.ModelNotDispatched):
            return JSONResponse({'code':exc.code},status_code=409,headers={'X-Chuanxu-Coordinator-No-Send':'1'})
        if isinstance(exc,ModelResultError) and exc.request_complete:
            return JSONResponse({'code':exc.code},status_code=502,headers={**headers,'X-Chuanxu-Coordinator-Request-Complete':'1'})
        if isinstance(exc,PermissionError):return JSONResponse({'code':'COORDINATOR_AUTHORIZATION_DENIED'},status_code=403)
        if isinstance(exc,(ValueError,ContinuityError)):return JSONResponse({'code':'COORDINATOR_REQUEST_REJECTED'},status_code=409,headers=headers)
        return JSONResponse({'code':'COORDINATOR_STATE_UNAVAILABLE'},status_code=503)

    @app.post('/api/model-gateway/coordinator-bindings')
    def binding(body:CoordinatorBinding,session=Depends(require_action('platform.manage'))):
        try:
            with schema_owner_context():return common.register_binding(str(session['principal_id']),body)
        except Exception as exc:return failure(exc)

    @app.post('/api/model-gateway/coordinator-routes')
    def route(body:CoordinatorRoute,session=Depends(require_action('platform.manage'))):
        try:
            with schema_owner_context():return common.register_route(str(session['principal_id']),body)
        except Exception as exc:return failure(exc)

    @app.get('/api/model-gateway/origin-requests/{receipt_id}')
    def origin_request(receipt_id:Identifier,session=Depends(require_action('workspaces.read'))):
        try:
            with schema_owner_context():return origin.read_receipt(str(session['principal_id']),receipt_id)
        except Exception as exc:return failure(exc)

    @app.post('/api/model-gateway/origin-requests/{receipt_id}/reconcile')
    def reconcile_origin(receipt_id:Identifier,body:ReceiptReconciliation,session=Depends(require_action('agents.operate'))):
        try:
            with schema_owner_context():return origin.reconcile_receipt(str(session['principal_id']),receipt_id,body)
        except Exception as exc:return failure(exc)

    @app.post('/api/model-gateway/coordinator/{binding_id}/reservations')
    def reserve(binding_id:Identifier,body:OriginEnvelope,request:Request):
        raw=token(request)
        try:
            with schema_owner_context():return coordinator.reserve(raw,binding_id,body)
        except Exception as exc:return failure(exc)

    @app.get('/api/model-gateway/coordinator/{binding_id}/requests/{request_id}')
    def observe(binding_id:Identifier,request_id:Identifier,request:Request):
        raw=token(request)
        try:
            with schema_owner_context():return coordinator.read_request(raw,binding_id,request_id)
        except Exception as exc:return failure(exc)

    @app.post('/api/model-gateway/coordinator/{binding_id}/requests/{request_id}/cancel')
    def cancel(binding_id:Identifier,request_id:Identifier,body:Contract,request:Request):
        raw=token(request)
        try:
            with schema_owner_context():return coordinator.cancel_reservation(raw,binding_id,request_id)
        except Exception as exc:return failure(exc)

    @app.post('/api/model-gateway/coordinator/{binding_id}/chat/completions')
    def complete(binding_id:Identifier,body:dict[str,Any],request:Request):
        raw=token(request)
        try:
            with schema_owner_context():value=coordinator.complete(raw,binding_id,request.headers.get('X-Chuanxu-Coordinator-Proof',''),body)
            observation=value.get('chuanxu_observation')
            headers={observations.HEADER:observations.encode(observation)} if observation else {}
            if body.get('stream'):
                def events():
                    # Native/Gateway behavior already validates and inspects
                    # the full stream before exposing safe content.
                    message=value['choices'][0]['message']
                    for event in (dict(model=value['model'],choices=[dict(index=0,delta={'content':message['content']},finish_reason=None)]),
                                  dict(model=value['model'],choices=[dict(index=0,delta={},finish_reason='stop')]),
                                  dict(model=value['model'],choices=[],usage=value['usage'])):
                        yield ('data: '+json.dumps(event,ensure_ascii=False)+'\n\n').encode()
                    yield b'data: [DONE]\n\n'
                return StreamingResponse(events(),media_type='text/event-stream',headers={**headers,'Cache-Control':'no-store'})
            return JSONResponse(value,headers=headers)
        except Exception as exc:return failure(exc)
