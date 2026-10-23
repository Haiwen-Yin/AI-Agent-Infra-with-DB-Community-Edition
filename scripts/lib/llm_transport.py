"""Local connection/read wait policy, separate from provider generation options."""
from __future__ import annotations

import math
from typing import Any


DEFAULT_REQUEST_TIMEOUT_SECONDS = 180


def validate_request_timeout_seconds(value: Any) -> float:
    """Reject invalid settings rather than silently changing a dispatch budget."""
    if (type(value) not in (int, float) or not 1 <= value <= 600
            or not math.isfinite(value)):
        raise ValueError("llm.request_timeout_seconds must be a finite number between 1 and 600")
    return float(value)


def request_timeout_seconds(llm: Any = None) -> float:
    """Return the same validated urllib connection/read timeout for each path.

    This is a socket wait timeout, not an end-to-end generation deadline.
    Loading config here avoids a config-module import cycle.
    """
    if llm is None:
        from .config import get_config
        llm = get_config().llm
    return validate_request_timeout_seconds(
        getattr(llm, "request_timeout_seconds", DEFAULT_REQUEST_TIMEOUT_SECONDS))
