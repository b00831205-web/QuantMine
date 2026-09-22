"""Market-neutral gates for deciding whether a scheduled date is a sessions."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol

import pandas as pd

class ExchangeCalendar(Protocol):
    def is_session(self, value: pd.Timestamp) -> bool: ...

CalendarFactory = Callable[[str], ExchangeCalendar]

def _load_exchange_calendar(name:str) -> ExchangeCalendar:
    try:
        import exchange_calendars as xcals

    except ImportError as error:
        raise RuntimeError(
            "exchange-calendar is required for exchanged-backed "
            "trading-sessions checks"
        ) from error

    return xcals.get_calendar(name)

@dataclass(frozen=True)
class StaticCalendarSessionGate:
    """Check a date against an immutable, explicitly supplied sessions calendar."""

    sessions: pd.DatetimeIndex

    def __post_init__(self) -> None:
        normalized = pd.DatetimeIndex(
            pd.to_datetime(self.sessions, errors = "raise"),
        ).normalize()
        if normalized.has_duplicates:
            raise ValueError("trading-session calendar contains duplicate dates")

        object.__setattr__(self, "sessions", normalized.sort_values())

    def is_session(self, as_of_date: pd.Timestamp | str) -> bool:
        date = pd.Timestamp(as_of_date).normalize()
        return date in self.sessions

@dataclass(frozen = True)
class ExchangeCalendarSessionGate:
    """Check a date against a named exchange calendar, such as XNYS"""
    calendar_name : str
    calendar_factory: CalendarFactory = field(default = _load_exchange_calendar,
                                              repr = False,
                                              compare = False,)

    def __post_init__(self) -> None:
        if(
            not self.calendar_name
            or self.calendar_name.strip() != self.calendar_name
        ):
            raise ValueError(
                "calendar_name must be a non-empty trimmed string"
            )

    def is_session(self, as_of_date: pd.Timestamp | str) -> bool:
        date = pd.Timestamp(as_of_date).normalize()
        return bool(
            self.calendar_factory(self.calendar_name).is_session(date)
        )

def is_xnys_trading_session(
        as_of_date: pd.Timestamp | str,
        *,
        calendar_factory: CalendarFactory = _load_exchange_calendar,
) -> bool:  
    """Return whether a date is an NYSE/XNYS trading session"""

    return ExchangeCalendarSessionGate(
        calendar_name = "XNYS",
        calendar_factory = calendar_factory,
    ).is_session(as_of_date)