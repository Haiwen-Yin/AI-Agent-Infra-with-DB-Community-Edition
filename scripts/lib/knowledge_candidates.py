"""Native candidate diversity and primary applicability before channel limits.

Only authorized input rows enter this query. Equal reviewed title/body and
declared scope follow distinct facts in the bounded pool. Alternative exact
sources remain available when original-source reauthorization rejects a copy.
Final selection removes redundant bodies after that reauthorization. Conflicts,
distinct applicability and exact graph endpoints remain distinct.
"""
from datetime import datetime

from . import knowledge_retrieval_adapter as native

FIELDS = ('applicable_product', 'applicable_version', 'decision_status', 'effective_from',
          'effective_until', 'classification', 'audience', 'subject', 'responsible_principal_id', 'purpose')


def artifact_entity_join(native_column, entity_column):
    """Exact native pointer equality shared by scope and candidate queries."""
    return native.artifact_entity_join(native_column, entity_column)


def query(base, params, *, ordering='DESC', suffix, bound=None, deduplicate=True):
    if ordering not in {'ASC', 'DESC'}:
        raise ValueError('Invalid internal candidate ordering')
    values = {field: native.intake_value('cx_ci.METADATA_JSON', field) for field in FIELDS}
    joined = (' FROM (' + base + ') cx_c JOIN ENTITIES cx_e ON cx_e.ENTITY_ID=cx_c.ENTITY_ID '
        "AND cx_e.ENTITY_TYPE='KNOWLEDGE' LEFT JOIN CX_CONTINUITY_ARTIFACT_REVS cx_cr "
        'ON ' + artifact_entity_join('cx_cr.NATIVE_ENTITY_ID', 'cx_c.ENTITY_ID') + ' '
        'LEFT JOIN CX_CONTINUITY_ARTIFACTS cx_ca ON cx_ca.ARTIFACT_ID=cx_cr.ARTIFACT_ID '
        "AND cx_ca.FAMILY='KNOWLEDGE' AND cx_ca.STATUS='ACTIVE' "
        'LEFT JOIN CX_KNOWLEDGE_INTAKE cx_ci ON cx_ci.CANDIDATE_ID=cx_cr.CANDIDATE_ID '
        'AND cx_ci.REVISION_NO=cx_cr.CANDIDATE_REVISION_NO AND cx_ca.ARTIFACT_ID IS NOT NULL')
    # Each revision keeps its own immutable declaration. Historical revision
    # reads remain possible; explicit current-domain discovery already narrows
    # roots in the authorized base query. Retired roots cannot borrow a grant.
    predicates = ['(cx_cr.ARTIFACT_ID IS NULL OR cx_ca.ARTIFACT_ID IS NOT NULL)']
    bound = bound or {}
    if bound.get('product'):
        params['candidate_product'] = bound['product']
        predicates.append(values['applicable_product'] + '=:candidate_product')
    version = values['applicable_version']
    normalized = "CASE WHEN LOWER(SUBSTR(" + version + ",1,1))='v' AND SUBSTR(" + version + ",2,1) BETWEEN '0' AND '9' THEN SUBSTR(" + version + ',2) ELSE ' + version + ' END'
    if bound.get('versions'):
        params.update({'candidate_version' + str(i): value for i, value in enumerate(bound['versions'])})
        allowed = ','.join(':candidate_version' + str(i) for i in range(len(bound['versions'])))
        match = '(' + normalized + ') IN (' + allowed + ')'
        predicates.append('(' + version + ' IS NULL OR ' + match + ')' if not bound.get('version') else match)
    if bound.get('decision_statuses'):
        params.update({'candidate_status' + str(i): value for i, value in enumerate(bound['decision_statuses'])})
        predicates.append(values['decision_status'] + ' IN (' + ','.join(':candidate_status' + str(i)
            for i in range(len(bound['decision_statuses']))) + ')')
    if bound.get('as_of'):
        # Native adapters normalize explicit offsets. Missing effective time
        # cannot satisfy an exact applicability instant.
        instant = datetime.fromisoformat(bound['as_of'].replace('Z', '+00:00')).isoformat()
        params['candidate_as_of'] = instant
        now = native.intake_instant(':candidate_as_of')
        predicates.extend([values['effective_from'] + ' IS NOT NULL',
            native.intake_instant(values['effective_from']) + '<=' + now,
            '(' + values['effective_until'] + ' IS NULL OR ' + native.intake_instant(values['effective_until']) + '>' + now + ')'])
    joined += ' WHERE ' + ' AND '.join(predicates)
    order = ' ORDER BY CHANNEL_SCORE ' + ordering + ',ENTITY_ID'
    if not deduplicate:
        return 'SELECT cx_c.ENTITY_ID,cx_c.CHANNEL_SCORE' + joined + ' ORDER BY cx_c.CHANNEL_SCORE ' + ordering + ',cx_c.ENTITY_ID' + suffix
    partition = ['COALESCE(cx_cr.CONTENT_DIGEST,CAST(cx_c.ENTITY_ID AS VARCHAR(128)))',
        'cx_ca.SECURITY_DOMAIN_ID', *values.values()]
    return ('SELECT ENTITY_ID,CHANNEL_SCORE FROM (SELECT cx_c.ENTITY_ID,cx_c.CHANNEL_SCORE,'
        'ROW_NUMBER() OVER (PARTITION BY ' + ','.join(partition) +
        ' ORDER BY cx_e.CREATED_AT,cx_c.ENTITY_ID) AS CX_DUPLICATE_SLOT' + joined +
        ') cx_unique ORDER BY CX_DUPLICATE_SLOT,CHANNEL_SCORE ' + ordering + ',ENTITY_ID' + suffix)


def signature(item):
    context = item.get('source_context') or {}
    intake = context.get('intake')
    if not isinstance(intake, dict):
        return ('exact', item['entity_id'])
    def scope(current, depth=0):
        if depth >= 16:
            raise ValueError('Excessive source applicability lineage')
        metadata = current.get('intake') or {}
        return (tuple(metadata.get(field) for field in FIELDS),
            tuple((entry.get('origin') or {}).get('decision_status') for entry in current.get('provenance') or ()),
            tuple(scope(entry.get('source_context') or {}, depth + 1) for entry in current.get('derived_sources') or ()))
    return ('reviewed', item.get('title'), item.get('content'), scope(context))


def distinct(items, *, preserve_ids=()):
    seen = set()
    result = []
    for item in items:
        key = ('exact', item['entity_id']) if item['entity_id'] in preserve_ids else signature(item)
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result
