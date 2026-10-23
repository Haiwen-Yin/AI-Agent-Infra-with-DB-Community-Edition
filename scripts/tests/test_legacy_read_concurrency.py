"""Slow legacy reads must not hold the ASGI loop or leak worker DB identity."""
import ast
import asyncio
from contextvars import ContextVar
from pathlib import Path
import threading
from types import SimpleNamespace

import pytest
from starlette.concurrency import run_in_threadpool
from starlette.responses import Response


def bridge(gate, dispatch, identity):
    path = Path(__file__).resolve().parents[1] / 'web_app.py'
    names = {'legacy_compatibility', '_legacy_read_dispatch', '_clear_legacy_thread_context'}
    nodes = [node for node in ast.parse(path.read_text()).body
             if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names]
    for node in nodes:
        node.decorator_list = []
    namespace = {'_legacy_gate': gate, '_legacy_dispatch': dispatch,
                 'connection': SimpleNamespace(set_agent_context=identity.set),
                 'run_in_threadpool': run_in_threadpool}
    tree = ast.Module(body=[ast.ImportFrom(module='__future__', names=[ast.alias(name='annotations')], level=0), *nodes], type_ignores=[])
    exec(compile(ast.fix_missing_locations(tree), str(path), 'exec'), namespace)
    return namespace


def request(method='GET'):
    async def body():
        return b'bounded body'
    return SimpleNamespace(method=method, url=SimpleNamespace(query='limit=10', port=18443),
                           headers={'Host': 'localhost:18443'}, body=body)


@pytest.mark.parametrize('method', ['GET', 'HEAD'])
def test_slow_read_gate_and_handler_leave_event_loop_available(method):
    identity = ContextVar('legacy_read_identity', default=None)
    entered, release = threading.Event(), threading.Event()
    threads = []
    def gate(req, path):
        assert identity.get() is None
        identity.set('request-agent')
        threads.append(threading.get_ident())
        entered.set()
        assert release.wait(2), 'event loop could not release a blocked database read'
    def dispatch(actual_method, path, query, headers, body):
        assert identity.get() == 'request-agent'
        assert (actual_method, path, query, headers['Host'], body) == (
            method, '/api/graph/all', 'limit=10', 'localhost:18443', b'bounded body')
        threads.append(threading.get_ident())
        return Response('authorized data')
    ns = bridge(gate, dispatch, identity)
    async def run():
        loop_thread = threading.get_ident()
        task = asyncio.create_task(ns['legacy_compatibility']('api/graph/all', request(method)))
        try:
            assert await asyncio.to_thread(entered.wait, 2)
            assert not task.done(), 'blocking legacy read ran on the event-loop thread'
            assert threads == [threads[0]] and threads[0] != loop_thread
            assert identity.get() is None
        finally:
            release.set()
            result = await task
        assert result.body == b'authorized data'
        assert len(threads) == 2 and threads[0] == threads[1]
        assert identity.get() is None
    asyncio.run(run())


@pytest.mark.parametrize('outcome', ['denied', 'gate-error', 'handler-error', 'success'])
def test_read_worker_fences_identity_even_on_denial_or_failure(outcome):
    identity = ContextVar('legacy_worker_identity', default=None)
    calls = []
    def gate(req, path):
        assert identity.get() is None
        identity.set('admitted-agent')
        if outcome == 'gate-error':
            raise PermissionError('authorization unavailable')
        if outcome == 'denied':
            return Response('denied', status_code=403)
    def dispatch(*args):
        assert identity.get() == 'admitted-agent'
        calls.append(True)
        if outcome == 'handler-error':
            raise RuntimeError('database unavailable')
        return Response('authorized data')
    worker = bridge(gate, dispatch, identity)['_legacy_read_dispatch']
    identity.set('previous-worker-agent')
    try:
        if outcome.endswith('error'):
            with pytest.raises((PermissionError, RuntimeError)):
                worker(request(), '/api/graph/all', b'')
        else:
            result = worker(request(), '/api/graph/all', b'')
            assert result.status_code == (403 if outcome == 'denied' else 200)
        assert bool(calls) == (outcome in {'handler-error', 'success'})
        assert identity.get() is None
    finally:
        identity.set(None)
