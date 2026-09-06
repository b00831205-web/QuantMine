"""Tests for the market-neutral daily market-status contract."""

from __future__ import annotations

import pandas as pd
import pytest

from quantmine.workflows.market_status import DailyMarketStatus


def _a_share_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": ["2024-01-02", "2024-01-02"],
            "ticker": ["000001", "000002"],
            "is_listed": [True, True],
            "is_tradable": [True, False],
            "listing_days": [100, 50],
            "listing_id": ["000001-1", "000002-1"],
            "is_st": [False, True],
            "is_suspended": [False, True],
            "is_limit_up": [False, False],
            "is_limit_down": [False, False],
        }
    )


def test_daily_market_status_normalizes_core_columns_and_preserves_extensions() -> None:
    status = DailyMarketStatus.from_frame(_a_share_frame())

    assert status.as_of_date == pd.Timestamp("2024-01-02")
    assert status.frame.to_dict("records") == [
        {
            "date": pd.Timestamp("2024-01-02"),
            "ticker": "000001",
            "is_listed": True,
            "is_tradable": True,
            "listing_days": 100,
            "listing_id": "000001-1",
            "is_st": False,
            "is_suspended": False,
            "is_limit_up": False,
            "is_limit_down": False,
        },
        {
            "date": pd.Timestamp("2024-01-02"),
            "ticker": "000002",
            "is_listed": True,
            "is_tradable": False,
            "listing_days": 50,
            "listing_id": "000002-1",
            "is_st": True,
            "is_suspended": True,
            "is_limit_up": False,
            "is_limit_down": False,
        },
    ]


def test_daily_market_status_accepts_other_market_extensions() -> None:
    frame = pd.DataFrame(
        {
            "date": ["2024-01-02"],
            "ticker": ["AAPL"],
            "is_listed": [True],
            "is_tradable": [False],
            "listing_days": [15_000],
            "is_halted": [True],
            "is_adr": [False],
        }
    )

    status = DailyMarketStatus.from_frame(frame)

    assert bool(status.frame.loc[0, "is_halted"]) is True
    assert bool(status.frame.loc[0, "is_adr"]) is False


@pytest.mark.parametrize(
    ("frame", "message"),
    [
        (_a_share_frame().drop(columns="is_tradable"), "missing required columns: is_tradable"),
        (
            pd.DataFrame(
                {
                    "date": ["2024-01-02", "2024-01-03"],
                    "ticker": ["000001", "000002"],
                    "is_listed": [True, True],
                    "is_tradable": [True, True],
                    "listing_days": [100, 101],
                }
            ),
            "exactly one date",
        ),
        (_a_share_frame().assign(ticker=["000001", "000001"]), "duplicate tickers"),
        (_a_share_frame().assign(listing_days=[100, -1]), "non-negative"),
    ],
)
def test_daily_market_status_rejects_invalid_core_data(
    frame: pd.DataFrame,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        DailyMarketStatus.from_frame(frame)
