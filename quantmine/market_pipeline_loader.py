"""Load persistent market-pipeline definitions from YAML"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import yaml

from .market_pipeline_config import MarketPipelineDefinition

def load_market_pipeline_definitions(
        yaml_path: Path | str
) -> tuple[MarketPipelineDefinition, ...]:
    """Load and validate the ``market_pipelines`` section of a YAML file."""

    path = Path(yaml_path)

    with path.open("r", encoding = "utf-8") as file:
        document = yaml.safe_load(file) or {}

    if not isinstance(document, Mapping):
        raise TypeError("pipeline configuration root must be a YAML object")

    raw_definitions = document.get("market_pipelines", [])

    if not isinstance(raw_definitions, list):
        raise TypeError("market_pipelines must be a YAML list")

    definitions = tuple(
        MarketPipelineDefinition.from_snapshot(raw_definition)
        for raw_definition in raw_definitions
    )
    _validate_unique_definitions(definitions)
    return definitions

def _validate_unique_definitions(
        definitions: tuple[MarketPipelineDefinition, ...],
) -> None:
    seen_pipeline_ids: set[str] = set()
    seen_dag_ids: set[str] = set()

    for definition in definitions:
        if definition.id in seen_pipeline_ids:
            raise ValueError(
                f"duplicate market pipeline id: {definition.id!r}"
            ) 
        if definition.dag_id in seen_dag_ids:
            raise ValueError(
                f"duplicate Airflow dag_id: {definition.dag_id!r}"
            )

        seen_pipeline_ids.add(definition.id)
        seen_dag_ids.add(definition.dag_id)
