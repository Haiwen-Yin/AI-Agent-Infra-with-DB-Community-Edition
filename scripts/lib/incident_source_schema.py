"""Add STATUSPAGE to the existing Source kind constraint without rewriting 104."""
from __future__ import annotations

import re

SCRIPT = '119_v5_0_4_incident_sources.sql'
CONSTRAINT = 'CX119_SOURCE_KIND'
KINDS = ('DOCUMENT', 'GITHUB', 'STATUSPAGE')


def render(database):
    if database == 'postgresql':
        database = 'pg'
    if database not in {'pg', 'oracle', 'yashandb'}:
        raise ValueError('Unsupported incident Source database')
    lines = ['-- v5.0.4 additive Source connector kinds; retain all rows, grants and historical SQL.',
             '-- Install the wider check first; remove only the exact predecessor kind check.']
    if database == 'pg':
        lines.append("""DO $cx119$
DECLARE r RECORD;
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid='cx_agent_sources'::regclass AND conname='cx119_source_kind') THEN
    ALTER TABLE CX_AGENT_SOURCES ADD CONSTRAINT CX119_SOURCE_KIND CHECK (SOURCE_KIND IN ('DOCUMENT','GITHUB','STATUSPAGE'));
  END IF;
  FOR r IN SELECT conname,pg_get_constraintdef(oid) AS definition FROM pg_constraint
    WHERE conrelid='cx_agent_sources'::regclass AND contype='c' AND conname<>'cx119_source_kind'
    AND conkey=ARRAY[(SELECT attnum FROM pg_attribute WHERE attrelid='cx_agent_sources'::regclass AND attname='source_kind')]::smallint[]
  LOOP
    IF regexp_replace(r.definition,'[[:space:]()]','','g') = 'CHECKsource_kind::text=ANYARRAY[''DOCUMENT''::charactervarying::text,''GITHUB''::charactervarying::text]' THEN
      EXECUTE format('ALTER TABLE CX_AGENT_SOURCES DROP CONSTRAINT %I',r.conname);
    END IF;
  END LOOP;
END;
$cx119$;""")
    else:
        lines.append("""DECLARE n NUMBER; v_condition VARCHAR2(32767);
BEGIN
  SELECT COUNT(*) INTO n FROM USER_CONSTRAINTS WHERE TABLE_NAME='CX_AGENT_SOURCES' AND CONSTRAINT_NAME='CX119_SOURCE_KIND';
  IF n=0 THEN
    EXECUTE IMMEDIATE 'ALTER TABLE CX_AGENT_SOURCES ADD CONSTRAINT CX119_SOURCE_KIND CHECK (SOURCE_KIND IN (''DOCUMENT'',''GITHUB'',''STATUSPAGE''))';
  END IF;
  FOR r IN (SELECT CONSTRAINT_NAME,SEARCH_CONDITION FROM USER_CONSTRAINTS
            WHERE TABLE_NAME='CX_AGENT_SOURCES' AND CONSTRAINT_TYPE='C' AND CONSTRAINT_NAME<>'CX119_SOURCE_KIND') LOOP
    v_condition := REGEXP_REPLACE(UPPER(r.SEARCH_CONDITION),'[[:space:]"()]','');
    IF v_condition='SOURCE_KINDIN''DOCUMENT'',''GITHUB''' THEN
      EXECUTE IMMEDIATE 'ALTER TABLE CX_AGENT_SOURCES DROP CONSTRAINT "' || REPLACE(r.CONSTRAINT_NAME,'"','""') || '"';
    END IF;
  END LOOP;
END;
/""")
    facts = dict(schema='v504-incident-sources/v1', database=database, table='CX_AGENT_SOURCES',
        constraint=CONSTRAINT, kinds=list(KINDS), nullable=False, historical_sql='UNCHANGED', grants='UNCHANGED')
    return SCRIPT, '\n'.join(lines)+'\n', facts


def errors(cursor, database):
    """Check exact native predicate, enabled validation and retained NOT NULL."""
    if database in {'pg', 'postgresql'}:
        cursor.execute("SELECT conname,pg_get_constraintdef(oid),convalidated FROM pg_constraint "
            "WHERE conrelid='cx_agent_sources'::regclass AND contype='c' "
            "AND conkey=ARRAY[(SELECT attnum FROM pg_attribute WHERE attrelid='cx_agent_sources'::regclass "
            "AND attname='source_kind')]::smallint[]")
        rows = [(str(name).upper(), definition, bool(valid)) for name, definition, valid in cursor.fetchall()]
        cursor.execute("SELECT attnotnull FROM pg_attribute WHERE attrelid='cx_agent_sources'::regclass AND attname='source_kind'")
        nullable = cursor.fetchall() != [(True,)]
    elif database in {'oracle', 'yashandb'}:
        cursor.execute("SELECT c.CONSTRAINT_NAME,c.SEARCH_CONDITION,c.STATUS,c.VALIDATED FROM USER_CONSTRAINTS c "
            "WHERE c.TABLE_NAME='CX_AGENT_SOURCES' AND c.CONSTRAINT_TYPE='C'")
        rows = [(name, text.read() if hasattr(text, 'read') else str(text), enabled=='ENABLED' and valid=='VALIDATED')
                for name, text, enabled, valid in cursor.fetchall()]
        cursor.execute("SELECT NULLABLE FROM USER_TAB_COLUMNS WHERE TABLE_NAME='CX_AGENT_SOURCES' AND COLUMN_NAME='SOURCE_KIND'")
        nullable = cursor.fetchall() != [('N',)]
    else:
        raise ValueError('Unsupported incident Source database')
    failures, found = [], False
    for name, definition, valid in rows:
        normalized = re.sub(r'[\s"()]', '', definition.upper())
        if 'SOURCE_KIND' not in normalized or normalized == 'SOURCE_KINDISNOTNULL':
            continue
        if name != CONSTRAINT:
            failures.append('COMPETING_SOURCE_KIND_CHECK')
            continue
        found = True
        # pg_get_constraintdef renders casts either on each array element or
        # on the complete array, depending on the server version. Both exact
        # forms express the same three-value predicate; accept no extra SQL.
        expected = ({
            "CHECKSOURCE_KIND::TEXT=ANYARRAY['DOCUMENT'::CHARACTERVARYING::TEXT,'GITHUB'::CHARACTERVARYING::TEXT,'STATUSPAGE'::CHARACTERVARYING::TEXT]",
            "CHECKSOURCE_KIND::TEXT=ANYARRAY['DOCUMENT'::CHARACTERVARYING,'GITHUB'::CHARACTERVARYING,'STATUSPAGE'::CHARACTERVARYING]::TEXT[]",
        } if database in {'pg', 'postgresql'} else {"SOURCE_KINDIN'DOCUMENT','GITHUB','STATUSPAGE'"})
        if normalized not in expected or not valid:
            failures.append('INVALID_SOURCE_KIND_CHECK')
    if not found:
        failures.append('MISSING_SOURCE_KIND_CHECK')
    if nullable:
        failures.append('SOURCE_KIND_NOT_NULL_MISSING')
    return failures
