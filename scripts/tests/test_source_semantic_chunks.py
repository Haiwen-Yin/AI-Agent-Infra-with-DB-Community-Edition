"""Source-sync cannot turn a sliced exception into an independent fact."""
import hashlib

import pytest

from lib import agent_source_sync
from lib.continuity_state import ContinuityError


def test_source_import_retains_exact_offsets_tables_code_and_exceptions():
    body=('Scope: Boreal only.\n\n'+'Explanatory paragraph. '*120+'\n\n'
          '| Case | Limit |\n| legal hold | never delete |\n\n'
          '```text\nDo not delete legal holds.\n\nKeep this complete code block.\n```\n\n'
          'Except during an active legal hold, retention is 30 days.\n')
    blocks=agent_source_sync._document_chunks(dict(text=body))
    assert ''.join(block['text'] for block in blocks)==body
    for block in blocks:
        assert block['text']==body[block['start']:block['end']]
        assert hashlib.sha256(block['text'].encode()).hexdigest()==block['digest']
        assert block['text'].count('```')%2==0
    table=next(block for block in blocks if '| legal hold |' in block['text'])
    assert '| Case | Limit |' in table['text']


@pytest.mark.parametrize('body',[
    'Boreal retention limit: 30 days. '+'x'*4200+' Exception: never delete legal holds.',
    '| Case | Limit |\n'+'| legal hold | never delete |\n'*150,
    '```text\n'+'x'*4200+'\n```',
    'Retention: 30 days.\n\n'+('Long explanation. '*180+'\n\n')*2+'Exception: never delete legal holds.',
])
def test_oversized_semantic_source_requires_author_preparation(body):
    with pytest.raises(ContinuityError) as raised:
        agent_source_sync._document_chunks(dict(text=body))
    assert raised.value.code=='SOURCE_CHUNK_REVIEW_REQUIRED'
