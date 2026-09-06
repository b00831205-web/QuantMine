from __future__ import annotations

from dataclasses import dataclass, field
import json
import re
from typing import Any, Mapping

from enum import StrEnum
from .plugins.contracts import PluginSpec

MARKET_PIPELINE_CONFIG_VERSION = 1
_SAFE_ID = re.compile(r"[a-z][a-z0-9_]*\Z")

class PipelineStageKind(StrEnum):
    SESSION_GATE = "session_gate"
    TASK = "task"

@dataclass(frozen=True)
class PipelineStageDefinition:
    """One DAG stage implemented by a configured stage-plugin factory"""

    id: str
    plugin: PluginSpec
    upstream: tuple[str, ...] =()
    kind: PipelineStageKind = PipelineStageKind.TASK
    def __post_init__(self) -> None:
        try:
            kind = PipelineStageKind(self.kind)
        except ValueError as error:
            raise ValueError(
                "stage kind must be 'session_gate' or 'task'",
            ) from error

        object.__setattr__(self, "kind", kind)

        _validate_id(self.id, label = "stage id")

        if not isinstance(self.plugin, PluginSpec):
            raise TypeError("stage plugin must be a PluginSpec")

        if not isinstance(self.upstream, tuple):
            raise TypeError("stage upstream must be a tuple of stage IDs")

        for stage_id in self.upstream:
            _validate_id(stage_id, label = "upstream stage id")

@dataclass(frozen = True)
class MarketPipelineDefinition:
    """Non-secret, persistent topology for one market-specific DAG instance."""

    id: str
    dag_id: str
    display_name: str
    schedule: str
    stages: tuple[PipelineStageDefinition, ...]
    connection_refs: tuple[str, ...] =()
    metadata: Mapping[str, Any] = field(default_factory = dict)

    def __post_init__(self) -> None:
        _validate_id(self.id, label = "pipeline id")

        for label, value in (
            ("dag_id", self.dag_id),
            ("display_name", self.display_name),
            ("schedule", self.schedule),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{label} must be a non-empty string")

        if not isinstance(self.connection_refs, tuple):
            raise TypeError("pipeline connection_refs must be a tuple")

        if len(self.connection_refs) != len(set(self.connection_refs)):
            raise ValueError("pipeline contains duplicate connection refs")

        for connection_ref in self.connection_refs:
            _validate_id(connection_ref, label = "connection ref")


        if not isinstance(self.stages, tuple) or not self.stages:
            raise ValueError("pipeline stages must be a non-empty tuple")

        stage_ids = [stage.id for stage in self.stages]
        if len(stage_ids) != len(set(stage_ids)):
            raise ValueError("pipeline contains duplicate stage IDs")

        known = set(stage_ids)
        for stage in self.stages:
            unknown = sorted(set(stage.upstream) - known)
            if unknown:
                raise ValueError(
                    f"stage {stage.id!r} has unknown upstream stage IDs: " + ", ".join(unknown),
                )
            if stage.id in stage.upstream:
                raise ValueError(
                    f"stage {stage.id!r} cannot depend on itself",
                )

        self._ordered_stage_ids()

        _json_copy(dict(self.metadata), label = "pipeline metadata")

    @property
    def ordered_stage_ids(self) -> tuple[str, ...]:
        """Stable topoligical order, perserving declararion order where possible"""

        return self._ordered_stage_ids()

    def to_snapshot(self) -> dict[str, Any]:
        return _json_copy(
            {
                "schema_version": MARKET_PIPELINE_CONFIG_VERSION,
                "id": self.id,
                "dag_id": self.dag_id,
                "display_name": self.display_name,
                "schedule": self.schedule,
                "connection_refs": list(self.connection_refs),
                "stages": [
                    {
                        "id": stage.id,
                        "plugin": {
                            "entry_point": stage.plugin.entry_point,
                            "params": dict(stage.plugin.params),
                        },
                        "upstream": list(stage.upstream),
                        "kind": stage.kind.value
                    }
                    for stage in self.stages
                ],
                "metadata": dict(self.metadata),
            },
            label = "market pipeline definition"
        )
    @classmethod
    def from_snapshot(
        cls,
        snapshot: Mapping[str, Any]
    ) -> "MarketPipelineDefinition":
        payload = _mapping(snapshot, label = "market pipeline definition")

        if payload.get("schema_version") != MARKET_PIPELINE_CONFIG_VERSION:
            raise ValueError(
                "unsupported market-pipeline schema version "
                f"{payload.get('schema_version')!r}"
            )
        raw_stages = payload.get("stages")
        if not isinstance(raw_stages, list):
            raise TypeError("pipeline stages must be JSON list")

        stages = tuple(_stage_from_snapshot(item) for item in raw_stages)

        raw_connection_refs = payload.get("connection_refs", [])
        if not isinstance(raw_connection_refs, list) or not all(
            isinstance(connection_ref, str)
            for connection_ref in raw_connection_refs
        ):
            raise TypeError("pipeline connection_refs must be a JSON list of strings")
        return cls(
            id=_string(payload.get("id"), label = "pipeline id"),
            dag_id = _string(payload.get("dag_id"), label = "dag_id"),
            display_name = _string(payload.get("display_name"),
                                   label = "display_name"
                                   ),
            schedule = _string(payload.get("schedule"), label = "schedule"),
            stages = stages,
            connection_refs = tuple(raw_connection_refs),
            metadata = _mapping(
                payload.get("metadata", {}),
                label = "pipeline metadata"
            ),
        )

    def _ordered_stage_ids(self) -> tuple[str, ...]:
        pending = {stage.id: set(stage.upstream) for stage in self.stages}
        ordered: list[str] = []

        while pending:
            ready = [
                stage.id
                for stage in self.stages
                if stage.id in pending and not pending[stage.id]
            ]
            if not ready:
                raise ValueError("pipeline stage dependency cycle detected")

            for stage_id in ready:
                ordered.append(stage_id)
                pending.pop(stage_id)
                for upstream in pending.values():
                    upstream.discard(stage_id)

        return tuple(ordered)

def _stage_from_snapshot(value: object) -> PipelineStageDefinition:
    payload = _mapping(value, label="pipeline stage")
    plugin_payload = _mapping(payload.get("plugin"), label = "stage plugin")
    kind = PipelineStageKind(
        payload.get("kind", PipelineStageKind.TASK.value)
    )

    raw_upstream = payload.get("upstream", [])

    if not isinstance(raw_upstream, list) or not all(
        isinstance(stage_id, str) for stage_id in raw_upstream
    ):
        raise TypeError("stage upstream must be a JSON list of strings")

    return PipelineStageDefinition(
        id = _string(payload.get("id"), label = "stage id"),
        plugin = PluginSpec(
            entry_point = _string(
                plugin_payload.get("entry_point"),
                label = "stage plugin entry_point"
            ),
            params=_mapping(
                plugin_payload.get("params", {}),
                label = "stage plugin params"
            ),
        ),
        upstream = tuple(raw_upstream),
        kind = kind
    )

def _validate_id(value: object, *, label: str) -> None:
    if not isinstance(value, str) or not _SAFE_ID.fullmatch(value):
        raise ValueError(
            f"{label} must use lowercase letters, digits, and underscores",
        )

def _string(value: object, *, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise TypeError(f"{label} must be a non-empty string")
    return value

def _mapping(value: object, *, label: str) ->dict[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{label} must be JSON object")

    return dict(value)

def _json_copy(value: object, *, label: str) -> dict[str, Any]:
    try:
        serialized = json.dumps(value, sort_keys = True, allow_nan = False)
    except(TypeError, ValueError) as error:
        raise TypeError(f"{label} must be JSON-serializable") from error

    result = json.loads(serialized)
    return _mapping(result, label = label)