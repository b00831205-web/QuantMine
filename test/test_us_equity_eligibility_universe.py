"""Tests for the US-equity adapter over the generic eligibility universe."""

from __future__ import annotations

import pandas as pd
import pytest

from quantmine.plugins.us_equity import (
    USEquityEligibilityPolicy,
    USEquityEligibilityUniverse,
)


def _eligibility_table() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": ["2024-01-02"] * 5,
            "ticker": ["AAA", "BBB", "CCC", "DDD", "EEE"],
            "is_listed": [True, True, True, True, True],
            "is_halted": [False, True, False, False, False],
            "listing_days": [100, 100, 100, 100, 10],
            "security_type": [
                "COMMON_STOCK",
                "COMMON_STOCK",
                "ETF",
                "COMMON_STOCK",
                "COMMON_STOCK",
            ],
            "is_adr": [False, False, False, True, False],
        }
    )


def test_us_universe_filters_halts_security_type_adrs_and_new_listings() -> None:
    universe = USEquityEligibilityUniverse.from_frame(_eligibility_table())

    assert universe.get_constituents(pd.Timestamp("2024-01-02")) == {"AAA"}
    assert universe.status_on(pd.Timestamp("2024-01-02"), "CCC") == {
        "is_halted": False,
        "security_type": "ETF",
        "is_adr": False,
    }


def test_us_policy_can_allow_etfs_and_adrs_without_allowing_halted_symbols() -> None:
    universe = USEquityEligibilityUniverse.from_frame(
        _eligibility_table(),
        policy=USEquityEligibilityPolicy(
            allowed_security_types=frozenset({"COMMON_STOCK", "ETF"}),
            exclude_adrs=False,
        ),
    )

    assert universe.get_constituents(pd.Timestamp("2024-01-02")) == {
        "AAA",
        "CCC",
        "DDD",
    }


def test_us_universe_rejects_missing_market_specific_status_columns() -> None:
    incomplete = _eligibility_table().drop(columns="is_halted")

    with pytest.raises(ValueError, match="missing required columns: is_halted"):
        USEquityEligibilityUniverse.from_frame(incomplete)
