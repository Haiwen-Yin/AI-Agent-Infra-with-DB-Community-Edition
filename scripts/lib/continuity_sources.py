"""Exact-version continuity source reads; locators never grant authority.

Resolvers run in the caller's transaction. Families without an integrated
versioned reader are rejected explicitly rather than copying ungoverned text.
"""
import json
import logging
from contextvars import ContextVar
from contextlib import contextmanager

from .continuity_contracts import SourceRef
from .continuity_state import ContinuityError, ContinuityConflict
from . import continuity_work as work,identity_api

_resolving=ContextVar('continuity_source_resolution_stack',default=())
_logger=logging.getLogger(__name__)
BULK_BIND_LIMIT=100


def read_ids(reader,statement,values,*,params=None):
    """Run trusted metadata SQL with at most 100 binds, preserving row values.

    Only server-owned statements contain the ``{ids}`` slot. This helper is
    neither an authorization cache nor a body reader; callers retain the
    original per-source permission and current-consumption checks.
    """
    values=list(dict.fromkeys(values));params=dict(params or {})
    if not values:return []
    if len(values)>500 or '{ids}' not in statement or len(params)>=BULK_BIND_LIMIT:
        raise ValueError('Invalid bounded source metadata read')
    if 'FOR UPDATE' in statement.upper():values.sort(key=str)
    limit=BULK_BIND_LIMIT-len(params);result=[]
    for start in range(0,len(values),limit):
        binds={f'cx_bulk_{index}':value for index,value in enumerate(values[start:start+limit])}
        if set(binds)&set(params):raise ValueError('Conflicting private bulk bind')
        result.extend(reader.query(statement.replace('{ids}',','.join(':'+name for name in binds)),dict(params,**binds)))
    return result


def locate_many(tx,values,*,lock=False):
    """Bulk locator/permission inputs only; richer families keep their reader.

    Missing entries stay missing until their original ordered validation.
    No body, permission decision or publication is materialized here.
    """
    sources=[value if isinstance(value,SourceRef) else SourceRef.model_validate(value) for value in values]
    locked=' FOR UPDATE' if lock else ''
    result={};families={source.family.value for source in sources}
    for family in sorted(families):
        selected=[source for source in sources if source.family.value==family]
        if family=='MEMORY':
            if lock:
                # Successor publication updates the family before its old
                # version. Lock those roots first, in the same stable order,
                # before locking any current/selected version in a join.
                read_ids(tx,"SELECT FAMILY_ID FROM CX_MEMORY_FAMILIES WHERE FAMILY_ID IN ({ids}) ORDER BY FAMILY_ID FOR UPDATE",
                    [source.entity_id for source in selected])
            rows=read_ids(tx,"SELECT v.FAMILY_ID AS BATCH_ENTITY_ID,v.VERSION_ID AS BATCH_REVISION_ID,"
                "v.SECURITY_DOMAIN_ID,v.OWNER_PRINCIPAL_ID,v.CLASSIFICATION FROM CX_MEMORY_VERSIONS v WHERE v.VERSION_ID IN ({ids}) ORDER BY v.VERSION_ID"+locked,
                [source.revision_id for source in selected])
            found={(row['batch_entity_id'],row['batch_revision_id']):row for row in rows}
            for source in selected:result[(family,source.entity_id,source.revision_id)]=found.get((source.entity_id,source.revision_id))
        elif family in {'KNOWLEDGE','EXPERIENCE','SKILL'}:
            rows=read_ids(tx,"SELECT a.ARTIFACT_ID AS BATCH_ENTITY_ID,a.SECURITY_DOMAIN_ID,a.OWNER_PRINCIPAL_ID,d.CLASSIFICATION "
                "FROM CX_CONTINUITY_ARTIFACTS a JOIN CX_SECURITY_DOMAINS d ON d.SECURITY_DOMAIN_ID=a.SECURITY_DOMAIN_ID "
                "WHERE a.ARTIFACT_ID IN ({ids}) AND a.FAMILY=:family AND a.STATUS='ACTIVE' ORDER BY a.ARTIFACT_ID"+locked,
                [source.entity_id for source in selected],params={'family':family})
            found={row['batch_entity_id']:row for row in rows}
            for source in selected:result[(family,source.entity_id,source.revision_id)]=found.get(source.entity_id)
        elif family=='SOURCE':
            rows=read_ids(tx,"SELECT s.SOURCE_ID AS BATCH_ENTITY_ID,r.REVISION_ID AS BATCH_REVISION_ID,"
                "s.SECURITY_DOMAIN_ID,s.OWNER_PRINCIPAL_ID,d.CLASSIFICATION FROM CX_AGENT_SOURCES s "
                "JOIN CX_SECURITY_DOMAINS d ON d.SECURITY_DOMAIN_ID=s.SECURITY_DOMAIN_ID "
                "JOIN CX_AGENT_SOURCE_REVISIONS r ON r.SOURCE_ID=s.SOURCE_ID WHERE r.REVISION_ID IN ({ids}) ORDER BY r.REVISION_ID"+locked,
                [source.revision_id for source in selected])
            found={(row['batch_entity_id'],row['batch_revision_id']):row for row in rows}
            for source in selected:result[(family,source.entity_id,source.revision_id)]=found.get((source.entity_id,source.revision_id))
        else:
            _logger.debug('context_read method=serial_fallback family=%s reason=rich_source_authority',family)
    return result


def _render(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)


def _memory_inputs(tx,sources):
    from .memory_quality import applicable_sql
    rows=read_ids(tx,"SELECT v.FAMILY_ID AS BATCH_ENTITY_ID,v.VERSION_ID AS BATCH_REVISION_ID,"
        "v.TITLE,v.CONTENT_DIGEST,v.LIFECYCLE_STATE,v.VALID_UNTIL,v.OWNER_PRINCIPAL_ID,v.SECURITY_DOMAIN_ID,"
        "v.MEMORY_SCOPE,v.CLASSIFICATION,c.LIFECYCLE_STATE AS BATCH_CURRENT_STATE,"
        "CASE WHEN "+applicable_sql('v')+" THEN 1 ELSE 0 END AS BATCH_APPLICABLE "
        "FROM CX_MEMORY_VERSIONS v JOIN CX_MEMORY_FAMILIES f ON f.FAMILY_ID=v.FAMILY_ID "
        "JOIN CX_MEMORY_VERSIONS c ON c.VERSION_ID=f.CURRENT_VERSION_ID WHERE v.VERSION_ID IN ({ids}) "
        "AND c.LIFECYCLE_STATE IN ('ACTIVE','STALE','CONFLICTED','MIGRATED') "
        "AND (v.VALID_UNTIL IS NULL OR v.VALID_UNTIL>CURRENT_TIMESTAMP) ORDER BY v.VERSION_ID FOR UPDATE",
        [source.revision_id for source in sources])
    return {(row['batch_entity_id'],row['batch_revision_id']):row for row in rows}


def resolve_many(tx,actor,domain,values,*,purpose=None,publication_ids=None,
                 require_publication_binding=False,omit_denied=False):
    """Batch authorized same-domain Memory bodies in this call's transaction.

    The shared original Memory authority and integrity helpers still validate
    every source. Publications and richer families keep their
    ordinary immediate reader. Nothing is retained for later consumption.
    """
    sources=[value if isinstance(value,SourceRef) else SourceRef.model_validate(value) for value in values]
    if len(sources)>500:raise ValueError('Too many exact source references')
    publications=[None]*len(sources) if publication_ids is None else list(publication_ids)
    if len(publications)!=len(sources):raise ValueError('Every source needs its original publication position')
    def serial(source,publication,**inputs):
        try:return resolve(tx,actor,domain,source,purpose=purpose,publication_id=publication,
            require_publication_binding=require_publication_binding,**inputs)
        except PermissionError:
            if not omit_denied:raise
            return None
    memories=[source for source,publication in zip(sources,publications)
        if source.family.value=='MEMORY' and publication is None]
    if len(memories)<2 or not callable(getattr(tx,'execute_many',None)):
        _logger.debug('context_read method=serial_fallback reason=small_or_legacy_reader sources=%d',len(sources))
        return [serial(source,publication) for source,publication in zip(sources,publications)]
    work._authorize(tx,actor,domain,write=False)
    principal=tx.query_one("SELECT STATUS,PERMISSION_VERSION FROM CX_PRINCIPALS WHERE PRINCIPAL_ID=:actor FOR UPDATE",{'actor':actor})
    if not principal or principal['status']!='ACTIVE':raise PermissionError('Source access denied')
    memory_policy=identity_api.effective_access_many(actor,{'memory.read'})
    located=locate_many(tx,memories,lock=True)
    same=[source for source in memories if (located.get(('MEMORY',source.entity_id,source.revision_id)) or {}).get('security_domain_id')==domain]
    records=_memory_inputs(tx,same);allowed={}
    for source in same:
        key=(source.entity_id,source.revision_id)
        try:
            record=records.get(key)
            with _resolution(source):
                _authorize_memory(tx,actor,domain,source,record,
                    {'lifecycle_state':record['batch_current_state']} if record else None)
            allowed[key]=source
        except PermissionError:
            if not omit_denied:raise
    # Only previously authorized versions can enter this body query.
    rows=read_ids(tx,"SELECT * FROM CX_MEMORY_VERSIONS WHERE VERSION_ID IN ({ids}) "
        "AND (VALID_UNTIL IS NULL OR VALID_UNTIL>CURRENT_TIMESTAMP) ORDER BY VERSION_ID FOR UPDATE",
        [source.revision_id for source in allowed.values()])
    bodies={(row['family_id'],row['version_id']):row for row in rows}
    result=[]
    same_keys={(source.entity_id,source.revision_id) for source in same}
    for source,publication in zip(sources,publications):
        key=(source.entity_id,source.revision_id)
        if source.family.value=='MEMORY' and publication is None and key in same_keys:
            if key not in allowed:result.append(None);continue
            body=bodies.get(key)
            if not body:raise PermissionError('Source access denied')
            with _resolution(source):
                result.append(_memory_value(source,body,domain))
        else:
            _logger.debug('context_read method=serial_fallback family=%s reason=original_source_authority',source.family.value)
            result.append(serial(source,publication))
    if locate_many(tx,memories,lock=True)!=located or _memory_inputs(tx,same)!=records:
        raise ContinuityConflict('STALE_CONTENT','Source authority changed during body loading')
    work._authorize(tx,actor,domain,write=False)
    if tx.query_one("SELECT STATUS,PERMISSION_VERSION FROM CX_PRINCIPALS WHERE PRINCIPAL_ID=:actor",{'actor':actor})!=principal:
        raise PermissionError('Source permission version changed')
    if identity_api.effective_access_many(actor,{'memory.read'})!=memory_policy:
        raise PermissionError('Source memory permission inputs expired or changed')
    return result


@contextmanager
def _resolution(source):
    key=(source.family.value,source.entity_id,source.revision_id)
    stack=_resolving.get()
    if key in stack or len(stack)>=32:
        raise ContinuityError('CYCLIC_SOURCE','Source references contain a cycle or exceed the nesting limit')
    token=_resolving.set(stack+(key,))
    try:
        yield
    finally:
        _resolving.reset(token)


def resolve(tx, actor, domain, value, *, purpose=None, publication_id=None, require_publication_binding=False):
    source=value if isinstance(value,SourceRef) else SourceRef.model_validate(value)
    with _resolution(source):
        return _resolve(tx,actor,domain,source,purpose=purpose,publication_id=publication_id,
                        require_publication_binding=require_publication_binding)


def _authorize_memory(tx,actor,domain,source,record,current):
    from . import memory_lifecycle as memory
    if not record or not current or current['lifecycle_state'] not in memory.ORDINARY_VISIBLE_STATES:
        raise PermissionError('Source access denied')
    try:
        memory._require_memory_access(actor,record,purpose='RUNTIME_CONTEXT')
    except memory.MemoryLifecycleError as exc:
        raise PermissionError('Source access denied') from exc
    if record.get('security_domain_id')!=domain:
        raise PermissionError('An explicit context publication is required')
    work._authorize(tx,actor,domain,write=False)
    from .memory_quality import require_applicable
    require_applicable(tx,source.revision_id)
    if record['content_digest']!=source.content_digest:
        raise ContinuityConflict('STALE_CONTENT','The referenced content digest does not match')


def _memory_value(source,record,domain):
    from . import memory_lifecycle as memory
    def text(value):return value.read() if hasattr(value,'read') else value
    fields={name:text(record[name]) for name in ['title','body_text','memory_type','memory_scope','classification']}
    actual=memory._digest(*(fields[name] for name in ['title','body_text','memory_type','memory_scope','classification']))
    if actual!=source.content_digest or record['content_digest']!=source.content_digest:
        raise ContinuityError('INTEGRITY_ERROR','Stored source failed integrity validation')
    return {'source':source.model_dump(mode='json'),'text':_render(fields),'content_digest':actual,'authorized_scope':domain}


def _resolve(tx,actor,domain,source,*,purpose=None,publication_id=None,require_publication_binding=False):
    # Cross-domain access is a separate explicit grant, evaluated for the
    # current recipient. It never substitutes a sender's session identity.
    metadata=locate(tx,source)
    if require_publication_binding and metadata['security_domain_id']!=domain and not publication_id:
        raise PermissionError('The original context publication binding is missing')
    if source.family.value=='SOURCE':
        if metadata['security_domain_id']!=domain or publication_id is not None:
            raise PermissionError('Configured source evidence requires its original domain')
        from .agent_source_sync import resolve_source
        return resolve_source(tx,actor,domain,source)
    if source.family.value=='WORKING_NOTE':
        if metadata['security_domain_id']!=domain or publication_id is not None:
            raise PermissionError('Working notes require their original domain')
        from .continuity_notes import resolve_note
        return resolve_note(tx,actor,domain,source)
    if source.family.value in {'TASK','GRAPH','DB4A2A','AUDIT'}:
        if metadata['security_domain_id']!=domain or publication_id is not None:
            raise PermissionError('Native source snapshots require their original domain')
        from .continuity_native_sources import resolve as native_resolve
        return native_resolve(tx,actor,domain,source)
    if source.family.value=='HANDOFF_OUTCOME':
        if metadata['security_domain_id']!=domain or publication_id is not None:
            raise PermissionError('Outcome evidence is limited to its original domain participants')
        from .continuity_handoff import _read_outcome
        record=_read_outcome(tx,actor,metadata['handoff_id'])
        if str(record['revision_no'])!=source.revision_id or record['content_digest']!=source.content_digest:
            raise ContinuityConflict('STALE_CONTENT','The outcome source revision or digest does not match')
        payload={key:value for key,value in record.items() if key not in {'created_at','content_digest'}}
        return {'source':source.model_dump(mode='json'),'text':_render(payload),
                'content_digest':record['content_digest'],'authorized_scope':domain}
    if metadata['security_domain_id']!=domain or publication_id is not None:
        from .continuity_publications import resolve_publication
        return resolve_publication(tx,actor,domain,source,metadata,purpose=purpose,publication_id=publication_id)
    if source.family.value=='HANDOFF':
        from .continuity_handoff import _read_handoff
        if not source.revision_id.isascii() or not source.revision_id.isdecimal() or str(int(source.revision_id))!=source.revision_id:
            raise ContinuityError('INVALID_REVISION','Handoff revisions require canonical positive integers')
        record=_read_handoff(tx,actor,source.entity_id,int(source.revision_id))
        root=tx.query_one("SELECT SECURITY_DOMAIN_ID FROM CX_WORK_CONTRACTS WHERE WORK_CONTRACT_ID=:work_id",
                          {'work_id':record['work_contract_id']})
        if root['security_domain_id']!=domain:
            raise PermissionError('An explicit context publication is required')
        if record['expired']:
            raise ContinuityConflict('EXPIRED','The referenced handoff expired')
        if record['content_digest']!=source.content_digest:
            raise ContinuityConflict('STALE_CONTENT','The referenced content digest does not match')
        return {'source':source.model_dump(mode='json'),'text':_render(record['content']),
                'content_digest':record['content_digest'],'authorized_scope':domain}
    if source.family.value=='MEMORY':
        record=tx.query_one("SELECT * FROM CX_MEMORY_VERSIONS WHERE VERSION_ID=:revision AND FAMILY_ID=:family "
                            "AND (VALID_UNTIL IS NULL OR VALID_UNTIL>CURRENT_TIMESTAMP)",
                            {'revision':source.revision_id,'family':source.entity_id})
        if not record:
            raise PermissionError('Source access denied')
        current=tx.query_one("SELECT v.LIFECYCLE_STATE FROM CX_MEMORY_FAMILIES f JOIN CX_MEMORY_VERSIONS v "
                             "ON v.VERSION_ID=f.CURRENT_VERSION_ID WHERE f.FAMILY_ID=:family",{'family':source.entity_id})
        _authorize_memory(tx,actor,domain,source,record,current)
        return _memory_value(source,record,domain)
    if source.family.value in {'KNOWLEDGE','EXPERIENCE','SKILL'}:
        from .continuity_promotions import resolve_artifact
        return resolve_artifact(tx,actor,domain,source)
    raise ContinuityError('SOURCE_RESOLVER_UNAVAILABLE','This source family has no integrated exact-version reader')


def locate(tx,source):
    """Read locator metadata only; callers must authorize before body access."""
    family=source.family.value
    if family=='SOURCE':
        row=tx.query_one("SELECT s.SECURITY_DOMAIN_ID,s.OWNER_PRINCIPAL_ID,d.CLASSIFICATION FROM CX_AGENT_SOURCES s "
                         "JOIN CX_SECURITY_DOMAINS d ON d.SECURITY_DOMAIN_ID=s.SECURITY_DOMAIN_ID "
                         "JOIN CX_AGENT_SOURCE_REVISIONS r ON r.SOURCE_ID=s.SOURCE_ID WHERE s.SOURCE_ID=:entity AND r.REVISION_ID=:revision",
                         {'entity':source.entity_id,'revision':source.revision_id})
        if not row:
            raise PermissionError('Source access denied')
        return row
    if family=='WORKING_NOTE':
        row=tx.query_one("SELECT n.SECURITY_DOMAIN_ID,n.OWNER_PRINCIPAL_ID,d.CLASSIFICATION "
                         "FROM CX_WORK_NOTES n JOIN CX_SECURITY_DOMAINS d ON d.SECURITY_DOMAIN_ID=n.SECURITY_DOMAIN_ID "
                         "WHERE n.NOTE_ID=:entity",{'entity':source.entity_id})
    elif family in {'TASK','GRAPH','DB4A2A','AUDIT'}:
        from .continuity_native_sources import locate as native_locate
        row=native_locate(tx,source)
    elif family=='MEMORY':
        row=tx.query_one("SELECT v.SECURITY_DOMAIN_ID,v.OWNER_PRINCIPAL_ID,v.CLASSIFICATION FROM CX_MEMORY_VERSIONS v "
                         "WHERE v.FAMILY_ID=:entity AND v.VERSION_ID=:revision",{'entity':source.entity_id,'revision':source.revision_id})
    elif family=='HANDOFF_OUTCOME':
        row=tx.query_one("SELECT w.SECURITY_DOMAIN_ID,o.SUBMITTED_BY AS OWNER_PRINCIPAL_ID,d.CLASSIFICATION,h.HANDOFF_ID "
                         "FROM CX_HANDOFF_OUTCOMES o JOIN CX_HANDOFFS h ON h.HANDOFF_ID=o.HANDOFF_ID "
                         "JOIN CX_WORK_CONTRACTS w ON w.WORK_CONTRACT_ID=h.WORK_CONTRACT_ID "
                         "JOIN CX_SECURITY_DOMAINS d ON d.SECURITY_DOMAIN_ID=w.SECURITY_DOMAIN_ID WHERE o.OUTCOME_ID=:entity",
                         {'entity':source.entity_id})
    elif family=='HANDOFF':
        row=tx.query_one("SELECT w.SECURITY_DOMAIN_ID,h.FROM_PRINCIPAL_ID AS OWNER_PRINCIPAL_ID,d.CLASSIFICATION "
                         "FROM CX_HANDOFFS h JOIN CX_WORK_CONTRACTS w ON w.WORK_CONTRACT_ID=h.WORK_CONTRACT_ID "
                         "JOIN CX_SECURITY_DOMAINS d ON d.SECURITY_DOMAIN_ID=w.SECURITY_DOMAIN_ID WHERE h.HANDOFF_ID=:entity",
                         {'entity':source.entity_id})
    elif family in {'KNOWLEDGE','EXPERIENCE','SKILL'}:
        row=tx.query_one("SELECT a.SECURITY_DOMAIN_ID,a.OWNER_PRINCIPAL_ID,d.CLASSIFICATION FROM CX_CONTINUITY_ARTIFACTS a "
                         "JOIN CX_SECURITY_DOMAINS d ON d.SECURITY_DOMAIN_ID=a.SECURITY_DOMAIN_ID "
                         "WHERE a.ARTIFACT_ID=:entity AND a.FAMILY=:family AND a.STATUS='ACTIVE'",
                         {'entity':source.entity_id,'family':family})
    else:
        raise ContinuityError('SOURCE_RESOLVER_UNAVAILABLE','This source family has no integrated exact-version reader')
    if not row or not row['security_domain_id'] or not row['owner_principal_id']:
        raise PermissionError('Source access denied')
    return row


def publication_payload(tx,source,domain,*,actor):
    """Reconstruct an exact source only after explicit publication authorization."""
    if source.family.value=='SOURCE':
        raise PermissionError('Configured source evidence cannot bypass its current origin authority')
    if source.family.value=='WORKING_NOTE':
        raise PermissionError('Working notes cannot be published across domains')
    if source.family.value=='HANDOFF':
        from .continuity_handoff import _handoff_payload
        if not source.revision_id.isascii() or not source.revision_id.isdecimal() or str(int(source.revision_id))!=source.revision_id:
            raise ContinuityError('INVALID_REVISION','Invalid Handoff revision')
        row=tx.query_one("SELECT * FROM CX_HANDOFFS WHERE HANDOFF_ID=:entity",{'entity':source.entity_id})
        if not row:
            raise PermissionError('Source access denied')
        record=_handoff_payload(tx,row,int(source.revision_id),actor=actor,domain=domain)
        if record['expired']:
            raise ContinuityConflict('EXPIRED','Published source expired')
        if record['content_digest']!=source.content_digest:
            raise ContinuityConflict('STALE_CONTENT','Published source changed')
        return {'source':source.model_dump(mode='json'),'text':_render(record['content']),'content_digest':source.content_digest,'authorized_scope':domain}
    if source.family.value=='MEMORY':
        from . import memory_lifecycle as memory
        record=tx.query_one("SELECT v.* FROM CX_MEMORY_VERSIONS v JOIN CX_MEMORY_FAMILIES f ON f.FAMILY_ID=v.FAMILY_ID "
                            "JOIN CX_MEMORY_VERSIONS current_v ON current_v.VERSION_ID=f.CURRENT_VERSION_ID "
                            "WHERE v.FAMILY_ID=:entity AND v.VERSION_ID=:revision AND v.LIFECYCLE_STATE IN ('ACTIVE','STALE','CONFLICTED','MIGRATED') "
                            "AND current_v.LIFECYCLE_STATE IN ('ACTIVE','STALE','CONFLICTED','MIGRATED') "
                            "AND (v.VALID_UNTIL IS NULL OR v.VALID_UNTIL>CURRENT_TIMESTAMP)",{'entity':source.entity_id,'revision':source.revision_id})
        if not record:
            raise PermissionError('Source access denied')
        from .memory_quality import require_applicable
        require_applicable(tx,source.revision_id)
        fields={key:(record[key].read() if hasattr(record[key],'read') else record[key]) for key in ['title','body_text','memory_type','memory_scope','classification']}
        digest=memory._digest(*(fields[key] for key in ['title','body_text','memory_type','memory_scope','classification']))
        if digest!=source.content_digest or record['content_digest']!=source.content_digest:
            raise ContinuityError('INTEGRITY_ERROR','Published source failed integrity validation')
        return {'source':source.model_dump(mode='json'),'text':_render(fields),'content_digest':digest,'authorized_scope':domain}
    from .continuity_promotions import _artifact_payload
    return _artifact_payload(tx,source,domain)
