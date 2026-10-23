"""Bounded, inspectable evidence decisions independent of retrieval rank."""
from __future__ import annotations

import re
from datetime import datetime, timezone

POLICY_REVISION = "answer-evidence-v1"

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
    return bool(re.search(r"(?<![a-z0-9_])" + re.escape(token) + r"(?![a-z0-9_])", text)) if token.isascii() else token in text


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
        if any(term in _FACETS[facet] for facet in facets):
            continue
        # Chinese questions lack whitespace. Strip only a recognized trailing
        # attribute and its possessive separator, retaining the whole subject.
        for facet in facets:
            for alias in _FACETS[facet]:
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


def assess(question, candidates):
    """Select usable evidence conservatively without consulting rank scores."""
    from .knowledge_grounding import _search_terms
    terms = _search_terms(question)
    query = question.casefold()
    company = any(_contains(query, alias) for alias in _COMPANY_ALIASES)
    facets = [key for key, aliases in _FACETS.items() if any(_contains(query, alias) for alias in aliases)]
    subject_terms = _subject_terms(question, terms, facets)
    years = sorted(set(re.findall(r"\b(?:19|20)\d{2}\b", query)))
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
        elif company:
            same_subject = any(_contains(text, alias) for alias in _COMPANY_ALIASES)
            company_title = any(_contains(title, alias) for alias in _COMPANY_ALIASES)
            direct_claim = bool(re.search(r"\boracle\s+(?:(?:was|is)\s+)?(?:founded|headquarters|revenue|employees)\b", text))
            same_subject = same_subject or direct_claim
            if not same_subject or (_INTEGRATION.search(title) and not _COMPANY_FACT.search(text)):
                reason = "SUBJECT_MISMATCH"
            elif not company_title and not _COMPANY_FACT.search(text):
                reason = "SUBJECT_EVIDENCE_INSUFFICIENT"
        elif subject_terms and not all(_supports_term(text, term) for term in subject_terms):
            reason = "SUBJECT_OR_CLAIM_UNSUPPORTED"
        if reason:
            rejected.append({"entity_id": item["entity_id"], "reason": reason})
            continue
        supported_facets = [facet for facet in facets if any(_contains(text, alias) for alias in _FACETS[facet])]
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
