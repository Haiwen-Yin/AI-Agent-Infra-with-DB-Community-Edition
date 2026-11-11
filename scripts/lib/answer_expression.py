"""Server-owned evidence expression limits, not a fact-verification engine.

This projection adds no business records and no model calls. Source content and
source-supplied flags cannot declare a calibrated probability or a passed check.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

REVISION = 'evidence-expression-v3'


def _instant(value):
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return parsed.astimezone(timezone.utc) if parsed.tzinfo is not None else None
    except (ValueError, OverflowError):
        return None


def applicability(intake, assessed_at):
    """Compare declared timezone-aware bounds, never infer an event timestamp."""
    now = _instant(assessed_at)
    start, end = (_instant(intake.get(key)) for key in ('effective_from', 'effective_until'))
    if (now is None or (intake.get('effective_from') is not None and start is None)
            or (intake.get('effective_until') is not None and end is None)
            or (start is not None and end is not None and start >= end)):
        return 'UNKNOWN'
    if end is not None and now >= end:
        return 'EXPIRED'
    if start is not None and now < start:
        return 'NOT_YET_EFFECTIVE'
    if start is not None:
        return 'WITHIN_DECLARED_INTERVAL'
    return 'UNKNOWN'


def contract(sources, retrieval, *, omitted=0):
    """Bind expression constraints to the final authorized reference window."""
    evidence = retrieval.get('evidence_decision') or {}
    references = []
    for index, item in enumerate(sources, 1):
        context = item.get('source_context') or {}
        intake = context.get('intake') or {}
        references.append(dict(
            citation=index, entity_id=item.get('entity_id'), digest=item.get('digest'),
            revision_id=item.get('revision_id'),
            origin='AUTHORIZED_REFERENCE_NOT_FACT_CERTIFICATION',
            declared_decision_status=intake.get('decision_status') or 'UNDECLARED',
            effective_from=intake.get('effective_from'), effective_until=intake.get('effective_until'),
            applicability_at_assessment=applicability(intake, retrieval.get('assessed_at')),
            time_meaning='DECLARED_APPLICABILITY_NOT_EVENT_OR_COLLECTION_TIME',
        ))
    return dict(
        revision=REVISION, probability_calibration='UNAVAILABLE',
        assessment_time_utc=retrieval.get('assessed_at'),
        answer_correctness_probability=None, rank_is_confidence=False,
        citation_meaning='EXACT_REFERENCE_NOT_CLAIM_VERIFICATION',
        coverage_meaning='LOCATION_OR_UNASSESSED_NOT_FACT_VERIFICATION',
        conflict_assessment=str(evidence.get('contradiction_method') or 'UNASSESSED'),
        omitted_reference_count=omitted, references=references,
        required_distinctions=['SOURCE_STATEMENT', 'LOCAL_PROJECTION', 'CALCULATION',
                               'CONDITIONAL_INFERENCE', 'PROPOSAL', 'UNKNOWN', 'CONFLICT'],
        unknown_meaning='UNAVAILABLE_IN_THIS_EVIDENCE_NOT_ZERO_OR_PROVIDER_ABSENCE',
        recommendation_meaning='NOT_APPROVAL_ASSIGNMENT_OR_EXECUTION',
        publication_screening='BOUNDED_RULES_NOT_SEMANTIC_VERIFICATION',
        action_outcome_screening='EXPLICIT_MISSING_RECEIPT_AND_CATEGORICAL_NEGATIVE_ONLY',
    )


# Deliberately bounded to answer/self confidence declarations. Ordinary numeric
# source facts, incident percentages, and source statistical intervals survive.
_NUMBER = r'(?:100|[0-9]{1,2})(?:\.[0-9]+)?\s*(?:%|％|percent\b)'
_SELF_CONFIDENCE = re.compile(
    rf'\bI\s+am\s+{_NUMBER}\s+(?:confident|certain|sure)\b'
    rf'|\b(?:my|our|this\s+answer(?:\x27s)?|this\s+response(?:\x27s)?)\s+'
    rf'(?:confidence|certainty)(?:\s+(?:level|score))?\s*(?:is|of|:|=)?\s*{_NUMBER}'
    rf'|(?:本(?:次)?回答|这(?:个|次)?(?:答案|回答)|我的(?:判断|回答|结论))'
    rf'[^。！\n]{{0,16}}(?:置信度|可信度|确信程度|确定性)\s*(?:为|是|[:：=])?\s*{_NUMBER}'
    rf'|(?:^|\n)\s*(?:\*\*)?(?:置信度|Confidence)(?:\*\*)?\s*[:：=]\s*{_NUMBER}',
    re.I,
)


_NUMERIC_REFERENCE = re.compile(r'(?<![\\!])\[(\d{1,3}(?:\s*[,，–-]\s*\d{1,3})*)\]')
_CODE = re.compile(r'(`{3,}[\s\S]*?`{3,}|`[^`\n]*`)')


def invalid_references(reply, policy):
    """Bound numeric prose markers to this exact window; code is not citation prose.

    This checks reference existence only, never whether a reference supports the
    adjacent claim. Small bracketed numeric lists/ranges are treated as markers.
    """
    allowed = {item['citation'] for item in policy.get('references', [])}
    invalid = set()
    for index, part in enumerate(_CODE.split(reply)):
        if index % 2:
            continue
        for match in _NUMERIC_REFERENCE.finditer(part):
            numbers = [int(value) for value in re.findall(r'\d+', match[1])]
            if re.search(r'[–-]', match[1]):
                # A range is supported only when its complete inclusive span is.
                if len(numbers) != 2 or numbers[0] > numbers[1]:
                    invalid.add(match[0])
                    continue
                numbers = range(numbers[0], numbers[1] + 1)
            if any(value not in allowed for value in numbers):
                invalid.add(match[0])
    return sorted(invalid)


_MISSING_ACTION_RECEIPT = re.compile(
    r'\bno\s+(?:execution|verification|completion)(?:\s+or\s+(?:execution|verification|completion))?\s+'
    r'(?:receipt|record|evidence)s?\b'
    r'|(?:没有|缺少|缺乏|无)(?:执行|验收|完成)(?:或(?:执行|验收|完成))?(?:记录|回执|证据)', re.I)
_NEGATIVE_ACTION_OUTCOME = re.compile(
    r'\b(?:has|have)\s+not\s+(?:succeeded|been\s+(?:completed|executed))\b'
    r'|\b(?:did|does)\s+not\s+succeed\b'
    r'|\b(?:was|is)\s+not\s+(?:completed|executed|successful)\b'
    r'|尚未完成|(?:尚未|并未|没有|未)(?:成功|执行)(?!记录|回执|证据)', re.I)


def unsupported_negative_outcome(reply, planned):
    """Conservative lexical withholding, never a semantic outcome verdict.

    Read only the final authorized extracts. Missing receipts can coexist with
    other evidence; this rule cannot resolve that situation and quotes sources
    instead. Neither source flags nor this result certify an action's outcome.
    """
    sources = planned.get('reference_extracts') or []
    if not any(_MISSING_ACTION_RECEIPT.search(item['content']) for item in sources):
        return False
    return any(_NEGATIVE_ACTION_OUTCOME.search(part)
               for index, part in enumerate(_CODE.split(reply)) if index % 2 == 0)


def _reference_fallback(planned, *, missing_receipt=False):
    notice = (
        '生成回答对操作结果作出确定判断，但本次授权原文记载缺少执行或验收记录，已暂缓展示该生成回答。'
        '此有限措辞检查不能确认操作成功、失败或未发生。以下仅为授权原文摘录，请核对实际执行记录。 / '
        'The generated answer was withheld because it asserted an action outcome while an authorized source '
        'reported missing execution or verification records. This bounded wording check cannot establish '
        'success, failure or non-execution. The following are authorized source extracts only; check actual execution records.'
    ) if missing_receipt else (
        '生成回答包含与本次授权资料不匹配的引用标号，已暂缓展示该生成回答。'
        '以下仅为本次授权资料原文摘录，不代表已核验事实或解决冲突；请核对原始资料。 / '
        'The generated answer was withheld because a reference marker did not match this authorized reference window. '
        'The following are source extracts only, not verified facts or a resolution of conflicting claims. '
        'Review the original references.'
    )
    extracts = planned.get('reference_extracts') or []
    if not extracts:
        return notice
    # Preserve source words as quoted data, without inventing a replacement
    # answer or assigning a nonexistent marker to another source.
    return notice + '\n\n' + '\n\n'.join(
        '[' + str(item['citation']) + ']\n' + '\n'.join('> ' + line for line in item['content'].split('\n'))
        for item in extracts
    )


def screen(reply, planned):
    """Withhold bounded reference, confidence and missing-receipt outcome matches.

    A nonmatch is UNASSESSED, never proof of factual correctness. Call before
    publication, after transport completion; do not retry or alter raw evidence.
    """
    policy = planned.get('answer_expression_contract') or {}
    if (policy.get('revision') != REVISION or planned.get('knowledge_reply') is not None
            or not reply):
        return reply
    if invalid_references(reply, policy):
        return _reference_fallback(planned)
    if unsupported_negative_outcome(reply, planned):
        return _reference_fallback(planned, missing_receipt=True)
    if not _SELF_CONFIDENCE.search(reply):
        return reply
    return (
        '本次生成包含没有校准依据的回答置信度数值，已暂缓展示该回答。'
        '检索排序和引用不能证明回答正确概率；请核对原始资料后重新提问。 / '
        'This generated answer was withheld because it stated an uncalibrated numerical answer confidence. '
        'Retrieval rank and citations do not establish a probability of correctness. '
        'Review the original references before making another request.'
    )
