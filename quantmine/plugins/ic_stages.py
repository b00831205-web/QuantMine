"""Built-in configured stage for persisted IC research."""

from __future__ import annotations

from dataclasses import dataclass

from .. import execution
from ..pipeline_stages import PipelineStageRequest, PipelineStageResult
from ..storage.runs import SQLAlchemyResearchRunStore, find_run_id_by_airflow_batch


@dataclass(frozen = True)
class PersistedICResearchStage:
    """Resume a batch-bound research run and execute its IC workflow."""

    research_run_connection_ref: str

    def __post_init__(self) -> None:
        if (not isinstance(self.research_run_connection_ref, str)
            or not self.research_run_connection_ref.strip()
            or self.research_run_connection_ref.strip()
            != self.research_run_connection_ref
            ):
            raise ValueError(
                "research_run_connection_ref must be a non-empty trimmed string"
            )

    def run(self, request: PipelineStageRequest,) ->PipelineStageResult:
        engine = request.context.connections.sqlalchemy_engine(self.research_run_connection_ref)
        run_id = find_run_id_by_airflow_batch(engine, request.batch_id)
        variants, test_results = execution.execute_persisted_ic_research(
            SQLAlchemyResearchRunStore(engine),
            run_id,
            artifact_root = request.context.artifact_dir,
            allowed_module_prefixes = request.allowed_module_prefixes,
        )

        return PipelineStageResult(
            metadata={
                "research_run_id": run_id,
                "variant_count": len(variants),
                "test_count": len(test_results),
                "ic_artifact_dir": str(request.context.artifact_dir / "ic_research" / str(run_id))
            },
        )

def create_persisted_ic_research_stage(*, research_run_connection_ref: str) -> PersistedICResearchStage:
    """Create the standard persisted IC DAG stage"""

    return PersistedICResearchStage(
        research_run_connection_ref= research_run_connection_ref,
    )