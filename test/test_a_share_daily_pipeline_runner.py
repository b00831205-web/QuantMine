"""End-to-end tests for the scheduler-neutral A-share daily pipeline."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

import pandas as pd
import pytest

import quantmine.workflows.a_share_daily_pipeline as daily_pipeline
from quantmine.dataset_versions import AS_OF_DATE_VERSION
from quantmine.plugins.context import SourceContext
from quantmine.plugins.contracts import VersionedDatasetBinding
from quantmine.storage.connections import (
    ConnectionKind,
    ConnectionRegistry,
    DataConnectionConfig,
)
from quantmine.workflows.a_share_daily_pipeline import (
    AStockDailyPipelineConfig,
    _load_existing_raw_snapshot,
    is_a_share_trading_session,
    run_a_share_daily_pipeline,
)
from quantmine.workflows.a_share_status import SpotCoveragePolicy
from quantmine.workflows.akshare_a_share_snapshot import (
    AkShareAStockRawSnapshotCollector,
)


def _context(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> SourceContext:
    refs = {
        "cn_raw_lake": "QUANTMINE_CN_RAW_LAKE",
        "cn_reference_lake": "QUANTMINE_CN_REFERENCE_LAKE",
        "cn_status_lake": "QUANTMINE_CN_STATUS_LAKE",
        "cn_eligibility_lake": "QUANTMINE_CN_ELIGIBILITY_LAKE",
    }
    configs: dict[str, DataConnectionConfig] = {}
    for ref, env_name in refs.items():
        root = tmp_path / ref
        root.mkdir()
        monkeypatch.setenv(env_name, str(root))
        configs[ref] = DataConnectionConfig(
            kind=ConnectionKind.PARQUET,
            root_env=env_name,
            read_only=False,
        )

    return SourceContext(
        connections=ConnectionRegistry(configs),
        run_id=1701,
        artifact_dir=tmp_path / "artifacts",
    )


def _config(
    *,
    spot_coverage_policy: SpotCoveragePolicy | None = None,
    reference_version: str = "20260830",
    eligibility_version: str = "history_v1",
) -> AStockDailyPipelineConfig:
    return AStockDailyPipelineConfig(
        raw_connection_ref="cn_raw_lake",
        reference_binding=VersionedDatasetBinding(
            connection_ref="cn_reference_lake",
            dataset="cn_a_share_reference",
            market="CN",
            version=reference_version,
        ),
        status_binding=VersionedDatasetBinding(
            connection_ref="cn_status_lake",
            dataset="daily_market_status",
            market="CN",
            version="history_v1",
        ),
        eligibility_binding=VersionedDatasetBinding(
            connection_ref="cn_eligibility_lake",
            dataset="cn_daily_eligibility",
            market="CN",
            version=eligibility_version,
        ),
        eligibility_rule_version="cn_eligibility_rules_v1",
        spot_coverage_policy=(
            spot_coverage_policy or SpotCoveragePolicy()
        ),
    )


def _write_reference_data(root: Path, *, version: str = "20260830") -> None:
    version_root = root / "cn_a_share_reference" / "versions" / version
    version_root.mkdir(parents=True)
    pd.DataFrame(
        {
            "listing_id": ["000001-1", "000002-1"],
            "ticker": ["000001", "000002"],
            "list_date": ["2020-01-01", "2020-01-01"],
            "delist_date": [None, None],
            "exchange": ["SZSE", "SZSE"],
            "security_type": ["COMMON_STOCK", "COMMON_STOCK"],
        }
    ).to_parquet(version_root / "security_master.parquet")
    pd.DataFrame({"date": ["2024-01-02"]}).to_parquet(
        version_root / "trading_calendar.parquet"
    )


def _collector(
    observed_at: datetime = datetime(
        2024,
        1,
        2,
        8,
        tzinfo=timezone.utc,
    ),
) -> AkShareAStockRawSnapshotCollector:
    return AkShareAStockRawSnapshotCollector(
        spot_loader=lambda _: pd.DataFrame(
            {
                "代码": ["000001", "000002"],
                "名称": ["平安银行", "*ST示例"],
                "最新价": [11.0, 5.0],
                "涨停": [11.0, 5.5],
                "跌停": [9.0, 4.5],
                "成交量": [100_000, 20_000],
            }
        ),
        suspension_loader=lambda _: pd.DataFrame(
            columns=["代码", "名称", "停牌时间"]
        ),
        clock=lambda: observed_at,
    )


def test_daily_pipeline_is_idempotent_and_publishes_versioned_outputs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    context = _context(monkeypatch, tmp_path)
    _write_reference_data(
        context.connections.parquet_root("cn_reference_lake")
    )

    first = run_a_share_daily_pipeline(
        context,
        config=_config(),
        as_of_date="2024-01-02",
        collector=_collector(),
    )
    second = run_a_share_daily_pipeline(
        context,
        config=_config(),
        as_of_date="2024-01-02",
        collector=_collector(
            datetime(2024, 1, 3, 8, tzinfo=timezone.utc)
        ),
    )

    assert second == first
    assert first.raw_snapshot.spot_path.is_file()
    assert first.status_publication.status_path.is_file()

    eligibility = pd.read_parquet(first.eligibility_publication.eligibility_path)
    assert eligibility["ticker"].tolist() == ["000001", "000002"]
    assert eligibility["is_tradable"].tolist() == [True, False]


def test_daily_pipeline_forwards_reference_calendar_to_eligibility_refresh(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    context = _context(monkeypatch, tmp_path)
    _write_reference_data(
        context.connections.parquet_root("cn_reference_lake")
    )
    original_refresh = (
        daily_pipeline.refresh_a_share_eligibility_from_market_status
    )
    observed: dict[str, object] = {}

    def spy_refresh(*args: object, **kwargs: object):
        observed["trading_sessions"] = kwargs["trading_sessions"]
        return original_refresh(*args, **kwargs)

    monkeypatch.setattr(
        daily_pipeline,
        "refresh_a_share_eligibility_from_market_status",
        spy_refresh,
    )

    run_a_share_daily_pipeline(
        context,
        config=_config(),
        as_of_date="2024-01-02",
        collector=_collector(),
    )

    assert pd.DatetimeIndex(observed["trading_sessions"]).tolist() == [
        pd.Timestamp("2024-01-02")
    ]


def test_a_share_session_gate_uses_the_versioned_reference_calendar(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    context = _context(monkeypatch, tmp_path)
    _write_reference_data(
        context.connections.parquet_root("cn_reference_lake")
    )

    assert is_a_share_trading_session(
        context,
        config=_config(),
        as_of_date="2024-01-02",
    ) is True
    assert is_a_share_trading_session(
        context,
        config=_config(),
        as_of_date="2024-01-01",
    ) is False


def test_daily_pipeline_resolves_the_reference_version_from_as_of_date(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    context = _context(monkeypatch, tmp_path)
    _write_reference_data(
        context.connections.parquet_root("cn_reference_lake"),
        version="20240102",
    )

    result = run_a_share_daily_pipeline(
        context,
        config=_config(reference_version=AS_OF_DATE_VERSION),
        as_of_date="2024-01-02",
        collector=_collector(),
    )

    assert result.status_publication.as_of_date == pd.Timestamp("2024-01-02")


def test_daily_pipeline_resolves_the_eligibility_version_from_as_of_date(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    context = _context(monkeypatch, tmp_path)
    _write_reference_data(
        context.connections.parquet_root("cn_reference_lake")
    )

    result = run_a_share_daily_pipeline(
        context,
        config=_config(eligibility_version=AS_OF_DATE_VERSION),
        as_of_date="2024-01-02",
        collector=_collector(),
    )

    assert result.eligibility_publication.output_dir.name == "20240102"
    assert result.eligibility_publication.max_date == pd.Timestamp("2024-01-02")
    assert result.status_publication.output_dir.name == "history_v1"


def test_daily_pipeline_persists_an_allowed_source_gap_as_non_tradable(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    context = _context(monkeypatch, tmp_path)
    _write_reference_data(
        context.connections.parquet_root("cn_reference_lake")
    )
    collector = AkShareAStockRawSnapshotCollector(
        spot_loader=lambda _: pd.DataFrame(
            {
                "代码": ["000001"],
                "名称": ["平安银行"],
                "最新价": [11.0],
                "涨停": [11.0],
                "跌停": [9.0],
                "成交量": [100_000],
            }
        ),
        suspension_loader=lambda _: pd.DataFrame(
            columns=["代码", "名称", "停牌时间"]
        ),
        clock=lambda: datetime(2024, 1, 2, 8, tzinfo=timezone.utc),
    )

    result = run_a_share_daily_pipeline(
        context,
        config=_config(
            spot_coverage_policy=SpotCoveragePolicy(
                max_missing_count=1,
                max_missing_ratio=0.5,
            )
        ),
        as_of_date="2024-01-02",
        collector=collector,
    )

    status = pd.read_parquet(result.status_publication.status_path)
    missing_status = status.set_index("ticker").loc["000002"]
    assert bool(missing_status["is_source_missing"]) is True
    assert bool(missing_status["is_suspended"]) is False
    assert bool(missing_status["is_tradable"]) is False

    eligibility = pd.read_parquet(result.eligibility_publication.eligibility_path)
    missing_eligibility = eligibility.set_index("ticker").loc["000002"]
    assert bool(missing_eligibility["is_tradable"]) is False


def test_existing_unversioned_raw_snapshot_is_not_silently_replayed(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "akshare_a_share_raw" / "2024-01-02"
    output_dir.mkdir(parents=True)
    (output_dir / "spot.parquet").touch()
    (output_dir / "suspension.parquet").touch()
    (output_dir / "manifest.json").write_text(
        json.dumps(
            {
                "as_of_date": "2024-01-02",
                "provider": "akshare",
                "spot_row_count": 2,
                "suspension_row_count": 0,
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="unsupported raw snapshot schema version",
    ):
        _load_existing_raw_snapshot(tmp_path, pd.Timestamp("2024-01-02"))
