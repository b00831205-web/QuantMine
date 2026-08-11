"""End-to-end check of the multi-window staging path introduced with P1.

task_1 now emits one staging file per download job, and jobs cover different
date ranges (a decade-long backfill next to a one-day increment). Two things
must survive that:

1. the sparsity filter must score each file against its own range, or every
   incremental ticker looks ~100% missing over the backfill's index and the
   whole live universe gets dropped;
2. the merge must be cell-level, or the backfill's rows overwrite the
   incremental tickers on the dates they share.

These are exercised together because the failure only appears when both run.
"""
import numpy as np
import pandas as pd

from pipelines.task_2 import drop_sparse_columns, merge_increment


def dates(start, periods):
    return pd.bdate_range(start, periods=periods)


def test_backfill_and_increment_staged_separately_both_survive():
    # Already collected: two tickers with a decade of history.
    history_index = dates("2026-07-01", 20)
    processed = pd.DataFrame(
        {"AAPL": np.arange(20.0), "MSFT": np.arange(100.0, 120.0)},
        index=history_index,
    )

    # Job 1 (increment): the live universe, 2 new days.
    increment = pd.DataFrame(
        {"AAPL": [20.0, 21.0], "MSFT": [120.0, 121.0]},
        index=dates("2026-07-29", 2),
    )
    # Job 2 (backfill): one newly added ticker, the full 20-day span.
    backfill = pd.DataFrame({"NEW": np.arange(200.0, 220.0)}, index=history_index)

    merged = processed
    for staged in (increment, backfill):
        cleaned, dropped = drop_sparse_columns(staged, missing_threshold=0.3)
        assert dropped == [], "each file is scored against its own range"
        merged = merge_increment(cleaned, merged)

    # The live universe kept every observation it had...
    assert merged["AAPL"].loc[history_index].tolist() == list(np.arange(20.0))
    assert merged["MSFT"].loc[history_index].tolist() == list(np.arange(100.0, 120.0))
    # ...gained the new days...
    assert merged["AAPL"].iloc[-1] == 21.0
    # ...and the newcomer arrived with its full history, not a single day.
    assert merged["NEW"].notna().sum() == 20


def test_pooling_the_files_first_is_what_destroys_the_universe():
    """Guards the reason the per-file design exists.

    Concatenating the jobs before filtering makes the incremental tickers
    ~100% NaN over the backfill's index, and the sparsity filter then drops
    them. This asserts the broken behaviour so the rationale stays visible if
    someone later 'simplifies' task_2 back into a single pooled read.
    """
    increment = pd.DataFrame(
        {"AAPL": [20.0, 21.0], "MSFT": [120.0, 121.0]},
        index=dates("2026-07-29", 2),
    )
    backfill = pd.DataFrame({"NEW": np.arange(200.0, 220.0)}, index=dates("2026-07-01", 20))

    pooled = pd.concat([increment, backfill], axis=1, sort=True)
    _, dropped = drop_sparse_columns(pooled, missing_threshold=0.3)

    assert "AAPL" in dropped and "MSFT" in dropped   # the live universe, gone
    assert "NEW" not in dropped


def test_two_backfills_over_the_same_dates_do_not_overwrite_each_other():
    index = dates("2026-07-01", 10)
    merged = None
    for ticker, base in (("A", 0.0), ("B", 50.0), ("C", 90.0)):
        staged = pd.DataFrame({ticker: np.arange(base, base + 10)}, index=index)
        merged = merge_increment(staged, merged)

    assert sorted(merged.columns) == ["A", "B", "C"]
    for ticker in ("A", "B", "C"):
        assert merged[ticker].notna().sum() == 10
