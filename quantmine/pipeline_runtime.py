"""Runtime assembly for configured market-pipeline stages."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path
import re
from typing import Any

from .market_pipeline_config import MarketPipelineDefinition
from .pipeline_stages import (
    evaluate_session_gate,
    run_pipeline_stage,
)
from .plugins.context import SourceContext
from .storage.connections import ConnectionRegistry
from .runtime_environment import load_environment_file

_BATCH_SAFE = re.compile(r"[^A-Za-z0-9_.-]+")

def run_configured_pipeline_stage(
        *,
        pipeline_snapshot: Mapping[str, Any],
        stage_id: str,
        as_of_date: str,
        batch_id: str,
        artifact_root: Path | str,
        allowed_module_prefixes: Iterable[str] | None = ("quantmine",),
        environment_file: Path | str | None= None
) -> dict[str, Any]: 
    """Restore a pipeline definition and execute one ordinary stage"""

    pipeline = _pipeline_from_snapshot(pipeline_snapshot)
    load_environment_file(environment_file)
    connections = ConnectionRegistry.from_environment(
        pipeline.connection_refs
    )
    context = _context(
        pipeline,
        connections = connections,
        artifact_root = artifact_root,
        batch_id = batch_id
    )

    try:
        result = run_pipeline_stage(
            pipeline,
            stage_id = stage_id,
            context= context,
            as_of_date = as_of_date,
            batch_id = batch_id,
            allowed_module_prefixes = allowed_module_prefixes,
        )
        return dict(result.metadata)
    finally:
        connections.dispose()

def evaluate_configured_session_gate(
        *,
        pipeline_snapshot: Mapping[str, Any],
        stage_id: str,
        as_of_date: str,
        batch_id: str,
        artifact_root: Path | str,
        allowed_module_prefixes: Iterable[str] | None = ("quantmine",),
        environment_file: Path | str | None = None
) -> bool:
    """Restore a pipeline definition and evaluate one session-gate stage"""

    pipeline = _pipeline_from_snapshot(pipeline_snapshot)
    load_environment_file(environment_file)
    connections = ConnectionRegistry.from_environment(
        pipeline.connection_refs,
    )
    context = _context(
        pipeline,
        connections = connections,
        artifact_root = artifact_root,
        batch_id = batch_id,
    )

    try:
        return evaluate_session_gate(
            pipeline,
            stage_id = stage_id,
            context = context,
            as_of_date = as_of_date,
            batch_id = batch_id,
            allowed_module_prefixes = allowed_module_prefixes,
        )
    finally:
        connections.dispose()

def _pipeline_from_snapshot(
        pipeline_snapshot: Mapping[str, Any],
) -> MarketPipelineDefinition:
    if not isinstance(pipeline_snapshot, Mapping):
        raise TypeError("pipeline snapshot must be a JSON object")

    return MarketPipelineDefinition.from_snapshot(pipeline_snapshot)

def _context(
        pipeline: MarketPipelineDefinition,
        *,
        connections: ConnectionRegistry,
        artifact_root: Path | str,
        batch_id: str,
) -> SourceContext:
    safe_batch = _BATCH_SAFE.sub("_", batch_id).strip("._") or "manual"
    artifact_dir = Path(artifact_root) / pipeline.id / safe_batch
    artifact_dir.mkdir(parents = True, exist_ok = True)

    return SourceContext(
        connections = connections,
        run_id = 0,
        artifact_dir = artifact_dir
    )