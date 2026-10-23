"""Reuse synchronous, same-identity reads within an existing DB transaction.

Only read helpers opt in. Write helpers retain their explicit transaction
boundaries, and changing an Agent or schema identity requires an independent
connection rather than borrowing the outer transaction's authority.
"""
from __future__ import annotations

import asyncio
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
import threading
from typing import Any, Callable


def connection_identity(config: Any, agent_id: str | None, credentials: dict | None = None) -> tuple:
    database = config.database
    credentials = credentials or {}
    return (
        config.agent.mode,
        *(getattr(database, field, None) for field in ("user", "dsn", "host", "port", "dbname")),
        agent_id,
        credentials.get("agent_id"),
        credentials.get("username") or credentials.get("user"),
        *(credentials.get(field) for field in ("dsn", "host", "port", "dbname")),
    )


def _task():
    try:
        return asyncio.current_task()
    except RuntimeError:
        return None


@dataclass
class _Binding:
    connection: Any
    identity: tuple
    thread: int
    task: Any
    active: bool = True


class TransactionReads:
    def __init__(self, identity: Callable[[], tuple]):
        self._identity = identity
        self._binding = ContextVar("transaction_read_connection", default=None)

    @contextmanager
    def bind(self, connection):
        binding = _Binding(connection, self._identity(), threading.get_ident(), _task())
        token = self._binding.set(binding)
        try:
            yield
        finally:
            # A copied Context must not retain a returned or closed connection.
            binding.active = False
            self._binding.reset(token)

    def owns(self, connection) -> bool:
        binding = self._binding.get()
        return bool(binding and binding.active and binding.connection is connection
                    and binding.thread == threading.get_ident() and binding.task is _task()
                    and binding.identity == self._identity())

    @contextmanager
    def connection(self, independent_connection):
        binding = self._binding.get()
        if binding is not None and self.owns(binding.connection):
            yield binding.connection
        else:
            with independent_connection() as connection:
                yield connection
