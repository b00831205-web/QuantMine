"""Convert quantile membership history into portfolio target weights"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from math import isfinite
from numbers import Real

import pandas as pd


def _validate_tickers(tickers: object) -> pd.Index:
    if not isinstance(tickers, pd.Index):
        tickers = pd.Index(tickers)

    if tickers.has_duplicates:
        raise ValueError("tickers must not contain duplicates")

    for ticker in tickers:
        if not isinstance(ticker, str) or not ticker or ticker.strip() != ticker:
            raise ValueError("tickers must contain non-empty trimmed strings")

    return tickers

def _member_weights(members: object, *, group: str) -> dict[str, float]:
    if isinstance(members, Mapping):
        raw_weights = dict(members)

    elif isinstance(members, Iterable) and not isinstance(members, (str, bytes)):
        member_list = list(members)

        if len(set(member_list)) != len(member_list):
            raise ValueError(f"quantile group {group!r} contains duplicate tickers")

        raw_weights = {ticker: 1.0 for ticker in member_list}

    else:
        raise TypeError(
            f"quantile group {group!r} must be a mapping or ticker iterable"
        )

    if not raw_weights:
        raise ValueError(f"quantile group {group!r} must not be empty")

    normalized: dict[str, float] = {}
    for ticker, weight in raw_weights.items():
        if not isinstance(ticker, str) or not ticker or ticker.strip() != ticker:
            raise ValueError(f"quantile group {group!r} contains an invalid ticker")

        if isinstance(weight, bool) or not isinstance(weight, Real):
            raise TypeError(f"quantile group {group!r} weights must be real numbers")

        numeric_weight = float(weight)
        if not isfinite(numeric_weight) or numeric_weight < 0:
            raise ValueError(f"quantile group {group!r} weights must be finite and non-negative")

        normalized[ticker] = numeric_weight

    total_weight = sum(normalized.values())
    if total_weight <= 0:
        raise ValueError(f"quantile group {group!r} weitghs must sum above zero")

    return {
        ticker: weight / total_weight for ticker, weight in normalized.items()
    }

def build_quantile_target_weights(ticker_history: object, *, tickers: pd.Index, group: str, gross_exposure: float = 1.0) -> pd.DataFrame:
    """Build a date-by-ticker target-weight schedule for one quantile"""

    if not isinstance(ticker_history, list):
        raise TypeError("ticker_history must be a list")

    universe = _validate_tickers(tickers)

    if not isinstance(group, str) or not group or group.strip() != group:
        raise ValueError("group must be a non-empty trimmed string")

    if isinstance(gross_exposure, bool) or not isinstance(gross_exposure, Real):
        raise TypeError("gross_exposure must be a real number")

    exposure = float(gross_exposure)
    if not isfinite(exposure) or exposure < 0 or exposure >1:
        raise ValueError("gross_exposure must be between zero and one")

    if not ticker_history:
        empty = pd.DataFrame(columns=universe.copy(), index= pd.DatetimeIndex([], name="date"), dtype=float)

        return empty
    rows: list[pd.Series] = []
    dates: list[pd.Timestamp] = []
    previous_date: pd.Timestamp | None = None

    for snapshot in ticker_history:
        if not isinstance(snapshot, Mapping):
            raise TypeError(
                "every ticker-history snapshot must be a mapping"
            )

        trade_date = snapshot.get("date")
        if not isinstance(trade_date, pd.Timestamp):
            raise TypeError("ticker-history date must be a pandas Timestamp")

        if pd.isna(trade_date):
            raise ValueError("ticker-history date must not be NaT")

        if previous_date is not None and trade_date <= previous_date:
            raise ValueError("ticker-history dates must be strictly increasing")

        if group not in snapshot:
            raise ValueError(f"ticker-history snapshot has no group {group!r}")

        group_weights= _member_weights(snapshot[group], group= group)

        unknown_tickers = sorted(set(group_weights).difference(universe))
        if unknown_tickers:
            raise ValueError(
                f"ticker-history group contains tickers unavailable in close {unknown_tickers}"
            )

        row = pd.Series(0.0, index =universe.copy(), dtype=float)
        for ticker, weight in group_weights.items():
            row.loc[ticker] = weight * exposure

        rows.append(row)
        dates.append(trade_date)
        previous_date =trade_date

    target_weights = pd.DataFrame(rows, index = pd.DatetimeIndex(dates, name= "date"), columns=universe.copy(), dtype=float)
    return target_weights