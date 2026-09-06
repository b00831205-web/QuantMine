"""Market-neutral trading-session gates used before scheduled production."""

from __future__ import annotations

import pandas as pd
import pytest

from quantmine.workflows.trading_sessions import (
    ExchangeCalendarSessionGate,
    StaticCalendarSessionGate,
    is_xnys_trading_session,
)


def test_static_calendar_gate_normalizes_dates_and_rejects_duplicates() -> None:
    gate = StaticCalendarSessionGate(
        pd.DatetimeIndex(["2024-01-02 15:00:00", "2024-01-03"]),
    )

    assert gate.is_session("2024-01-02") is True
    assert gate.is_session("2024-01-01") is False

    with pytest.raises(ValueError, match="duplicate"):
        StaticCalendarSessionGate(
            pd.DatetimeIndex(["2024-01-02", "2024-01-02 12:00:00"]),
        )


def test_exchange_calendar_gate_delegates_to_the_named_calendar() -> None:
    requested: list[str] = []

    class FakeCalendar:
        def is_session(self, value: pd.Timestamp) -> bool:
            return value == pd.Timestamp("2024-07-03")

    def fake_factory(name: str) -> FakeCalendar:
        requested.append(name)
        return FakeCalendar()

    gate = ExchangeCalendarSessionGate(
        calendar_name="XNYS",
        calendar_factory=fake_factory,
    )

    assert gate.is_session("2024-07-03") is True
    assert gate.is_session("2024-07-04") is False
    assert requested == ["XNYS", "XNYS"]


def test_exchange_calendar_gate_rejects_an_empty_calendar_name() -> None:
    with pytest.raises(ValueError, match="calendar_name"):
        ExchangeCalendarSessionGate(calendar_name=" ")


def test_xnys_helper_uses_the_us_market_calendar() -> None:
    requested: list[str] = []

    class FakeCalendar:
        def is_session(self, value: pd.Timestamp) -> bool:
            return value == pd.Timestamp("2024-11-29")

    def fake_factory(name: str) -> FakeCalendar:
        requested.append(name)
        return FakeCalendar()

    assert is_xnys_trading_session(
        "2024-11-29",
        calendar_factory=fake_factory,
    ) is True
    assert is_xnys_trading_session(
        "2024-11-28",
        calendar_factory=fake_factory,
    ) is False
    assert requested == ["XNYS", "XNYS"]
