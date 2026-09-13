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