from __future__ import annotations
from collections.abc import Mapping
from pathlib import Path

import yaml

from .workflows.a_share_daily_pipeline import(
    AStockDailyPipelineConfig,
)

def load_a_share_daily_pipeline_config(
        yaml_path: Path | str,
) -> AStockDailyPipelineConfig:
    """Load and validate the top-level ``a_share_daily_pipeline`` section."""

    path = Path(yaml_path)
    with path.open("r", encoding ="utf-8") as file:
        document = yaml.safe_load(file) or {}

    if not isinstance(document, Mapping):
        raise TypeError(
            "pipeline configuration root must be a YAML object"
        )

    try:
        payload = document["a_share_daily_pipeline"]
    except KeyError as error:
        raise KeyError(
            'Missing "a_share_daily_pipeline" section in config file'
        ) from error

    return AStockDailyPipelineConfig.from_mapping(payload)