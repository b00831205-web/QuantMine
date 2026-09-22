"""Research readiness gate for immutable market-data base/revision versions.

Roadmap: ``NEXT_PHASE_ENGINEERING_DESIGN_v2026.09.21-r1.md`` section 5.

The gate consumes the coverage audit of the *latest* version through the run
date.  A base version whose historical gap has not been repaired by a same-day
revision must not reach research, IC, or backtest.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from quantmine.datareader import MarketData
from quantmine.plugins.contracts import MarketDataBundle
from quantmine.workflows.coverage_audit import (
    CoverageAudit,
    CoverageAuditPolicy,
    audit_market_data_coverage,
    persist_coverage_audit,
)
from quantmine.workflows.market_data_publication import (
    MarketDataPublishSpec,
    publish_market_data_bundle,
)
from quantmine.workflows.market_data_readiness import (
    MarketDataReadiness,
    assess_market_data_readiness,
    readiness_audit_path,
)


DATASET_ID = "cn_a_share_daily_bars"


def _bundle(*, close_shift: float = 0.0) -> MarketDataBundle:
    dates = pd.DatetimeIndex(["2024-01-02", "2024-01-03"])
    return MarketDataBundle(
        market=MarketData(
            close=pd.DataFrame(
                {
                    "000001.SZ": [10.0 + close_shift, 11.0 + close_shift],
                    "600000.SH": [20.0 + close_shift, 21.0 + close_shift],
                },
                index=dates,
            ),
            volume=pd.DataFrame(
                {
                    "000001.SZ": [100.0, 110.0],
                    "600000.SH": [200.0, 210.0],
                },
                index=dates,
            ),
        ),
        calendar=dates,
    )


def _gapped_bundle() -> MarketDataBundle:
    dates = pd.DatetimeIndex(["2024-01-02", "2024-01-03"])
    return MarketDataBundle(
        market=MarketData(
            close=pd.DataFrame(
                {
                    "000001.SZ": [float("nan"), 11.0],
                    "600000.SH": [float("nan"), 21.0],
                },
                index=dates,
            ),
            volume=pd.DataFrame(
                {
                    "000001.SZ": [float("nan"), 110.0],
                    "600000.SH": [float("nan"), 210.0],
                },
                index=dates,
            ),
        ),
        calendar=dates,
    )


def _publish(
    root: Path,
    *,
    version: str,
    bundle: MarketDataBundle | None = None,
    close_shift: float = 0.0,
):
    return publish_market_data_bundle(
        bundle if bundle is not None else _bundle(close_shift=close_shift),
        root=root,
        spec=MarketDataPublishSpec(
            dataset_id=DATASET_ID,
            market="CN",
            version=version,
            source="fixture",
            frequency="daily",
            adjustment="hfq",
        ),
    )


def _audit(
    *,
    published_version: str,
    close: pd.DataFrame,
    volume: pd.DataFrame,
    complete: bool,
) -> CoverageAudit:
    """Build the audit through the real audit function for a fixed policy."""

    sessions = pd.DatetimeIndex(close.index)
    symbols = tuple(str(value) for value in close.columns)

    policy = CoverageAuditPolicy(
        minimum_coverage_ratio=1.0 if complete else 0.99,
        max_backfill_tasks=4,
        max_symbols_per_task=4,
    )
    return audit_market_data_coverage(
        market="CN",
        published_version=published_version,
        expected_sessions=sessions,
        eligible_symbols=symbols,
        fields={"close": close, "volume": volume},
        policy=policy,
    )


def _persist_audit(root: Path, audit: CoverageAudit, *, version: str) -> Path:
    artifact_dir = readiness_audit_path(
        root,
        market="CN",
        version=version,
    ).parent
    return persist_coverage_audit(audit, artifact_dir=artifact_dir)


def _coverage_frames() -> tuple[pd.DataFrame, pd.DataFrame]:
    index = pd.DatetimeIndex(["2024-01-02", "2024-01-03"])
    close = pd.DataFrame(
        {"000001.SZ": [10.0, 11.0], "600000.SH": [20.0, 21.0]},
        index=index,
    )
    volume = pd.DataFrame(
        {"000001.SZ": [100.0, 110.0], "600000.SH": [200.0, 210.0]},
        index=index,
    )
    return close, volume


def test_readiness_audit_path_is_keyed_by_market_and_version(tmp_path: Path) -> None:
    assert readiness_audit_path(
        tmp_path,
        market="CN",
        version="20240103-r2",
    ) == (
        tmp_path
        / "market=CN"
        / "version=20240103-r2"
        / "coverage_audit.json"
    )


def test_readiness_is_false_when_no_version_is_published(tmp_path: Path) -> None:
    readiness = assess_market_data_readiness(
        tmp_path,
        dataset_id=DATASET_ID,
        market="CN",
        as_of_date="2024-01-03",
    )

    assert isinstance(readiness, MarketDataReadiness)
    assert readiness.ready is False
    assert readiness.resolved_version is None
    assert readiness.reason == "no_published_version"


def test_readiness_is_false_without_a_coverage_audit(tmp_path: Path) -> None:
    _publish(tmp_path, version="20240103")

    readiness = assess_market_data_readiness(
        tmp_path,
        dataset_id=DATASET_ID,
        market="CN",
        as_of_date="2024-01-03",
    )

    assert readiness.ready is False
    assert readiness.resolved_version == "20240103"
    assert readiness.audit_path == readiness_audit_path(
        tmp_path,
        market="CN",
        version="20240103",
    )
    assert not readiness.audit_path.exists()
    assert readiness.reason == "coverage_audit_missing"


def _with_missing_first_session(
    frame: pd.DataFrame,
) -> pd.DataFrame:
    gapped = frame.copy()
    gapped.loc[pd.Timestamp("2024-01-02"), :] = float("nan")
    return gapped


def test_readiness_uses_the_latest_revision_and_not_the_base_version(
    tmp_path: Path,
) -> None:
    _publish(tmp_path, version="20240103", bundle=_gapped_bundle())
    _publish(tmp_path, version="20240103-r1", close_shift=0.0)

    close, volume = _coverage_frames()
    incomplete = _audit(
        published_version="20240103",
        close=_with_missing_first_session(close),
        volume=_with_missing_first_session(volume),
        complete=False,
    )
    _persist_audit(tmp_path, incomplete, version="20240103")

    complete = _audit(
        published_version="20240103-r1",
        close=close,
        volume=volume,
        complete=True,
    )
    _persist_audit(tmp_path, complete, version="20240103-r1")

    readiness = assess_market_data_readiness(
        tmp_path,
        dataset_id=DATASET_ID,
        market="CN",
        as_of_date="2024-01-03",
    )

    assert readiness.ready is True
    assert readiness.resolved_version == "20240103-r1"
    assert readiness.coverage_ratio == 1.0
    assert readiness.gap_count == 0
    assert readiness.base_version == "20240103"
    assert readiness.revision == 1
    assert readiness.audit_path == readiness_audit_path(
        tmp_path,
        market="CN",
        version="20240103-r1",
    )


def test_incomplete_base_version_keeps_research_blocked(tmp_path: Path) -> None:
    _publish(tmp_path, version="20240103", bundle=_gapped_bundle())

    close, volume = _coverage_frames()
    incomplete = _audit(
        published_version="20240103",
        close=_with_missing_first_session(close),
        volume=_with_missing_first_session(volume),
        complete=False,
    )
    _persist_audit(tmp_path, incomplete, version="20240103")

    readiness = assess_market_data_readiness(
        tmp_path,
        dataset_id=DATASET_ID,
        market="CN",
        as_of_date="2024-01-03",
    )

    assert readiness.ready is False
    assert readiness.resolved_version == "20240103"
    assert readiness.revision == 0
    assert readiness.coverage_ratio < 1.0
    assert readiness.gap_count > 0
    assert readiness.reason == "coverage_incomplete"


def test_an_unreadable_audit_blocks_research_instead_of_crashing(
    tmp_path: Path,
) -> None:
    _publish(tmp_path, version="20240103")
    audit_path = readiness_audit_path(
        tmp_path,
        market="CN",
        version="20240103",
    )
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.write_text("{not json", encoding="utf-8")

    readiness = assess_market_data_readiness(
        tmp_path,
        dataset_id=DATASET_ID,
        market="CN",
        as_of_date="2024-01-03",
    )

    assert readiness.ready is False
    assert readiness.resolved_version == "20240103"
    assert readiness.reason == "coverage_audit_invalid"


def test_readiness_never_resolves_a_version_after_the_run_date(
    tmp_path: Path,
) -> None:
    _publish(tmp_path, version="20240104")

    readiness = assess_market_data_readiness(
        tmp_path,
        dataset_id=DATASET_ID,
        market="CN",
        as_of_date="2024-01-03",
    )

    assert readiness.ready is False
    assert readiness.resolved_version is None
    assert readiness.reason == "no_published_version"


def test_readiness_rejects_a_naive_or_missing_date(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="as_of_date"):
        assess_market_data_readiness(
            tmp_path,
            dataset_id=DATASET_ID,
            market="CN",
            as_of_date=pd.NaT,
        )
