"""Tests for shared HTTP retry classification."""

from __future__ import annotations

from types import SimpleNamespace

from curl_cffi.requests import exceptions as curl_exceptions
import pytest
import requests

from quantmine.http_resilience import (
    is_transient_http_error,
    retry_http_call,
)


@pytest.mark.parametrize(
    "error",
    [
        requests.exceptions.Timeout("timeout"),
        requests.exceptions.ConnectionError("connection"),
        requests.exceptions.SSLError("tls"),
        requests.exceptions.ChunkedEncodingError("stream"),
        curl_exceptions.Timeout("timeout"),
        curl_exceptions.ConnectionError("connection"),
        curl_exceptions.SSLError("tls"),
        curl_exceptions.ChunkedEncodingError("stream"),
    ],
)
def test_transient_transport_errors_are_retryable(error: Exception) -> None:
    assert is_transient_http_error(error) is True


@pytest.mark.parametrize(
    ("error_type", "status_code", "expected"),
    [
        (requests.exceptions.HTTPError, 400, False),
        (requests.exceptions.HTTPError, 408, True),
        (requests.exceptions.HTTPError, 425, True),
        (requests.exceptions.HTTPError, 429, True),
        (requests.exceptions.HTTPError, 503, True),
        (curl_exceptions.HTTPError, 404, False),
        (curl_exceptions.HTTPError, 429, True),
        (curl_exceptions.HTTPError, 502, True),
    ],
)
def test_http_status_classification(
    error_type,
    status_code: int,
    expected: bool,
) -> None:
    error = error_type(
        "response status",
        response=SimpleNamespace(status_code=status_code),
    )

    assert is_transient_http_error(error) is expected


def test_data_and_programming_errors_are_not_retryable() -> None:
    assert is_transient_http_error(ValueError("invalid schema")) is False
    assert is_transient_http_error(KeyError("missing field")) is False


def test_retry_http_call_retries_tls_failure_without_real_sleep() -> None:
    attempts = 0
    sleeps: list[float] = []

    def operation() -> str:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise requests.exceptions.SSLError("temporary TLS failure")
        return "ok"

    result = retry_http_call(
        operation,
        label="market-data request",
        sleeper=sleeps.append,
    )

    assert result == "ok"
    assert attempts == 3
    assert sleeps == [1.0, 2.0]


def test_retry_http_call_does_not_retry_schema_failure() -> None:
    attempts = 0
    sleeps: list[float] = []

    def operation() -> None:
        nonlocal attempts
        attempts += 1
        raise ValueError("missing columns")

    with pytest.raises(ValueError, match="missing columns"):
        retry_http_call(
            operation,
            label="market-data request",
            sleeper=sleeps.append,
        )

    assert attempts == 1
    assert sleeps == []
