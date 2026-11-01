"""Immutable client observations over the original admitted model request.

This is metadata, not another usage charge or a claim about answer correctness.
Business views supply their original current-resource authorization before read.
"""
from . import connection, model_endpoint_capacity as capacity
from .agent_extension_contracts import digest, row
from .continuity_state import ContinuityConflict
from .model_results import ModelResultError, normalize_usage


def safe_result(result):
    counts = normalize_usage(result.get("usage"))
    complete = all(counts[key] is not None for key in ("prompt_tokens", "completion_tokens", "total_tokens"))
    derived = result.get("usage_field_provenance", {}).get("total_tokens") == "SUM_OF_REPORTED_INPUT_OUTPUT"
    provenance = ("DERIVED_TOTAL" if complete and derived else "PROVIDER_REPORTED" if complete
                  else "PARTIAL" if any(value is not None for value in counts.values()) else "INCOMPLETE")
    return {"usage": counts, "usage_provenance": provenance}


def record_dispatch(ticket, error):
    """Persist once before releasing occupancy; failures leave it occupied."""
    import time
    result = ticket.result_observation
    if result is None:
        observed = error.observation if isinstance(error, ModelResultError) else getattr(error, "model_observation", {})
        result = safe_result(observed or {})
    provider_ms = max(0, round((time.monotonic() - ticket.started) * 1000))
    complete = ticket.complete
    result_state = "UNKNOWN" if not complete else "REJECTED" if error is not None else "COMPLETED"
    code = error.code if isinstance(error, ModelResultError) else "OUTPUT_REJECTED" if error is not None and complete else ticket.code if complete else "REMOTE_UNCONFIRMED"

    def write(tx):
        record = row(tx.query_one("SELECT a.ACTOR_ID,a.CREATED_AT_MS,t.ATTEMPT_ID,t.DISPATCH_AT_MS,t.FENCING_TOKEN "
            "FROM CX_MODEL_ADMISSIONS a JOIN CX_MODEL_CAP_ATTEMPTS t ON t.ADMISSION_ID=a.ADMISSION_ID "
            "WHERE a.ADMISSION_ID=:admission FOR UPDATE", {"admission": ticket.request_id}))
        if (record.get("actor_id") != ticket.context.actor or record.get("attempt_id") != ticket.record["attempt_id"]
                or int(record.get("fencing_token") or 0) != int(ticket.record["fencing_token"])):
            raise PermissionError("Runtime observation requires the original admitted dispatch")
        existing = row(tx.query_one("SELECT * FROM CX_MODEL_RUNTIME_OBSERVATIONS WHERE ADMISSION_ID=:admission", {"admission": ticket.request_id}))
        # A repeated local finish never overwrites previously unknown timing or
        # accounting. Later evidence belongs to the capacity reconciliation log.
        if existing:
            if (existing["attempt_id"] != record["attempt_id"] or existing["request_complete"] != ("Y" if complete else "N")
                    or existing["result_state"] != result_state or existing["usage_provenance"] != result["usage_provenance"]
                    or any((int(existing[key]) if existing[key] is not None else None) != value for key, value in result["usage"].items())):
                raise ContinuityConflict("OBSERVATION_CONFLICT", "The dispatch already has a different immutable observation")
            return existing
        queue_ms = max(0, int(record["dispatch_at_ms"]) - int(record["created_at_ms"]))
        value = dict(admission_id=ticket.request_id, attempt_id=record["attempt_id"], api_dialect="CHAT_COMPLETIONS",
            request_complete="Y" if complete else "N", result_state=result_state, finish_code=code,
            usage_provenance=result["usage_provenance"], **result["usage"], queue_ms=queue_ms,
            first_content_ms=ticket.first_token_ms, provider_ms=provider_ms, total_ms=queue_ms + provider_ms)
        value["observation_digest"] = digest(value)
        value["observed_at_ms"] = capacity._now_ms(tx)
        columns = list(value)
        tx.execute("INSERT INTO CX_MODEL_RUNTIME_OBSERVATIONS(" + ",".join(key.upper() for key in columns) + ") VALUES(" +
                   ",".join(":" + key for key in columns) + ")", value)
        return value
    return connection.execute_transaction_callback(write)


def read_for_source(actor, source_kind, source_id, *, authorize_source, transaction=None):
    """Used only by trusted business adapters, never caller-provided callbacks."""
    if not callable(authorize_source):
        raise PermissionError("Original business resource authorization is required")
    def read(tx):
        if authorize_source(tx, actor, source_id) is not None:
            raise TypeError("Source authorization must check and return None")
        values = tx.query("SELECT a.ADMISSION_ID,a.SOURCE_ATTEMPT_ID,a.PROFILE_ID,a.PROFILE_VERSION,a.MODEL_ID,a.STATUS AS ADMISSION_STATUS,"
            "a.CANCEL_STATE,o.* FROM CX_MODEL_ADMISSIONS a JOIN CX_MODEL_RUNTIME_OBSERVATIONS o ON o.ADMISSION_ID=a.ADMISSION_ID "
            "WHERE a.SOURCE_KIND=:kind AND a.SOURCE_ID=:source ORDER BY a.QUEUE_SEQUENCE", {"kind": source_kind, "source": source_id})
        if len(values) > 100:
            raise ContinuityConflict("OBSERVATION_BOUND", "Runtime observation count exceeds its business bound")
        for value in values:
            for key in ("profile_version", "prompt_tokens", "completion_tokens", "total_tokens", "cached_tokens", "cache_write_tokens",
                        "reasoning_tokens", "queue_ms", "first_content_ms", "provider_ms", "total_ms", "observed_at_ms"):
                if value.get(key) is not None:
                    value[key] = int(value[key])
        return values
    return read(transaction) if transaction is not None else connection.execute_transaction_callback(read)
