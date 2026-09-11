"""Tests for publishing A-share eligibility from persisted generic status."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

import quantmine.workflows.a_share_eligibility_refresh as eligibility_refresh
from quantmine.plugins.context import SourceContext
from quantmine.storage.connections import (
    ConnectionKind,
    ConnectionRegistry,
    DataConnectionConfig,
)
from quantmine.workflows.a_share_eligibility_refresh import (
    refresh_a_share_eligibility_from_market_status,
)
from quantmine.workflows.eligibility import (
    EligibilityDataTier,
    EligibilityPublishSpec,
)
from quantmine.workflows.market_status import DailyMarketStatus
from quantmine.workflows.market_status_publication import (
    MarketStatusPublishSpec,
    publish_daily_market_status,
)


def _context(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> SourceContext:
    status_lake = tmp_path / "status-lake"
    status_lake.mkdir()
    monkeypatch.setenv("QUANTMINE_STATUS_LAKE", str(status_lake))

    return SourceContext(
        connections=ConnectionRegistry(
            {
                "status_lake": DataConnectionConfig(
                    kind=ConnectionKind.PARQUET,
                    root_env="QUANTMINE_STATUS_LAKE",
                )
            }
        ),
        run_id=1601,
        artifact_dir=tmp_path / "artifacts",
    )


def _publish_status(root: Path) -> None:
    publish_daily_market_status(
        DailyMarketStatus.from_frame(
            pd.DataFrame(
                {
                    "date": ["2024-01-02", "2024-01-02"],
                    "ticker": ["000001", "000002"],
                    "is_listed": [True, True],
                    "is_tradable": [True, True],
                    "listing_days": [100, 100],
                    "is_st": [False, True],
                    "is_suspended": [False, False],
                    "is_limit_up": [False, True],
                    "is_limit_down": [False, False],
                }
            )
        ),
        root=root,
        spec=MarketStatusPublishSpec(
            dataset_id="daily_market_status",
            market="CN",
            version="history_v1",
            source="fixture",
        ),
    )


def _eligibility_spec() -> EligibilityPublishSpec:
    return EligibilityPublishSpec(
        dataset_id="cn_daily_eligibility",
        version="history_v1",
        market="CN",
        data_tier=EligibilityDataTier.RECONSTRUCTED,
        source="a_share_market_status",
        rule_version="cn_eligibility_rules_v1",
    )


def test_refresh_publishes_policy_adjusted_a_share_eligibility(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    context = _context(monkeypatch, tmp_path)
    _publish_status(context.connections.parquet_root("status_lake"))

    publication = refresh_a_share_eligibility_from_market_status(
        context,
        as_of_date="2024-01-02 16:30:00",
        status_connection_ref="status_lake",
        status_dataset="daily_market_status",
        status_version="history_v1",
        eligibility_root=tmp_path / "eligibility-lake",
        eligibility_spec=_eligibility_spec(),
    )

    saved = pd.read_parquet(publication.eligibility_path)
    assert saved["ticker"].tolist() == ["000001", "000002"]
    assert saved["is_tradable"].tolist() == [True, False]
    assert saved["is_st"].tolist() == [False, True]


def test_refresh_forwards_trading_sessions_to_cumulative_publication(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    context = _context(monkeypatch, tmp_path)
    _publish_status(context.connections.parquet_root("status_lake"))
    original_refresh = eligibility_refresh.refresh_cumulative_daily_eligibility
    observed: dict[str, object] = {}

    def spy_refresh(*args: object, **kwargs: object):
        observed["trading_sessions"] = kwargs["trading_sessions"]
        return original_refresh(*args, **kwargs)

    monkeypatch.setattr(
        eligibility_refresh,
        "refresh_cumulative_daily_eligibility",
        spy_refresh,
    )

    refresh_a_share_eligibility_from_market_status(
        context,
        as_of_date="2024-01-02",
        status_connection_ref="status_lake",
        status_dataset="daily_market_status",
        status_version="history_v1",
        eligibility_root=tmp_path / "eligibility-lake",
        eligibility_spec=_eligibility_spec(),
        trading_sessions=("2024-01-02",),
    )

    assert tuple(observed["trading_sessions"]) == ("2024-01-02",)


def test_refresh_rejects_a_non_cn_eligibility_spec(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    context = _context(monkeypatch, tmp_path)

    with pytest.raises(ValueError, match="requires eligibility_spec.market='CN'"):
        refresh_a_share_eligibility_from_market_status(
            context,
            as_of_date="2024-01-02",
            status_connection_ref="status_lake",
            status_dataset="daily_market_status",
            status_version="history_v1",
            eligibility_root=tmp_path / "eligibility-lake",
            eligibility_spec=EligibilityPublishSpec(
                dataset_id="us_daily_eligibility",
                version="history_v1",
                market="US",
                data_tier=EligibilityDataTier.RECONSTRUCTED,
                source="fixture",
                rule_version="us_eligibility_rules_v1",
            ),
        )
