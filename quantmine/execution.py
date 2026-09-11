from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from .plugins.context import SourceContext

from .research import FactorResearchResult, run_configured_research
from .research_config import ResearchRunConfig
from .storage.connections import ConnectionRegistry
from .storage.runs import ResearchRunStore

from .workflows.factor_research_artifacts import (
    publish_factor_research_artifacts,
)

def execute_persisted_research(
        store: ResearchRunStore,
        run_id: int,
        *,
        artifact_root: Path,
        allowed_module_prefixes: Iterable[str] | None = ("quantmine",),
) -> FactorResearchResult:
    """Execute one persisted run through the shared plugin pipeline.

    The configuration supplies only a connection alias. The registry resolves
    its actual DSN or Parquet root from the current deployment environment.
    """

    config = store.load(run_id)
    artifact_dir = artifact_root / str(run_id)
    artifact_dir.mkdir(parents = True, exist_ok = True)


    connections = ConnectionRegistry.from_environment(
        required_research_connection_refs(config)
    )

    context = SourceContext(
        connections = connections,
        run_id = run_id,
        artifact_dir = artifact_dir,
    )

    try: 
        result = run_configured_research(
            config,
            context,
            allowed_module_prefixes=allowed_module_prefixes,
        )
        publish_factor_research_artifacts(
            result,
            run_id = run_id,
            root = artifact_root / "factor_research"
        )
        return result

    finally:
        connections.dispose()

def required_research_connection_refs(
        config: ResearchRunConfig,
) -> tuple[str, ...]:
    """Return every external connection required by one research run."""

    eligibility_binding = config.data_binding.eligibility_binding

    candidates = (
        config.data_binding.connection_ref,
        (
            eligibility_binding.connection_ref
            if eligibility_binding is not None
            else None
        ),
    )

    return tuple(
        dict.fromkeys(
            connection_ref for connection_ref in candidates
            if connection_ref is not None
        )
    )