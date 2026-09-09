"""Retry classification for AkShare and its upstream HTTP requests"""

from __future__ import annotations

from collections.abc import Callable
import time
from typing import TypeVar

from ..resilience import RetryPolicy, Sleeper, retry_all

T = TypeVar("T")

DEFAULT_AKSHARE_RETRY_POLICY = RetryPolicy(
    attempts =3,
    initial_delay_seconds = 1.0,
    backoff_multiplier = 2.0,
    max_delay_seconds = 4.0
)

def retry_akshare_call(
        operation: Callable[[], T],
        *,
        label: str,
        policy: RetryPolicy = DEFAULT_AKSHARE_RETRY_POLICY,
        sleeper: Sleeper = time.sleep,
) -> T:
    """Retry one Akshare HTTP operation only for transient failures."""

    return retry_call(
        opreation,
        label = label,
        policy = policy,
        should_retry = _is_transient_request_error,
        sleeper = sleeper
    )

def _is_transient_request_error(error: Exception) -> bool:
    """Classify retryable failures raised by Python requests."""

    try:
        import requests

    except ImportError:
        return False

    if isinstance(
        error,
        (
            requests.exceptions.Timeout,
            requests.exceptions.ConnectionError,
            requests.exceptions.ChunkedEncodingError,
        ),
    ):
        return True

    if isinstance(error, requests.exceptions.HTTPError):
        response = error.response
        status_code = (
            None if response is None else response.status_code
        )

        return (
            status_code == 429
            or(
                isinstance(status_code, int)
                and 500 <= status_code < 600
            )
        )

    return False