"""Reusable bounded retry support for transient external failures."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import logging
import time
from typing import TypeVar

T = TypeVar("T")
RetryPredicate = Callable[[Exception], bool]
Sleeper = Callable[[float], None]

_LOGGER = logging.getLogger(__name__)

@dataclass(frozen = True)
class RetryPolicy:
    """Bounded exponential-backoff policy."""

    attempts: int =3
    initial_delay_seconds: float = 1.0
    backoff_multiplier: float = 2.0
    max_delay_seconds: float = 8.0

    def __post_init__(self) -> None:
        if (
            not isinstance(self.attempts, int)
            or isinstance(self.attempts, bool)
            or self.attempts < 1
        ):
            raise ValueError("attempts must be a positive integer")

        if self.initial_delay_seconds < 0:
            raise ValueError(
                "initial_delay_seconds must be non-negative"
            )
        if self.backoff_multiplier < 1:
            raise ValueError(
                "backoff_multiplier must be at least 1"
            )

        if self.max_delay_seconds < 0:
            raise ValueError(
                "max_delay_seconds must be non-negative"
            )

    def delay_after(self, failed_attempt: int) -> float:
        """Return the bounded delay following a failed attempt"""

        if failed_attempt <1:
            raise ValueError("failed_attempt must be a positive integer")

        delay = (
            self.initial_delay_seconds * self.backoff_multiplier ** (failed_attempt - 1)
        )
        return min(delay, self.max_delay_seconds)

def retry_call(
        operation: Callable[[], T],
        *,
        label: str,
        policy: RetryPolicy,
        should_retry: RetryPredicate,
        sleeper: Sleeper = time.sleep
) -> T:
    """Run an operation, retrying only errors approved by the caller"""

    if not callable(operation):
        raise TypeError("operation must be callable")

    if not isinstance(label, str) or not label.strip():
        raise ValueError("label must be a non-empty string")

    if not isinstance(policy, RetryPolicy):
        raise TypeError("policy must be a RetryPolicy")

    if not callable(should_retry):
        raise TypeError("should_retry must be callable")

    if not callable(sleeper):
        raise TypeError("sleeper must be callable")

    for attempt in range(1, policy.attempts+1):
        try:
            return operation()
        except Exception as error:
            if (
                attempt == policy.attempts or not should_retry(error)
            ):
                raise

            delay = policy.delay_after(attempt)
            _LOGGER.warning(
                '%s failed with %s on attempt %d/%d; retyring in %.1fs',
                label,
                type(error).__name__,
                attempt,
                policy.attempts,
                delay,
            )
            sleeper(delay)

    raise AssertionError("retry loop exited without returning or raising")
