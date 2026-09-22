"""Public contract for the resolved market-data readiness state."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from fastapi.testclient import TestClient

from app.api.v1.market import readiness as market_readiness
from quantmine.workflows.market_data_readiness import MarketDataReadiness


def test_market_data_readiness_returns_the_resolved_revision_and_coverage(
    client: TestClient,
    monkeypatch,
) -> None:
    market_root = Path("/market-lake")
    checkpoint_root = Path("/checkpoint-lake")
    observed: dict[str, object] = {}

    monkeypatch.setattr(
        market_readiness,
        "_market_roots",
        lambda: (market_root, checkpoint_root),
    )

    def fake_assess(root, **kwargs):
        observed["root"] = root
        observed.update(kwargs)
        return MarketDataReadiness(
            market="CN",
            dataset_id="cn_a_share_daily_bars",
            as_of_date=pd.Timestamp(kwargs["as_of_date"]),
            resolved_version="20240103-r2",
            base_version="20240103",
            revision=2,
            ready=True,
            reason="ready",
            coverage_ratio=1.0,
            gap_count=0,
            deferred_gap_count=0,
            audit_path=checkpoint_root / "market=CN/version=20240103-r2/coverage_audit.json",
        )

    monkeypatch.setattr(
        market_readiness,
        "assess_market_data_readiness",
        fake_assess,
    )

    response = client.get("/api/v1/market/data-readiness?asOfDate=2024-01-03")

    assert response.status_code == 200
    assert response.json() == {
        "market": "CN",
        "datasetId": "cn_a_share_daily_bars",
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
            checkpoint_root / "market=CN/version=20240103-r2/coverage_audit.json"
        ),
    }
    assert observed == {
        "root": market_root,
        "dataset_id": "cn_a_share_daily_bars",
        "market": "CN",
        "as_of_date": "2024-01-03",
        "coverage_root": checkpoint_root,
    }


def test_market_data_readiness_exposes_an_unready_state_instead_of_a_404(
    client: TestClient,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        market_readiness,
        "_market_roots",
        lambda: (Path("/market-lake"), Path("/checkpoint-lake")),
    )
    monkeypatch.setattr(
        market_readiness,
        "assess_market_data_readiness",
        lambda root, **kwargs: MarketDataReadiness(
            market="CN",
            dataset_id="cn_a_share_daily_bars",
            as_of_date=pd.Timestamp(kwargs["as_of_date"]),
            resolved_version=None,
            base_version=None,
            revision=0,
            ready=False,
            reason="no_published_version",
        ),
    )

    response = client.get("/api/v1/market/data-readiness?asOfDate=2024-01-03")

    assert response.status_code == 200
    assert response.json()["researchReady"] is False
    assert response.json()["marketDataVersion"] is None
    assert response.json()["reason"] == "no_published_version"
