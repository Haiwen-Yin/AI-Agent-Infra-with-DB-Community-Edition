"""Native NUMBER revisions retain exact Channel source integrity."""
from copy import deepcopy
from decimal import Decimal

import pytest

from lib import native_runtime


class SourceRows:
    def __init__(self, revision):
        self.source = dict(principal_id='human', body_text='Authorized source text',
            thread_type='CHANNEL', thread_id=None, reference_json='{"mentions":["agent"]}',
            redacted_at=None, message_type='TEXT')
        self.policy = dict(policy_id='DEFAULT', mode='KNOWLEDGE_FIRST',
            allow_model_supplement='Y', disclosure_profiles_json='["profile"]', version=revision)

    def query_one(self, statement, parameters):
        assert statement.startswith('SELECT ')
        if 'FROM CX_CHANNEL_MESSAGES ' in statement:
            assert parameters == dict(message_id='message', channel_id='channel')
            return deepcopy(self.source)
        assert 'FROM CX_PORTAL_KNOWLEDGE_POLICY ' in statement and parameters == {}
        return deepcopy(self.policy)


PAYLOAD = dict(channel_dispatch=dict(kind='BUSINESS_MENTION', channel_id='channel',
    message_id='message', requester_principal_id='human', thread_type='CHANNEL', thread_id=''))


@pytest.mark.parametrize('revision', [Decimal('1'), Decimal('1.000'), Decimal('12')])
def test_native_number_policy_revision_matches_integer_digest(revision):
    decimal_rows, integer_rows = SourceRows(revision), SourceRows(int(revision))
    before = deepcopy(decimal_rows.policy)
    assert native_runtime._runtime_channel_source(decimal_rows, PAYLOAD) == native_runtime._runtime_channel_source(integer_rows, PAYLOAD)
    assert decimal_rows.policy == before


def test_channel_source_digest_still_detects_policy_and_message_changes():
    rows = SourceRows(Decimal('1'))
    original = native_runtime._runtime_channel_source(rows, PAYLOAD)
    rows.policy['version'] = Decimal('2')
    assert native_runtime._runtime_channel_source(rows, PAYLOAD) != original
    rows.policy['version'] = Decimal('1')
    rows.policy['disclosure_profiles_json'] = '["different-profile"]'
    assert native_runtime._runtime_channel_source(rows, PAYLOAD) != original
    rows.policy['disclosure_profiles_json'] = '["profile"]'
    rows.source['body_text'] = 'Changed source text'
    assert native_runtime._runtime_channel_source(rows, PAYLOAD) != original


@pytest.mark.parametrize('revision', [None, True, False, '1', 1.0, 0, -1,
    Decimal('0'), Decimal('1.5'), Decimal('NaN'), Decimal('Infinity')])
def test_invalid_policy_revision_never_produces_source_digest(revision):
    with pytest.raises(PermissionError, match='policy revision is invalid'):
        native_runtime._runtime_channel_source(SourceRows(revision), PAYLOAD)


def test_revision_normalization_does_not_bypass_source_identity():
    rows = SourceRows(Decimal('1'))
    rows.source['redacted_at'] = '2026-10-31T00:00:00Z'
    with pytest.raises(PermissionError, match='message is no longer current'):
        native_runtime._runtime_channel_source(rows, PAYLOAD)
