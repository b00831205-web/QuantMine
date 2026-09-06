from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from .plugins.context import SourceContext

from .research import FactorResearchResult, run_configured_research
from .storage.connections import ConnectionRegistry
from .storage.runs import ResearchRunStore

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

    connection_refs = (() if config.data_binding.connection_ref is None else (config.data_binding.connection_ref,))

    connections = ConnectionRegistry.from_environment(
        (connection_refs)
    )

    context = SourceContext(
        connections = connections,
        run_id = run_id,
        artifact_dir = artifact_dir,
    )

    try: 
        return run_configured_research(
        config, context, allowed_module_prefixes = allowed_module_prefixes
    )   

    finally:
        connections.dispose()