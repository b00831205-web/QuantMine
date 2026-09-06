"""Tests for adapting generic daily status into A-share eligibility input."""

from __future__ import annotations

import pandas as pd
import pytest

from quantmine.plugins.a_share import AStockDailyMarketStatusEligibilityBuilder
from quantmine.workflows.market_status import DailyMarketStatus


def _status(as_of_date: pd.Timestamp) -> DailyMarketStatus:
    return DailyMarketStatus.from_frame(
        pd.DataFrame(
            {
                "date": [as_of_date] * 4,
                "ticker": ["000001", "000002", "000003", "000004"],
                "is_listed": [True, True, False, True],
                "is_tradable": [True, False, False, True],
                "listing_days": [100, 100, 0, 100],
                "is_st": [False, True, False, True],
                "is_suspended": [False, True, False, False],
                "is_limit_up": [False, False, False, False],
                "is_limit_down": [False, False, False, False],
                "exchange": ["SZSE", "SZSE", "SSE", "SZSE"],
            }
        )
    )


def test_builder_adapts_generic_market_status_and_applies_a_share_policy() -> None:
    builder = AStockDailyMarketStatusEligibilityBuilder(status_loader=_status)

    frame = builder.build(pd.Timestamp("2024-01-02 14:30:00"))

    assert frame.to_dict("records") == [
        {
            "date": pd.Timestamp("2024-01-02"),
            "ticker": "000001",
            "is_listed": True,
            "is_tradable": True,
            "listing_days": 100,
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
            "listing_days": 100,
            "is_st": True,
            "is_suspended": True,
            "is_limit_up": False,
            "is_limit_down": False,
        },
        {
            "date": pd.Timestamp("2024-01-02"),
            "ticker": "000003",
            "is_listed": False,
            "is_tradable": False,
            "listing_days": 0,
            "is_st": False,
            "is_suspended": False,
            "is_limit_up": False,
            "is_limit_down": False,
        },
        {
            "date": pd.Timestamp("2024-01-02"),
            "ticker": "000004",
            "is_listed": True,
            "is_tradable": False,
            "listing_days": 100,
            "is_st": True,
            "is_suspended": False,
            "is_limit_up": False,
            "is_limit_down": False,
        },
    ]


def test_builder_rejects_a_status_loader_returning_another_date() -> None:
    builder = AStockDailyMarketStatusEligibilityBuilder(
        status_loader=lambda _: _status(pd.Timestamp("2024-01-03"))
    )

    with pytest.raises(ValueError, match="does not match requested date"):
        builder.build(pd.Timestamp("2024-01-02"))
