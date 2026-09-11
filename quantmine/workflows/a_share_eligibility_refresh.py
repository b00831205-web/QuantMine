"""Schedular-neutral A-share eligibility refresh from persisted market status"""

from __future__ import annotations

from pathlib import Path
import pandas as pd

from ..plugins.a_share import (
    AStockEligibilityPolicy,
    create_parquet_a_share_market_status_eligibility_builder,
)
from ..plugins.context import SourceContext
from .eligibility import (
    EligibilityPublication,
    EligibilityPublishSpec,
    refresh_cumulative_daily_eligibility,
)

from collections.abc import Iterable

def refresh_a_share_eligibility_from_market_status(
        context: SourceContext,
        *,
        as_of_date: pd.Timestamp | str,
        status_connection_ref: str,
        status_dataset: str,
        status_version: str,
        eligibility_root: Path,
        eligibility_spec: EligibilityPublishSpec,
        status_market: str = "CN",
        policy: AStockEligibilityPolicy | None = None,
        trading_sessions : Iterable[pd.Timestamp | str] | None = None
) -> EligibilityPublication:
    """Build and publish one A-share eligibility snapshot from generic status. """

    if status_market != "CN":
        raise ValueError(
            "A-share eligibility refresh requires status_market='CN'"
        )

    if eligibility_spec.market != "CN":
        raise ValueError(
            "A-share eligibility refresh requires eligibility_spec.market='CN'"
        )
    builder = create_parquet_a_share_market_status_eligibility_builder(
        context,
        connection_ref = status_connection_ref,
        dataset = status_dataset,
        version = status_version,
        market = status_market,
        policy = policy
    )
    return refresh_cumulative_daily_eligibility(
        builder,
        as_of_date = as_of_date,
        root = eligibility_root,
        spec = eligibility_spec,
        trading_sessions=trading_sessions,
    )