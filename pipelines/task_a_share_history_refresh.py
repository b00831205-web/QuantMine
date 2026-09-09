"""Run one configured A-share historical market-data backfill."""

from __future__ import annotations
import argparse
from collections.abc import Sequence
import os
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from quantmine.a_share_history_loader import (
    load_a_share_history_refresh_config,
)

from quantmine.plugins.context import SourceContext
from quantmine.runtime_environment import load_environment_file
from quantmine.storage.connections import ConnectionRegistry
from quantmine.workflows.a_share_market_data_refresh import(
    AStockHistoryRefreshConfig,
    run_configured_a_share_history_refresh,
)

def _project_path(value: str) -> Path:
    path = Path(value).expanduser()
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path

def _allowed_plugin_prefixes() -> tuple[str, ...]:
    raw_value = os.environ.get(
        "QUANTMINE_PLUGIN_ALLOWED_PREFIXES",
        "quantmine"
    )
    prefixes = tuple(
        value.strip() for value in raw_value.split(",") if value.strip()
    )
    if not prefixes:
        raise RuntimeError(
            "QUANTMINE_PLUGIN_ALLOWED_PREFIXES must contain "
            "at least one module prefix"
        )

    return prefixes

def required_connection_refs(
        config: AStockHistoryRefreshConfig,
) -> tuple[str, ...]:
    """Return unique connections needed by one history refresh"""

    candidates= (
        config.binding.connection_ref,
        config.reference_binding.connection_ref,
        config.output_connection_ref
    )

    return tuple(
        dict.fromkeys(
            connection_ref for connection_ref in candidates if connection_ref is not None
        )
    )

def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Load a configured A-share data source and publish "
            "one immutable historical market-data version"
        )
    )

    parser.add_argument(
        "--config",
        default = "config.yaml",
        help="YAML configuration file"
    )
    parser.add_argument(
        "--env-file",
        default=".env",
        help = "Runtime environment file"
    )

    args = parser.parse_args(argv)

    env_path = _project_path(args.env_file)
    config_path = _project_path(args.config)

    load_environment_file(env_path)
    config = load_a_share_history_refresh_config(
        config_path
    )

    connections = ConnectionRegistry.from_environment(
        required_connection_refs(config)
    )
    context = SourceContext(
        connections = connections,
        run_id = 0,
        artifact_dir=(PROJECT_ROOT / "data" / "artifacts" / "a_share_history" / config.publication.version)
    )
    try:
        publication = run_configured_a_share_history_refresh(
            context,
            config = config,
            allowed_module_prefixes= _allowed_plugin_prefixes()
        )
    finally:
        connections.dispose()

    print(
        "A-share historical market-data publication completed: "
        f"version={config.publication.version}, "
        f"dates={publication.date_count}, "
        f"tickers={publication.ticker_count}, "
        f"output={publication.output_dir}"
    )

if __name__ == "__main__":
    main()