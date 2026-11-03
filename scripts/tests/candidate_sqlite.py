"""SQLite-only normalized candidate metadata for portable query unit tests."""
from types import SimpleNamespace


def adapter():
    return SimpleNamespace(intake_value=lambda column,field:"json_extract("+column+", '$."+field+"')",
        artifact_entity_join=lambda native,entity:native+'=CAST('+entity+' AS VARCHAR(128))',
        intake_instant=lambda value:'julianday('+value+')')


def schema(database):
    if 'CREATED_AT' not in {row[1].upper() for row in database.execute('PRAGMA table_info(ENTITIES)')}:
        database.execute('ALTER TABLE ENTITIES ADD COLUMN CREATED_AT TEXT')
    database.executescript('''
        CREATE TABLE CX_CONTINUITY_ARTIFACTS(ARTIFACT_ID TEXT,FAMILY TEXT,SECURITY_DOMAIN_ID TEXT,
          STATUS TEXT,CURRENT_REVISION_ID TEXT);
        CREATE TABLE CX_CONTINUITY_ARTIFACT_REVS(ARTIFACT_ID TEXT,NATIVE_ENTITY_ID TEXT,REVISION_ID TEXT,
          CANDIDATE_ID TEXT,CANDIDATE_REVISION_NO INT,CONTENT_DIGEST TEXT);
        CREATE TABLE CX_KNOWLEDGE_INTAKE(CANDIDATE_ID TEXT,REVISION_NO INT,METADATA_JSON TEXT);
    ''')
