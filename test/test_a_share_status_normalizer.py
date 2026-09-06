"""Tests for normalizing forward AkShare snapshots into daily status tables."""

from __future__ import annotations

import pandas as pd
import pytest

from quantmine.plugins.a_share import AStockSecurityMaster
from quantmine.workflows.a_share_status import AStockDailyStatusNormalizer
from quantmine.workflows.market_status import DailyMarketStatus


def _master() -> AStockSecurityMaster:
    return AStockSecurityMaster.from_frame(
        pd.DataFrame(
            {
                "listing_id": ["000001-1", "000002-1", "000003-1"],
                "ticker": ["000001", "000002", "000003"],
                "list_date": ["2020-01-01", "2020-01-01", "2020-01-01"],
                "delist_date": [None, None, "2024-01-02"],
                "exchange": ["SZSE", "SZSE", "SSE"],
                "security_type": ["COMMON_STOCK"] * 3,
            }
        )
    )


def _spot() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "代码": ["000001", "000002"],
            "名称": ["平安银行", "*ST示例"],
            "最新价": [11.0, 5.0],
            "涨停": [11.0, 5.5],
            "跌停": [9.0, 4.5],
        }
    )


def _suspension() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "代码": ["000002"],
            "名称": ["*ST示例"],
            "停牌时间": ["2024-01-02"],
        }
    )


def test_normalizer_derives_one_generic_daily_market_status() -> None:
    normalizer = AStockDailyStatusNormalizer(
        security_master=_master(),
        trading_calendar=pd.DatetimeIndex(["2024-01-02"]),
    )

    result = normalizer.normalize(
        as_of_date="2024-01-02",
        spot=_spot(),
        suspension=_suspension(),
    )

    assert isinstance(result, DailyMarketStatus)
    assert result.as_of_date == pd.Timestamp("2024-01-02")
    assert result.frame.to_dict("records") == [
        {
            "date": pd.Timestamp("2024-01-02"),
            "ticker": "000001",
            "is_listed": True,
            "is_tradable": True,
            "listing_days": 1,
            "listing_id": "000001-1",
            "exchange": "SZSE",
            "security_type": "COMMON_STOCK",
            "is_st": False,
            "is_suspended": False,
            "is_limit_up": True,
            "is_limit_down": False,
        },
        {
            "date": pd.Timestamp("2024-01-02"),
            "ticker": "000002",
            "is_listed": True,
            "is_tradable": False,
            "listing_days": 1,
            "listing_id": "000002-1",
            "exchange": "SZSE",
            "security_type": "COMMON_STOCK",
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
            "listing_id": "000003-1",
            "exchange": "SSE",
            "security_type": "COMMON_STOCK",
            "is_st": False,
            "is_suspended": False,
            "is_limit_up": False,
            "is_limit_down": False,
        },
    ]


def test_normalizer_rejects_an_active_master_ticker_missing_from_spot() -> None:
    normalizer = AStockDailyStatusNormalizer(
        security_master=_master(),
        trading_calendar=pd.DatetimeIndex(["2024-01-02"]),
    )

    with pytest.raises(ValueError, match="active master tickers missing from spot"):
        normalizer.normalize(
            as_of_date="2024-01-02",
            spot=_spot().iloc[:1],
            suspension=_suspension(),
        )
