"""Built-in configured stages for persisted factor research."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from ..execution import execute_persisted_research
from ..pipeline_stages import (
    PipelineStageRequest,
    PipelineStageResult,
)

from ..research_config import ResearchRunConfig, resolve_research_run_config_for_as_of_date
from ..storage.runs import (
    SQLAlchemyResearchRunStore,
    get_or_create_research_run_for_batch,
)


@dataclass(frozen=True)
class PersistedFactorResearchStage:
    """Create or resume one batch-bound research run and publish its factors."""

    research_run_connection_ref: str
    config: ResearchRunConfig

    def __post_init__(self) -> None:
        if (
            not isinstance(self.research_run_connection_ref, str)
            or not self.research_run_connection_ref.strip()
            or self.research_run_connection_ref.strip() != self.research_run_connection_ref
        ):
            raise ValueError(
                "research_run_connection_ref must be a non-empty "
                "trimmed string"
            )

        if not isinstance(self.config, ResearchRunConfig):
            raise TypeError("config must be a ResearchRunConfig")


    def run(
            self,
            request: PipelineStageRequest,
    ) -> PipelineStageResult:
        engine = request.context.connections.sqlalchemy_engine(
            self.research_run_connection_ref
        )

        resolved_config = resolve_research_run_config_for_as_of_date(
                        self.config,
                        as_of_date=request.as_of_date
                    )
        
        run_id = get_or_create_research_run_for_batch(
            engine,
            resolved_config,
            batch_id = request.batch_id,
        )
        result = execute_persisted_research(
            SQLAlchemyResearchRunStore(engine),
            run_id,
            artifact_root = request.context.artifact_dir,
            allowed_module_prefixes = request.allowed_module_prefixes,
        )

        factor_artifact_dir = (
            request.context.artifact_dir / "factor_research" / str(run_id)
        )
        return PipelineStageResult(
            metadata={
                "research_run_id": run_id,
                "requested_signal_count": len(result.requested_signals),
                "factor_count": len(result.factors),
                "pending_count": len(result.pending),
                "factor_artifact_dir": str(factor_artifact_dir),
            }
        )

def create_persisted_factor_research_stage(
        *,
        research_run_connection_ref: str,
        config: Mapping[str, Any],
) -> PersistedFactorResearchStage:
    """Create the standard DAG research stage from non-secret YAML config."""

    return PersistedFactorResearchStage(
        research_run_connection_ref=research_run_connection_ref,
        config = ResearchRunConfig.from_snapshot(config)
    )