"""Built-in configured stage for persisted backtest execution."""

from __future__ import annotations

from dataclasses import dataclass

from ..import execution
from ..pipeline_stages import PipelineStageRequest, PipelineStageResult
from ..storage.runs import SQLAlchemyResearchRunStore, find_run_id_by_airflow_batch


@dataclass(frozen=True)
class PersistedBacktestStage:
    """Resume one batch-bound research run and execute its backtest engine."""

    research_run_connection_ref: str

    def __post_init__(self) -> None:
        if (not isinstance(self.research_run_connection_ref, str) 
            or not self.research_run_connection_ref.strip()
            or self.research_run_connection_ref.strip() != self.research_run_connection_ref ):

            raise ValueError(
                "research_run_connection_ref must be a non-empty trimmed string"
            )

    def run(self, request: PipelineStageRequest) -> PipelineStageResult:
        engine = request.context.connections.sqlalchemy_engine(self.research_run_connection_ref)
        run_id = find_run_id_by_airflow_batch(engine, request.batch_id)

        result = execution.execute_persisted_backtest(
            SQLAlchemyResearchRunStore(engine),
            run_id,
            artifact_root = request.context.artifact_dir,
            allowed_module_prefixes = request.allowed_module_prefixes,
        )

        position_artifact_dir = request.context.artifact_dir / "position_backtests" / str(run_id)

        run_manifest_path = position_artifact_dir / "run_manifest.json"

        return PipelineStageResult(
            metadata = {
                "research_run_id": run_id,
                "backtest_job_count": len(result.job_results),
                "position_backtest_artifact_dir": str(
                    position_artifact_dir
                ),
                "position_backtest_run_manifest": (
                    str(run_manifest_path) if run_manifest_path.is_file() else None
                ),
            }
        )

def create_persisted_backtest_stage(*, research_run_connection_ref: str,) -> PersistedBacktestStage:
    """Create the standard persisted-backtest DAG stage"""

    return PersistedBacktestStage(
        research_run_connection_ref= research_run_connection_ref,
    )