"""Tests for reusable bounded retry behavior."""

from __future__ import annotations

import pytest

from quantmine.resilience import RetryPolicy, retry_call


class _TransientError(RuntimeError):
    pass


class _PermanentError(RuntimeError):
    pass


def test_retry_call_returns_immediately_without_sleeping() -> None:
    sleeps: list[float] = []

    result = retry_call(
        lambda: "ok",
        label="test operation",
        policy=RetryPolicy(),
        should_retry=lambda error: isinstance(error, _TransientError),
        sleeper=sleeps.append,
    )

    assert result == "ok"
    assert sleeps == []


def test_retry_call_uses_bounded_exponential_backoff() -> None:
    attempts = 0
    sleeps: list[float] = []

    def operation() -> str:
        nonlocal attempts
        attempts += 1
        if attempts < 4:
            raise _TransientError("temporary")
        return "recovered"

    result = retry_call(
        operation,
        label="test operation",
        policy=RetryPolicy(
            attempts=4,
            initial_delay_seconds=2,
            backoff_multiplier=3,
            max_delay_seconds=5,
        ),
        should_retry=lambda error: isinstance(error, _TransientError),
        sleeper=sleeps.append,
    )

    assert result == "recovered"
    assert attempts == 4
    assert sleeps == [2, 5, 5]


def test_retry_call_does_not_retry_a_rejected_error() -> None:
    attempts = 0
    sleeps: list[float] = []

    def operation() -> None:
        nonlocal attempts
        attempts += 1
        raise _PermanentError("invalid data")

    with pytest.raises(_PermanentError, match="invalid data"):
        retry_call(
            operation,
            label="test operation",
            policy=RetryPolicy(attempts=5),
            should_retry=lambda error: isinstance(error, _TransientError),
            sleeper=sleeps.append,
        )

    assert attempts == 1
    assert sleeps == []


def test_retry_call_reraises_original_error_after_exhaustion() -> None:
    error = _TransientError("still unavailable")
    attempts = 0
    sleeps: list[float] = []

    def operation() -> None:
        nonlocal attempts
        attempts += 1
        raise error

    with pytest.raises(_TransientError) as captured:
        retry_call(
            operation,
            label="test operation",
            policy=RetryPolicy(
                attempts=3,
                initial_delay_seconds=1,
            ),
            should_retry=lambda candidate: True,
            sleeper=sleeps.append,
        )

    assert captured.value is error
    assert attempts == 3
    assert sleeps == [1, 2]


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"attempts": 0}, "attempts"),
        ({"attempts": True}, "attempts"),
        ({"initial_delay_seconds": -1}, "initial_delay_seconds"),
        ({"backoff_multiplier": 0.5}, "backoff_multiplier"),
        ({"max_delay_seconds": -1}, "max_delay_seconds"),
    ],
)
def test_retry_policy_rejects_invalid_values(kwargs, message) -> None:
    with pytest.raises(ValueError, match=message):
        RetryPolicy(**kwargs)


def test_delay_after_rejects_non_positive_attempt_number() -> None:
    with pytest.raises(ValueError, match="failed_attempt"):
        RetryPolicy().delay_after(0)
