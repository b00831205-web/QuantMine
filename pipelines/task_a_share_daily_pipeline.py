"""Run one scheduler-triggered A-share daily production pipeline"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Sequence
from pathlib import Path
import os

from quantmine.a_share_pipeline_loader import (
    load_a_share_daily_pipeline_config,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from quantmine.plugins.context import SourceContext
from quantmine.storage.connections import ConnectionRegistry
from quantmine.workflows.a_share_daily_pipeline import (
    AStockDailyPipelineConfig,
    run_a_share_daily_pipeline
)

def load_project_environment(
        env_path: Path = PROJECT_ROOT / ".env"
) -> None:
    """Fill missing runtime variable from the project .env file"""

    if not env_path.is_file():
        return

    for line in env_path.read_text(encoding = "utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        if line.startswith("export "):
            line = line[len("export "):]

        key, value = line.split("=", 1)
        os.environ.setdefault(
            key.strip(),
            value.strip().strip('"').strip("'")
        )


def required_connection_refs(
        config: AStockDailyPipelineConfig,
) -> tuple[str, ...]:
    """Return unique connection aliases required for one production day."""

    return tuple(
        dict.fromkeys(
            (
                config.raw_connection_ref,
                config.reference_binding.connection_ref,
                config.status_binding.connection_ref,
                config.eligibility_binding.connection_ref,
            )
        )
    )

def _artifact_dir(batch: str) -> Path:
    safe_batch = re.sub(r"[^A-Za-z0-9_.-]+","_", batch)
    safe_batch = safe_batch.strip("._") or "manual"

    return PROJECT_ROOT / "data" / "artifacts" / "a_share_daily" / safe_batch

def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description = "Run one A-share daily production pipeline",
    )
    parser.add_argument("--date", required = True)
    parser.add_argument("--batch", required = True)
    parser.add_argument(
        "--config",
        default = "config.yaml",
        help = 'YAML file containing the "a_share_daily_pipeline" section'
    )
    args = parser.parse_args(argv)
    load_project_environment()
    config =  load_a_share_daily_pipeline_config(
        PROJECT_ROOT / args.config,
    )

    context = SourceContext(
        connections = ConnectionRegistry.from_environment(
            required_connection_refs(config),
        ),
        run_id = 0,
        artifact_dir = _artifact_dir(args.batch),
    )

    run_a_share_daily_pipeline(
        context,
        config = config,
        as_of_date = args.date,
    )
    print(f"A-share daily pipeline completed: date={args.date}")

if __name__ == "__main__":
    main()