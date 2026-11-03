"""Deterministic knowledge quality guidance on existing candidate revisions.

No generation, embedding, publication, or visibility expansion occurs here.
SourceRef authorization is owned by continuity_candidates, including previews.
Metadata is declared applicability and retains unknowns until explicit review.
"""
from __future__ import annotations

import hashlib
import json

from .continuity_contracts import KnowledgeIntake
from .continuity_state import ContinuityConflict, ContinuityError
from . import knowledge_retrieval_adapter as native

MUTABLE = {}
POLICY = 'guided-knowledge-v1'
REQUIRED = ('purpose', 'source_locator', 'responsible_principal_id', 'subject',
            'applicable_product', 'applicable_version', 'effective_from', 'classification', 'audience')


def schema_statements(dialect):
    if dialect not in {'pg', 'postgresql', 'oracle', 'yashandb'}:
        raise ValueError('Unsupported database adapter')
    body = 'TEXT' if dialect in {'pg', 'postgresql'} else 'CLOB'
    return ["CREATE TABLE CX_KNOWLEDGE_INTAKE (CANDIDATE_ID VARCHAR(128) NOT NULL, "
            "REVISION_NO INTEGER NOT NULL CHECK(REVISION_NO>0), POLICY_VERSION VARCHAR(64) NOT NULL, "
            f"METADATA_JSON {body} NOT NULL, METADATA_DIGEST VARCHAR(64) NOT NULL, "
            "PRIMARY KEY(CANDIDATE_ID,REVISION_NO), "
            "FOREIGN KEY(CANDIDATE_ID,REVISION_NO) REFERENCES CX_CANDIDATE_KNOWLEDGE(CANDIDATE_ID,REVISION_NO))"]


def canonical(metadata):
    return json.dumps(metadata.model_dump(mode='json'), ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def write(tx, candidate, revision, metadata):
    if metadata is None:
        return
    body = canonical(metadata)
    tx.execute("INSERT INTO CX_KNOWLEDGE_INTAKE(CANDIDATE_ID,REVISION_NO,POLICY_VERSION,METADATA_JSON,METADATA_DIGEST) "
               "VALUES(:candidate,:revision,:policy,:metadata,:digest)",
               {'candidate': candidate, 'revision': revision, 'policy': POLICY, 'metadata': body,
                'digest': hashlib.sha256(body.encode()).hexdigest()})


def read(tx, candidate, revision):
    row = tx.query_one("SELECT POLICY_VERSION,METADATA_JSON,METADATA_DIGEST FROM CX_KNOWLEDGE_INTAKE "
                       "WHERE CANDIDATE_ID=:candidate AND REVISION_NO=:revision",
                       {'candidate': candidate, 'revision': revision})
    if row is None:
        return None
    raw = row['metadata_json']
    body = raw.read() if hasattr(raw, 'read') else raw
    if row['policy_version'] != POLICY or hashlib.sha256(body.encode()).hexdigest() != row['metadata_digest']:
        raise ContinuityError('INTEGRITY_ERROR', 'Knowledge intake failed integrity validation')
    metadata = KnowledgeIntake.model_validate_json(body)
    if canonical(metadata) != body:
        raise ContinuityError('INTEGRITY_ERROR', 'Knowledge intake is not canonical')
    return metadata


def chunks(body, target=1200):
    """Keep exact paragraphs, fenced code and complete contiguous table rows.

    Large semantic blocks stay whole and are reported for an author to split.
    The 4000-character proposal contract bounds both parsing and returned text.
    Offsets index the submitted Python/Unicode text, including whitespace.
    """
    blocks, start, offset, fence = [], 0, 0, None
    for line in body.splitlines(keepends=True):
        stripped = line.lstrip()
        marker = stripped[:3]
        if marker in {'```', '~~~'}:
            if fence is None:
                fence = marker
            elif marker == fence:
                fence = None
        offset += len(line)
        if not line.strip() and fence is None:
            blocks.append((start, offset))
            start = offset
    if start < len(body):
        blocks.append((start, len(body)))
    spans = []
    for begin, end in blocks:
        if spans and end - spans[-1][0] <= target:
            spans[-1] = (spans[-1][0], end)
        else:
            spans.append((begin, end))
    return [{'number': number, 'start': begin, 'end': end, 'text': body[begin:end],
             'digest': hashlib.sha256(body[begin:end].encode()).hexdigest(),
             'oversize': end - begin > target}
            for number, (begin, end) in enumerate(spans, 1)]


def inspect(payload):
    metadata = payload.intake
    missing = [key for key in REQUIRED if metadata is None or getattr(metadata, key) is None]
    findings = [{'code': 'MISSING_' + key.upper(), 'field': key, 'severity': 'BLOCK_PUBLICATION',
                 'next_step': 'Declare ' + key + ' from an accountable source; keep unknown as a pending candidate.'}
                for key in missing]
    if metadata and metadata.decision_status != 'CURRENT':
        findings.append({'code': 'NONCURRENT_DECISION', 'field': 'decision_status', 'severity': 'NOTICE',
                         'next_step': 'Retain the stated decision status; do not present a proposal or historical decision as current policy.'})
    preview = chunks(payload.content.body)
    if any(item['oversize'] for item in preview):
        findings.append({'code': 'LARGE_SEMANTIC_BLOCK', 'field': 'body', 'severity': 'NOTICE',
                         'next_step': 'Review the whole block; retain table headers, units, conditions and exceptions when splitting.'})
    return {'policy': POLICY, 'publication_eligible': not missing, 'findings': findings, 'chunks': preview,
            'automatic_publication': False, 'audience_applied_by_intake': False,
            'duplicate_check': 'NOT_CHECKED', 'conflict_check': 'NOT_CHECKED'}


def preview(tx, actor, payload):
    """Bounded exact-title comparison with only currently readable live facts.

    A different body is a *possible* conflict; this deterministic check never
    decides which statement is true, which revision supersedes another, or
    whether documents with different titles are duplicates.
    """
    from .knowledge_api import knowledge_access_predicate
    result = inspect(payload)
    rows = tx.query("SELECT e.ENTITY_ID,e.CONTENT FROM ENTITIES e WHERE e.ENTITY_TYPE='KNOWLEDGE' "
                    "AND e.STATUS='ACTIVE' AND (e.EXPIRES_AT IS NULL OR e.EXPIRES_AT>CURRENT_TIMESTAMP) "
                    "AND e.TITLE=:title AND " + knowledge_access_predicate('e', ':actor') +
                    " ORDER BY e.ENTITY_ID" + native.limit_clause(),
                    {'actor': actor, 'title': payload.content.title, 'candidate_limit': 20})
    comparisons = []
    for row in rows:
        from .continuity_promotions import require_original_sources
        try:
            require_original_sources(tx,actor,row['entity_id'])
        except PermissionError:
            continue
        body = row['content'].read() if hasattr(row['content'], 'read') else row['content']
        code = 'POSSIBLE_DUPLICATE' if body == payload.content.body else 'POSSIBLE_CONFLICT'
        comparisons.append({'entity_id': str(row['entity_id']), 'code': code})
    for code in dict.fromkeys(item['code'] for item in comparisons):
        result['findings'].append({'code': code, 'field': 'body', 'severity': 'NOTICE',
            'next_step': 'Compare authorized original revisions and applicability; do not automatically replace or merge content.'})
    result.update(duplicate_check='AUTHORIZED_EXACT_TITLE_MAX20', conflict_check='AUTHORIZED_EXACT_TITLE_MAX20',
                  comparisons=comparisons, exhaustive=False)
    return result


def validate_publication(tx, payload, domain):
    result = inspect(payload)
    if not result['publication_eligible']:
        raise ContinuityConflict('KNOWLEDGE_INTAKE_REQUIRED',
                                 'Complete knowledge applicability and source metadata before approval or promotion')
    metadata = payload.intake
    row = tx.query_one("SELECT CLASSIFICATION FROM CX_SECURITY_DOMAINS WHERE SECURITY_DOMAIN_ID=:domain",
                       {'domain': domain})
    if not row or metadata.classification != row['classification']:
        raise ContinuityConflict('KNOWLEDGE_CLASSIFICATION_MISMATCH',
                                 'Select a security domain matching the declared knowledge classification')
    owner = tx.query_one("SELECT p.PRINCIPAL_ID FROM CX_PRINCIPALS p JOIN CX_DOMAIN_MEMBERS m ON m.PRINCIPAL_ID=p.PRINCIPAL_ID "
                         "WHERE p.PRINCIPAL_ID=:responsible AND p.STATUS='ACTIVE' AND m.SECURITY_DOMAIN_ID=:domain "
                         "AND m.STATUS='ACTIVE' AND (m.VALID_UNTIL IS NULL OR m.VALID_UNTIL>CURRENT_TIMESTAMP)",
                         {'responsible': metadata.responsible_principal_id, 'domain': domain})
    if not owner:
        raise PermissionError('Knowledge requires a currently accountable domain member')
    return result


def require_reviewed_projection(tx,actor,entity_id):
    """No private upload can become shared merely by changing its policy.

    Current artifact identity, exact approved bytes and original sources remain
    authoritative. The caller's transaction owns the policy mutation as well.
    """
    from . import continuity_candidates as candidates, connection
    from .continuity_contracts import KnowledgeProposal, content_digest
    row=tx.query_one("SELECT r.ARTIFACT_ID,r.REVISION_ID,r.CANDIDATE_ID,r.CANDIDATE_REVISION_NO,r.CONTENT_DIGEST "
        "FROM CX_CONTINUITY_ARTIFACT_REVS r JOIN CX_CONTINUITY_ARTIFACTS a ON a.ARTIFACT_ID=r.ARTIFACT_ID "
        "WHERE r.NATIVE_ENTITY_ID=:entity AND a.FAMILY='KNOWLEDGE' AND a.STATUS='ACTIVE' "
        "AND a.CURRENT_REVISION_ID=r.REVISION_ID",{'entity':str(entity_id)})
    if row is None:
        raise ContinuityConflict('KNOWLEDGE_INTAKE_REQUIRED','Shared knowledge requires a current reviewed and promoted intake candidate')
    root=candidates._lock(tx,actor,row['candidate_id'])
    candidates._authority(tx,actor,root['security_domain_id'],'KNOWLEDGE',review=actor!=root['proposed_by'])
    if (root['status']!='APPROVED' or root['result_entity_id']!=row['artifact_id']
            or root['result_revision_id']!=row['revision_id'] or int(root['current_revision_no'])!=int(row['candidate_revision_no'])):
        raise ContinuityConflict('REVIEW_UNAVAILABLE','Sharing requires the current approved projection')
    payload,digest=candidates._read(tx,root)
    review=tx.query_one("SELECT REVIEWER_ID,CONTENT_DIGEST FROM CX_CANDIDATE_REVIEWS WHERE CANDIDATE_ID=:candidate "
        "AND REVISION_NO=:revision AND DECISION='APPROVED'",{'candidate':row['candidate_id'],'revision':row['candidate_revision_no']})
    if not review or review['reviewer_id']==root['proposed_by'] or review['content_digest']!=digest:
        raise ContinuityConflict('REVIEW_UNAVAILABLE','Sharing requires an exact independent approval')
    reviewer=tx.query_one("SELECT p.PRINCIPAL_ID FROM CX_PRINCIPALS p JOIN CX_DOMAIN_MEMBERS m ON m.PRINCIPAL_ID=p.PRINCIPAL_ID "
        "WHERE p.PRINCIPAL_ID=:reviewer AND p.STATUS='ACTIVE' AND m.SECURITY_DOMAIN_ID=:domain AND m.STATUS='ACTIVE' "
        "AND m.MEMBERSHIP_TIER IN ('OWNER','ADMIN') AND (m.VALID_UNTIL IS NULL OR m.VALID_UNTIL>CURRENT_TIMESTAMP)",
        {'reviewer':review['reviewer_id'],'domain':root['security_domain_id']})
    if not reviewer or candidates.identity_api.effective_access(review['reviewer_id'],'knowledge.write',
            resource={'security_domain_id':root['security_domain_id']}).get('decision')!='ALLOW':
        raise PermissionError('The approval no longer has an authorized reviewer')
    candidates._sources(tx,actor,root['security_domain_id'],payload)
    validate_publication(tx,payload,root['security_domain_id'])
    native_id=int(entity_id) if connection.DATABASE_DIALECT in {'pg','postgresql'} else str(entity_id)
    entity=tx.query_one("SELECT TITLE,CONTENT FROM ENTITIES WHERE ENTITY_ID=:entity AND ENTITY_TYPE='KNOWLEDGE' "
        "AND STATUS='ACTIVE' AND (EXPIRES_AT IS NULL OR EXPIRES_AT>CURRENT_TIMESTAMP) FOR UPDATE",{'entity':native_id})
    if entity is None:
        raise PermissionError('Knowledge access denied')
    body=entity['content'].read() if hasattr(entity['content'],'read') else entity['content']
    actual=KnowledgeProposal(family='KNOWLEDGE',title=entity['title'],body=body)
    if content_digest(actual)!=row['content_digest'] or actual!=payload.content:
        raise ContinuityConflict('STALE_CONTENT','The native content no longer matches its approved revision')
    return root
