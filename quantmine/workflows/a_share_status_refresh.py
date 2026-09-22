"""Scheduler-neutral A-share raw-snapshot to market-status refresh"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from .a_share_status import AStockDailyStatusNormalizer
from .akshare_a_share_snapshot import AStockRawSnapshot
from .market_status_publication import (
    MarketStatusPublication,
    MarketStatusPublishSpec,
    publish_daily_market_status,
)

def refresh_a_share_market_status(
        snapshot: AStockRawSnapshot,
        normalizer: AStockDailyStatusNoramlizer,
        *,
        as_of_date: pd.Timestamp | str,
        root: Path,
        spec: MarketStatusPublishSpec
) -> MarketStatusPublication:
    """Normalize an immutable A-share raw snapshot and publish market status"""
    date = pd.Timestamp(as_of_date).normalize()

    if spec.market != "CN":
        raise ValueError(
            "A-share market-status refresh requires spec.market='CN"
        )

    for path, label in (
        (snapshot.spot_path, "spot snapshot"),
        (snapshot.suspension_path, "suspension snapshot"),
        (snapshot.manifest_path, "raw snapshot manifest")
    ):
        if not path.is_file():
            raise FileNotFoundError(f"{label} does not exist: {path}")

    raw_manifest = json.loads(
        snapshot.manifest_path.read_text(encoding ="utf-8")
    )
    if raw_manifest.get("as_of_date") != date.date().isoformat():
        raise ValueError(
            "raw snapshot date does not match requested date"
        )

    status = normalizer.normalize(
        as_of_date = date,
        spot = pd.read_parquet(snapshot.spot_path),
        suspension = pd.read_parquet(snapshot.suspension_path),
    )

    return publish_daily_market_status(
        status,
        root = root,
        spec = spec,
    )