"""Bounded whole-reference selection for the shared answer path.

Dropping an entire reference is observable. Cutting arbitrary prose cannot
establish that a prerequisite, exception, table or contradictory clause survived.
Selection receipts measure prepared messages. Dispatch separately bounds the
final serialized Provider payload; neither receipt is Provider-reported usage.
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar

from . import context_selection
from .continuity_state import ContinuityConflict


DEFAULT_TOKEN_BUDGET = 32768
DEFAULT_OUTPUT_RESERVE = 4096
DEFAULT_BYTE_BUDGET = 131072
_dispatch_budget = ContextVar('answer_dispatch_budget', default=None)


@contextmanager
def dispatch_budget(selection):
    """Carry a server-prepared answer budget to its exact Provider send.

    This is a bound, never disclosure authority. The transport still rechecks
    the original Profile, credential and current source permissions. Reset on
    every exit so an unrelated request cannot inherit another answer's budget.
    Older frozen inputs without a selection retain their original contract.
    """
    limits=None
    if selection is not None:
        if (not isinstance(selection,dict) or selection.get('policy_revision')!='whole-reference-v1'
                or selection.get('stage')!='PREPARED_ANSWER_MESSAGES'):
            raise ValueError('Invalid prepared answer budget')
        budget=selection.get('budget') or {}
        limits={key:budget.get(key) for key in ('token_budget','byte_budget','output_reserve')}
        for key,value in limits.items():
            if type(value) is not int or not 1<=value<=16777216:
                raise ValueError('Invalid answer budget '+key)
        if limits['output_reserve']>32768:
            raise ValueError('Invalid answer output reserve')
    token=_dispatch_budget.set(limits)
    try:
        yield
    finally:
        _dispatch_budget.reset(token)


def final_payload(payload):
    """Bound the exact JSON after transport conversion/verified parameters.

    No prompt clipping or source selection occurs at this stage. A failure is
    known-no-send. The receipt measures serialized input, not Provider usage.
    """
    limits=_dispatch_budget.get()
    if limits is None:
        return payload,None
    try:
        reserve=limits['output_reserve']
        if 'max_tokens' in payload and payload['max_tokens']!=reserve:
            raise ContinuityConflict('ANSWER_OUTPUT_BUDGET_MISMATCH',
                'The final Provider output limit differs from the prepared answer reserve')
        bounded={**payload,'max_tokens':reserve}
        receipt=context_selection.provider_contract_budget({},base_payload=bounded,
            model_name=str(payload.get('model') or ''),**limits)
    except (ValueError,ContinuityConflict) as exc:
        exc.model_not_dispatched=True
        raise
    return bounded,dict(receipt,stage='FINAL_PROVIDER_JSON',
        scope='SERIALIZED_INPUT_NOT_PROVIDER_REPORTED_USAGE',ranking_generation_calls=0)


def groups(items, retrieval):
    """Keep reported conflict sets and relationship endpoints together."""
    positions = {str(item['entity_id']): index for index, item in enumerate(items)}
    roots = list(range(len(items)))

    def root(index):
        while roots[index] != index:
            index = roots[index]
        return index

    def join(keys):
        indexes = [positions[str(key)] for key in keys if str(key) in positions]
        for index in indexes[1:]:
            roots[root(index)] = root(indexes[0])

    for conflict in (retrieval.get('evidence_decision') or {}).get('contradictions') or []:
        join(conflict.get('source_ids') or [])
    for link in retrieval.get('relationships') or []:
        join([link.get('source_entity_id'), link.get('target_entity_id')])
    result = {}
    for index in range(len(items)):
        result.setdefault(root(index), []).append(index)
    return list(result.values())


def select(items, retrieval, render, *, token_budget=DEFAULT_TOKEN_BUDGET,
           byte_budget=DEFAULT_BYTE_BUDGET, output_reserve=DEFAULT_OUTPUT_RESERVE,
           model_name=''):
    """Select bounded complete sources in retrieval order without a model call.

    ``render`` includes instructions, question, metadata and citations before
    measuring. Try later, smaller groups after one fails; never silently clip
    the failed group. Count omissions in the rendered boundary as well.
    """
    def measure(planned):
        messages = planned['messages'] or [{'role': 'assistant', 'content': planned['knowledge_reply']}]
        return context_selection.provider_contract_budget({}, token_budget=token_budget,
            byte_budget=byte_budget, model_name=model_name, base_payload={'messages': messages},
            output_reserve=output_reserve if planned['messages'] else 0)

    selected = set()
    # The complete input must at least accommodate the question/instructions
    # and explicit omission boundary. A failure must stop before dispatch.
    planned = render([], len(items))
    receipt = measure(planned)
    for group in groups(items, retrieval):
        candidate = selected | set(group)
        chosen = [item for index, item in enumerate(items) if index in candidate]
        attempt = render(chosen, len(items) - len(chosen))
        try:
            candidate_receipt = measure(attempt)
        except ContinuityConflict as exc:
            if exc.code not in {'PROVIDER_INPUT_EXCEEDS_BYTE_BUDGET', 'PROVIDER_INPUT_EXCEEDS_TOKEN_BUDGET'}:
                raise
            continue
        selected, planned, receipt = candidate, attempt, candidate_receipt
    count, method = context_selection.counter(model_name)
    representations = [dict(entity_id=item['entity_id'], content_digest=item.get('digest'),
        representation='COMPLETE' if index in selected else 'OMITTED',
        reason='COMPLETE_REFERENCE' if index in selected else 'COMPLETE_GROUP_EXCEEDS_BUDGET',
        original_bytes=len(str(item.get('content') or '').encode('utf-8')),
        original_tokens=count(str(item.get('content') or '')))
        for index, item in enumerate(items)]
    planned['context_selection'] = dict(stage='PREPARED_ANSWER_MESSAGES',
        scope='NOT_FINAL_PROVIDER_PAYLOAD_OR_REPORTED_USAGE', policy_revision='whole-reference-v1',
        budget=receipt, representations=representations, count_method=method,
        ranking_generation_calls=0, omitted_count=len(items) - len(selected))
    return planned
