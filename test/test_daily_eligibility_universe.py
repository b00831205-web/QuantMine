"""Market-neutral point-in-time eligibility universe tests."""

from __future__ import annotations

import pandas as pd
import pytest

from quantmine.plugins.eligibility import (
    DailyEligibilityPolicy,
    DailyEligibilityUniverse,
)


def _daily_status() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": ["2024-01-02", "2024-01-02", "2024-01-02"],
            "ticker": ["AAA", "BBB", "CCC"],
            "is_listed": [True, True, True],
            "is_tradable": [True, False, True],
            "listing_days": [100, 100, 10],
            "is_halted": [False, True, False],
        }
    )


def test_daily_eligibility_universe_uses_the_shared_market_neutral_contract() -> None:
    universe = DailyEligibilityUniverse.from_frame(_daily_status())

    assert universe.get_constituents(pd.Timestamp("2024-01-02")) == {"AAA"}
    assert universe.status_on(pd.Timestamp("2024-01-02"), "BBB") == {
        "is_halted": True,
    }


def test_daily_eligibility_policy_can_allow_new_listings_or_untradable_records() -> None:
    universe = DailyEligibilityUniverse.from_frame(
        _daily_status(),
        policy=DailyEligibilityPolicy(
            min_listing_days=0,
            require_tradable=False,
        ),
    )

    assert universe.get_constituents(pd.Timestamp("2024-01-02")) == {
        "AAA", "BBB", "CCC"
    }


def test_daily_eligibility_universe_rejects_missing_canonical_fields() -> None:
    with pytest.raises(ValueError, match="missing required columns: is_tradable"):
        DailyEligibilityUniverse.from_frame(
            _daily_status().drop(columns="is_tradable")
        )
