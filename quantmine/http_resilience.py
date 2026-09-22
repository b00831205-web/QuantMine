"""HTTP-specific retry classification shared by market-data providers"""

from __future__ import annotations

from collections.abc import Callable
import time
from typing import TypeVar

from .resilience import RetryPolicy, Sleeper, retry_call

T = TypeVar("T")

DEFAULT_HTTP_RETRY_POLICY = RetryPolicy(
    attempts = 3,
    initial_delay_seconds = 1.0,
    backoff_multiplier = 2.0,
    max_delay_seconds = 4.0
)

_RETRYABLE_HTTP_STATUSES = {
    408,
    425,
    429,
}

def retry_http_call(
        operation: Callable[[], T],
        *,
        label: str,
        policy: RetryPolicy = DEFAULT_HTTP_RETRY_POLICY,
        sleeper: Sleeper = time.sleep,
) -> T:
    """Retry one HTTP operation for recognized transient failures."""

    return retry_call(
        operation,
        label = label,
        policy = policy,
        should_retry = is_transient_http_error,
        sleeper = sleeper,
    )

def is_transient_http_error(error: Exception) -> bool:
    """Return whether a supported HTTP client reports a transient failure."""

    return (
        _is_transient_requests_error(error) or _is_transient_curl_cffi_error(error)
    )

def _is_transient_requests_error(error: Exception) -> bool:
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
        return _is_retryable_http_status(
            _response_status_code(error)
        )

    return False

def _is_transient_curl_cffi_error(
        error: Exception,
) -> bool:
    try:
        from curl_cffi.requests import exceptions
    except ImportError:
        return False

    if isinstance(
        error,
        (
            exceptions.Timeout,
            exceptions.ConnectionError,
            exceptions.ChunkedEncodingError,
        ),
    ):
        return True

    if isinstance(error, exceptions.HTTPError):
        return _is_retryable_http_status(
            _response_status_code(error)
        )
    return False

def _response_status_code(
        error: Exception,
) -> int | None:
    response = getattr(error, "response", None)
    status_code = getattr(response, "status_code", None)

    if isinstance(status_code, int):
        return status_code

    return None

def _is_retryable_http_status(
        status_code: int | None,
) -> bool:
    if status_code in _RETRYABLE_HTTP_STATUSES:
        return True

    return (
        status_code is not None
        and 500 <= status_code < 600
    )
