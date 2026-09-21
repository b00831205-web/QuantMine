"""Built-in market-specific adapters for generic pipeline stages"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from ..pipeline_stages import PipelineStageRequest, PipelineStageResult
from ..workflows.a_share_daily_pipeline import(
    AStockDailyPipelineConfig,
    is_a_share_trading_session,
    run_a_share_daily_pipeline
)

from ..dataset_versions import resolve_versioned_dataset_binding
from ..workflows.a_share_reference_refresh import refresh_akshare_a_stock_reference
from ..workflows.a_share_market_data_refresh import (AStockDailyMarketDataRefreshConfig, run_configured_a_share_cumulative_refresh)

from ..workflows.trading_sessions import ExchangeCalendarSessionGate
from ..workflows.a_share_reference import ParquetAStockReferenceLoader
from ..workflows.coverage_audit import (
    CoverageAuditPolicy,
    audit_market_data_coverage,
    persist_coverage_audit,
)
from ..plugins.contracts import DataSourceComponent
from ..plugins.loader import resolve_plugin
from ..workflows.coverage_audit import load_coverage_audit
from ..workflows.market_data_backfill import (
    stage_market_data_backfill,
)
from ..workflows.market_data_backfill import (
    load_staged_market_data_backfill,
)
from ..workflows.market_data_repair_publication import (
    publish_market_data_repair_revision,
)
from ..workflows.market_data_readiness import (
    assess_market_data_readiness,
)
import pandas as pd

@dataclass(frozen = True)
class AShareReferenceRefreshStage:
    """Publish an immutable A-share reference version for the run date."""

    config: AStockDailyPipelineConfig

    def run(
            self,
            request: PipelineStageRequest,
    ) -> PipelineStageResult:
        binding = resolve_versioned_dataset_binding(
            self.config.reference_binding,
            as_of_date = request.as_of_date,
        )

        publication = refresh_akshare_a_stock_reference(
            request.context,
            binding = binding,
        )

        return PipelineStageResult(
            metadata = {
                "reference_version": binding.version,
                "reference_dir": str(publication.output_dir),
                "listing_count": publication.listing_count,
                "session_count": publication.session_count,
                "min_session_date": (
                    publication.min_session_date.date().isoformat()
                ),
                "max_session_date": (
                    publication.max_session_date.date().isoformat()
                ),
                "reference_content_sha256": (
                    publication.content_sha256
                ),
            }
        )

@dataclass(frozen=True)
class AShareCumulativeMarketDataRefreshStage:
    """Publish one cumulative A-share market-data version."""

    config: AStockDailyMarketDataRefreshConfig

    def run(
            self,
            request: PipelineStageRequest,
    ) -> PipelineStageResult:
        publication = run_configured_a_share_cumulative_refresh(
            request.context,
            config = self.config,
            as_of_date= request.as_of_date,
            allowed_module_prefixes=request.allowed_module_prefixes,
        )

        return PipelineStageResult(
            metadata={
                "market_data_version": (
                    request.as_of_date.strftime("%Y%m%d")
                ),
                "market_data_dir": str(publication.output_dir),
                "close_path": str(publication.close_path),
                "volume_path": str(publication.volume_path),
                "date_count": publication.date_count,
                "ticker_count": publication.ticker_count,
                "market_data_content_sha256": (
                    publication.content_sha256
                )
            }
        )

@dataclass(frozen = True)
class ExchangeCalendarSessionStage:
    """Generic session-gate stage backed by an exchange calendar"""

    calendar_name: str

    def __post_init__(self) -> None:
        if (
            not self.calendar_name or self.calendar_name.strip() != self.calendar_name
        ):
            raise ValueError(
                "calendar_name must be a non-empty trimmed string"
            )

    def allows(self, request: PipelineStageRequest) -> bool:
        return ExchangeCalendarSessionGate(
            calendar_name = self.calendar_name
        ).is_session(request.as_of_date)

@dataclass(frozen = True)
class AShareSessionStage:
    """A-share session gate backed by the configured reference calendar."""

    config: AStockDailyPipelineConfig

    def allows(self, request: PipelineStageRequest) -> bool:
        return is_a_share_trading_session(
            request.context,
            config = self.config,
            as_of_date = request.as_of_date,
        )

@dataclass(frozen=True)
class AShareDailyProductionStage:
    """Run the existing A-share daily producer as a generic task stage"""
    config: AStockDailyPipelineConfig
    def run(
            self,
            request: PipelineStageRequest,
    ) -> PipelineStageResult:
        result = run_a_share_daily_pipeline(
            request.context,
            config = self.config,
            as_of_date=request.as_of_date,
        )
        raw = result.raw_snapshot
        status = result.status_publication
        eligibility = result.eligibility_publication

        return PipelineStageResult(
            metadata = {
                "as_of_date": request.as_of_date.date().isoformat(),
                "raw_snapshot_dir" : str(raw.output_dir),
                "spot_row_count": raw.spot_row_count,
                "suspension_row_count": raw.suspension_row_count,
                "status_path": str(status.status_path),
                "status_row_count": status.row_count,
                "status_content_sha256": status.content_sha256,
                "eligibility_path": str(
                    eligibility.eligibility_path
                ),
                "eligibility_row_count": eligibility.row_count,
                "eligibility_content_sha256": (
                    eligibility.content_sha256
                ),
            }
        )

def create_exchange_calendar_session_gate(
        *,
        calendar_name: str,
) -> ExchangeCalendarSessionStage:
    """Create a named exchange_calendar gate such as XNYS."""

    return ExchangeCalendarSessionStage(calendar_name = calendar_name)

def create_a_share_session_gate(
        *,
        config: Mapping[str, Any]
) -> AShareSessionStage:
    """Create an A-share gate from persistent non-secret configuration"""

    return AShareSessionStage(
        config = AStockDailyPipelineConfig.from_mapping(config)
    )

def create_a_share_daily_production(
        *,
        config: Mapping[str, Any],
) -> AShareDailyProductionStage:
    """Create the built-in A-share daily production stage"""

    return AShareDailyProductionStage(
        config = AStockDailyPipelineConfig.from_mapping(config)
    )

def create_a_share_reference_refresh(
        *,
        config: Mapping[str, Any],
        ) -> AShareReferenceRefreshStage:
    """Create the A-share reference refresh stage."""

    return AShareReferenceRefreshStage(config = AStockDailyPipelineConfig.from_mapping(config))

def create_a_share_cumulative_market_data_refresh(
        *,
        config: Mapping[str, Any],
) -> AShareCumulativeMarketDataRefreshStage:
    """Create the configured cumulative A-share market-data stage."""

    return AShareCumulativeMarketDataRefreshStage(
        config = AStockDailyMarketDataRefreshConfig.from_mapping(config)
    )

@dataclass(frozen=True)
class AShareMarketDataCoverageAuditStage:
    market_data_connection_ref: str
    dataset_id: str
    reference_connection_ref: str
    reference_dataset: str
    plan_connection_ref: str
    policy: CoverageAuditPolicy

    def run(
        self,
        request: PipelineStageRequest,
    ) -> PipelineStageResult:
        version = request.as_of_date.strftime("%Y%m%d")

        market_root = request.context.connections.parquet_root(
            self.market_data_connection_ref
        )
        version_root = (
            market_root
            / self.dataset_id
            / "versions"
            / version
        )

        close_path = version_root / "close.parquet"
        volume_path = version_root / "volume.parquet"

        if not close_path.is_file() or not volume_path.is_file():
            raise FileNotFoundError(
                "market-data version required for coverage audit is missing: "
                f"{version_root}"
            )

        reference = ParquetAStockReferenceLoader(
            context=request.context,
            connection_ref=self.reference_connection_ref,
            dataset=self.reference_dataset,
            version=version,
        ).load()

        sessions = reference.trading_calendar[
            reference.trading_calendar <= request.as_of_date
        ]
        if sessions.empty:
            raise ValueError(
                "reference calendar contains no sessions through audit date"
            )

        symbols = tuple(
            reference.security_master.tickers_during(
                sessions.min(),
                sessions.max(),
            )
        )
        if not symbols:
            raise ValueError(
                "reference security master contains no eligible symbols "
                "for the audit window"
            )

        audit = audit_market_data_coverage(
            market="CN",
            published_version=version,
            expected_sessions=sessions,
            eligible_symbols=symbols,
            fields={
                "close": pd.read_parquet(close_path),
                "volume": pd.read_parquet(volume_path),
            },
            policy=self.policy,
        )

        plan_root = request.context.connections.writable_parquet_root(
            self.plan_connection_ref
        )
        audit_path = persist_coverage_audit(
            audit,
            artifact_dir=(
                plan_root
                / "coverage_audits"
                / "market=CN"
                / f"version={version}"
            ),
        )

        return PipelineStageResult(
            metadata={
                "market_data_version": version,
                "coverage_ratio": audit.coverage_ratio,
                "gap_count": audit.gap_count,
                "complete": audit.complete,
                "backfill_plan_id": audit.backfill_plan.plan_id,
                "backfill_task_count": len(audit.backfill_plan.tasks),
                "deferred_gap_count": (
                    audit.backfill_plan.deferred_gap_count
                ),
                "coverage_audit_path": str(audit_path),
            }
        )

def create_a_share_market_data_coverage_audit(
    *,
    market_data_connection_ref: str,
    dataset_id: str,
    reference_connection_ref: str,
    reference_dataset: str,
    plan_connection_ref: str,
    policy: Mapping[str, Any],
) -> AShareMarketDataCoverageAuditStage:
    return AShareMarketDataCoverageAuditStage(
        market_data_connection_ref=market_data_connection_ref,
        dataset_id=dataset_id,
        reference_connection_ref=reference_connection_ref,
        reference_dataset=reference_dataset,
        plan_connection_ref=plan_connection_ref,
        policy=CoverageAuditPolicy(
            minimum_coverage_ratio=float(
                policy["minimum_coverage_ratio"]
            ),
            max_backfill_tasks=int(policy["max_backfill_tasks"]),
            max_symbols_per_task=int(
                policy["max_symbols_per_task"]
            ),
        ),
    )

@dataclass(frozen=True)
class AShareHistoryBackfillStage:
    config: AStockDailyMarketDataRefreshConfig
    plan_connection_ref: str
    staging_connection_ref: str

    def run(
        self,
        request: PipelineStageRequest,
    ) -> PipelineStageResult:
        version = request.as_of_date.strftime("%Y%m%d")
        plan_root = request.context.connections.parquet_root(
            self.plan_connection_ref
        )
        audit_path = (
            plan_root
            / "coverage_audits"
            / "market=CN"
            / f"version={version}"
            / "coverage_audit.json"
        )
        audit = load_coverage_audit(audit_path)

        source_component = resolve_plugin(
            self.config.source,
            allowed_module_prefixes=request.allowed_module_prefixes,
        )
        if not isinstance(source_component, DataSourceComponent):
            raise TypeError(
                f"source factory {self.config.source.entry_point!r} "
                "must return DataSourceComponent"
            )

        staged = [
            stage_market_data_backfill(
                request.context,
                source_component=source_component,
                binding_template=self.config.binding,
                policy=self.config.policy,
                plan_id=audit.backfill_plan.plan_id,
                task=task,
                staging_connection_ref=self.staging_connection_ref,
            )
            for task in audit.backfill_plan.tasks
        ]

        return PipelineStageResult(
            metadata={
                "market_data_version": version,
                "backfill_plan_id": audit.backfill_plan.plan_id,
                "staged_task_count": len(staged),
                "deferred_gap_count": (
                    audit.backfill_plan.deferred_gap_count
                ),
                "staged_output_dirs": [
                    str(result.output_dir)
                    for result in staged
                ],
            }
        )


def create_a_share_history_backfill(
    *,
    config: Mapping[str, Any],
    plan_connection_ref: str,
    staging_connection_ref: str,
) -> AShareHistoryBackfillStage:
    return AShareHistoryBackfillStage(
        config=AStockDailyMarketDataRefreshConfig.from_mapping(config),
        plan_connection_ref=plan_connection_ref,
        staging_connection_ref=staging_connection_ref,
    )

@dataclass(frozen=True)
class AShareRepairPublicationStage:
    market_data_connection_ref: str
    dataset_id: str
    plan_connection_ref: str
    staging_connection_ref: str

    def run(
        self,
        request: PipelineStageRequest,
    ) -> PipelineStageResult:
        version = request.as_of_date.strftime("%Y%m%d")

        plan_root = request.context.connections.parquet_root(
            self.plan_connection_ref
        )
        audit = load_coverage_audit(
            plan_root
            / "coverage_audits"
            / "market=CN"
            / f"version={version}"
            / "coverage_audit.json"
        )

        if not audit.backfill_plan.tasks:
            return PipelineStageResult(
                metadata={
                    "base_market_data_version": audit.published_version,
                    "market_data_version": audit.published_version,
                    "backfill_plan_id": audit.backfill_plan.plan_id,
                    "applied_task_count": 0,
                }
            )

        repairs = tuple(
            load_staged_market_data_backfill(
                request.context,
                plan_id=audit.backfill_plan.plan_id,
                task=task,
                staging_connection_ref=self.staging_connection_ref,
            )
            for task in audit.backfill_plan.tasks
        )

        market_root = request.context.connections.writable_parquet_root(
            self.market_data_connection_ref
        )
        publication = publish_market_data_repair_revision(
            root=market_root,
            dataset_id=self.dataset_id,
            base_version=audit.published_version,
            repairs=repairs,
            coverage_complete=(
                audit.complete
                and audit.backfill_plan.deferred_gap_count == 0
            ),
        )

        return PipelineStageResult(
            metadata={
                "base_market_data_version": audit.published_version,
                "market_data_version": publication.output_dir.name,
                "backfill_plan_id": audit.backfill_plan.plan_id,
                "applied_task_count": len(repairs),
                "market_data_dir": str(publication.output_dir),
                "market_data_content_sha256": (
                    publication.content_sha256
                ),
            }
        )


def create_a_share_repair_publication(
    *,
    market_data_connection_ref: str,
    dataset_id: str,
    plan_connection_ref: str,
    staging_connection_ref: str,
) -> AShareRepairPublicationStage:
    return AShareRepairPublicationStage(
        market_data_connection_ref=market_data_connection_ref,
        dataset_id=dataset_id,
        plan_connection_ref=plan_connection_ref,
        staging_connection_ref=staging_connection_ref,
    )

@dataclass(frozen=True)
class ResearchReadinessGateStage:
    """Report whether the latest market-data version may feed research.

    This is a task stage rather than a session gate: the DAG needs the resolved
    version and its coverage numbers for artifact provenance, and downstream
    stages decide from ``research_ready`` whether to run.
    """

    market_data_connection_ref: str
    dataset_id: str
    market: str
    plan_connection_ref: str

    def run(
        self,
        request: PipelineStageRequest,
    ) -> PipelineStageResult:
        market_root = request.context.connections.parquet_root(
            self.market_data_connection_ref
        )
        plan_root = request.context.connections.parquet_root(
            self.plan_connection_ref
        )

        readiness = assess_market_data_readiness(
            market_root,
            dataset_id=self.dataset_id,
            market=self.market,
            as_of_date=request.as_of_date,
            coverage_root=plan_root,
        )

        return PipelineStageResult(metadata=readiness.to_mapping())

def create_research_readiness_gate(
    *,
    market_data_connection_ref: str,
    dataset_id: str,
    market: str,
    plan_connection_ref: str,
) -> ResearchReadinessGateStage:
    return ResearchReadinessGateStage(
        market_data_connection_ref=market_data_connection_ref,
        dataset_id=dataset_id,
        market=market,
        plan_connection_ref=plan_connection_ref,
    )

@dataclass(frozen=True)
class ResearchReadinessGateStage:
    """Allow research only when the resolved market-data version is complete"""

    market_data_connection_ref: str
    dataset_id: str
    market: str
    plan_connection_ref: str

    def allows(self, request: PipelineStageRequest) -> bool:
        market_root = request.context.connections.parquet_root(self.market_data_connection_ref)
        plan_root = request.context.connections.parquet_root(self.plan_connection_ref)

        readiness = assess_market_data_readiness(market_root, dataset_id= self.dataset_id, market= self.market, as_of_date= request.as_of_date, coverage_root=plan_root)

        return readiness.ready
