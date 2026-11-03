"""Bounded, inspectable evidence decisions independent of retrieval rank."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from . import answer_query, knowledge_applicability

POLICY_REVISION = "answer-evidence-v4"

# These identity aliases describe a single subject, never a search permission.
_COMPANY_ALIASES = ("oracle corporation", "oracle corp", "甲骨文公司", "甲骨文")
_SUBJECT_ALIASES = (
    ("chuanxu", "川序"), ("postgresql", "postgres", "pg"),
    ("yashandb", "崖山数据库"), ("oracle corporation", "oracle corp", "甲骨文公司", "甲骨文"),
)
_INTEGRATION = re.compile(r"川序|chuanxu|适配|集成|integration|connector|adapter", re.I)
_COMPANY_FACT = re.compile(r"成立|创立|总部|营收|收入|雇员|员工|founded|headquarters|revenue|employees", re.I)
_FACETS = {
    "deployment": ("部署", "安装", "deployment", "deploy", "installation", "install"),
    "revenue": ("收入", "营收", "revenue"),
    "headquarters": ("总部", "headquarters"),
    "founding": ("成立", "创立", "founded", "founding"),
    "security": ("安全", "security"),
}


def _contains(text, token):
    return answer_query.supports_term(text, token)


def subject_aliases(question):
    """Return one unambiguous known subject for bounded conjunction handling."""
    lowered = question.casefold()
    matches = [aliases for aliases in _SUBJECT_ALIASES if any(_contains(lowered, alias) for alias in aliases)]
    return matches[0] if len(matches) == 1 else ()


def _supports_term(text, term):
    if _contains(text, term):
        return True
    for aliases in (*_SUBJECT_ALIASES, *(_FACETS[key] for key in _FACETS)):
        if term in aliases:
            return any(_contains(text, alias) for alias in aliases)
    return False


def _subject_terms(question, terms, facets):
    """Separate recognized requested attributes from the entity identifier."""
    result = []
    for term in terms:
        if any(term in _FACETS.get(facet, ()) for facet in facets):
            continue
        # Chinese questions lack whitespace. Strip only a recognized trailing
        # attribute and its possessive separator, retaining the whole subject.
        for facet in facets:
            for alias in _FACETS.get(facet, ()):
                if not alias.isascii():
                    term = re.sub(r"(?:的|如何|怎么|怎样)?" + re.escape(alias) + r"(?:情况|信息|说明|方式|流程)?$", "", term)
                    term = re.sub(r"^(?:如何|怎么|怎样)" + re.escape(alias), "", term)
        if term:
            result.append(term)
    return result


def _expired(item):
    now = datetime.now(timezone.utc)
    for key, future_invalid in (("expires_at", False), ("valid_until", False), ("valid_from", True)):
        value = item.get(key)
        if not value:
            continue
        try:
            date = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            date = date.replace(tzinfo=date.tzinfo or timezone.utc)
        except (ValueError, TypeError):
            return True
        invalid = date > now if future_invalid else date <= now
        if invalid:
            return True
    return False


def _conflicts(items):
    """Recognize explicit conflicting attribute statements; do not infer truth.

    Other disagreements remain unassessed, which is recorded in the decision.
    Content instructions cannot set trusted conflict or confidence flags.
    """
    claims = {}
    for item in items:
        body = str(item.get("content") or "")
        for attribute, pattern in (
            ("headquarters", r"(?:headquarters(?:\s+(?:is|are|in))?|总部(?:位于|在|是)?)\s*[:：]?\s*([^。.;\n]{2,100})"),
            ("revenue", r"(?:revenue|营收|收入)\s*(?:is|为|是)?\s*[:：]?\s*([0-9][^。;\n]{0,80})"),
        ):
            for match in re.finditer(pattern, body, re.I):
                value = re.sub(r"\s+", " ", match.group(1)).strip().casefold()
                temporal_scope = tuple(sorted(set(re.findall(r"\b(?:19|20)\d{2}\b", match.group(0)))))
                claims.setdefault((attribute, temporal_scope), {}).setdefault(value, set()).add(item["entity_id"])
    return [{"attribute": attribute, "temporal_scope": list(scope),
             "source_ids": sorted({key for ids in values.values() for key in ids})}
            for (attribute, scope), values in claims.items() if len(values) > 1
            and len({key for ids in values.values() for key in ids}) > 1]


def assess(question, candidates, *, relationships=()):
    """Select usable evidence conservatively without consulting rank scores."""
    interpretation = answer_query.interpret(question)
    if interpretation.requirements:
        return _assess_requirements(interpretation,candidates,relationships)
    terms = interpretation.terms
    query = question.casefold()
    company = any(_contains(query, alias) for alias in _COMPANY_ALIASES)
    facets = [key for key, aliases in _FACETS.items() if any(_contains(query, alias) for alias in aliases)]
    facets = list(dict.fromkeys([*facets, *interpretation.attributes]))
    subject_terms = _subject_terms(question, terms, facets)
    years = [qualifier.value for qualifier in interpretation.qualifiers if qualifier.kind == "year"]
    selected, rejected = [], []
    coverage = {key: [] for key in facets}
    for item in candidates:
        title = str(item.get("title") or "").casefold()
        text = title + "\n" + str(item.get("content") or "").casefold()
        reason = None
        if _expired(item):
            reason = "OUTSIDE_VALIDITY"
        elif years and not all(_contains(text, year) for year in years):
            reason = "TEMPORAL_SCOPE_UNSUPPORTED"
        elif not all(answer_query.supports_qualifier(text, qualifier) for qualifier in interpretation.qualifiers):
            reason = "QUERY_QUALIFIER_UNSUPPORTED"
        elif company:
            same_subject = any(_contains(text, alias) for alias in _COMPANY_ALIASES)
            company_title = any(_contains(title, alias) for alias in _COMPANY_ALIASES)
            direct_claim = bool(re.search(r"\boracle\s+(?:(?:was|is)\s+)?(?:founded|headquarters|revenue|employees)\b", text))
            same_subject = same_subject or direct_claim
            if not same_subject or (_INTEGRATION.search(title) and not _COMPANY_FACT.search(text)):
                reason = "SUBJECT_MISMATCH"
            elif not company_title and not _COMPANY_FACT.search(text):
                reason = "SUBJECT_EVIDENCE_INSUFFICIENT"
            elif interpretation.frame_candidate:
                residual = interpretation.subject.casefold()
                for alias in sorted(_COMPANY_ALIASES, key=len, reverse=True):
                    residual = re.sub(r"(?<![a-z0-9_])" + re.escape(alias) + r"(?![a-z0-9_])", " ", residual)
                if not all(_supports_term(text, term) for term in answer_query.interpret(residual).terms):
                    reason = "SUBJECT_OR_CLAIM_UNSUPPORTED"
        elif subject_terms and not all(_supports_term(text, term) for term in subject_terms):
            reason = "SUBJECT_OR_CLAIM_UNSUPPORTED"
        if reason:
            rejected.append({"entity_id": item["entity_id"], "reason": reason})
            continue
        supported_facets = [facet for facet in facets if
            (facet == "identity" and bool(str(item.get("content") or "").strip()))
            or (facet == "version" and any(qualifier.kind == "version" for qualifier in answer_query.qualifiers(text)))
            or (facet in _FACETS and any(_contains(text, alias) for alias in _FACETS[facet]))]
        if facets and not supported_facets:
            rejected.append({"entity_id": item["entity_id"], "reason": "REQUESTED_CLAIM_UNSUPPORTED"})
            continue
        selected.append(item)
        for facet in supported_facets:
            coverage[facet].append(item["entity_id"])
    conflicts = _conflicts(selected)
    missing = [facet for facet, source_ids in coverage.items() if not source_ids]
    status = "AMBIGUOUS" if conflicts else "PARTIAL_MATCH" if selected and missing else "MATCHED" if selected else "NO_MATCH"
    return {"status": status, "items": selected, "missing_parts": missing,
            "evidence_decision": {"policy_revision": POLICY_REVISION,
                "subject_type": "COMPANY" if company else "QUERY_TERMS", "status": status,
                "requested_facets": facets, "coverage": coverage, "rejected_sources": rejected,
                "contradictions": conflicts, "contradiction_method": "EXPLICIT_ATTRIBUTES_ONLY",
                "rank_used_as_confidence": False}}


def assess_for_answer(question, candidates, *, relationships=()):
    """Keep authorized references for open questions without declaring support.

    Literal claim location remains useful for explicit factual requests. It
    cannot prove that a paraphrased procedural question has no source. The
    answer path may inspect such references, with coverage explicitly unknown;
    neither their presence nor their retrieval rank establishes a fact.
    Call only after the normal dual-reader source authorization and loading.
    """
    result = assess(question, candidates, relationships=relationships)
    parsed = answer_query.interpret(question)
    lowered = question.casefold()
    natural = bool(re.search(r'如何|怎么|怎样|为什么|是否|能否|哪些|什么|[吗呢][？?]?|'
        r'^\s*(?:how|why|can|could|should|would|does|do|what)\b', lowered))
    factual_company = any(_contains(lowered, alias) for alias in _COMPANY_ALIASES)
    scalar = any(_contains(lowered, alias) for key in ('revenue', 'headquarters', 'founding') for alias in _FACETS[key])
    # Explicit document frames and named-claim lists retain their strict
    # subject/claim contract. A source cannot opt itself into this review mode.
    if (not natural or parsed.framed or parsed.frame_candidate or factual_company or scalar
            or re.search(r'[:：]|https?://|[\n`{}]', question)):
        return result
    present = {item['entity_id'] for item in result['items']}
    provisional = []
    hard_rejections = []
    rejected = {item['entity_id']: item['reason'] for item in result['evidence_decision']['rejected_sources']}
    for item in candidates:
        if item['entity_id'] in present:
            # A source can locate one clause literally while supporting other
            # clauses through paraphrase. Its earlier selection must not turn
            # unlocated natural-language clauses into proven evidence gaps.
            if result['missing_parts']:
                provisional.append(dict(entity_id=item['entity_id'],
                    lexical_reason='LITERAL_COVERAGE_INCOMPLETE',
                    coverage='UNASSESSED_NOT_SUPPORTED', reason='NATURAL_LANGUAGE_REQUIRES_SEMANTIC_REVIEW'))
            continue
        text = str(item.get('title') or '') + '\n' + str(item.get('content') or '')
        if _expired(item):
            hard_rejections.append(dict(entity_id=item['entity_id'], reason='OUTSIDE_VALIDITY'))
            continue
        valid = True
        for qualifier in parsed.qualifiers:
            if qualifier.kind == 'version' and item.get('source_context'):
                # A reviewed applicability declaration is distinct from a
                # literal version in prose. Do not guess a range or date.
                bound = knowledge_applicability.constraints(question)
                valid = knowledge_applicability.matches(item, bound)
            else:
                valid = answer_query.supports_qualifier(text, qualifier)
            if not valid:
                break
        if not valid:
            hard_rejections.append(dict(entity_id=item['entity_id'], reason='QUERY_QUALIFIER_UNSUPPORTED'))
            continue
        provisional.append(dict(entity_id=item['entity_id'],
            lexical_reason=rejected.get(item['entity_id'], 'LITERAL_COVERAGE_UNAVAILABLE'),
            coverage='UNASSESSED_NOT_SUPPORTED', reason='NATURAL_LANGUAGE_REQUIRES_SEMANTIC_REVIEW'))
        present.add(item['entity_id'])
    if not provisional:
        return result
    result['items'] = [item for item in candidates if item['entity_id'] in present]
    decision = result['evidence_decision']
    conflicts = _conflicts(result['items'])
    decision['contradictions'] = [*decision['contradictions'], *[item for item in conflicts if item not in decision['contradictions']]]
    result['status'] = 'AMBIGUOUS' if decision['contradictions'] else 'PARTIAL_MATCH'
    decision.update(status=result['status'], semantic_review=dict(status='REQUIRED',
        candidates=provisional, meaning='AUTHORIZED_REFERENCES_NOT_VERIFIED_CLAIM_SUPPORT',
        rank_used_as_confidence=False), rejected_sources=hard_rejections)
    result['missing_parts'] = list(dict.fromkeys([*result['missing_parts'], 'SEMANTIC_EVIDENCE_REVIEW']))
    return result


def _assess_requirements(request,candidates,relationships=()):
    """Locate arbitrary explicit requested claims across qualified sources.

    Lexical coverage locates evidence; it does not prove a value, a procedural
    prerequisite, or a recommendation. Rank and caller-provided flags never
    establish coverage. Unknown claims remain missing rather than disappear.
    """
    coverage={claim:[] for claim in request.requirements}
    selected,rejected=[],[]
    values={}
    related=_relation_coverage(request,candidates,relationships)
    for item in candidates:
        text=str(item.get('title') or '')+'\n'+str(item.get('content') or '')
        direct_subject=all(_supports_term(text,term) for term in request.subject_terms)
        reason=None
        if _expired(item):
            reason='OUTSIDE_VALIDITY'
        elif not all(answer_query.supports_qualifier(text,value) for value in request.qualifiers):
            reason='QUERY_QUALIFIER_UNSUPPORTED'
        elif not direct_subject and not any(item['entity_id'] in keys for keys in related.values()):
            reason='SUBJECT_OR_CLAIM_UNSUPPORTED'
        supported=[claim for claim in coverage if item['entity_id'] in related.get(claim,[]) or
            (direct_subject and all(_supports_term(text,term) for term in answer_query.claim_terms(claim)))] if reason is None else []
        if reason or not supported:
            rejected.append(dict(entity_id=item['entity_id'],reason=reason or 'REQUESTED_CLAIM_UNSUPPORTED'))
            continue
        selected.append(item)
        for claim in supported:
            coverage[claim].append(item['entity_id'])
            # Only explicit labelled scalar statements are compared. Complex
            # prose and inferred disagreement remain unassessed, never a pass.
            pattern=re.compile(re.escape(claim)+r'\s*(?:[:：=]|\bis\b|\bare\b|为|是)\s*([^\n。;；|]{1,160})',re.I)
            for match in pattern.finditer(str(item.get('content') or '')):
                value=re.sub(r'\s+',' ',match[1]).strip().rstrip('.').casefold()
                if value:
                    values.setdefault(claim,{}).setdefault(value,set()).add(item['entity_id'])
    conflicts=_conflicts(selected)
    for claim,claims in values.items():
        source_ids=sorted({key for identifiers in claims.values() for key in identifiers})
        if len(claims)>1 and len(source_ids)>1:
            conflicts.append(dict(attribute=claim,temporal_scope=[],source_ids=source_ids))
    missing=[claim for claim,identifiers in coverage.items() if not identifiers]
    status='AMBIGUOUS' if conflicts else 'PARTIAL_MATCH' if selected and missing else 'MATCHED' if selected else 'NO_MATCH'
    return dict(status=status,items=selected,missing_parts=missing,evidence_decision=dict(
        policy_revision=POLICY_REVISION,subject_type='EXPLICIT_REQUEST',status=status,
        requested_facets=list(request.requirements),coverage=coverage,rejected_sources=rejected,
        contradictions=conflicts,contradiction_method='EXPLICIT_LABELLED_CLAIMS_ONLY',
        coverage_meaning='CLAIM_LOCATION_NOT_FACT_VERIFICATION',rank_used_as_confidence=False))


def _relation_coverage(request,candidates,relationships):
    """Only explicit outgoing relation requests can use native edge evidence.

    The separate server-supplied relation contract includes exact source bytes;
    content flags, scores or a neighbor mentioning the query cannot supply it.
    Link semantics never become verified execution or supersession facts.
    """
    kinds={
        'related sources':None,'relationships':None,'关联资料':None,'关联关系':None,'相关知识':None,
        'dependencies':{'DEPENDS_ON','DEPENDENCY'},'dependency':{'DEPENDS_ON','DEPENDENCY'},'依赖':{'DEPENDS_ON','DEPENDENCY'},
        '依赖关系':{'DEPENDS_ON','DEPENDENCY'},
        'lineage':{'DERIVED_FROM','CITES','SOURCE_OF'},'来源关系':{'DERIVED_FROM','CITES','SOURCE_OF'},
    }
    result={}
    located={str(item['entity_id']):item for item in candidates if not _expired(item)}
    for claim in request.requirements:
        normalized=claim.casefold()
        if normalized not in kinds:
            continue
        allowed=kinds[normalized]
        keys=set()
        for link in relationships:
            origin=located.get(link.get('source_entity_id'));target=located.get(link.get('target_entity_id'))
            if (not origin or not target or link.get('source_digest')!=origin.get('digest')
                    or link.get('target_digest')!=target.get('digest') or not link.get('edge_id') or not link.get('edge_digest')
                    or (allowed is not None and link.get('edge_type') not in allowed)):
                continue
            text=str(origin.get('title') or '')+'\n'+str(origin.get('content') or '')
            target_text=str(target.get('title') or '')+'\n'+str(target.get('content') or '')
            if (all(_supports_term(text,term) for term in request.subject_terms)
                    and all(answer_query.supports_qualifier(text,value) and answer_query.supports_qualifier(target_text,value)
                            for value in request.qualifiers)):
                keys.update((origin['entity_id'],target['entity_id']))
        result[claim]=keys
    return result
