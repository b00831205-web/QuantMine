"""Pipeline stage contract for the research readiness gate (roadmap r1 §5)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from quantmine.datareader import MarketData
from quantmine.market_pipeline_config import (
    MarketPipelineDefinition,
    PipelineStageDefinition,
    PipelineStageKind,
)
from quantmine.pipeline_stages import PipelineStageRequest
from quantmine.plugins import market_stages
from quantmine.plugins.contracts import MarketDataBundle, PluginSpec
from quantmine.plugins.context import SourceContext
from quantmine.storage.connections import (
    ConnectionKind,
    ConnectionRegistry,
    DataConnectionConfig,
)
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
from quantmine.workflows.market_data_readiness import readiness_audit_path


DATASET_ID = "cn_a_share_daily_bars"
MARKET_ROOT_ENV = "QUANTMINE_TEST_GATE_MARKET_ROOT"
PLAN_ROOT_ENV = "QUANTMINE_TEST_GATE_PLAN_ROOT"
SESSIONS = pd.DatetimeIndex(["2024-01-02", "2024-01-03"])
SYMBOLS = ("000001.SZ", "600000.SH")


def _frames(*, missing_first_session: bool) -> tuple[pd.DataFrame, pd.DataFrame]:
    close = pd.DataFrame(
        {"000001.SZ": [10.0, 11.0], "600000.SH": [20.0, 21.0]},
        index=SESSIONS,
    )
    volume = pd.DataFrame(
        {"000001.SZ": [100.0, 110.0], "600000.SH": [200.0, 210.0]},
        index=SESSIONS,
    )
    if missing_first_session:
        close.loc[SESSIONS[0], :] = float("nan")
        volume.loc[SESSIONS[0], :] = float("nan")
    return close, volume


def _bundle(*, missing_first_session: bool = False) -> MarketDataBundle:
    close, volume = _frames(missing_first_session=missing_first_session)
    return MarketDataBundle(
        market=MarketData(close=close, volume=volume),
        calendar=SESSIONS,
    )


def _publish(
    root: Path,
    *,
    version: str,
    missing_first_session: bool = False,
    coverage_complete: bool | None = None,
):
    return publish_market_data_bundle(
        _bundle(missing_first_session=missing_first_session),
        root=root,
        spec=MarketDataPublishSpec(
            dataset_id=DATASET_ID,
            market="CN",
            version=version,
            source="fixture",
            frequency="daily",
            adjustment="hfq",
        ),
        coverage_complete=coverage_complete,
    )


def _persist(root: Path, *, version: str, missing_first_session: bool) -> CoverageAudit:
    close, volume = _frames(missing_first_session=missing_first_session)
    audit = audit_market_data_coverage(
        market="CN",
        published_version=version,
        expected_sessions=SESSIONS,
        eligible_symbols=SYMBOLS,
        fields={"close": close, "volume": volume},
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
    return audit


def _request(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> PipelineStageRequest:
    market_root = tmp_path / "market_lake"
    plan_root = tmp_path / "plan_lake"
    market_root.mkdir(parents=True, exist_ok=True)
    plan_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv(MARKET_ROOT_ENV, str(market_root))
    monkeypatch.setenv(PLAN_ROOT_ENV, str(plan_root))

    stage = PipelineStageDefinition(
        id="research_readiness_gate",
        kind=PipelineStageKind.SESSION_GATE,
        plugin=PluginSpec(
            "quantmine.plugins.market_stages:create_research_readiness_gate"
        ),
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
            connections=ConnectionRegistry(
                {
                    "cn_market_data": DataConnectionConfig(
                        kind=ConnectionKind.PARQUET,
                        root_env=MARKET_ROOT_ENV,
                    ),
                    "cn_market_checkpoint": DataConnectionConfig(
                        kind=ConnectionKind.PARQUET,
                        root_env=PLAN_ROOT_ENV,
                    ),
                }
            ),
            run_id=7,
            artifact_dir=tmp_path / "artifacts",
        ),
        as_of_date=pd.Timestamp("2024-01-03"),
        batch_id="manual",
    )


def test_readiness_gate_allows_research_for_a_complete_version(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    request = _request(tmp_path, monkeypatch)
    market_root = request.context.connections.parquet_root("cn_market_data")
    plan_root = request.context.connections.parquet_root(
        "cn_market_checkpoint"
    )
    _publish(market_root, version="20240103")
    _persist(plan_root, version="20240103", missing_first_session=False)

    plugin = market_stages.create_research_readiness_gate(
        market_data_connection_ref="cn_market_data",
        dataset_id=DATASET_ID,
        market="CN",
        plan_connection_ref="cn_market_checkpoint",
    )
    assert plugin.allows(request) is True


def test_readiness_gate_blocks_research_until_the_revision_is_published(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    request = _request(tmp_path, monkeypatch)
    market_root = request.context.connections.parquet_root("cn_market_data")
    plan_root = request.context.connections.parquet_root(
        "cn_market_checkpoint"
    )
    _publish(market_root, version="20240103", missing_first_session=True)
    _persist(plan_root, version="20240103", missing_first_session=True)

    plugin = market_stages.create_research_readiness_gate(
        market_data_connection_ref="cn_market_data",
        dataset_id=DATASET_ID,
        market="CN",
        plan_connection_ref="cn_market_checkpoint",
    )
    assert plugin.allows(request) is False

    _publish(
        market_root,
        version="20240103-r1",
        missing_first_session=False,
        coverage_complete=True,
    )
    _persist(plan_root, version="20240103-r1", missing_first_session=False)

    assert plugin.allows(request) is True


def test_readiness_gate_blocks_research_before_any_version_exists(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    request = _request(tmp_path, monkeypatch)

    plugin = market_stages.create_research_readiness_gate(
        market_data_connection_ref="cn_market_data",
        dataset_id=DATASET_ID,
        market="CN",
        plan_connection_ref="cn_market_checkpoint",
    )
    assert plugin.allows(request) is False


def test_readiness_gate_exposes_a_session_gate_plugin_factory() -> None:
    assert hasattr(market_stages, "create_research_readiness_gate")
