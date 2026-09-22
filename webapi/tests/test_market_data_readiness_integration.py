"""End-to-end readiness endpoint coverage for same-day revisions."""

from __future__ import annotations

import pandas as pd
from fastapi.testclient import TestClient

from quantmine.datareader import MarketData
from quantmine.plugins.contracts import MarketDataBundle
from quantmine.workflows.coverage_audit import (
    CoverageAuditPolicy,
    audit_market_data_coverage,
    persist_coverage_audit,
)
from quantmine.workflows.market_data_publication import (
    MarketDataPublishSpec,
    publish_market_data_bundle,
)
from quantmine.workflows.market_data_readiness import readiness_audit_path


DATASET_ID = "cn_a_share_daily_bars"
SESSIONS = pd.DatetimeIndex(["2024-01-02", "2024-01-03"])
SYMBOLS = ("000001.SZ", "600000.SH")


def _bundle() -> MarketDataBundle:
    return MarketDataBundle(
        market=MarketData(
            close=pd.DataFrame(
                {"000001.SZ": [10.0, 11.0], "600000.SH": [20.0, 21.0]},
                index=SESSIONS,
            ),
            volume=pd.DataFrame(
                {"000001.SZ": [100.0, 110.0], "600000.SH": [200.0, 210.0]},
                index=SESSIONS,
            ),
        ),
        calendar=SESSIONS,
    )


def _publish(root, version: str) -> None:
    publish_market_data_bundle(
        _bundle(),
        root=root,
        spec=MarketDataPublishSpec(
            dataset_id=DATASET_ID,
            market="CN",
            version=version,
            source="fixture",
            frequency="daily",
            adjustment="hfq",
        ),
        coverage_complete=True,
    )


def _persist_complete_audit(root, version: str) -> None:
    bundle = _bundle()
    audit = audit_market_data_coverage(
        market="CN",
        published_version=version,
        expected_sessions=SESSIONS,
        eligible_symbols=SYMBOLS,
        fields={
            "close": bundle.market.close,
            "volume": bundle.market.volume,
        },
        policy=CoverageAuditPolicy(
            minimum_coverage_ratio=1.0,
            max_backfill_tasks=4,
            max_symbols_per_task=4,
        ),
    )
    persist_coverage_audit(
        audit,
        artifact_dir=readiness_audit_path(
            root,
            market="CN",
            version=version,
        ).parent,
    )


def test_readiness_endpoint_uses_the_highest_same_day_revision(
    client: TestClient,
    monkeypatch,
    tmp_path,
) -> None:
    market_root = tmp_path / "market"
    checkpoint_root = tmp_path / "checkpoint"
    market_root.mkdir()
    checkpoint_root.mkdir()
    monkeypatch.setenv("QUANTMINE_CONNECTION_CN_MARKET_DATA_KIND", "parquet")
    monkeypatch.setenv("QUANTMINE_CONNECTION_CN_MARKET_DATA_ROOT", str(market_root))
    monkeypatch.setenv("QUANTMINE_CONNECTION_CN_MARKET_CHECKPOINT_KIND", "parquet")
    monkeypatch.setenv(
        "QUANTMINE_CONNECTION_CN_MARKET_CHECKPOINT_ROOT",
        str(checkpoint_root),
    )

    _publish(market_root, "20240103")
    _publish(market_root, "20240103-r1")
    _publish(market_root, "20240103-r2")
    _persist_complete_audit(checkpoint_root, "20240103-r2")

    response = client.get("/api/v1/market/data-readiness?asOfDate=2024-01-03")

    assert response.status_code == 200
    assert response.json() == {
        "market": "CN",
        "datasetId": DATASET_ID,
        "asOfDate": "2024-01-03",
        "marketDataVersion": "20240103-r2",
        "baseMarketDataVersion": "20240103",
        "revision": 2,
        "researchReady": True,
        "reason": "ready",
        "coverageRatio": 1.0,
        "gapCount": 0,
        "deferredGapCount": 0,
        "coverageAuditPath": str(
            readiness_audit_path(
                checkpoint_root,
                market="CN",
                version="20240103-r2",
            )
        ),
    }
