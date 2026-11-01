"""Dashboard Session/CSRF routes for explicit observed-answer Human reviews."""
from contextlib import nullcontext

from fastapi import APIRouter, Depends, HTTPException

from . import observed_answer_review as service, model_credentials
from .continuity_state import ContinuityConflict


def install(app, require_action, schema_owner_context=nullcontext):
    if not service.schema_enabled():
        return
    router = APIRouter(prefix='/api/observed-answer-reviews')

    def invoke(operation, session, *args):
        try:
            with schema_owner_context(), model_credentials.server_session(session):
                return operation(str(session['principal_id']), *args)
        except ContinuityConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.post('/sets')
    def register(body: service.Registration, session=Depends(require_action('platform.manage'))):
        return invoke(service.register, session, body)

    @router.get('/sets/{set_id}')
    def read(set_id: service.Identifier, session=Depends(require_action('platform.manage'))):
        return invoke(service.read_set, session, set_id)

    @router.post('/sets/{set_id}/outputs/{key}/reviews')
    def review(set_id: service.Identifier, key: service.Identifier, body: service.Decision,
               session=Depends(require_action('platform.manage'))):
        return invoke(service.review, session, set_id, key, body)

    @router.get('/sets/{set_id}/export')
    def export(set_id: service.Identifier, session=Depends(require_action('platform.manage'))):
        return invoke(service.export, session, set_id)

    app.include_router(router)
