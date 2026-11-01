"""Transport admission shared by selected model ingresses.

Business entrypoints install authenticated context after their own authority
checks. The context is local and never populated from model/provider output.
Unadapted direct routes fail before sending to a registered capacity resource.
Remote installations participate through the same coordinator gateway; a
separate local database is explicitly outside that coordination domain.
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
import time
from threading import Event, Lock, Thread
import urllib.request
from typing import Callable

from . import connection, edition_features, model_endpoint_capacity as capacity
from .agent_extension_contracts import digest, opener
from .continuity_state import ContinuityConflict
from .model_results import ModelResultError
from .model_native_numeric import native_revision

_context = ContextVar("authenticated_model_dispatch", default=None)
_opening = {}
_opening_lock = Lock()


@dataclass(frozen=True)
class DispatchContext:
    actor: str
    source_kind: str
    source_id: str
    source_attempt_id: str
    credential_digest: str
    reauthorize: Callable
    worker_key: str
    origin_id: str | None = None
    allow_wait: bool = True
    cancelled: Callable | None = None
    lock_principals: tuple[str, ...] = ()


class ModelNotDispatched(ContinuityConflict):
    model_not_dispatched = True


class CapacityQueued(ModelNotDispatched):
    def __init__(self, record):
        super().__init__("MODEL_CAPACITY_QUEUED", "Model request is durably queued without dispatch")
        self.admission = record


@contextmanager
def authenticated_context(actor, source_kind, source_id, source_attempt_id, *, credential_digest,
                          reauthorize, worker_key, origin_id=None, allow_wait=True, cancelled=None, lock_principals=()):
    if not actor or not callable(reauthorize):
        raise PermissionError("Authenticated model dispatch context is required")
    token = _context.set(DispatchContext(actor, source_kind, source_id, source_attempt_id, credential_digest,
                                        reauthorize, worker_key, origin_id, allow_wait, cancelled, tuple(lock_principals)))
    try:
        yield
    finally:
        _context.reset(token)


class DispatchTicket:
    def __init__(self, context=None, record=None, started=None):
        self.context, self.record = context, record
        self.started = started if started is not None else time.monotonic()
        self.complete = False
        self.code = "PROVIDER_REQUEST_COMPLETE"
        self.first_token_ms = None
        self.result_observation = None
        self.model_id = None

    @property
    def request_id(self):
        return self.record["admission_id"] if self.record else None

    @property
    def socket_seconds(self):
        return self.record["socket_ms"] / 1000 if self.record else None

    def timeout_seconds(self, default, *, stream=False):
        if not self.record:
            return default
        remaining = self.record["remaining_ms"] / 1000 - (time.monotonic() - self.started)
        if remaining <= 0:
            raise TimeoutError("MODEL_OVERALL_DEADLINE")
        bounds = [default, self.record["socket_ms"] / 1000, remaining]
        if stream:
            bounds.append(self.record["idle_ms"] / 1000)
        return min(bounds)

    def open(self, request, *, timeout, default_open=None):
        # The controlled alias is the exact destination; redirects must not
        # carry credentials or input to an unregistered inference resource.
        if not self.record:
            return (default_open or urllib.request.urlopen)(request, timeout=timeout)
        self.check_deadline()
        # Socket timeouts alone do not bound DNS or a peer that slowly trickles
        # response headers. The caller's absolute deadline also bounds open.
        # A late opener is tracked, closes its response, and never releases the
        # durable possible-send occupancy just because the caller timed out.
        ready, abandoned, state_lock = Event(), Event(), Lock()
        result = {}
        admission_id = self.record["admission_id"]
        def opening():
            try:
                response = open_controlled(request, timeout=timeout)
                with state_lock:
                    if abandoned.is_set():
                        response.close()
                    else:
                        result["response"] = response
            except BaseException as exc:
                with state_lock:
                    result["error"] = exc
            finally:
                ready.set()
                with _opening_lock:
                    _opening.pop(admission_id, None)
        thread = Thread(target=opening, name="model-open-" + admission_id, daemon=True)
        with _opening_lock:
            _opening[admission_id] = thread
        thread.start()
        remaining = self.record["remaining_ms"] / 1000 - (time.monotonic() - self.started)
        if not ready.wait(max(0, remaining)):
            with state_lock:
                abandoned.set()
                response = result.pop("response", None)
                if response is not None:
                    response.close()
            raise TimeoutError("MODEL_OVERALL_OPEN_DEADLINE")
        try:
            self.check_deadline()
        except BaseException:
            response = result.pop("response", None)
            if response is not None:
                response.close()
            raise
        if "error" in result:
            raise result["error"]
        return result["response"]

    def _read_chunks(self, response, *, stream=False):
        reader = getattr(response, "read1", None)
        if not callable(reader):
            # Independent fixture peers may provide an iterable/read API. The
            # production urllib response has read1 and an underlying socket.
            if stream:
                for chunk in response:
                    self.check_deadline()
                    yield chunk
            else:
                self.check_deadline()
                yield response.read(4 * 1024 * 1024 + 1)
            return
        while True:
            self.check_deadline()
            if callable(getattr(response, "isclosed", None)) and response.isclosed():
                return
            if self.record:
                raw = getattr(getattr(response, "fp", None), "raw", None)
                sock = getattr(raw, "_sock", None)
                if sock is None:
                    raise RuntimeError("Controlled model response has no supported bounded socket")
                sock.settimeout(self.timeout_seconds(self.record["socket_ms"] / 1000, stream=stream))
            chunk = reader(65536)
            if not chunk:
                return
            yield chunk

    def read_response(self, response, maximum):
        output = bytearray()
        for chunk in self._read_chunks(response):
            output.extend(chunk)
            if len(output) > maximum:
                raise ModelResultError("RESPONSE_TOO_LARGE")
        return bytes(output)

    def stream_response(self, response):
        return self._read_chunks(response, stream=True)

    def response_complete(self, code="PROVIDER_REQUEST_COMPLETE"):
        self.complete, self.code = True, code

    def observe_result(self, result):
        """Retain only normalized metadata; output and reasoning never enter it."""
        from .model_observations import safe_result
        self.result_observation = safe_result(result)

    def first_token(self):
        if self.first_token_ms is None:
            self.first_token_ms = max(0, round((time.monotonic() - self.started) * 1000))

    def check_deadline(self):
        if not self.record:
            return
        # This checks elapsed active time without opening a transaction while
        # waiting on the provider. Durable expiration remains DB-authoritative.
        if time.monotonic() - self.started >= self.record["remaining_ms"] / 1000:
            raise TimeoutError("MODEL_OVERALL_DEADLINE")
        if self.context.cancelled and self.context.cancelled():
            raise InterruptedError("MODEL_LOCAL_CANCELLED")

    def finish(self, error):
        if not self.record:
            return
        if isinstance(error, ModelResultError) and error.request_complete:
            self.response_complete(error.code)
        from .model_observations import record_dispatch
        record_dispatch(self, error)
        current = capacity.read_admission(self.context.actor, self.record["admission_id"])
        if current["status"] in capacity.TERMINAL:
            return
        capacity.observe_completion(self.context.actor, current["admission_id"], dict(
            expected_version=current["version"], attempt_id=self.record["attempt_id"],
            fencing_token=self.record["fencing_token"], evidence_kind="COMPLETE_RESPONSE" if self.complete else "TRANSPORT_UNKNOWN",
            evidence_digest=digest({"admission_id": current["admission_id"], "attempt_id": self.record["attempt_id"],
                                    "complete": self.complete, "code": self.code if self.complete else "REMOTE_UNCONFIRMED"}),
            finish_code=self.code if self.complete else "REMOTE_UNCONFIRMED", reason="Local dispatcher observed exact request lifecycle",
            idempotency_key="lifecycle:" + self.record["attempt_id"],
        ))


def _lookup(profile):
    def locate(tx):
        group_id = capacity.selected_group(tx, str(profile.get("profile_id") or ""), str(profile.get("provider_url") or ""))
        if not group_id:
            return None
        context = _context.get()
        if not context:
            raise PermissionError("Capacity-controlled endpoint requires an authenticated supported dispatch route")
        origins = tx.query("SELECT ORIGIN_ID FROM CX_MODEL_CAP_ORIGINS WHERE GROUP_ID=:group_id AND PRINCIPAL_ID=:actor AND STATUS='ACTIVE'",
                           {"group_id": group_id, "actor": context.actor})
        if context.origin_id:
            origins = [origin for origin in origins if origin["origin_id"] == context.origin_id]
        if len(origins) != 1:
            raise PermissionError("The authenticated installation must select exactly one registered coordinator origin")
        return group_id, origins[0]["origin_id"]
    return connection.execute_transaction_callback(locate)


def open_controlled(request, *, timeout):
    return opener().open(request, timeout=timeout)


@contextmanager
def dispatch(profile, request_payload):
    if not getattr(edition_features, "MODEL_RUNTIME_CONTEXT_ENABLED", False):
        yield DispatchTicket()
        return
    from . import model_coordinator_origin
    try:
        remote_route = model_coordinator_origin.selected_route(profile)
    except Exception as exc:
        exc.model_not_dispatched = True
        raise
    if remote_route:
        with model_coordinator_origin.dispatch(profile, request_payload, _context.get(), remote_route) as ticket:
            yield ticket
        return
    try:
        selected = _lookup(profile)
    except (PermissionError, ValueError) as exc:
        exc.model_not_dispatched = True
        raise
    if not selected:
        yield DispatchTicket()
        return
    group_id, origin_id = selected
    context = _context.get()
    request_digest = digest(request_payload)
    key = "model:" + digest({"source_kind": context.source_kind, "source_id": context.source_id,
                             "source_attempt_id": context.source_attempt_id})
    record = capacity.admit(context.actor, group_id, dict(
        origin_id=origin_id, profile_id=profile["profile_id"], profile_version=native_revision(profile["version"]), model_id=profile["model_id"],
        endpoint_url=profile["provider_url"], input_digest=request_digest, credential_digest=context.credential_digest,
        source_kind=context.source_kind, source_id=context.source_id, source_attempt_id=context.source_attempt_id,
        idempotency_key=key, reason="Authenticated model request admission",
    ))
    while record["status"] == "QUEUED":
        if not context.allow_wait:
            raise CapacityQueued(record)
        if context.cancelled and context.cancelled():
            record = capacity.cancel_admission(context.actor, record["admission_id"], dict(
                expected_version=record["version"], reason="Cancelled while queued", idempotency_key="cancel:" + record["admission_id"]))
            break
        time.sleep(0.1)
        record = capacity.read_admission(context.actor, record["admission_id"], reserve=True)
    if record["status"] != "RESERVED":
        error = ModelNotDispatched if record["status"] in {"REJECTED", "CANCELLED", "EXPIRED"} else ContinuityConflict
        raise error("MODEL_CAPACITY_UNAVAILABLE", "Model request has no unused dispatch reservation")
    dispatched = capacity.begin_dispatch(context.actor, record["admission_id"], dict(
        expected_version=record["version"], fencing_token=record["fencing_token"], worker_key=context.worker_key,
        credential_digest=context.credential_digest, reason="Current business and credential authority rechecked",
        idempotency_key="dispatch:" + record["admission_id"],
    ), reauthorize=context.reauthorize, lock_principals=context.lock_principals)
    if not dispatched["dispatch_authorized"]:
        if dispatched["status"] in {"REJECTED", "EXPIRED", "CANCELLED"}:
            raise ModelNotDispatched("MODEL_DISPATCH_DENIED", "Current authority or deadline denied model dispatch")
        raise ContinuityConflict("UNKNOWN_SEND", "A prior dispatch prevents automatic sending")
    # The dispatch committed before this clock observation. Account for time
    # already spent in the queue instead of restarting the overall budget.
    remaining_ms = connection.execute_transaction_callback(lambda tx: int(dispatched["overall_until_ms"]) - capacity._now_ms(tx))
    ticket = DispatchTicket(context, dispatched | {"remaining_ms": max(0, remaining_ms)})
    ticket.model_id = profile["model_id"]
    error = None
    try:
        ticket.check_deadline()
        yield ticket
    except BaseException as exc:
        error = exc
        raise
    finally:
        # A ledger failure must not free capacity. It leaves the durable
        # DISPATCHING attempt occupied for later evidence-bound reconciliation.
        try:
            ticket.finish(error)
        except Exception as ledger_error:
            # Storage failure must leave capacity occupied, while retaining
            # the safe measurements actually observed before that failure.
            # It is not evidence that the Provider became unhealthy.
            from .model_observations import safe_result
            measured = ticket.result_observation or safe_result(
                error.observation if isinstance(error, ModelResultError) else getattr(error, "model_observation", {}) or {})
            ledger_error.model_ledger_failed = True
            ledger_error.model_observation = dict(model=ticket.model_id, usage=measured["usage"],
                request_complete=ticket.complete, usage_observation="PROVIDER_REPORTED" if measured["usage_provenance"] in {"PROVIDER_REPORTED", "DERIVED_TOTAL"} else "INCOMPLETE",
                usage_field_provenance={"total_tokens": "SUM_OF_REPORTED_INPUT_OUTPUT"} if measured["usage_provenance"] == "DERIVED_TOTAL" else {})
            raise
