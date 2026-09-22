"""Tests for the audited, point-in-time A-share eligibility universe model."""

from __future__ import annotations

import pandas as pd
import pytest

from quantmine.plugins.a_share import (
    AStockEligibilityPolicy,
    AStockEligibilityUniverse,
)


def _eligibility_table() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": [
                "2024-01-02", "2024-01-02", "2024-01-02", "2024-01-02",
                "2024-01-02", "2024-01-03", "2024-01-03",
            ],
            "ticker": ["AAA", "BBB", "CCC", "DDD", "EEE", "AAA", "BBB"],
            "is_listed": [True, True, True, True, True, True, True],
            "is_st": [False, True, False, False, False, True, False],
            "is_suspended": [False, False, True, False, False, False, False],
            "listing_days": [100, 100, 100, 10, 100, 101, 101],
            "is_limit_up": [False, False, False, False, True, False, False],
            "is_limit_down": [False, False, False, False, False, False, False],
        }
    )


def test_eligibility_universe_filters_st_suspension_and_new_listings() -> None:
    universe = AStockEligibilityUniverse.from_frame(_eligibility_table())

    assert universe.get_constituents(pd.Timestamp("2024-01-02")) == {"AAA", "EEE"}
    assert universe.get_constituents(pd.Timestamp("2024-01-03")) == {"BBB"}


def test_limit_flags_are_preserved_but_not_used_for_signal_day_membership() -> None:
    universe = AStockEligibilityUniverse.from_frame(_eligibility_table())

    assert "EEE" in universe.get_constituents(pd.Timestamp("2024-01-02"))
    assert universe.status_on(pd.Timestamp("2024-01-02"), "EEE") == {
        "is_suspended": False,
        "is_limit_up": True,
        "is_limit_down": False,
    }


def test_execution_status_is_available_for_excluded_securities() -> None:
    universe = AStockEligibilityUniverse.from_frame(_eligibility_table())

    assert "CCC" not in universe.get_constituents(pd.Timestamp("2024-01-02"))
    assert universe.status_on(pd.Timestamp("2024-01-02"), "CCC") == {
        "is_suspended": True,
        "is_limit_up": False,
        "is_limit_down": False,
    }


def test_eligibility_policy_can_change_the_minimum_listing_age() -> None:
    universe = AStockEligibilityUniverse.from_frame(
        _eligibility_table(),
        policy=AStockEligibilityPolicy(min_listing_days=0),
    )

    assert "DDD" in universe.get_constituents(pd.Timestamp("2024-01-02"))


def test_eligibility_policy_can_keep_suspended_non_st_securities() -> None:
    universe = AStockEligibilityUniverse.from_frame(
        _eligibility_table(),
        policy=AStockEligibilityPolicy(exclude_st=True, exclude_suspended=False),
    )

    assert universe.get_constituents(pd.Timestamp("2024-01-02")) == {
        "AAA",
        "CCC",
        "EEE",
    }


def test_eligibility_universe_rejects_missing_or_duplicate_daily_records() -> None:
    incomplete = _eligibility_table().drop(columns="is_suspended")
    with pytest.raises(ValueError, match="missing required columns: is_suspended"):
        AStockEligibilityUniverse.from_frame(incomplete)

    duplicate = pd.concat([_eligibility_table(), _eligibility_table().iloc[[0]]])
    with pytest.raises(ValueError, match="duplicate date/ticker rows"):
        AStockEligibilityUniverse.from_frame(duplicate)
