"""Contract tests for daily market-bar and latest-snapshot preparation."""

import numpy as np
import pandas as pd

from quantmine.storage.market import build_latest_snapshot, build_market_bars


def test_build_market_bars_merges_close_volume_and_builds_latest_snapshot():
    dates = pd.to_datetime(["2026-07-20", "2026-07-21"])
    close = pd.DataFrame(
        {
            "AAA": [10.0, 11.0],
            "BBB": [np.nan, 21.0],
        },
        index=dates,
    )
    volume = pd.DataFrame(
        {
            "AAA": [100, 110],
            "BBB": [np.nan, 210],
        },
        index=dates,
    )

    bars = build_market_bars(close, volume, source_run_id=42)

    # shares/market_cap 未传时列仍然存在（填 NA），下游 snapshot 与 upsert 依赖这一保证
    assert list(bars.columns) == [
        "trade_date", "ticker", "close", "volume",
        "shares_outstanding", "market_cap", "source_run_id",
    ]
    assert bars["shares_outstanding"].isna().all()
    assert bars["market_cap"].isna().all()
    # BBB on 2026-07-20 has neither close nor volume, so it is excluded.
    assert len(bars) == 3
    assert bars.loc[
        (bars["trade_date"] == dates[1]) & (bars["ticker"] == "AAA"),
        "volume",
    ].item() == 110
    assert bars["source_run_id"].eq(42).all()

    latest = build_latest_snapshot(bars)

    assert set(latest["ticker"]) == {"AAA", "BBB"}
    assert latest["trade_date"].eq(dates[1]).all()
    assert latest.loc[latest["ticker"] == "BBB", "close"].item() == 21.0
