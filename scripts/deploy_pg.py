#!/usr/bin/env python3.14
"""PostgreSQL package deployment tool without a psql dependency.

The release SQL originates partly from pg_dump and can contain dollar-quoted
functions and COPY FROM stdin payloads.  This parser is intentionally limited
to that trusted package format; it does not accept arbitrary SQL from a model
or remote caller.
"""

from __future__ import annotations

import io
import re
import shlex
import sys
from pathlib import Path
from typing import Iterator, Mapping, Tuple


def _expand_psql_variables(sql: str, variable_overrides: Mapping[str, str] | None = None) -> str:
    """Expand the small trusted ``pg_dump`` variable subset used by 1_schema.

    The package never accepts caller supplied SQL.  Values originate only from
    a ``\\set`` directive in that checked file, so this is not a general psql
    interpreter or an injection surface.
    """
    variables: dict[str, str] = {}
    retained = []
    for line in sql.splitlines(keepends=True):
        match = re.match(r"^\s*\\set\s+([A-Za-z_][A-Za-z0-9_]*)\s+(.+?)\s*$", line)
        if match:
            try:
                values = shlex.split(match.group(2))
                variables[match.group(1)] = values[0] if values else ""
            except ValueError as exc:
                raise ValueError("invalid trusted psql variable declaration") from exc
            continue
        retained.append(line)
    for key, value in dict(variable_overrides or {}).items():
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", str(key)):
            raise ValueError("invalid trusted psql variable name")
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_$]*", str(value)):
            raise ValueError("invalid trusted psql identifier override")
        variables[str(key)] = str(value)
    source = "".join(retained)
    for key, value in variables.items():
        literal = "'" + value.replace("'", "''") + "'"
        identifier = '"' + value.replace('"', '""') + '"'
        source = source.replace(f":'{key}'", literal)
        source = source.replace(f':"{key}"', identifier)
        source = re.sub(rf":{re.escape(key)}\b", value, source)
    return source


def _skip_psql_meta(sql: str, variable_overrides: Mapping[str, str] | None = None) -> str:
    sql = _expand_psql_variables(sql, variable_overrides)
    return "\n".join(
        line for line in sql.splitlines()
        if line.strip() == "\\." or not line.lstrip().startswith("\\")
    ) + "\n"


def _dollar_tag(source: str, position: int) -> str | None:
    match = re.match(r"\$[A-Za-z_][A-Za-z0-9_]*\$|\$\$", source[position:])
    return match.group(0) if match else None


def _leading_comments_removed(statement: str) -> str:
    """Keep parser offsets intact while recognizing pg_dump COPY headers."""
    return re.sub(r"^(?:\s*--[^\n]*(?:\n|$))+", "", statement).lstrip()


def statements(content: str, variable_overrides: Mapping[str, str] | None = None) -> Iterator[Tuple[str, str | None]]:
    """Yield trusted SQL statements and optional COPY payloads."""
    source = _skip_psql_meta(content, variable_overrides)
    size = len(source)
    start = 0
    index = 0
    quote = ""
    dollar = ""
    line_comment = False
    block_comment = False
    while index < size:
        char = source[index]
        next_two = source[index:index + 2]
        if line_comment:
            if char == "\n":
                line_comment = False
            index += 1
            continue
        if block_comment:
            if next_two == "*/":
                block_comment = False
                index += 2
            else:
                index += 1
            continue
        if dollar:
            if source.startswith(dollar, index):
                index += len(dollar)
                dollar = ""
            else:
                index += 1
            continue
        if quote:
            if char == quote:
                if quote == "'" and index + 1 < size and source[index + 1] == "'":
                    index += 2
                    continue
                quote = ""
            index += 1
            continue
        if next_two == "--":
            line_comment = True
            index += 2
            continue
        if next_two == "/*":
            block_comment = True
            index += 2
            continue
        if char in {"'", '"'}:
            quote = char
            index += 1
            continue
        tag = _dollar_tag(source, index) if char == "$" else None
        if tag:
            dollar = tag
            index += len(tag)
            continue
        if char == ";":
            statement = source[start:index + 1].strip()
            index += 1
            start = index
            if not statement:
                continue
            executable = _leading_comments_removed(statement)
            # A package file may end with release comments after its final
            # statement.  psycopg2 rejects that as an empty query, whereas
            # psql silently ignores it.
            if not executable:
                continue
            if re.match(r"^COPY\s+.+\s+FROM\s+stdin\s*;$", executable, re.IGNORECASE | re.DOTALL):
                end = source.find("\\.\n", index)
                if end < 0:
                    end = source.find("\\.\r\n", index)
                if end < 0:
                    raise ValueError("COPY FROM stdin payload is missing its terminator")
                payload = source[index:end]
                if payload.startswith("\r\n"):
                    payload = payload[2:]
                elif payload.startswith("\n"):
                    payload = payload[1:]
                terminator_end = source.find("\n", end)
                index = size if terminator_end < 0 else terminator_end + 1
                start = index
                yield executable, payload
            else:
                yield statement, None
            continue
        index += 1
    trailing = source[start:].strip()
    if trailing and _leading_comments_removed(trailing):
        yield trailing, None


def execute_sql_file(conn, sql_file: str | Path, verbose: bool = True,
                     define_overrides: Mapping[str, str] | None = None) -> bool:
    path = Path(sql_file)
    content = path.read_text(encoding="utf-8")
    ok = True
    for number, (statement, payload) in enumerate(statements(content, define_overrides), start=1):
        try:
            with conn.cursor() as cursor:
                if payload is not None:
                    cursor.copy_expert(statement, io.StringIO(payload))
                else:
                    cursor.execute(statement)
            conn.commit()
        except Exception as exc:
            conn.rollback()
            message = str(exc).lower()
            idempotent = any(item in message for item in (
                "already exists", "duplicate column", "duplicate key", "already a member", "is already",
            ))
            if not idempotent:
                ok = False
                if verbose:
                    first = statement.splitlines()[0][:120]
                    print(f"[{path.name}:{number}] {first}: {type(exc).__name__}: {str(exc)[:240]}", file=sys.stderr)
                break
    return ok


def main() -> int:
    try:
        import psycopg2
    except ImportError as exc:
        print("psycopg2 is required to deploy PostgreSQL", file=sys.stderr)
        raise SystemExit(2) from exc
    if len(sys.argv) < 7:
        print("Usage: python3.14 deploy_pg.py <user> <password> <host> <port> <dbname> <sql_file> [sql_file...]", file=sys.stderr)
        return 2
    user, password, host, port, dbname, *paths = sys.argv[1:]
    conn = psycopg2.connect(user=user, password=password, host=host, port=int(port), dbname=dbname, connect_timeout=10)
    try:
        return 0 if all(execute_sql_file(conn, path) for path in paths) else 1
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
