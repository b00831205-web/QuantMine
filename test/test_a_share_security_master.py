"""Tests for point-in-time A-share security-master status derivation."""

from __future__ import annotations

import pandas as pd
import pytest

from quantmine.plugins.a_share import AStockSecurityMaster


def _master_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "listing_id": ["000001-1", "000002-1", "000003-1", "000004-1", "000004-2"],
            "ticker": ["000001", "000002", "000003", "000004", "000004"],
            "list_date": ["2023-12-29", "2024-01-04", "2020-01-01", "2020-01-01", "2024-01-04"],
            "delist_date": [None, None, "2024-01-03", "2024-01-03", None],
            "exchange": ["SZSE", "SZSE", "SSE", "SSE", "SSE"],
            "security_type": ["COMMON_STOCK"] * 5,
        }
    )


def _calendar() -> pd.DatetimeIndex:
    return pd.DatetimeIndex(["2024-01-02", "2024-01-03", "2024-01-04"])


def test_security_master_derives_listing_state_and_trading_age() -> None:
    master = AStockSecurityMaster.from_frame(_master_frame())

    status = master.status_on(
        pd.Timestamp("2024-01-04"),
        trading_calendar=_calendar(),
    )

    assert status.to_dict("records") == [
        {
            "listing_id": "000001-1",
            "ticker": "000001",
            "is_listed": True,
            "listing_days": 3,
            "exchange": "SZSE",
            "security_type": "COMMON_STOCK",
        },
        {
            "listing_id": "000002-1",
            "ticker": "000002",
            "is_listed": True,
            "listing_days": 1,
            "exchange": "SZSE",
            "security_type": "COMMON_STOCK",
        },
        {
            "listing_id": "000003-1",
            "ticker": "000003",
            "is_listed": False,
            "listing_days": 0,
            "exchange": "SSE",
            "security_type": "COMMON_STOCK",
        },
        {
            "listing_id": "000004-2",
            "ticker": "000004",
            "is_listed": True,
            "listing_days": 1,
            "exchange": "SSE",
            "security_type": "COMMON_STOCK",
        },
    ]


def test_security_master_rejects_overlapping_intervals_and_invalid_date_ranges() -> None:
    overlap = _master_frame()
    overlap.loc[4, "list_date"] = "2024-01-02"
    with pytest.raises(ValueError, match="overlapping listing intervals"):
        AStockSecurityMaster.from_frame(overlap)

    invalid = _master_frame()
    invalid.loc[0, "delist_date"] = "2023-12-01"
    with pytest.raises(ValueError, match="before list_date"):
        AStockSecurityMaster.from_frame(invalid)


def test_security_master_exports_a_defensive_normalized_frame() -> None:
    master = AStockSecurityMaster.from_frame(_master_frame())

    exported = master.to_frame()
    exported.loc[0, "ticker"] = "changed"

    restored = master.to_frame()
    assert restored.loc[0, "ticker"] == "000001"
    assert list(restored.columns) == [
        "listing_id",
        "ticker",
        "list_date",
        "delist_date",
        "exchange",
        "security_type",
    ]
    assert restored["exchange"].tolist() == [
        "SZSE",
        "SZSE",
        "SSE",
        "SSE",
        "SSE",
    ]
