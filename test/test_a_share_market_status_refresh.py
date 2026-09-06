"""Tests for scheduler-neutral A-share raw-snapshot status refresh."""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from quantmine.plugins.a_share import AStockSecurityMaster
from quantmine.workflows.a_share_status import AStockDailyStatusNormalizer
from quantmine.workflows.a_share_status_refresh import refresh_a_share_market_status
from quantmine.workflows.akshare_a_share_snapshot import (
    AkShareAStockRawSnapshotCollector,
)
from quantmine.workflows.market_status_publication import (
    MarketStatusPublishSpec,
)


def _master() -> AStockSecurityMaster:
    return AStockSecurityMaster.from_frame(
        pd.DataFrame(
            {
                "listing_id": ["000001-1", "000002-1"],
                "ticker": ["000001", "000002"],
                "list_date": ["2020-01-01", "2020-01-01"],
                "delist_date": [None, None],
                "exchange": ["SZSE", "SZSE"],
                "security_type": ["COMMON_STOCK", "COMMON_STOCK"],
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
            "成交量": [100_000, 20_000],
        }
    )


def test_refresh_normalizes_one_raw_snapshot_and_publishes_status(tmp_path) -> None:
    snapshot = AkShareAStockRawSnapshotCollector(
        spot_loader=_spot,
        suspension_loader=lambda _: pd.DataFrame(
            columns=["代码", "名称", "停牌时间"]
        ),
        clock=lambda: datetime(2024, 1, 2, 8, tzinfo=timezone.utc),
    ).collect(as_of_date="2024-01-02", root=tmp_path / "raw")

    publication = refresh_a_share_market_status(
        snapshot,
        AStockDailyStatusNormalizer(
            security_master=_master(),
            trading_calendar=pd.DatetimeIndex(["2024-01-02"]),
        ),
        as_of_date="2024-01-02 16:00:00",
        root=tmp_path / "status",
        spec=MarketStatusPublishSpec(
            dataset_id="daily_market_status",
            market="CN",
            version="history_v1",
            source="akshare_a_share_raw_snapshot",
        ),
    )

    assert publication.as_of_date == pd.Timestamp("2024-01-02")
    saved = pd.read_parquet(publication.status_path)
    assert saved["ticker"].tolist() == ["000001", "000002"]
    assert saved["is_tradable"].tolist() == [True, True]
    assert saved["is_st"].tolist() == [False, True]
    assert saved["is_limit_up"].tolist() == [True, False]
