#!/usr/bin/env python3.14
"""AI Agent Infra v5.0.1 - YashanDB Edition - Schema Deployment Tool

Uses yaspy driver to deploy SQL scripts to YashanDB 23.5.4+.
Handles PROMPT removal, / block splitting, ; statement splitting.
"""

import re
import sys
import os

def parse_defines(content):
    defines = {}
    for m in re.finditer(r'^DEFINE\s+(\w+)\s*=\s*(.+)$', content, re.MULTILINE):
        val = m.group(2).strip().strip("'\"")
        defines[m.group(1)] = val
    return defines

def substitute_vars(content, defines):
    for key, val in defines.items():
        content = content.replace(f'&&{key}.', val)
        content = content.replace(f'&{key}.', val)
        content = content.replace(f'&&{key}', val)
        content = content.replace(f'&{key}', val)
    return content

def remove_prompts(content):
    return re.sub(r'^PROMPT.*$', '', content, flags=re.MULTILINE)

def strip_leading_comments(text):
    lines = text.strip().splitlines()
    while lines and (not lines[0].strip() or lines[0].lstrip().startswith('--')):
        lines.pop(0)
    return '\n'.join(lines).strip()


def is_plsql_block(text):
    """Check if a text block is a PL/SQL block."""
    stripped = strip_leading_comments(text).upper()
    return bool(re.match(r'^(BEGIN|DECLARE|CREATE\s+OR\s+REPLACE\s+(PACKAGE|PROCEDURE|FUNCTION|TRIGGER|TYPE))\b', stripped))


def normalize_statement(text, plsql=False):
    statement = strip_leading_comments(text).strip()
    if plsql:
        return statement
    return statement.rstrip(';').strip()

def split_statements(content):
    """Split SQL and PL/SQL without breaking mixed blocks between slash lines."""
    # Remove PROMPT, WHENEVER, DEFINE lines
    content = re.sub(r'^PROMPT.*$', '', content, flags=re.MULTILINE)
    content = re.sub(r'^WHENEVER\s+.*$', '', content, flags=re.MULTILINE)
    content = re.sub(r'^DEFINE\s+.*$', '', content, flags=re.MULTILINE)
    content = re.sub(r'^SHOW\s+.*$', '', content, flags=re.MULTILINE)
    
    statements = []
    current = []
    plsql = False
    for line in content.splitlines():
        stripped = line.strip()
        if not current and (not stripped or stripped.startswith('--')):
            continue
        # SQL*Plus SET commands are only valid before a statement starts.
        # Keep SQL DML clauses such as UPDATE ... SET intact.
        if not current and re.match(r'^SET\s+', stripped, re.IGNORECASE):
            continue
        if stripped == '/':
            statement = normalize_statement('\n'.join(current), plsql)
            if statement:
                statements.append(statement)
            current = []
            plsql = False
            continue
        if not current:
            plsql = is_plsql_block(stripped)
        current.append(line)
        if not plsql and stripped.endswith(';'):
            statement = normalize_statement('\n'.join(current))
            if statement:
                statements.append(statement)
            current = []

    statement = normalize_statement('\n'.join(current), plsql)
    if statement:
        statements.append(statement)
    
    return statements


def main():
    import yaspy
    
    if len(sys.argv) < 5:
        print("Usage: python3.14 deploy_yashandb.py <user> <password> <dsn> <sql_file> [sql_file...]")
        print("Example: python3.14 deploy_yashandb.py <user> <password> <host>:1688/<service> scripts/deploy/1_schema.sql")
        sys.exit(1)
    
    user = sys.argv[1]
    password = sys.argv[2]
    dsn = sys.argv[3]
    sql_files = sys.argv[4:]
    
    dsn_str = f"{user}/{password}@{dsn}"
    print(f"[deploy] Connecting to {user}@{dsn}...")
    
    try:
        conn = yaspy.Connection(dsn_str)
    except Exception as e:
        print(f"[deploy] Connection failed: {e}")
        sys.exit(1)
    
    print(f"[deploy] Connected. Processing {len(sql_files)} SQL file(s)...")
    
    cur = conn.cursor()
    
    for sql_file in sql_files:
        print(f"\n[deploy] Executing: {sql_file}")
        
        with open(sql_file) as f:
            content = f.read()
        
        defines = parse_defines(content)
        content = substitute_vars(content, defines)
        content = remove_prompts(content)
        
        statements = split_statements(content)
        print(f"  [{os.path.basename(sql_file)}] {len(statements)} statements to execute")
        
        success = 0
        failed = 0
        
        for i, stmt in enumerate(statements, 1):
            first_line = stmt.split('\n')[0][:80]
            try:
                cur.execute(stmt)
                conn.commit()
                success += 1
            except Exception as e:
                err_msg = str(e)[:120]
                if 'already exists' in err_msg or 'YAS-04207' in err_msg or 'YAS-02013' in err_msg:
                    success += 1
                elif 'has been indexed' in err_msg or 'YAS-02043' in err_msg:
                    success += 1  # Index already exists
                else:
                    failed += 1
                    print(f"    [{i}/{len(statements)}] ERROR: {first_line}")
                    print(f"           {err_msg}")
        
        print(f"  [{os.path.basename(sql_file)}] Done: {success} success, {failed} failed")
    
    cur.close()
    conn.close()
    print(f"\n[deploy] Completed.")


if __name__ == '__main__':
    main()
