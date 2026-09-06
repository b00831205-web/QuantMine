"""Discover market DAGs from persistent YAML pipeline definition"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

PROJECT_ROOT = Path(
    os.environ.get(
        "QUANT_PROJECT_ROOT",
        Path(__file__).resolve().parents[1],
    )
).resolve()

sys.path.insert(0, str(PROJECT_ROOT))

from quantmine.airflow_dag_factory import build_market_pipeline_dag
from quantmine.market_pipeline_loader import (
    load_market_pipeline_definitions,
)

def _project_path(
        environment_name: str,
        default: str,
) -> Path:
    value = Path(os.environ.get(environment_name, default))
    if not value.is_absolute():
        value = PROJECT_ROOT / value
    return value.resolve()

def _allowed_plugin_prefixes() -> tuple[str, ...]:
    raw_value = os.environ.get(
        "QUANTMINE_PLUGIN_ALLOWED_PREFIXES",
        "quantmine"
    )
    prefixes = tuple(
        value.strip()
        for value in raw_value.split(",")
        if value.strip()
    )

    if not prefixes:
        raise RuntimeError(
            "QUANTMINE_PLUGIN_ALLOWED_PREFIXES must contain "
            "at least one module prefix"
        )

    return prefixes

CONFIG_PATH = _project_path(
    "QUANT_MARKET_PIPELINE_CONFIG_PATH",
    "config.yaml",
)

ARTIFACT_ROOT = _project_path(
    "QUANT_PIPELINE_ARIFACT_ROOT",
    "data/artifacts/market_pipeline",
)
ENVIRONMENT_FILE = _project_path(
    "QUANT_ENV_FILE",
    ".env",
)

PIPELINE_DEFINITIONS = load_market_pipeline_definitions(CONFIG_PATH)
ALLOWED_PLUGIN_PREFIXES = _allowed_plugin_prefixes()

for _definition in PIPELINE_DEFINITIONS:
    globals()[f"dag_{_definition.id}"] = build_market_pipeline_dag(
        _definition,
        start_date = datetime(
            2026,
            1,
            1,
            tzinfo = ZoneInfo("Asia/Shanghai")
        ),
        artifact_root = ARTIFACT_ROOT,
        environment_file = ENVIRONMENT_FILE,
        allowed_module_prefixes=ALLOWED_PLUGIN_PREFIXES,
        default_args={
            "retries": 1,
            "retry_delay": timedelta(minutes = 10),
        },
        tags = (
            "quant_factor_mining",
            "configuerd_pipeline",
        )
    )