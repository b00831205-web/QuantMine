"""Tests for normalizing forward AkShare snapshots into daily status tables."""

from __future__ import annotations

import pandas as pd
import pytest

from quantmine.plugins.a_share import AStockSecurityMaster
from quantmine.workflows.a_share_status import (
    AStockDailyStatusNormalizer,
    SpotCoveragePolicy,
)
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


def test_security_master_returns_tickers_listed_during_research_window() -> None:
    master = AStockSecurityMaster.from_frame(
        pd.DataFrame(
            {
                "listing_id": ["A-1", "B-1", "C-1", "D-1", "E-1"],
                "ticker": ["000001", "000002", "000003", "000004", "000004"],
                "list_date": [
                    "2020-01-01",
                    "2020-01-01",
                    "2024-02-01",
                    "2020-01-01",
                    "2024-01-03",
                ],
                "delist_date": [
                    None,
                    "2024-01-02",
                    None,
                    "2023-01-01",
                    None,
                ],
                "exchange": ["SZSE"] * 5,
                "security_type": ["COMMON_STOCK"] * 5,
            }
        )
    )

    assert master.tickers_during(
        "2024-01-02",
        "2024-01-31",
    ) == ("000001", "000004")

    with pytest.raises(ValueError, match="end_date must not be before start_date"):
        master.tickers_during("2024-02-01", "2024-01-01")


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
            "is_source_missing": False,
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
            "is_source_missing": False,
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
            "is_source_missing": False,
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


def test_normalizer_ignores_out_of_universe_suspension_rows() -> None:
    suspension = pd.concat(
        [
            _suspension(),
            pd.DataFrame(
                {
                    "代码": ["200016"],
                    "名称": ["B股示例"],
                    "停牌时间": ["2024-01-02"],
                }
            ),
        ],
        ignore_index=True,
    )
    normalizer = AStockDailyStatusNormalizer(
        security_master=_master(),
        trading_calendar=pd.DatetimeIndex(["2024-01-02"]),
    )

    result = normalizer.normalize(
        as_of_date="2024-01-02",
        spot=_spot(),
        suspension=suspension,
    )

    status = result.frame.set_index("ticker")
    assert "200016" not in status.index
    assert bool(status.loc["000002", "is_suspended"]) is True


def test_normalizer_marks_an_allowed_source_gap_as_non_tradable() -> None:
    normalizer = AStockDailyStatusNormalizer(
        security_master=_master(),
        trading_calendar=pd.DatetimeIndex(["2024-01-02"]),
        spot_coverage_policy=SpotCoveragePolicy(
            max_missing_count=1,
            max_missing_ratio=0.5,
        ),
    )

    result = normalizer.normalize(
        as_of_date="2024-01-02",
        spot=_spot().iloc[:1],
        suspension=_suspension().iloc[:0],
    )

    missing = result.frame.set_index("ticker").loc["000002"]
    assert bool(missing["is_listed"]) is True
    assert bool(missing["is_source_missing"]) is True
    assert bool(missing["is_suspended"]) is False
    assert bool(missing["is_tradable"]) is False
    assert bool(missing["is_st"]) is False
    assert bool(missing["is_limit_up"]) is False
    assert bool(missing["is_limit_down"]) is False


def test_normalizer_rejects_a_source_gap_exceeding_either_threshold() -> None:
    normalizer = AStockDailyStatusNormalizer(
        security_master=_master(),
        trading_calendar=pd.DatetimeIndex(["2024-01-02"]),
        spot_coverage_policy=SpotCoveragePolicy(
            max_missing_count=1,
            max_missing_ratio=0.1,
        ),
    )

    with pytest.raises(ValueError, match="active master tickers missing from spot"):
        normalizer.normalize(
            as_of_date="2024-01-02",
            spot=_spot().iloc[:1],
            suspension=_suspension().iloc[:0],
        )


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"max_missing_count": -1}, "max_missing_count"),
        ({"max_missing_count": True}, "max_missing_count"),
        ({"max_missing_ratio": -0.01}, "max_missing_ratio"),
        ({"max_missing_ratio": 1.01}, "max_missing_ratio"),
        ({"max_missing_ratio": True}, "max_missing_ratio"),
    ],
)
def test_spot_coverage_policy_rejects_invalid_thresholds(
    kwargs: dict[str, object],
    message: str,
) -> None:
    with pytest.raises((TypeError, ValueError), match=message):
        SpotCoveragePolicy(**kwargs)


def test_normalizer_accepts_precomputed_limit_flags_from_a_fallback_source() -> None:
    spot = _spot().drop(columns=["涨停", "跌停"])
    spot["is_limit_up"] = [True, False]
    spot["is_limit_down"] = [False, True]

    normalized = AStockDailyStatusNormalizer._normalize_spot(spot)

    assert normalized.loc[:, ["ticker", "is_limit_up", "is_limit_down"]].to_dict(
        "records"
    ) == [
        {
            "ticker": "000001",
            "is_limit_up": True,
            "is_limit_down": False,
        },
        {
            "ticker": "000002",
            "is_limit_up": False,
            "is_limit_down": True,
        },
    ]


def test_normalizer_rejects_spot_without_any_limit_status_representation() -> None:
    spot = _spot().drop(columns=["涨停", "跌停"])

    with pytest.raises(ValueError, match="limit status representation"):
        AStockDailyStatusNormalizer._normalize_spot(spot)
