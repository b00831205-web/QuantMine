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

from ..workflows.trading_sessions import ExchangeCalendarSessionGate

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