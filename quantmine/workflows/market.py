"""Daily cleaned-market-data persistence workflow."""

import pandas as pd
from sqlalchemy.engine import Engine

from ..storage.market import (
    build_latest_snapshot,
    build_market_bars,
    upsert_latest_snapshot,
    upsert_market_bars,
)


def save_daily_market_data(
    engine: Engine,
    close: pd.DataFrame,
    volume: pd.DataFrame,
    source_run_id: int,
) -> dict[str, int]:
    """Build, persist, and summarize one cleaned market-data load."""
    bars = build_market_bars(close, volume, source_run_id)
    latest = build_latest_snapshot(bars)
    return {
        "bars_written": upsert_market_bars(engine, bars),
        "snapshots_written": upsert_latest_snapshot(engine, latest),
    }
