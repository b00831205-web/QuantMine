"""Tests for immutable publication of generic daily market status."""

from __future__ import annotations

import json

import pandas as pd
import pytest

from quantmine.workflows.market_status import DailyMarketStatus
from quantmine.workflows.market_status_publication import (
    MarketStatusPublishSpec,
    publish_daily_market_status,
)


def _status() -> DailyMarketStatus:
    return DailyMarketStatus.from_frame(
        pd.DataFrame(
            {
                "date": ["2024-01-02", "2024-01-02"],
                "ticker": ["000002", "000001"],
                "is_listed": [True, True],
                "is_tradable": [False, True],
                "listing_days": [100, 100],
                "is_st": [True, False],
                "is_suspended": [True, False],
            }
        )
    )


def _spec() -> MarketStatusPublishSpec:
    return MarketStatusPublishSpec(
        dataset_id="daily_market_status",
        market="CN",
        version="20240102T160000Z",
        source="akshare_a_share_raw_snapshot",
        source_observed_at="2024-01-02T16:00:00+08:00",
    )


def test_publish_writes_one_immutable_market_and_date_partition(tmp_path) -> None:
    publication = publish_daily_market_status(
        _status(),
        root=tmp_path,
        spec=_spec(),
    )

    expected_directory = (
        tmp_path
        / "daily_market_status"
        / "market=CN"
        / "date=2024-01-02"
        / "versions"
        / "20240102T160000Z"
    )
    assert publication.output_dir == expected_directory
    assert publication.status_path == expected_directory / "status.parquet"
    assert publication.manifest_path == expected_directory / "manifest.json"
    assert publication.row_count == 2
    assert publication.as_of_date == pd.Timestamp("2024-01-02")

    saved = pd.read_parquet(publication.status_path)
    assert saved["ticker"].tolist() == ["000001", "000002"]
    assert saved["is_st"].tolist() == [False, True]

    manifest = json.loads(publication.manifest_path.read_text(encoding="utf-8"))
    assert manifest == {
        "as_of_date": "2024-01-02",
        "content_sha256": publication.content_sha256,
        "dataset_id": "daily_market_status",
        "market": "CN",
        "row_count": 2,
        "schema_version": "daily_market_status_v1",
        "source": "akshare_a_share_raw_snapshot",
        "source_observed_at": "2024-01-02T16:00:00+08:00",
        "version": "20240102T160000Z",
    }


def test_publish_is_idempotent_but_rejects_different_content_for_one_version(tmp_path) -> None:
    first = publish_daily_market_status(_status(), root=tmp_path, spec=_spec())
    second = publish_daily_market_status(_status(), root=tmp_path, spec=_spec())
    assert second == first

    changed = DailyMarketStatus.from_frame(
        _status().frame.assign(is_tradable=[True, True])
    )
    with pytest.raises(FileExistsError, match="already exists with different content"):
        publish_daily_market_status(changed, root=tmp_path, spec=_spec())


def test_publish_rejects_a_specification_for_another_market_date(tmp_path) -> None:
    with pytest.raises(ValueError, match="market must be a safe path segment"):
        MarketStatusPublishSpec(
            dataset_id="daily_market_status",
            market="../US",
            version="20240102T160000Z",
            source="fixture",
        )
