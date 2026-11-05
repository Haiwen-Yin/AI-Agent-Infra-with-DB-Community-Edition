"""Inspect and serialize the final native Provider request exactly once."""
from __future__ import annotations

import hashlib
import json

from . import answer_context, content_security


def prepare(value, *, managed_images=False):
    """Inspect final text fields, bound image envelopes, retain byte identity.

    This extends existing deterministic rules to tools/schema/Provider fields.
    Image pixels are not semantically inspected and no DLP guarantee is made.
    The caller must send the returned bytes without subsequent transformation.
    """
    try:
        payload, budget = answer_context.final_payload(value)
        content_security.inspect_messages(payload['messages'], allow_managed_images=managed_images)
        raw = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode('utf-8')
        if len(raw) > (6000000 if managed_images else content_security.MAX_BYTES):
            raise content_security.ContentDenied({'code': 'CONTENT_TOO_LARGE'})
        # Inspect all final JSON text fields together, including message extras,
        # tools, schemas, model name and verified Provider parameters. Managed
        # image URLs were validated above; omit only their opaque base64 bytes.
        inspected = payload
        if managed_images:
            inspected = dict(payload, messages=[dict(message, content=[
                dict(part, image_url=dict(part['image_url'], url='MANAGED_PNG_BYTES_SEPARATELY_BOUNDED'))
                if part.get('type')=='image_url' else part for part in message['content']])
                if isinstance(message.get('content'),list) else message for message in payload['messages']])
        check = content_security.enforce(json.dumps(inspected, ensure_ascii=False, allow_nan=False), 'AGENT_PROMPT')
        receipt = dict(schema='final-provider-input/v1', stage='FINAL_SERIALIZED_PROVIDER_JSON',
            request_sha256=hashlib.sha256(raw).hexdigest(), byte_count=len(raw),
            ruleset_digest=check['ruleset_digest'], decision=check['decision'],
            managed_image_pixels_inspected=False,
            scope='FINAL_JSON_TEXT_AND_BOUNDED_MANAGED_IMAGES' if managed_images else 'FINAL_JSON_TEXT',
            usage='NOT_PROVIDER_REPORTED_USAGE')
        return payload, raw, budget, receipt
    except (ValueError, KeyError, TypeError) as exc:
        exc.model_not_dispatched = True
        raise
