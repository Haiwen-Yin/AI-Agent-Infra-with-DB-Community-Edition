"""Explicit curator-supplied document snapshots on existing Source entities.

The reserved content-addressed URN is not a remote-fetch claim or a filesystem
path. This synchronous import commits exact source revisions, pending candidates
and the existing source checkpoint together. Independent review and promotion
remain mandatory; no model, scheduler, new authority store or publication runs.
"""
from __future__ import annotations

import hashlib
import re
from typing import Annotated,Literal

from pydantic import Field,StrictBool,StrictInt,model_validator

from . import connection,agent_source_sync as sync,continuity_candidates as candidates
from .agent_extension_contracts import bounded_json,digest,identifier
from .continuity_contracts import Contract,Identifier,Reason,KnowledgeIntake,NewCandidate
from .continuity_state import ContinuityConflict,ContinuityError

URN_PREFIX='urn:chuanxu:curated:sha256:'
Hash=Annotated[str,Field(pattern=r'^[0-9a-f]{64}$')]


def manifest_id(endpoint):
    match=re.fullmatch(re.escape(URN_PREFIX)+r'([0-9a-f]{64})',endpoint)
    return match[1] if match else None


class Origin(Contract):
    locator:Annotated[str,Field(min_length=1,max_length=500)]
    revision:Annotated[str,Field(min_length=1,max_length=256)]
    parent_sha256:Hash
    parent_char_count:Annotated[StrictInt,Field(ge=1,le=1048576)]
    start:Annotated[StrictInt,Field(ge=0)]
    end:Annotated[StrictInt,Field(ge=1)]
    decision_status:Literal['CURRENT','PROPOSED','HISTORICAL','REJECTED','SUPERSEDED']
    context_reviewed:StrictBool
    context_note:Annotated[str,Field(min_length=3,max_length=2000)]


class Document(Contract):
    path:Annotated[str,Field(min_length=1,max_length=500)]
    title:Annotated[str,Field(min_length=1,max_length=500)]
    text:Annotated[str,Field(min_length=1,max_length=4000)]
    content_type:Literal['text/plain','text/markdown']='text/markdown'
    origin:Origin
    intake:KnowledgeIntake | None=None

    @model_validator(mode='after')
    def exact_span(self):
        sync.validate_path(self.path)
        value=self.origin
        if (not self.text.strip() or not value.context_reviewed or value.end>value.parent_char_count
                or value.end-value.start!=len(self.text)):
            raise ValueError('An explicitly reviewed complete source unit and exact character span are required')
        if value.start==0 and value.end==value.parent_char_count:
            if hashlib.sha256(self.text.encode()).hexdigest()!=value.parent_sha256:
                raise ValueError('The complete parent document digest differs')
        if self.intake and self.intake.decision_status!=value.decision_status:
            raise ValueError('Intake must retain the original decision status')
        return self


class Import(Contract):
    expected_version:Annotated[StrictInt,Field(ge=1)]
    documents:Annotated[tuple[Document,...],Field(min_length=1,max_length=50)]
    reason:Reason
    idempotency_key:Identifier

    @model_validator(mode='after')
    def bounded(self):
        if len({item.path for item in self.documents})!=len(self.documents):
            raise ValueError('Curated source paths must be unique')
        bounded_json(self.model_dump(mode='json'),maximum=1048576)
        return self


def source_payload(document):
    return document.model_dump(mode='json',exclude={'intake'})


def manifest_digest(documents):
    return digest([source_payload(item) for item in documents])


def import_documents(actor,source_id,value):
    request=Import.model_validate(value)
    expected=manifest_digest(request.documents)
    def perform(tx):
        source=sync._configuration(tx,sync._source(tx,actor,source_id,write=True))
        if source['source_kind']!='DOCUMENT' or manifest_id(source['endpoint'])!=expected:
            raise ContinuityConflict('CURATED_MANIFEST_MISMATCH','The exact configured curator manifest is required')
        if int(source['row_version'])!=request.expected_version:
            raise ContinuityConflict('SOURCE_STATE_CONFLICT','The configured source version changed')
        if (set(item.path for item in request.documents)!=set(source['paths'])
                or any(item.content_type not in source['types'] for item in request.documents)
                or sum(len(item.text.encode()) for item in request.documents)>int(source['max_bytes'])):
            raise ValueError('Curated documents differ from their configured paths, types or byte limit')
        prior=sync._receipt(tx,actor,'SOURCE_CURATED_IMPORT',request,source_id)
        imported=[]
        for document in request.documents:
            payload=source_payload(document)
            version='curated:v1:'+digest(payload)
            content_hash=hashlib.sha256(document.text.encode()).hexdigest()
            revision=tx.query_one('SELECT REVISION_ID,LIFECYCLE_STATE FROM CX_AGENT_SOURCE_REVISIONS '
                'WHERE SOURCE_ID=:source AND SOURCE_VERSION=:version AND SOURCE_PATH=:path AND CONTENT_DIGEST=:digest',
                dict(source=source_id,version=version,path=document.path,digest=content_hash))
            if revision and revision['lifecycle_state']!='AVAILABLE':
                raise PermissionError('A retired curated source revision cannot be reactivated')
            revision_id=revision['revision_id'] if revision else identifier('SR')
            if not revision:
                tx.execute('INSERT INTO CX_AGENT_SOURCE_REVISIONS(REVISION_ID,SOURCE_ID,SOURCE_VERSION,SOURCE_PATH,TITLE,CONTENT_DIGEST,CONTENT_CIPHER,LIFECYCLE_STATE) '
                    "VALUES(:revision,:source,:version,:path,:title,:digest,:cipher,'AVAILABLE')",
                    dict(revision=revision_id,source=source_id,version=version,path=document.path,title=document.title,
                        digest=content_hash,cipher=sync.encrypt_section(dict(text=document.text,curated=payload))))
            reference=dict(family='SOURCE',entity_id=source_id,revision_id=revision_id,content_digest=content_hash)
            proposal=NewCandidate.model_validate(dict(security_domain_id=source['security_domain_id'],
                content=dict(family='KNOWLEDGE',title=document.title,body=document.text),sources=[reference],
                intake=document.intake.model_dump(mode='json') if document.intake else None,
                reason='Curator-supplied exact source; independent review and explicit promotion required',
                idempotency_key='curated:'+digest([source_id,revision_id,document.intake.model_dump(mode='json') if document.intake else None])))
            candidate=candidates._create_candidate(tx,actor,proposal)
            imported.append(dict(source=reference,candidate_id=candidate['candidate_id']))
        if not prior:
            tx.execute('UPDATE CX_AGENT_SOURCES SET CURRENT_REVISION_ID=:revision,CHECKPOINT_DIGEST=:checkpoint WHERE SOURCE_ID=:source',
                dict(source=source_id,revision=imported[-1]['source']['revision_id'],checkpoint=expected))
        receipt=prior or sync._record(tx,actor,'SOURCE_CURATED_IMPORT',request,source_id,
            request.expected_version,target=source_id)
        return dict(receipt,imports=imported,manifest_digest=expected,automatic_publication=False,
            provenance='CURATOR_SUPPLIED_NOT_REMOTE_FETCHED')
    return connection.execute_transaction_callback(perform)


def verify_snapshot(record,stored):
    """Metadata/body binding is verified on every exact curated source read."""
    document=Document.model_validate(stored.get('curated'))
    if (stored.get('text')!=document.text or record['source_version']!='curated:v1:'+digest(source_payload(document))
            or record['source_path']!=document.path or record['title']!=document.title):
        raise ContinuityError('INTEGRITY_ERROR','Curated source provenance failed integrity validation')
    return dict(document.origin.model_dump(mode='json'),method='CURATOR_SUPPLIED_NOT_REMOTE_FETCHED')
