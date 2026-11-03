"""Deterministic declared applicability; relevance never supplies missing scope.

Filters constrain authorized evidence, not permissions. Versions are exact
identifiers (a leading numeric ``v`` is cosmetic), not guessed version ranges.
Missing legacy declarations remain unknown, rather than becoming universal.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from .continuity_contracts import KnowledgeRetrievalScope as Scope
from . import answer_query


POLICY = 'declared-applicability-v1'


def _version(value):
    return re.sub(r'^v(?=\d)', '', value.strip(), flags=re.I)


def constraints(query, scope=None):
    """Bind caller filters and explicit question versions before recall.

    A date mentioned in a question may be an event date, not an effective-time
    request. Only the typed ``as_of`` filter selects a validity instant.
    """
    typed = scope if isinstance(scope, Scope) else Scope.model_validate({} if scope is None else scope)
    versions = list(dict.fromkeys(_version(item.value) for item in answer_query.qualifiers(query)
                                  if item.kind == 'version'))
    if typed.version is not None:
        version = _version(typed.version)
        if versions and version not in versions:
            raise ValueError('Question and applicability version disagree')
        versions = [version]
    return dict(policy=POLICY, versions=versions, **typed.model_dump(mode='json', exclude_none=True))


def active(bound):
    return bool(bound['versions'] or bound.get('product') or bound.get('as_of') or bound.get('decision_statuses'))


def _instant(value):
    result = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError('Declared source applicability requires an explicit timezone')
    return result.astimezone(timezone.utc)


def _contexts(root, depth=0):
    if not isinstance(root, dict) or depth >= 16:
        raise ValueError('Invalid or excessive source applicability lineage')
    yield root
    for item in root.get('derived_sources') or ():
        if not isinstance(item, dict) or not isinstance(item.get('source_context'), dict):
            raise ValueError('Invalid source applicability lineage')
        yield from _contexts(item['source_context'], depth + 1)


def matches(item, bound):
    """Check every declared ancestor without changing its exact source text.

    Unknown declarations cannot satisfy explicit structured filters. A legacy
    source may satisfy a question's version using exact literal evidence;
    mentioning another version cannot override a contradictory declaration.
    """
    if not active(bound):
        return True
    contexts = list(_contexts(item['source_context'])) if item.get('source_context') else []
    declared_versions = []
    declarations=0
    status_evidence=0
    for context in contexts:
        # Memory has no separate Knowledge intake. Its unchanged original
        # Knowledge declarations remain available in derived_sources.
        if 'intake' not in context:
            if bound.get('decision_statuses'):
                for provenance in context.get('provenance') or ():
                    if (provenance.get('origin') or {}).get('decision_status') not in bound['decision_statuses']:
                        return False
                    status_evidence+=1
            continue
        declarations+=1
        intake = context.get('intake') or {}
        if not isinstance(intake, dict):
            raise ValueError('Invalid declared source applicability')
        if bound.get('product') and intake.get('applicable_product') != bound['product']:
            return False
        declared = intake.get('applicable_version')
        if declared:
            declared_versions.append(_version(declared))
            if bound['versions'] and _version(declared) not in bound['versions']:
                return False
        elif bound.get('version'):
            return False
        if bound.get('as_of'):
            if not intake.get('effective_from'):
                return False
            instant = _instant(bound['as_of'])
            if instant < _instant(intake['effective_from']):
                return False
            if intake.get('effective_until') and instant >= _instant(intake['effective_until']):
                return False
        allowed = bound.get('decision_statuses')
        if allowed:
            if intake.get('decision_status') not in allowed:
                return False
            status_evidence+=1
            # A summary declaring CURRENT cannot relabel an original proposal.
            for provenance in context.get('provenance') or ():
                origin = provenance.get('origin') or {}
                if origin.get('decision_status') not in allowed:
                    return False
                status_evidence+=1
    if not contexts and any(bound.get(key) for key in ('product', 'version', 'as_of', 'decision_statuses')):
        return False
    if not declarations and any(bound.get(key) for key in ('product','version','as_of')):
        return False
    if bound.get('decision_statuses') and not status_evidence:
        return False
    if bound['versions'] and not declared_versions:
        literal = answer_query.qualifiers(str(item.get('title') or '') + '\n' + str(item.get('content') or ''))
        return any(value.kind == 'version' and _version(value.value) in bound['versions'] for value in literal)
    return True
