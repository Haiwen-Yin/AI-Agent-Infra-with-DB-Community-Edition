"""Immutable approval bindings shared by bounded platform mutations."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Any

from . import identity_api


class ApprovalRequired(PermissionError):
    pass


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=True,
                                     separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def request(actor: str, action_type: str, binding: dict[str, Any], reason: str) -> dict[str, Any]:
    if not action_type.startswith("PLATFORM_") or not reason.strip():
        raise ValueError("A platform action and reason are required")
    payload = {"binding": binding, "binding_digest": digest(binding), "requested_by": actor,
               "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat()}
    return identity_api.create_action_card(actor, "CH_PLATFORM_ADMINISTRATION", action_type, payload, reason,
        "GOVERNED:" + digest({"actor": actor, "type": action_type, "payload": payload}))


def _business_read_channel_tx(tx: Any, channel_id: str, domain_id: str) -> None:
    """A read-call approval retains its original business boundary."""
    channel = tx.query_one('SELECT SECURITY_DOMAIN_ID,STATUS,CHANNEL_TYPE FROM CX_CHANNELS '
                           'WHERE CHANNEL_ID=:channel FOR UPDATE', {'channel': channel_id})
    if (not channel or channel['status'] != 'ACTIVE' or channel['security_domain_id'] != domain_id
            or channel['channel_type'] == 'SYSTEM_PROTECTED'):
        raise ApprovalRequired('The approval Channel must remain active in the original Security Domain')
    domain = tx.query_one('SELECT STATUS FROM CX_SECURITY_DOMAINS WHERE SECURITY_DOMAIN_ID=:domain FOR UPDATE',
                          {'domain': domain_id})
    if not domain or domain['status'] != 'ACTIVE':
        raise ApprovalRequired('The original approval Security Domain is unavailable')


def require_tx(tx: Any, action_id: str, action_type: str, binding: dict[str, Any],
               required_action: str, *, expected_channel: str = 'CH_PLATFORM_ADMINISTRATION') -> dict[str, Any]:
    business = expected_channel != 'CH_PLATFORM_ADMINISTRATION'
    if business and (action_type != 'PLATFORM_MODEL_READ_TOOL_CALL' or required_action != 'actions.propose'
            or binding.get('approval_channel_id') != expected_channel or binding.get('impact') != 'READ'
            or not binding.get('security_domain_id') or not binding.get('principal_id')):
        raise ApprovalRequired('Only the exact governed read-call binding may use a business Channel')
    if not action_id:
        raise ApprovalRequired("An independently approved Action Card is required")
    raw = tx.query_one("SELECT ACTION_ID,ACTION_TYPE,CHANNEL_ID,PROPOSED_BY,DECIDED_BY,STATUS,PAYLOAD_JSON "
                       "FROM CX_ACTION_CARDS WHERE ACTION_ID=:id FOR UPDATE", {"id": action_id})
    row = {str(key).lower(): value for key, value in (raw or {}).items()}
    if (row.get("status") != "CONFIRMED" or row.get("action_type") != action_type
            or row.get("channel_id") != expected_channel):
        raise ApprovalRequired("Matching confirmed Action Card is required")
    try:
        raw_payload = row['payload_json']
        if hasattr(raw_payload, 'read'):
            raw_payload = raw_payload.read()
        payload = raw_payload if isinstance(raw_payload, dict) else json.loads(raw_payload)
        expiry = datetime.fromisoformat(payload["expires_at"])
        valid = (expiry.tzinfo is not None and expiry > datetime.now(timezone.utc)
                 and payload["binding"] == binding and payload["binding_digest"] == digest(binding)
                 and payload["requested_by"] == row["proposed_by"])
    except (KeyError, ValueError, TypeError):
        valid = False
    if not valid:
        raise ApprovalRequired("Approval binding changed or expired; request approval again")
    if not row.get("decided_by") or row["decided_by"] == row["proposed_by"]:
        raise ApprovalRequired("An independent Human approval is required")
    if business:
        if row['proposed_by'] != binding['principal_id']:
            raise ApprovalRequired('The business approval must retain its original Agent')
        _business_read_channel_tx(tx, expected_channel, binding['security_domain_id'])
    for principal, action in ((row["proposed_by"], required_action), (row["decided_by"], "channels.actions.decide")):
        identity = tx.query_one("SELECT PRINCIPAL_TYPE,STATUS FROM CX_PRINCIPALS WHERE PRINCIPAL_ID=:id FOR UPDATE", {"id": principal})
        identity = {str(key).lower(): value for key, value in (identity or {}).items()}
        if identity.get("status") != "ACTIVE" or (principal == row["decided_by"] and identity.get("principal_type") != "HUMAN"):
            raise ApprovalRequired("Approval principal is inactive or is not a Human approver")
        if identity_api.effective_access(principal, action).get("decision") != "ALLOW":
            raise ApprovalRequired("Approval principal authority was revoked")
        if business:
            if principal == row['proposed_by'] and identity.get('principal_type') != 'AGENT':
                raise ApprovalRequired('The original business requester must remain an Agent')
            domain = binding['security_domain_id']
            member = tx.query_one('SELECT PRINCIPAL_ID FROM CX_DOMAIN_MEMBERS WHERE SECURITY_DOMAIN_ID=:domain '
                "AND PRINCIPAL_ID=:principal AND STATUS='ACTIVE' AND (VALID_UNTIL IS NULL OR VALID_UNTIL>CURRENT_TIMESTAMP) FOR UPDATE",
                {'domain': domain, 'principal': principal})
            channel_member = tx.query_one('SELECT MEMBER_ID FROM CX_CHANNEL_MEMBERS WHERE CHANNEL_ID=:channel '
                "AND PRINCIPAL_ID=:principal AND STATUS='ACTIVE' AND (VALID_UNTIL IS NULL OR VALID_UNTIL>CURRENT_TIMESTAMP) FOR UPDATE",
                {'channel': expected_channel, 'principal': principal})
            if not member or not channel_member:
                raise ApprovalRequired('Both approval participants must retain their original Channel and Domain membership')
            if identity_api.effective_access(principal, action, resource={'security_domain_id': domain}).get('decision') != 'ALLOW':
                raise ApprovalRequired('The approval participant no longer has authority in the original Domain')
            identity_api._assert_channel_member(principal, expected_channel,
                'channels.write' if principal == row['proposed_by'] else action, transaction=tx)
        else:
            identity_api._assert_channel_member(principal, expected_channel, action)
    return row
