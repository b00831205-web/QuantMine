"""Built-in market-specific plugins for generic pipeline stages."""

from pathlib import Path

import pandas as pd

import quantmine.plugins.market_stages as market_stages
from quantmine.market_pipeline_config import (
    MarketPipelineDefinition,
    PipelineStageDefinition,
    PipelineStageKind,
)
from quantmine.pipeline_stages import PipelineStageRequest
from quantmine.plugins.context import SourceContext
from quantmine.plugins.contracts import PluginSpec
from quantmine.storage.connections import ConnectionRegistry
from quantmine.workflows.a_share_daily_pipeline import (
    AStockDailyPipelineResult,
)
from quantmine.workflows.akshare_a_share_snapshot import AStockRawSnapshot
from quantmine.workflows.eligibility import EligibilityPublication
from quantmine.workflows.market_status_publication import (
    MarketStatusPublication,
)


def _request(tmp_path: Path) -> PipelineStageRequest:
    stage = PipelineStageDefinition(
        id="session_gate",
        kind=PipelineStageKind.SESSION_GATE,
        plugin=PluginSpec("quantmine.plugins.market_stages:create_gate"),
    )
    pipeline = MarketPipelineDefinition(
        id="market_fixture",
        dag_id="quantmine_market_fixture",
        display_name="Market fixture",
        schedule="@daily",
        stages=(stage,),
    )
    return PipelineStageRequest(
        pipeline=pipeline,
        stage=stage,
        context=SourceContext(
            connections=ConnectionRegistry({}),
            run_id=0,
            artifact_dir=tmp_path,
        ),
        as_of_date=pd.Timestamp("2026-09-04"),
        batch_id="manual",
    )


def _a_share_config() -> dict[str, object]:
    return {
        "schema_version": 1,
        "raw_connection_ref": "cn_raw",
        "reference_binding": {
            "connection_ref": "cn_reference",
            "dataset": "cn_a_share_reference",
            "market": "CN",
            "version": "20260830",
        },
        "status_binding": {
            "connection_ref": "cn_status",
            "dataset": "cn_a_share_status",
            "market": "CN",
            "version": "history_v1",
        },
        "eligibility_binding": {
            "connection_ref": "cn_eligibility",
            "dataset": "cn_a_share_eligibility",
            "market": "CN",
            "version": "history_v1",
        },
        "eligibility_rule_version": "cn_equity_v1",
    }


def test_exchange_calendar_gate_forwards_the_requested_date(
    monkeypatch,
    tmp_path: Path,
) -> None:
    calls: list[tuple[str, pd.Timestamp]] = []

    class FakeExchangeGate:
        def __init__(self, calendar_name: str) -> None:
            self.calendar_name = calendar_name

        def is_session(self, as_of_date) -> bool:
            calls.append((self.calendar_name, pd.Timestamp(as_of_date)))
            return True

    monkeypatch.setattr(
        market_stages,
        "ExchangeCalendarSessionGate",
        FakeExchangeGate,
    )
    plugin = market_stages.create_exchange_calendar_session_gate(
        calendar_name="XNYS"
    )

    assert plugin.allows(_request(tmp_path)) is True
    assert calls == [("XNYS", pd.Timestamp("2026-09-04"))]


def test_a_share_gate_builds_typed_config_and_forwards_context(
    monkeypatch,
    tmp_path: Path,
) -> None:
    observed = {}

    def fake_is_session(context, *, config, as_of_date) -> bool:
        observed["context"] = context
        observed["config"] = config
        observed["date"] = as_of_date
        return False

    monkeypatch.setattr(
        market_stages,
        "is_a_share_trading_session",
        fake_is_session,
    )
    plugin = market_stages.create_a_share_session_gate(
        config=_a_share_config()
    )
    request = _request(tmp_path)

    assert plugin.allows(request) is False
    assert observed["context"] is request.context
    assert observed["config"].raw_connection_ref == "cn_raw"
    assert observed["date"] == pd.Timestamp("2026-09-04")


def test_a_share_production_stage_returns_only_serializable_artifact_metadata(
    monkeypatch,
    tmp_path: Path,
) -> None:
    raw_dir = tmp_path / "raw"
    status_dir = tmp_path / "status"
    eligibility_dir = tmp_path / "eligibility"
    observed = {}

    def fake_run(context, *, config, as_of_date):
        observed["context"] = context
        observed["config"] = config
        observed["date"] = as_of_date
        return AStockDailyPipelineResult(
            raw_snapshot=AStockRawSnapshot(
                output_dir=raw_dir,
                spot_path=raw_dir / "spot.parquet",
                suspension_path=raw_dir / "suspension.parquet",
                manifest_path=raw_dir / "manifest.json",
                spot_row_count=5000,
                suspension_row_count=12,
            ),
            status_publication=MarketStatusPublication(
                output_dir=status_dir,
                status_path=status_dir / "status.parquet",
                manifest_path=status_dir / "manifest.json",
                row_count=5000,
                as_of_date=pd.Timestamp("2026-09-04"),
                content_sha256="status-sha",
            ),
            eligibility_publication=EligibilityPublication(
                output_dir=eligibility_dir,
                eligibility_path=eligibility_dir / "eligibility.parquet",
                manifest_path=eligibility_dir / "manifest.json",
                row_count=100000,
                min_date=pd.Timestamp("2026-01-01"),
                max_date=pd.Timestamp("2026-09-04"),
                content_sha256="eligibility-sha",
            ),
        )

    monkeypatch.setattr(
        market_stages,
        "run_a_share_daily_pipeline",
        fake_run,
    )
    plugin = market_stages.create_a_share_daily_production(
        config=_a_share_config()
    )
    request = _request(tmp_path)

    result = plugin.run(request)

    assert observed["context"] is request.context
    assert observed["config"].raw_connection_ref == "cn_raw"
    assert observed["date"] == pd.Timestamp("2026-09-04")
    assert result.metadata == {
        "as_of_date": "2026-09-04",
        "raw_snapshot_dir": str(raw_dir),
        "spot_row_count": 5000,
        "suspension_row_count": 12,
        "status_path": str(status_dir / "status.parquet"),
        "status_row_count": 5000,
        "status_content_sha256": "status-sha",
        "eligibility_path": str(
            eligibility_dir / "eligibility.parquet"
        ),
        "eligibility_row_count": 100000,
        "eligibility_content_sha256": "eligibility-sha",
    }
