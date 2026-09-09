"""Collect and publish one configured A-share reference-date version"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from quantmine.a_share_pipeline_loader import (
    load_a_share_daily_pipeline_config,
)

from quantmine.plugins.context import SourceContext
from quantmine.runtime_environment import load_environment_file
from quantmine.storage.connections import ConnectionRegistry
from quantmine.workflows.a_share_reference_refresh import (
    refresh_akshare_a_stock_reference
)
from quantmine.dataset_versions import (
    AS_OF_DATE_VERSION,
    resolve_versioned_dataset_binding,
)


def _project_path(value: str) -> Path:
    path = Path(value).expanduser()
    if path.is_absolute():
        return path

    return PROJECT_ROOT / path

def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description= (
            "Collect AkShare A-share security-master and calendar data, "
            "then publish one immutable configured version"
        )
    )
    parser.add_argument(
        "--config",
        default = "config.yaml",
        help = "YAML configuration file",
    )
    parser.add_argument(
        "--env-file",
        default = ".env",
        help = "Runtime environment file",
    )
    parser.add_argument(
        "--date",
        help = (
            "Reference date in YYYY-MM-DD format; required when "
            "reference_binding.version is {as_of_date}"
        ),
    )

    args = parser.parse_args(argv)

    load_environment_file(
        _project_path(args.env_file)
    )
    config = load_a_share_daily_pipeline_config(
        _project_path(args.config)
    )

    binding = config.reference_binding

    if binding.version == AS_OF_DATE_VERSION:
        if args.date is None:
            parser.error(
                "--date is required when reference version is {as_of_date}"
            )
        binding = resolve_versioned_dataset_binding(
            binding,
            as_of_date = args.date
        )

    connections = ConnectionRegistry.from_environment(
        (binding.connection_ref,)
    )
    context = SourceContext(
        connections = connections,
        run_id = 0,
        artifact_dir = (
            PROJECT_ROOT / "data" / "artifacts" / "a_share_reference" / binding.version
        ),
    )

    try:
        publication = refresh_akshare_a_stock_reference(
            context,
            binding = binding,
        )
    finally:
        connections.dispose()

    print(
        "A-share reference publication completed: "
        f"version={binding.version}, "
        f"listings={publication.listing_count}, "
        f"sessions={publication.session_count}, "
        f"output={publication.output_dir}"
    )

if __name__ == "__main__":
    main()