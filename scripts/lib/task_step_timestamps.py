"""Add observed Task Step times without inventing times for historical rows."""
from __future__ import annotations

import re

SCRIPT = '117_v5_0_3_task_step_timestamps.sql'
COLUMNS = ('STARTED_AT', 'COMPLETED_AT')


def render(database):
    if database == 'postgresql':
        database = 'pg'
    if database not in {'pg', 'oracle', 'yashandb'}:
        raise ValueError('Unsupported Task Step database')
    output = ['-- v5.0.3 observed Task Step times; unknown historical times remain NULL.',
              '-- Additive migration: preserve existing rows, grants and historical SQL.']
    for column in COLUMNS:
        if database == 'pg':
            output.append(f'ALTER TABLE TASK_STEPS ADD COLUMN IF NOT EXISTS {column} TIMESTAMP;')
        else:
            output.append("DECLARE n NUMBER; BEGIN SELECT COUNT(*) INTO n FROM USER_TAB_COLUMNS "
                f"WHERE TABLE_NAME='TASK_STEPS' AND COLUMN_NAME='{column}'; IF n=0 THEN "
                f"EXECUTE IMMEDIATE 'ALTER TABLE TASK_STEPS ADD ({column} TIMESTAMP)'; END IF; END;\n/")
    facts = dict(schema='v503-task-step-timestamps/v1', database=database, table='TASK_STEPS',
                 columns={column: dict(type='TIMESTAMP', nullable=True, default=None) for column in COLUMNS},
                 historical_backfill=False, grants='UNCHANGED')
    return SCRIPT, '\n'.join(output) + '\n', facts


def errors(cursor, database):
    """Verify both native columns, including nullability and absence of a default."""
    if database in {'pg', 'postgresql'}:
        cursor.execute("SELECT UPPER(column_name),data_type,is_nullable,column_default "
            "FROM information_schema.columns WHERE table_schema=current_schema() "
            "AND table_name='task_steps' AND column_name IN ('started_at','completed_at')")
    elif database in {'oracle', 'yashandb'}:
        cursor.execute("SELECT COLUMN_NAME,DATA_TYPE,NULLABLE,DATA_DEFAULT FROM USER_TAB_COLUMNS "
            "WHERE TABLE_NAME='TASK_STEPS' AND COLUMN_NAME IN ('STARTED_AT','COMPLETED_AT')")
    else:
        raise ValueError('Unsupported Task Step database')
    seen = set()
    failures = []
    for name, data_type, nullable, default in cursor.fetchall():
        if name not in COLUMNS or name in seen:
            failures.append('UNEXPECTED_TASK_STEP_COLUMN')
            continue
        seen.add(name)
        normalized_type = str(data_type).upper()
        correct_type = (normalized_type == 'TIMESTAMP WITHOUT TIME ZONE' if database in {'pg', 'postgresql'}
                        else bool(re.fullmatch(r'TIMESTAMP(?:\(\d+\))?', normalized_type)))
        if hasattr(default, 'read'):
            default = default.read()
        if not correct_type or nullable not in {'YES', 'Y'} or default is not None and str(default).strip():
            failures.append('INVALID_TASK_STEP_COLUMN:' + name)
    failures.extend('MISSING_TASK_STEP_COLUMN:' + column for column in COLUMNS if column not in seen)
    return failures
