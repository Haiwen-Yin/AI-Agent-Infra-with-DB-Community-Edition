"""Historical seeds remain valid after the supported product publication lifecycle.

SQLite executes the actual read predicates here; native migration-ledger and
checksum validation remain separate gates and are not simulated as acceptance.
"""
from pathlib import Path
import sqlite3

import pytest

import migration_runner as runner


@pytest.fixture
def seeds():
    db = sqlite3.connect(':memory:')
    db.executescript('''
        CREATE TABLE ENTITIES(ENTITY_ID INTEGER,ENTITY_TYPE TEXT,TITLE TEXT,CONTENT TEXT,STATUS TEXT,VISIBILITY TEXT);
        CREATE TABLE KNOWLEDGE_META(ENTITY_ID INTEGER,ENTITY_TYPE TEXT);
    ''')
    texts = ('database-authoritative enterprise platform', 'Portal checks both principals',
        'Humans and Agents are governed principals', 'Chuanxu governs Agent Pool assignment',
        'Unified entities and edges preserve', 'This database adapter provides')
    for number, text in enumerate(texts, 1):
        db.execute('INSERT INTO ENTITIES VALUES(?,?,?,?,?,?)',
            (number, 'KNOWLEDGE', '川序 v4.4.13 section ' + str(number), text, 'ACTIVE', 'PUBLIC'))
        db.execute('INSERT INTO KNOWLEDGE_META VALUES(?,?)', (number, 'KNOWLEDGE'))
    try:
        yield db
    finally:
        db.close()


@pytest.mark.parametrize('database', ['pg', 'oracle', 'yashandb'])
@pytest.mark.parametrize('status', ['ACTIVE', 'ARCHIVED'])
@pytest.mark.parametrize('step', ['80_v4_4_13_portal_builtin_knowledge.sql', '81_v4_4_13_portal_bilingual_knowledge.sql'])
def test_supported_retirement_preserves_historical_migration_completeness(seeds, database, status, step):
    seeds.execute('UPDATE ENTITIES SET STATUS=?', (status,))
    assert runner._step_objects_complete(seeds.cursor(), database, Path(step), version='5.0.2')


@pytest.mark.parametrize('step', ['80_v4_4_13_portal_builtin_knowledge.sql', '81_v4_4_13_portal_bilingual_knowledge.sql'])
@pytest.mark.parametrize('mutation', ['missing', 'private', 'invalid_status', 'foreign_type', 'wrong_title'])
def test_retirement_does_not_allow_missing_or_ineligible_seed_rows(seeds, step, mutation):
    seeds.execute("UPDATE ENTITIES SET STATUS='ARCHIVED'")
    statements = {
        'missing': 'DELETE FROM ENTITIES WHERE ENTITY_ID=1',
        'private': "UPDATE ENTITIES SET VISIBILITY='PRIVATE' WHERE ENTITY_ID=1",
        'invalid_status': "UPDATE ENTITIES SET STATUS='REVOKED' WHERE ENTITY_ID=1",
        'foreign_type': "UPDATE ENTITIES SET ENTITY_TYPE='MEMORY' WHERE ENTITY_ID=1",
        'wrong_title': "UPDATE ENTITIES SET TITLE='Unrelated Knowledge' WHERE ENTITY_ID=1",
    }
    seeds.execute(statements[mutation])
    assert not runner._step_objects_complete(seeds.cursor(), 'pg', Path(step), version='5.0.2')


def test_archived_seed_still_requires_original_knowledge_metadata(seeds):
    seeds.execute("UPDATE ENTITIES SET STATUS='ARCHIVED'")
    seeds.execute('DELETE FROM KNOWLEDGE_META WHERE ENTITY_ID=1')
    assert not runner._step_objects_complete(seeds.cursor(), 'pg', Path('80_v4_4_13_portal_builtin_knowledge.sql'), version='5.0.2')


def test_archived_bilingual_seed_still_requires_english_content(seeds):
    seeds.execute("UPDATE ENTITIES SET STATUS='ARCHIVED'")
    seeds.execute("UPDATE ENTITIES SET CONTENT='Only unrelated text' WHERE ENTITY_ID=1")
    assert not runner._step_objects_complete(seeds.cursor(), 'pg', Path('81_v4_4_13_portal_bilingual_knowledge.sql'), version='5.0.2')
