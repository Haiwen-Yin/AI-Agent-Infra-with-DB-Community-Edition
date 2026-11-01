"""Explicit Human processing decisions over existing authenticated resources."""
from fastapi import Depends, Query

from . import processing_recovery as recovery
from .continuity_contracts import Contract


def install(router, prefix, invoke, require_action):
    """Keep parent session, CSRF and Agent-scope guards; gate the new schema."""
    if not recovery.schema_enabled():
        return
    root = prefix + "/processing"

    @router.get(root + "/{continuity_id}")
    def read(continuity_id: recovery.Key, after: str = "", limit: int = Query(100, ge=1, le=100),
             session=Depends(require_action("workspaces.read"))):
        return invoke(recovery.read_processing, session, continuity_id, after=after, limit=limit)

    @router.post(root + "/retries")
    def retry(body: recovery.RetryDecision, session=Depends(require_action("workspaces.write"))):
        return invoke(recovery.admit_retry, session, body)

    @router.post(root + "/blocks/{block_id}/reconcile")
    def reconcile(block_id: recovery.Key, body: recovery.ReconcileDecision,
                  session=Depends(require_action("workspaces.write"))):
        return invoke(recovery.reconcile_decision, session, block_id, body)

    @router.post(root + "/recoveries/{recovery_id}/dispatch")
    def dispatch(recovery_id: recovery.Key, body: Contract,
                 session=Depends(require_action("workspaces.write"))):
        return invoke(recovery.dispatch_retry, session, recovery_id)
