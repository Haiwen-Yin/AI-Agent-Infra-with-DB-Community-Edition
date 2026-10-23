"""Temporal memory evidence and authorized reconciliation proposals.

Time evidence supplements immutable memory versions. Proposed relationships do
not change family pointers or publish content; publication stays on the existing
independently reviewed candidate chain.
"""
from __future__ import annotations

from datetime import datetime, timezone
import math

from . import connection, identity_api, continuity_work as work
from .continuity_contracts import SourceRef
from .agent_extension_contracts import digest as content_digest
from .continuity_state import ContinuityConflict, ContinuityError


def schema_statements(dialect):
    if dialect not in {'pg', 'postgresql', 'oracle', 'yashandb'}:
        raise ValueError('unsupported database adapter')
    body = 'TEXT' if dialect in {'pg', 'postgresql'} else 'CLOB'
    return [
        "CREATE TABLE CX_MEMORY_TIME_FACTS (VERSION_ID VARCHAR(128) PRIMARY KEY REFERENCES CX_MEMORY_VERSIONS(VERSION_ID), "
        "EVENT_AT TIMESTAMP, EVENT_TIME_TEXT VARCHAR(128), EVENT_TIME_STATE VARCHAR(24) NOT NULL "
        "CHECK(EVENT_TIME_STATE IN ('KNOWN','UNKNOWN','UNKNOWN_OFFSET')), OBSERVED_AT TIMESTAMP NOT NULL, "
        "APPLIES_FROM TIMESTAMP, APPLIES_UNTIL TIMESTAMP, CORRECTS_VERSION_ID VARCHAR(128) REFERENCES CX_MEMORY_VERSIONS(VERSION_ID), "
        "CORRECTION_SCOPE VARCHAR(1000), CONTENT_DIGEST VARCHAR(64) NOT NULL, CREATED_BY VARCHAR(128) NOT NULL "
        "REFERENCES CX_PRINCIPALS(PRINCIPAL_ID), INGESTED_AT TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL, "
        "CHECK(APPLIES_UNTIL IS NULL OR APPLIES_FROM IS NULL OR APPLIES_UNTIL>APPLIES_FROM), "
        "CHECK((EVENT_TIME_STATE='KNOWN' AND EVENT_AT IS NOT NULL) OR (EVENT_TIME_STATE<>'KNOWN' AND EVENT_AT IS NULL)), "
        "CHECK((CORRECTS_VERSION_ID IS NULL AND CORRECTION_SCOPE IS NULL) OR "
        "(CORRECTS_VERSION_ID IS NOT NULL AND CORRECTION_SCOPE IS NOT NULL AND APPLIES_FROM IS NOT NULL)))",
        "CREATE TABLE CX_MEMORY_RECON_PROPOSALS (PROPOSAL_ID VARCHAR(128) PRIMARY KEY, "
        "SECURITY_DOMAIN_ID VARCHAR(128) NOT NULL REFERENCES CX_SECURITY_DOMAINS(SECURITY_DOMAIN_ID), "
        "RELATION_KIND VARCHAR(24) NOT NULL CHECK(RELATION_KIND IN ('DUPLICATE','CONTRADICTION','REPLACEMENT','UNRESOLVED')), "
        "STATUS VARCHAR(24) NOT NULL CHECK(STATUS IN ('PENDING','UNRESOLVED','APPROVED','REJECTED')), "
        "METHOD VARCHAR(128) NOT NULL, POLICY_REVISION VARCHAR(128) NOT NULL, CONFIDENCE DECIMAL(8,7), "
        "CONFIDENCE_MEANING VARCHAR(1000) NOT NULL, REASON VARCHAR(1000) NOT NULL, "
        "CREATED_BY VARCHAR(128) NOT NULL REFERENCES CX_PRINCIPALS(PRINCIPAL_ID), "
        "IDEMPOTENCY_KEY VARCHAR(128) NOT NULL, REQUEST_DIGEST VARCHAR(64) NOT NULL, "
        "CREATED_AT TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL, UNIQUE(CREATED_BY,IDEMPOTENCY_KEY), "
        "CHECK(CONFIDENCE IS NULL OR (CONFIDENCE>=0 AND CONFIDENCE<=1)))",
        "CREATE TABLE CX_MEMORY_RECON_SOURCES (PROPOSAL_ID VARCHAR(128) NOT NULL REFERENCES CX_MEMORY_RECON_PROPOSALS(PROPOSAL_ID), "
        "ITEM_NO INTEGER NOT NULL CHECK(ITEM_NO IN (1,2)), FAMILY_ID VARCHAR(128) NOT NULL REFERENCES CX_MEMORY_FAMILIES(FAMILY_ID), "
        "VERSION_ID VARCHAR(128) NOT NULL REFERENCES CX_MEMORY_VERSIONS(VERSION_ID), CONTENT_DIGEST VARCHAR(64) NOT NULL, "
        "PRIMARY KEY(PROPOSAL_ID,ITEM_NO), UNIQUE(PROPOSAL_ID,VERSION_ID))",
        f"CREATE TABLE CX_MEMORY_RECON_REVIEWS (PROPOSAL_ID VARCHAR(128) PRIMARY KEY REFERENCES CX_MEMORY_RECON_PROPOSALS(PROPOSAL_ID), "
        "REVIEWED_BY VARCHAR(128) NOT NULL REFERENCES CX_PRINCIPALS(PRINCIPAL_ID), DECISION VARCHAR(24) NOT NULL "
        f"CHECK(DECISION IN ('APPROVED','REJECTED')), REASON {body} NOT NULL, CREATED_AT TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL)",
        "CREATE TABLE CX_MEMORY_RESTORE_REQUESTS (ACTOR_ID VARCHAR(128) NOT NULL REFERENCES CX_PRINCIPALS(PRINCIPAL_ID), "
        "IDEMPOTENCY_KEY VARCHAR(128) NOT NULL, REQUEST_DIGEST VARCHAR(64) NOT NULL, "
        "FAMILY_ID VARCHAR(128) NOT NULL REFERENCES CX_MEMORY_FAMILIES(FAMILY_ID), "
        "ORIGIN_VERSION_ID VARCHAR(128) NOT NULL REFERENCES CX_MEMORY_VERSIONS(VERSION_ID), "
        "RESULT_VERSION_ID VARCHAR(128) NOT NULL REFERENCES CX_MEMORY_VERSIONS(VERSION_ID), "
        "REASON VARCHAR(1000) NOT NULL, CREATED_AT TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL, PRIMARY KEY(ACTOR_ID,IDEMPOTENCY_KEY))",
    ]


def _instant(value, *, field, allow_unknown_offset=False):
    if value is None or value == '':
        return None, None, 'UNKNOWN'
    original = value.isoformat() if isinstance(value, datetime) else str(value).strip()
    if len(original) > 128:
        raise ValueError(field + ' exceeds the supported size')
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(original.replace('Z', '+00:00'))
    except (TypeError, ValueError) as exc:
        raise ValueError(field + ' requires an ISO 8601 timestamp') from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        if allow_unknown_offset:
            return None, original, 'UNKNOWN_OFFSET'
        raise ValueError(field + ' requires an explicit timezone')
    return parsed.astimezone(timezone.utc).replace(tzinfo=None), original, 'KNOWN'


def temporal_facts(value):
    """Retain an unknown event/offset without inventing it from ingestion time."""
    event, original, state = _instant(value.get('event_at'), field='event_at', allow_unknown_offset=True)
    observed, _, _ = _instant(value.get('observed_at'), field='observed_at')
    start, _, _ = _instant(value.get('applies_from'), field='applies_from')
    until, _, _ = _instant(value.get('applies_until'), field='applies_until')
    if start and until and until <= start:
        raise ValueError('applies_until must follow applies_from')
    correction = value.get('corrects_version_id') or None
    scope = str(value.get('correction_scope') or '').strip() or None
    if correction and (not scope or not start):
        raise ValueError('A correction requires its scope and applicable start time')
    if scope and not correction:
        raise ValueError('A correction scope requires an exact corrected version')
    if correction and (len(str(correction)) > 128 or len(scope) > 1000):
        raise ValueError('Correction metadata exceeds the supported size')
    return dict(event_at=event, event_time_text=original, event_time_state=state,
                observed_at=observed or datetime.now(timezone.utc).replace(tzinfo=None),
                applies_from=start, applies_until=until, corrects_version_id=correction, correction_scope=scope)


def record_time(tx, version_id, facts, *, actor):
    digest = content_digest({key: value.isoformat() if isinstance(value, datetime) else value for key, value in facts.items()})
    tx.execute("INSERT INTO CX_MEMORY_TIME_FACTS(VERSION_ID,EVENT_AT,EVENT_TIME_TEXT,EVENT_TIME_STATE,OBSERVED_AT,"
               "APPLIES_FROM,APPLIES_UNTIL,CORRECTS_VERSION_ID,CORRECTION_SCOPE,CONTENT_DIGEST,CREATED_BY) "
               "VALUES(:version,:event_at,:event_time_text,:event_time_state,:observed_at,:applies_from,:applies_until,"
               ":corrects_version_id,:correction_scope,:digest,:actor)", dict(facts, version=version_id, digest=digest, actor=actor))


def guard_successor(tx, expected_version, facts):
    """Late old evidence is retained as a proposal, not an implicit replacement."""
    if facts.get('corrects_version_id'):
        if facts['corrects_version_id'] != expected_version:
            raise ContinuityConflict('STALE_CORRECTION', 'The correction must identify the exact current version')
        return
    current = tx.query_one("SELECT EVENT_AT,APPLIES_FROM FROM CX_MEMORY_TIME_FACTS WHERE VERSION_ID=:version", {'version': expected_version})
    if not current:
        return
    previous = current.get('applies_from') or current.get('event_at')
    incoming = facts.get('applies_from') or facts.get('event_at')
    # Database TIMESTAMP values are UTC-naive by contract; text is accepted by
    # unit harnesses, never interpreted as a newly observed source offset.
    if isinstance(previous, str):
        previous = datetime.fromisoformat(previous)
    if previous and incoming and incoming < previous:
        raise ContinuityConflict('LATE_EVIDENCE', 'Older applicable evidence requires reconciliation, not automatic replacement')


def applicable_sql(alias='v'):
    if alias not in {'v','current_v'}:
        raise ValueError('Unsupported memory SQL alias')
    now = utc_now_expression()
    return ("NOT EXISTS (SELECT 1 FROM CX_MEMORY_TIME_FACTS mt WHERE mt.VERSION_ID="+alias+".VERSION_ID AND "
            "((mt.APPLIES_FROM IS NOT NULL AND mt.APPLIES_FROM>"+now+") OR "
            "(mt.APPLIES_UNTIL IS NOT NULL AND mt.APPLIES_UNTIL<="+now+")))")


def utc_now_expression():
    """Compare UTC-naive temporal facts without inheriting session time zones."""
    dialect = str(getattr(connection, 'DATABASE_DIALECT', '')).lower()
    if dialect in {'pg', 'postgresql'}:
        return "CURRENT_TIMESTAMP AT TIME ZONE 'UTC'"
    if dialect in {'oracle', 'yashandb'}:
        return 'SYS_EXTRACT_UTC(SYSTIMESTAMP)'
    if dialect == 'sqlite':
        return 'CURRENT_TIMESTAMP'
    raise ValueError('unsupported database adapter')


def require_applicable(tx,version_id):
    now = utc_now_expression()
    row=tx.query_one("SELECT VERSION_ID FROM CX_MEMORY_TIME_FACTS WHERE VERSION_ID=:version AND "
        "((APPLIES_FROM IS NOT NULL AND APPLIES_FROM>"+now+") OR "
        "(APPLIES_UNTIL IS NOT NULL AND APPLIES_UNTIL<="+now+"))",{'version':version_id})
    if row:
        raise ContinuityConflict('NOT_APPLICABLE','The memory evidence is not currently applicable')


def _text(value, name, maximum=128):
    result = str(value or '').strip()
    if not result or len(result) > maximum:
        raise ValueError(name + ' is required and must be bounded')
    return result


def propose_reconciliation(actor, value):
    """Record two exact authorized versions; a failed judgment stays unresolved."""
    allowed = {'security_domain_id','sources','relation_kind','method','policy_revision','confidence',
               'confidence_meaning','reason','idempotency_key','judgment_available'}
    if set(value) - allowed:
        raise ValueError('Unsupported reconciliation fields')
    domain = _text(value.get('security_domain_id'), 'security_domain_id')
    refs = [SourceRef.model_validate(item) for item in value.get('sources', [])]
    if len(refs) != 2 or any(ref.family.value != 'MEMORY' for ref in refs) or refs[0] == refs[1]:
        raise ValueError('Two distinct exact memory sources are required')
    kind = str(value.get('relation_kind') or '').upper()
    if kind not in {'DUPLICATE','CONTRADICTION','REPLACEMENT','UNRESOLVED'}:
        raise ValueError('Unsupported reconciliation relation')
    judgment_available = value.get('judgment_available', True)
    if not isinstance(judgment_available, bool):
        raise ValueError('judgment_available requires a boolean')
    confidence = value.get('confidence')
    if confidence is not None and (isinstance(confidence, bool) or not isinstance(confidence, (int,float))
                                   or not math.isfinite(confidence) or not 0 <= confidence <= 1):
        raise ValueError('confidence must be finite and between zero and one')
    fields = {name: _text(value.get(name), name, 1000 if name in {'confidence_meaning','reason'} else 128)
              for name in ['method','policy_revision','confidence_meaning','reason','idempotency_key']}
    request = dict(fields, security_domain_id=domain, sources=[ref.model_dump(mode='json') for ref in refs],
                   relation_kind=kind, confidence=confidence, judgment_available=judgment_available)
    digest = content_digest(request)
    def perform(tx):
        work._authorize(tx, actor, domain, write=True)
        if identity_api.effective_access(actor, 'actions.propose', resource={'security_domain_id':domain}).get('decision') != 'ALLOW':
            raise PermissionError('Reconciliation access denied')
        from .continuity_sources import resolve
        for ref in refs:
            resolve(tx, actor, domain, ref, purpose='MEMORY_RECONCILIATION')
        prior = tx.query_one("SELECT PROPOSAL_ID,REQUEST_DIGEST,STATUS FROM CX_MEMORY_RECON_PROPOSALS "
                             "WHERE CREATED_BY=:actor AND IDEMPOTENCY_KEY=:idem", {'actor':actor,'idem':fields['idempotency_key']})
        if prior:
            if prior['request_digest'] != digest:
                raise ContinuityConflict('IDEMPOTENCY_CONFLICT', 'The key belongs to different reconciliation facts')
            return dict(proposal_id=prior['proposal_id'], status=prior['status'], replayed=True)
        proposal_id = work._id('MRP')
        status = 'PENDING' if judgment_available and kind != 'UNRESOLVED' else 'UNRESOLVED'
        tx.execute("INSERT INTO CX_MEMORY_RECON_PROPOSALS(PROPOSAL_ID,SECURITY_DOMAIN_ID,RELATION_KIND,STATUS,METHOD,"
                   "POLICY_REVISION,CONFIDENCE,CONFIDENCE_MEANING,REASON,CREATED_BY,IDEMPOTENCY_KEY,REQUEST_DIGEST) "
                   "VALUES(:proposal,:domain,:kind,:status,:method,:policy_revision,:confidence,:confidence_meaning,:reason,"
                   ":actor,:idempotency_key,:digest)", dict(fields, proposal=proposal_id,domain=domain,kind=kind,status=status,
                   confidence=confidence if judgment_available else None,actor=actor,digest=digest))
        for number, ref in enumerate(refs, 1):
            tx.execute("INSERT INTO CX_MEMORY_RECON_SOURCES(PROPOSAL_ID,ITEM_NO,FAMILY_ID,VERSION_ID,CONTENT_DIGEST) "
                       "VALUES(:proposal,:v_item_no,:family,:version,:digest)", dict(proposal=proposal_id,v_item_no=number,
                       family=ref.entity_id,version=ref.revision_id,digest=ref.content_digest))
        identity_api._audit_tx(tx,actor,'MEMORY_RECONCILIATION_PROPOSE','MEMORY_RECONCILIATION',proposal_id,'ALLOW',fields['reason'])
        return dict(proposal_id=proposal_id,status=status,replayed=False)
    return connection.execute_transaction_callback(perform)


def review_reconciliation(actor, proposal_id, *, decision, reason):
    decision = str(decision).upper()
    if decision not in {'APPROVED','REJECTED'}:
        raise ValueError('Unsupported review decision')
    reason = _text(reason, 'reason', 1000)
    def perform(tx):
        work._lock_actor(tx,actor)
        root = tx.query_one("SELECT * FROM CX_MEMORY_RECON_PROPOSALS WHERE PROPOSAL_ID=:proposal FOR UPDATE", {'proposal':proposal_id})
        if not root:
            raise PermissionError('Reconciliation access denied')
        from .continuity_candidates import _authority
        _authority(tx,actor,root['security_domain_id'],'MEMORY',review=True)
        if root['created_by'] == actor:
            raise PermissionError('A proposer cannot review their own reconciliation')
        previous=tx.query_one("SELECT REVIEWED_BY,DECISION,REASON FROM CX_MEMORY_RECON_REVIEWS WHERE PROPOSAL_ID=:proposal",
                              {'proposal':proposal_id})
        if previous:
            if (previous['reviewed_by']==actor and previous['decision']==decision and previous['reason']==reason):
                return dict(proposal_id=proposal_id,status=previous['decision'],activated=False,replayed=True)
            raise ContinuityConflict('RECONCILIATION_CLOSED','The reconciliation was already reviewed')
        if root['status'] != 'PENDING':
            raise ContinuityConflict('RECONCILIATION_CLOSED', 'Only a resolved pending judgment can be reviewed')
        from .continuity_sources import resolve
        for row in tx.query("SELECT FAMILY_ID,VERSION_ID,CONTENT_DIGEST FROM CX_MEMORY_RECON_SOURCES WHERE PROPOSAL_ID=:proposal ORDER BY ITEM_NO", {'proposal':proposal_id}):
            resolve(tx,actor,root['security_domain_id'],dict(family='MEMORY',entity_id=row['family_id'],
                    revision_id=row['version_id'],content_digest=row['content_digest']),purpose='MEMORY_RECONCILIATION')
        tx.execute("INSERT INTO CX_MEMORY_RECON_REVIEWS(PROPOSAL_ID,REVIEWED_BY,DECISION,REASON) VALUES(:proposal,:actor,:decision,:reason)",
                   dict(proposal=proposal_id,actor=actor,decision=decision,reason=reason))
        tx.execute("UPDATE CX_MEMORY_RECON_PROPOSALS SET STATUS=:decision WHERE PROPOSAL_ID=:proposal",dict(decision=decision,proposal=proposal_id))
        identity_api._audit_tx(tx,actor,'MEMORY_RECONCILIATION_REVIEW','MEMORY_RECONCILIATION',proposal_id,'ALLOW',reason)
        return dict(proposal_id=proposal_id,status=decision,activated=False)
    return connection.execute_transaction_callback(perform)


def read_reconciliation(actor, proposal_id):
    def perform(tx):
        work._lock_actor(tx,actor)
        root=tx.query_one("SELECT * FROM CX_MEMORY_RECON_PROPOSALS WHERE PROPOSAL_ID=:proposal",{'proposal':proposal_id})
        if not root:
            raise PermissionError('Reconciliation access denied')
        from .continuity_candidates import _authority
        _authority(tx,actor,root['security_domain_id'],'MEMORY',review=actor!=root['created_by'])
        from .continuity_sources import resolve
        refs=[]
        for row in tx.query("SELECT FAMILY_ID,VERSION_ID,CONTENT_DIGEST FROM CX_MEMORY_RECON_SOURCES WHERE PROPOSAL_ID=:proposal ORDER BY ITEM_NO",{'proposal':proposal_id}):
            ref=dict(family='MEMORY',entity_id=row['family_id'],revision_id=row['version_id'],content_digest=row['content_digest'])
            resolve(tx,actor,root['security_domain_id'],ref,purpose='MEMORY_RECONCILIATION')
            refs.append(ref)
        review=tx.query_one("SELECT REVIEWED_BY,DECISION,REASON,CREATED_AT FROM CX_MEMORY_RECON_REVIEWS WHERE PROPOSAL_ID=:proposal",{'proposal':proposal_id})
        return dict(root,sources=refs,review=review)
    return connection.execute_transaction_callback(perform)


def read_time(actor, value):
    """Read exact authorized temporal metadata without widening source scope."""
    source=value if isinstance(value,SourceRef) else SourceRef.model_validate(value)
    if source.family.value!='MEMORY':
        raise ValueError('An exact memory source is required')
    def perform(tx):
        from .continuity_sources import locate,resolve
        metadata=locate(tx,source)
        work._authorize(tx,actor,metadata['security_domain_id'],write=False)
        access=identity_api.effective_access(actor,'memory.read',resource={'security_domain_id':metadata['security_domain_id']})
        if (access.get('decision')!='ALLOW' or
                (metadata['owner_principal_id']!=actor and 'ALL' not in set(access.get('scopes') or []))):
            raise PermissionError('Memory temporal history is unavailable')
        result=tx.query_one("SELECT * FROM CX_MEMORY_TIME_FACTS WHERE VERSION_ID=:version",{'version':source.revision_id})
        if not result:
            # CREATED_AT is trustworthy ingestion/observation time, not event time.
            version=tx.query_one("SELECT CREATED_AT FROM CX_MEMORY_VERSIONS WHERE VERSION_ID=:version",
                                 {'version':source.revision_id}) or {}
            return dict(version_id=source.revision_id,event_at=None,event_time_state='UNKNOWN',
                        observed_at=version.get('created_at'),applies_from=None,applies_until=None,
                        provenance='HISTORICAL_INGESTION_TIME')
        # DB timestamp text and driver datetime values serialize differently;
        # normalize absolute UTC-naive facts before checking their original hash.
        canonical={key:result.get(key) for key in ('event_at','event_time_text','event_time_state','observed_at',
                                                   'applies_from','applies_until','corrects_version_id','correction_scope')}
        for key in ('event_at','observed_at','applies_from','applies_until'):
            if isinstance(canonical[key],str):
                canonical[key]=datetime.fromisoformat(canonical[key])
        actual=content_digest({key:(item.isoformat() if isinstance(item,datetime) else item) for key,item in canonical.items()})
        if actual!=result['content_digest']:
            raise ContinuityError('INTEGRITY_ERROR','Stored temporal facts failed integrity validation')
        return dict(result,provenance='RECORDED')
    return connection.execute_transaction_callback(perform)


def restore_version(actor, family_id, value):
    """Restore authorized history as a new immutable version, never a rewind."""
    allowed={'expected_version_id','historical_version_id','reason','idempotency_key'}
    if set(value)!=allowed:
        raise ValueError('Restore requires exact current/history IDs, reason and idempotency key')
    fields={name:_text(value.get(name),name,1000 if name=='reason' else 128) for name in allowed}
    digest=content_digest(dict(fields,family_id=family_id))
    def perform(tx):
        from . import memory_lifecycle as memory
        work._lock_actor(tx,actor)
        root=tx.query_one("SELECT * FROM CX_MEMORY_FAMILIES WHERE FAMILY_ID=:family FOR UPDATE",{'family':family_id})
        if not root:
            raise PermissionError('Memory history unavailable')
        domain=root.get('security_domain_id')
        if domain:
            work._authorize(tx,actor,domain,write=True)
        if identity_api.effective_access(actor,'memory.write',resource={'security_domain_id':domain}).get('decision')!='ALLOW':
            raise PermissionError('Memory restoration denied')
        current=tx.query_one("SELECT * FROM CX_MEMORY_VERSIONS WHERE VERSION_ID=:version AND FAMILY_ID=:family",
                             {'version':root['current_version_id'],'family':family_id})
        if not current:
            raise PermissionError('Memory history unavailable')
        memory._require_memory_access(actor,current,purpose='MEMORY_RESTORE')
        prior=tx.query_one("SELECT * FROM CX_MEMORY_RESTORE_REQUESTS WHERE ACTOR_ID=:actor AND IDEMPOTENCY_KEY=:idem",
                           {'actor':actor,'idem':fields['idempotency_key']})
        if prior:
            if prior['request_digest']!=digest or prior['family_id']!=family_id:
                raise ContinuityConflict('IDEMPOTENCY_CONFLICT','The restore key belongs to different history')
            return dict(family_id=family_id,version_id=prior['result_version_id'],origin_version_id=prior['origin_version_id'],replayed=True)
        if current['version_id']!=fields['expected_version_id']:
            raise ContinuityConflict('STALE_VERSION','The current memory revision changed')
        historical=tx.query_one("SELECT * FROM CX_MEMORY_VERSIONS WHERE VERSION_ID=:version AND FAMILY_ID=:family",
                                {'version':fields['historical_version_id'],'family':family_id})
        if (not historical or historical['lifecycle_state'] not in {'ACTIVE','STALE','CONFLICTED','MIGRATED','SUPERSEDED','ARCHIVED'}
                or historical.get('security_domain_id')!=domain):
            raise PermissionError('Memory history unavailable')
        # Current domain/owner authority is still required for historical bodies;
        # lifecycle eligibility alone is relaxed, never the reader's grant.
        memory._require_memory_access(actor,dict(historical,lifecycle_state='ACTIVE'),purpose='MEMORY_RESTORE')
        text=lambda value:value.read() if hasattr(value,'read') else value
        facts={name:text(historical[name]) for name in ['title','body_text','memory_type','memory_scope','classification']}
        if memory._digest(*(facts[name] for name in facts))!=historical['content_digest']:
            raise ContinuityError('INTEGRITY_ERROR','Historical memory content failed integrity validation')
        classification=max((facts['classification'],current['classification']),key=lambda value:memory.CLASSIFICATION_LEVELS[value])
        request=memory._request(dict(title=facts['title'],body=facts['body_text'],memory_type=facts['memory_type'],
            memory_scope=facts['memory_scope'],classification=classification,owner_principal_id=historical.get('owner_principal_id'),
            owner_agent_id=historical.get('owner_agent_id'),workspace_id=historical.get('workspace_id'),security_domain_id=domain,
            source_ref='RESTORE:'+historical['version_id'],source_digest=historical['content_digest'],reason=fields['reason'],
            applies_from=datetime.now(timezone.utc).isoformat(),corrects_version_id=current['version_id'],correction_scope=fields['reason']))
        version_id=memory._id('MV')
        number=tx.query_one("SELECT COALESCE(MAX(VERSION_NUMBER),0) AS VERSION_NUMBER FROM CX_MEMORY_VERSIONS WHERE FAMILY_ID=:family",{'family':family_id})
        version=int(number['version_number'])+1
        new_digest=memory._digest(request.title,request.body,request.memory_type,request.memory_scope,request.classification)
        memory._insert_version(tx,version_id,family_id,version,request,new_digest,actor)
        memory._insert_source_representation(tx,version_id,request.body,new_digest)
        tx.execute("UPDATE CX_MEMORY_FAMILIES SET CURRENT_VERSION_ID=:version,FAMILY_STATE='ACTIVE',ROW_VERSION=ROW_VERSION+1,UPDATED_AT=CURRENT_TIMESTAMP "
                   "WHERE FAMILY_ID=:family",{'version':version_id,'family':family_id})
        tx.execute("UPDATE CX_MEMORY_VERSIONS SET LIFECYCLE_STATE='SUPERSEDED' WHERE VERSION_ID=:version",{'version':current['version_id']})
        memory._relation(tx,historical['version_id'],version_id,'DERIVED_FROM',deterministic=True,actor=actor)
        tx.execute("INSERT INTO CX_MEMORY_RESTORE_REQUESTS(ACTOR_ID,IDEMPOTENCY_KEY,REQUEST_DIGEST,FAMILY_ID,ORIGIN_VERSION_ID,RESULT_VERSION_ID,REASON) "
                   "VALUES(:actor,:idem,:digest,:family,:origin,:result,:reason)",dict(actor=actor,idem=fields['idempotency_key'],digest=digest,
                   family=family_id,origin=historical['version_id'],result=version_id,reason=fields['reason']))
        memory._outbox(tx,'FAMILY',family_id,'CURRENT_VERSION_CHANGED',dict(family_id=family_id,version_id=version_id,origin_version_id=historical['version_id']))
        identity_api._audit_tx(tx,actor,'MEMORY_RESTORE','MEMORY',family_id,'ALLOW',fields['reason'])
        return dict(family_id=family_id,version_id=version_id,version_number=version,origin_version_id=historical['version_id'],replayed=False)
    return connection.execute_transaction_callback(perform)
