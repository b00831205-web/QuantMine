"""Runtime contracts and dispatch for generic market-pipeline stages"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
import json
from typing import Any, Mapping, Protocol, runtime_checkable

import pandas as pd

from .market_pipeline_config import(
    MarketPipelineDefinition,
    PipelineStageDefinition,
    PipelineStageKind,
)

from .plugins.context import SourceContext
from .plugins.loader import resolve_plugin

@dataclass(frozen = True)
class PipelineStageRequest:
    """Runtime inputs shared by every configured pipeline stage"""

    pipeline: MarketPipelineDefinition
    stage: PipelineStageDefinition
    context: SourceContext = field(repr = False, compare = False)
    as_of_date: pd.Timestamp
    batch_id:str
    allowed_module_prefixes: tuple[str, ...] | None = ("quantmine",)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "as_of_date",
            pd.Timestamp(self.as_of_date).normalize()
        )
        if not self.batch_id or self.batch_id.strip() != self.batch_id:
            raise ValueError("batch_id must be a non-empty trimmed string")

@dataclass(frozen = True)
class PipelineStageResult:
    """JSON-safe metadata emitted by a completed non-gate stage"""
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        try:
            json.dumps(dict(self.metadata), sort_keys = True, allow_nan=False)
        except(TypeError, ValueError) as error:
            raise TypeError(
                "pipeline stage result metadata must be JSON-serializable"
            ) from error

@runtime_checkable
class PipelineTaskPlugin(Protocol):
    def run(self, request: PipelineStageRequest) -> PipelineStageResult: ...

@runtime_checkable
class PipelineSessionGatePlugin(Protocol):
    def allows(self, request: PipelineStageRequest) -> bool: ...

def run_pipeline_stage(
        pipeline: MarketPipelineDefinition,
        *,
        stage_id: str,
        context: SourceContext,
        as_of_date: pd.Timestamp| str,
        batch_id: str,
        allowed_module_prefixes: Iterable[str] | None = ("quantmine",)
) -> PipelineStageResult:
    """Resolve and execute one ordinary stage declared by a pipeline"""

    stage = _stage_by_id(pipeline, stage_id)
    if stage.kind is not PipelineStageKind.TASK:
        raise ValueError(f"stage {stage_id!r} is not a task stage")

    request = PipelineStageRequest(
        pipeline, 
        stage,
        context,
        as_of_date,
        batch_id,
        allowed_module_prefixes=(
            None if allowed_module_prefixes is None else tuple(allowed_module_prefixes)
        )
    )
    plugin = resolve_plugin(
        stage.plugin,
        allowed_module_prefixes = allowed_module_prefixes,
    )

    if not isinstance(plugin, PipelineTaskPlugin):
        raise TypeError(
            f"stage plugin {stage.plugin.entry_point!r} "
            "must implement run(request)",
        )

    result = plugin.run(request)
    if not isinstance(result, PipelineStageResult):
        raise TypeError(
            f"stage plugin {stage.plugin.entry_point!r} returned "
            f"{type(result).__name__}; expected PipelineStageResult",
        )
    return result

def evaluate_session_gate(
        pipeline: MarketPipelineDefinition,
        *,
        stage_id: str,
        context: SourceContext,
        as_of_date: pd.Timestamp | str,
        batch_id : str,
        allowed_module_prefixes: Iterable[str] | None = ("quantmine",)
) -> bool:
    """Resolve and evaluate one session-gate stage for ShortCircuitOperator."""

    stage = _stage_by_id(pipeline, stage_id)
    if stage.kind is not PipelineStageKind.SESSION_GATE:
        raise ValueError(f"stage{stage_id!r} is not a session-gate stage")

    request = PipelineStageRequest(
        pipeline,
        stage,
        context,
        as_of_date,
        batch_id
    )
    plugin = resolve_plugin(
        stage.plugin,
        allowed_module_prefixes = allowed_module_prefixes
    )

    if not isinstance(plugin, PipelineSessionGatePlugin):
        raise TypeError(
            f"stage plugin {stage.plugin.entry_point!r} "
            "must implement allows(request)",
        )

    allowed = plugin.allows(request)
    if not isinstance(allowed, bool):
        raise TypeError(
            f"session-gate plugin {stage.plugin.entry_point!r} "
            "must return bool"
        )

    return allowed

def _stage_by_id(
        pipeline: MarketPipelineDefinition,
        stage_id: str,
) -> PipelineStageDefinition:
    for stage in pipeline.stages:
        if stage.id == stage_id:
            return stage

    raise KeyError(
        f"pipeline {pipeline.id!r} has no stage {stage_id!r}",
    )
