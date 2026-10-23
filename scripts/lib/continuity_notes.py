"""Typed, exact-revision working notes on existing Work contracts.

Notes are transient continuity evidence, never automatically published Memory,
Knowledge or Skills. Authorization reuses current Work/domain/execution grants.
"""
from datetime import datetime, timezone

from pydantic import Field, StrictInt, field_validator
from typing import Annotated, Literal

from . import connection, identity_api, continuity_work as work
from .continuity_contracts import Contract, Identifier, Text, Reason, Revision, SourceRef, content_digest, request_digest
from .continuity_state import ContinuityConflict, ContinuityError, require_version, require_idempotent_request


class NoteContent(Contract):
    note_type: Literal['FINDING','REJECTED_APPROACH','VALIDATION','OPEN_QUESTION','NEXT_ACTION']
    title: Text
    body: Text
    sources: Annotated[tuple[SourceRef,...], Field(max_length=100)] = ()
    expires_at: datetime | None = None

    @field_validator('expires_at')
    @classmethod
    def explicit_timezone(cls, value):
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError('expires_at must include a timezone')
        return value.astimezone(timezone.utc) if value else None


class NewNote(Contract):
    expected_work_version: Revision
    content: NoteContent
    reason: Reason
    idempotency_key: Identifier


class ReviseNote(Contract):
    expected_version: Revision
    content: NoteContent
    reason: Reason
    idempotency_key: Identifier


class NoteState(Contract):
    expected_version: Revision
    status: Literal['ACTIVE','RETIRED']
    reason: Reason
    idempotency_key: Identifier


def _normalise_rows(rows):
    """Return adapter rows in the lower-case HTTP contract shape."""
    return [{str(key).lower(): value for key, value in dict(row).items()} for row in rows]


def schema_statements(dialect):
    if dialect not in {'pg','postgresql','oracle','yashandb'}:
        raise ValueError('unsupported database adapter')
    body = 'TEXT' if dialect in {'pg','postgresql'} else 'CLOB'
    return [
        "CREATE TABLE CX_WORK_NOTES (NOTE_ID VARCHAR(128) PRIMARY KEY, "
        "WORK_CONTRACT_ID VARCHAR(128) NOT NULL REFERENCES CX_WORK_CONTRACTS(WORK_CONTRACT_ID), "
        "SECURITY_DOMAIN_ID VARCHAR(128) NOT NULL REFERENCES CX_SECURITY_DOMAINS(SECURITY_DOMAIN_ID), "
        "OWNER_PRINCIPAL_ID VARCHAR(128) NOT NULL REFERENCES CX_PRINCIPALS(PRINCIPAL_ID), "
        "VERSION INTEGER NOT NULL CHECK(VERSION>0), CURRENT_REVISION_NO INTEGER NOT NULL CHECK(CURRENT_REVISION_NO>0), "
        "STATUS VARCHAR(24) NOT NULL CHECK(STATUS IN ('ACTIVE','RETIRED')), CREATED_AT TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL)",
        "CREATE TABLE CX_WORK_NOTE_REVISIONS (NOTE_ID VARCHAR(128) NOT NULL REFERENCES CX_WORK_NOTES(NOTE_ID), "
        "REVISION_NO INTEGER NOT NULL CHECK(REVISION_NO>0), NOTE_TYPE VARCHAR(24) NOT NULL "
        "CHECK(NOTE_TYPE IN ('FINDING','REJECTED_APPROACH','VALIDATION','OPEN_QUESTION','NEXT_ACTION')), "
        f"TITLE {body} NOT NULL, BODY_TEXT {body} NOT NULL, CONTENT_DIGEST VARCHAR(64) NOT NULL, EXPIRES_AT TIMESTAMP, "
        "CREATED_BY VARCHAR(128) NOT NULL REFERENCES CX_PRINCIPALS(PRINCIPAL_ID), REASON VARCHAR(1000) NOT NULL, "
        "CREATED_AT TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL, PRIMARY KEY(NOTE_ID,REVISION_NO))",
        "CREATE TABLE CX_WORK_NOTE_SOURCES (NOTE_ID VARCHAR(128) NOT NULL, REVISION_NO INTEGER NOT NULL, "
        "ITEM_NO INTEGER NOT NULL CHECK(ITEM_NO>0), FAMILY VARCHAR(24) NOT NULL, ENTITY_ID VARCHAR(128) NOT NULL, "
        "SOURCE_REVISION_ID VARCHAR(128) NOT NULL, CONTENT_DIGEST VARCHAR(64) NOT NULL, PRIMARY KEY(NOTE_ID,REVISION_NO,ITEM_NO), "
        "FOREIGN KEY(NOTE_ID,REVISION_NO) REFERENCES CX_WORK_NOTE_REVISIONS(NOTE_ID,REVISION_NO))",
        "CREATE TABLE CX_WORK_NOTE_EVENTS (NOTE_ID VARCHAR(128) NOT NULL REFERENCES CX_WORK_NOTES(NOTE_ID), "
        "VERSION INTEGER NOT NULL CHECK(VERSION>0), REVISION_NO INTEGER NOT NULL, "
        "OPERATION VARCHAR(24) NOT NULL CHECK(OPERATION IN ('CREATE','REVISE','STATE')), "
        "STATUS VARCHAR(24) NOT NULL CHECK(STATUS IN ('ACTIVE','RETIRED')), "
        "ACTOR_ID VARCHAR(128) NOT NULL REFERENCES CX_PRINCIPALS(PRINCIPAL_ID), REASON VARCHAR(1000) NOT NULL, "
        "CREATED_AT TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL, PRIMARY KEY(NOTE_ID,VERSION), "
        "FOREIGN KEY(NOTE_ID,REVISION_NO) REFERENCES CX_WORK_NOTE_REVISIONS(NOTE_ID,REVISION_NO))",
        "CREATE TABLE CX_WORK_NOTE_REQUESTS (ACTOR_ID VARCHAR(128) NOT NULL REFERENCES CX_PRINCIPALS(PRINCIPAL_ID), "
        "OPERATION VARCHAR(24) NOT NULL, IDEMPOTENCY_KEY VARCHAR(128) NOT NULL, REQUEST_DIGEST VARCHAR(64) NOT NULL, "
        "NOTE_ID VARCHAR(128) NOT NULL REFERENCES CX_WORK_NOTES(NOTE_ID), VERSION INTEGER NOT NULL, REVISION_NO INTEGER NOT NULL, "
        "PRIMARY KEY(ACTOR_ID,OPERATION,IDEMPOTENCY_KEY), FOREIGN KEY(NOTE_ID,VERSION) REFERENCES CX_WORK_NOTE_EVENTS(NOTE_ID,VERSION))",
    ]


def _utc(value):
    if isinstance(value,str):
        value = datetime.fromisoformat(value.replace('Z','+00:00'))
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _expiry(content):
    if content.expires_at and content.expires_at <= datetime.now(timezone.utc):
        raise ContinuityConflict('EXPIRED','New note content must not already be expired')


def _authorize(tx, actor, root, *, write=False):
    current = tx.query_one("SELECT SECURITY_DOMAIN_ID,OWNER_PRINCIPAL_ID,STATUS FROM CX_WORK_CONTRACTS "
                           "WHERE WORK_CONTRACT_ID=:work",{'work':root['work_contract_id']})
    if not current or current['security_domain_id'] != root['security_domain_id']:
        raise PermissionError('Working note access denied')
    work._authorize(tx,actor,root['security_domain_id'],write=write)
    from .continuity_execution_links import read as read_links
    read_links(tx,actor,root['security_domain_id'],root['work_contract_id'])
    if write:
        if actor not in {root['owner_principal_id'],current['owner_principal_id']}:
            raise PermissionError('Only the note owner or current Work owner may change the note')
        if current['status'] in {'COMPLETED','CANCELLED','EXPIRED'}:
            raise ContinuityConflict('TERMINAL_WORK','Notes on closed Work cannot be changed')
    return current


def _receipt(tx,actor,operation,request,note_id=None):
    row = tx.query_one("SELECT NOTE_ID,VERSION,REVISION_NO,REQUEST_DIGEST FROM CX_WORK_NOTE_REQUESTS "
                       "WHERE ACTOR_ID=:actor AND OPERATION=:operation AND IDEMPOTENCY_KEY=:idem",
                       dict(actor=actor,operation=operation,idem=request.idempotency_key))
    if not row:
        return None
    require_idempotent_request(row['request_digest'],request_digest(actor,operation,request))
    if note_id is not None and row['note_id'] != note_id:
        raise ContinuityConflict('IDEMPOTENCY_CONFLICT','The key belongs to another note')
    return dict(note_id=row['note_id'],version=int(row['version']),revision_no=int(row['revision_no']),replayed=True)


def _record(tx,actor,operation,request,note_id,version,revision,status):
    tx.execute("INSERT INTO CX_WORK_NOTE_EVENTS(NOTE_ID,VERSION,REVISION_NO,OPERATION,STATUS,ACTOR_ID,REASON) "
               "VALUES(:note,:version,:revision,:operation,:status,:actor,:reason)",
               dict(note=note_id,version=version,revision=revision,operation=operation,status=status,actor=actor,reason=request.reason))
    tx.execute("INSERT INTO CX_WORK_NOTE_REQUESTS(ACTOR_ID,OPERATION,IDEMPOTENCY_KEY,REQUEST_DIGEST,NOTE_ID,VERSION,REVISION_NO) "
               "VALUES(:actor,:operation,:idem,:digest,:note,:version,:revision)",dict(actor=actor,operation=operation,
               idem=request.idempotency_key,digest=request_digest(actor,operation,request),note=note_id,version=version,revision=revision))
    identity_api._audit_tx(tx,actor,'WORK_NOTE_'+operation,'WORKING_NOTE',note_id,'ALLOW',request.reason)
    return dict(note_id=note_id,version=version,revision_no=revision,status=status,replayed=False)


def _write(tx,actor,root,revision,content,reason):
    from .continuity_sources import resolve
    for source in content.sources:
        resolve(tx,actor,root['security_domain_id'],source,purpose='WORKING_NOTE')
    tx.execute("INSERT INTO CX_WORK_NOTE_REVISIONS(NOTE_ID,REVISION_NO,NOTE_TYPE,TITLE,BODY_TEXT,CONTENT_DIGEST,EXPIRES_AT,CREATED_BY,REASON) "
               "VALUES(:note,:revision,:kind,:title,:body,:digest,:expiry,:actor,:reason)",dict(note=root['note_id'],revision=revision,
               kind=content.note_type,title=content.title,body=content.body,digest=content_digest(content),
               expiry=content.expires_at.replace(tzinfo=None) if content.expires_at else None,actor=actor,reason=reason))
    for number,source in enumerate(content.sources,1):
        tx.execute("INSERT INTO CX_WORK_NOTE_SOURCES(NOTE_ID,REVISION_NO,ITEM_NO,FAMILY,ENTITY_ID,SOURCE_REVISION_ID,CONTENT_DIGEST) "
                   "VALUES(:note,:revision,:v_item_no,:family,:entity,:source_revision,:digest)",dict(note=root['note_id'],revision=revision,
                   v_item_no=number,family=source.family.value,entity=source.entity_id,source_revision=source.revision_id,digest=source.content_digest))


def create_note(actor,work_id,value):
    request = value if isinstance(value,NewNote) else NewNote.model_validate(value)
    _expiry(request.content)
    def perform(tx):
        current = work._read_work(tx,actor,work_id)
        work._authorize(tx,actor,current['security_domain_id'],write=True)
        # Lock the parent before comparing version or adding a child.
        locked=tx.query_one("SELECT VERSION,STATUS FROM CX_WORK_CONTRACTS WHERE WORK_CONTRACT_ID=:work FOR UPDATE",{'work':work_id})
        prior=_receipt(tx,actor,'CREATE',request)
        if prior:
            existing=tx.query_one("SELECT * FROM CX_WORK_NOTES WHERE NOTE_ID=:note",{'note':prior['note_id']})
            if not existing or existing['work_contract_id']!=work_id:
                raise ContinuityConflict('IDEMPOTENCY_CONFLICT','The key belongs to another Work')
            _authorize(tx,actor,existing)
            return prior
        require_version(int(locked['version']),request.expected_work_version)
        if locked['status'] in {'COMPLETED','CANCELLED','EXPIRED'}:
            raise ContinuityConflict('TERMINAL_WORK','Notes on closed Work cannot be created')
        note_id=work._id('WN')
        root=dict(note_id=note_id,work_contract_id=work_id,security_domain_id=current['security_domain_id'],owner_principal_id=actor)
        tx.execute("INSERT INTO CX_WORK_NOTES(NOTE_ID,WORK_CONTRACT_ID,SECURITY_DOMAIN_ID,OWNER_PRINCIPAL_ID,VERSION,CURRENT_REVISION_NO,STATUS) "
                   "VALUES(:note,:work,:domain,:actor,1,1,'ACTIVE')",dict(note=note_id,work=work_id,domain=current['security_domain_id'],actor=actor))
        _write(tx,actor,root,1,request.content,request.reason)
        return _record(tx,actor,'CREATE',request,note_id,1,1,'ACTIVE')
    return connection.execute_transaction_callback(perform)


def _root(tx,actor,note_id,*,write=False):
    # Match the existing actor -> Work -> child global lock order.
    work._lock_actor(tx,actor)
    locator=tx.query_one("SELECT WORK_CONTRACT_ID FROM CX_WORK_NOTES WHERE NOTE_ID=:note",{'note':note_id})
    if not locator:
        raise PermissionError('Working note access denied')
    tx.query_one("SELECT VERSION FROM CX_WORK_CONTRACTS WHERE WORK_CONTRACT_ID=:work FOR UPDATE",{'work':locator['work_contract_id']})
    root=tx.query_one("SELECT * FROM CX_WORK_NOTES WHERE NOTE_ID=:note"+(' FOR UPDATE' if write else ''),{'note':note_id})
    _authorize(tx,actor,root,write=write)
    return root


def revise_note(actor,note_id,value):
    request=value if isinstance(value,ReviseNote) else ReviseNote.model_validate(value)
    _expiry(request.content)
    def perform(tx):
        root=_root(tx,actor,note_id,write=True)
        prior=_receipt(tx,actor,'REVISE',request,note_id)
        if prior:
            return prior
        require_version(int(root['version']),request.expected_version)
        if root['status']!='ACTIVE':
            raise ContinuityConflict('RETIRED','Retired notes cannot be revised')
        revision=int(root['current_revision_no'])+1
        _write(tx,actor,root,revision,request.content,request.reason)
        tx.execute("UPDATE CX_WORK_NOTES SET VERSION=VERSION+1,CURRENT_REVISION_NO=:revision WHERE NOTE_ID=:note AND VERSION=:expected",
                   dict(note=note_id,revision=revision,expected=request.expected_version))
        return _record(tx,actor,'REVISE',request,note_id,request.expected_version+1,revision,'ACTIVE')
    return connection.execute_transaction_callback(perform)


def change_state(actor,note_id,value):
    request=value if isinstance(value,NoteState) else NoteState.model_validate(value)
    def perform(tx):
        root=_root(tx,actor,note_id,write=True)
        prior=_receipt(tx,actor,'STATE',request,note_id)
        if prior:
            return prior
        require_version(int(root['version']),request.expected_version)
        if root['status']==request.status:
            raise ContinuityConflict('UNCHANGED_STATE','The note already has this status')
        if root['status']!='ACTIVE' or request.status!='RETIRED':
            raise ContinuityConflict('INVALID_TRANSITION','Retired notes cannot be reactivated')
        tx.execute("UPDATE CX_WORK_NOTES SET VERSION=VERSION+1,STATUS=:status WHERE NOTE_ID=:note",
                   dict(note=note_id,status=request.status))
        return _record(tx,actor,'STATE',request,note_id,request.expected_version+1,int(root['current_revision_no']),request.status)
    return connection.execute_transaction_callback(perform)


def _read_note(tx,actor,note_id,revision=None,*,consume=False):
    root=_root(tx,actor,note_id)
    selected=int(root['current_revision_no']) if revision is None else revision
    if isinstance(selected,bool) or not isinstance(selected,int) or selected<1:
        raise ValueError('A canonical positive revision is required')
    params=dict(note=note_id,revision=selected)
    record=tx.query_one("SELECT * FROM CX_WORK_NOTE_REVISIONS WHERE NOTE_ID=:note AND REVISION_NO=:revision",params)
    if not record:
        raise ContinuityConflict('REVISION_UNAVAILABLE','The exact note revision is unavailable')
    sources=tx.query("SELECT FAMILY,ENTITY_ID,SOURCE_REVISION_ID AS REVISION_ID,CONTENT_DIGEST FROM CX_WORK_NOTE_SOURCES "
                     "WHERE NOTE_ID=:note AND REVISION_NO=:revision ORDER BY ITEM_NO",params)
    text=lambda value: value.read() if hasattr(value,'read') else value
    content=NoteContent(note_type=record['note_type'],title=text(record['title']),body=text(record['body_text']),
                        sources=sources,expires_at=_utc(record.get('expires_at')))
    if content_digest(content)!=record['content_digest']:
        raise ContinuityError('INTEGRITY_ERROR','Stored note revision failed integrity validation')
    expired=bool(content.expires_at and content.expires_at<=datetime.now(timezone.utc))
    if consume and (expired or root['status']!='ACTIVE'):
        raise ContinuityConflict('EXPIRED' if expired else 'RETIRED','The note is not available for new context use')
    sources_available=True
    from .continuity_sources import resolve
    for source in content.sources:
        try:
            resolve(tx,actor,root['security_domain_id'],source,purpose='WORKING_NOTE')
        except (PermissionError,ContinuityConflict):
            sources_available=False
            if consume:
                raise
    return dict(root,revision_no=selected,content=content.model_dump(mode='json') if sources_available else None,
                content_digest=record['content_digest'],content_unavailable=None if sources_available else 'SOURCE_AUTHORITY_CHANGED',
                expired=expired,available_for_context=not expired and root['status']=='ACTIVE' and sources_available)


def read_note(actor,note_id,revision=None):
    return connection.execute_transaction_callback(lambda tx:_read_note(tx,actor,note_id,revision))


def list_notes(actor,work_id,*,limit=20,after=''):
    if isinstance(limit,bool) or not isinstance(limit,int) or not 1<=limit<=100:
        raise ValueError('limit must be between 1 and 100')
    if not isinstance(after,str) or len(after)>128:
        raise ValueError('after exceeds the supported size')
    def perform(tx):
        parent=tx.query_one("SELECT SECURITY_DOMAIN_ID FROM CX_WORK_CONTRACTS WHERE WORK_CONTRACT_ID=:work",{'work':work_id})
        if not parent:
            raise PermissionError('Working note access denied')
        work._authorize(tx,actor,parent['security_domain_id'],write=False)
        from .continuity_execution_links import read as read_links
        read_links(tx,actor,parent['security_domain_id'],work_id)
        sql=("SELECT NOTE_ID,OWNER_PRINCIPAL_ID,STATUS,VERSION,CURRENT_REVISION_NO FROM CX_WORK_NOTES "
             "WHERE WORK_CONTRACT_ID=:work")
        params=dict(work=work_id,lim=limit+1)
        # An absent cursor is not a comparison value: Oracle treats '' as NULL,
        # so binding it to NOTE_ID > :after_id hides every first-page row.
        if after:
            sql+=" AND NOTE_ID>:after_id"
            params['after_id']=after
        rows=tx.query(sql+" ORDER BY NOTE_ID FETCH FIRST :lim ROWS ONLY",params)
        # Oracle and YashanDB return unquoted identifiers in uppercase while
        # PostgreSQL commonly returns lowercase. The HTTP contract is
        # lower-case JSON across all adapters; normalize before pagination so
        # the continuation cursor and UI note ids are portable.
        rows=_normalise_rows(rows)
        return dict(items=rows[:limit],next_after=rows[limit-1]['note_id'] if len(rows)>limit else None)
    return connection.execute_transaction_callback(perform)


def resolve_note(tx,actor,domain,source):
    if not source.revision_id.isascii() or not source.revision_id.isdecimal() or str(int(source.revision_id))!=source.revision_id:
        raise ContinuityError('INVALID_REVISION','Working note revisions require canonical positive integers')
    record=_read_note(tx,actor,source.entity_id,int(source.revision_id),consume=True)
    if record['security_domain_id']!=domain:
        raise PermissionError('Working notes require their original domain')
    if record['content_digest']!=source.content_digest:
        raise ContinuityConflict('STALE_CONTENT','The exact note digest does not match')
    from .continuity_sources import _render
    return dict(source=source.model_dump(mode='json'),text=_render(record['content']),
                content_digest=record['content_digest'],authorized_scope=domain)
