"""Unit tests for folding a download increment into the cumulative frame.

The regression that motivated these: the merge used to ``concat`` then keep the
last row per date. That is correct only while every increment covers dates the
cumulative frame has never seen. As soon as a backfill carries a few tickers
over historical dates, the padded-with-NaN new row wins and every other ticker
on those dates is wiped -- silently, since the file still parses and still has
the right shape.
"""
import numpy as np
import pandas as pd

from pipelines.task_2 import drop_sparse_columns, merge_increment

DATES = pd.to_datetime(["2026-08-03", "2026-08-04", "2026-08-05"])


def test_forward_increment_appends():
    existing = pd.DataFrame({"AAPL": [1.0, 2.0]}, index=DATES[:2])
    new_data = pd.DataFrame({"AAPL": [3.0]}, index=DATES[2:])

    merged = merge_increment(new_data, existing)

    assert list(merged.index) == list(DATES)
    assert merged["AAPL"].tolist() == [1.0, 2.0, 3.0]


def test_backfill_of_one_ticker_preserves_the_others_on_the_same_dates():
    """The bug: MSFT must survive a backfill that only carries NEW1."""
    existing = pd.DataFrame(
        {"AAPL": [1.0, 2.0, 3.0], "MSFT": [10.0, 20.0, 30.0]}, index=DATES
    )
    backfill = pd.DataFrame({"NEW1": [7.0, 8.0, 9.0]}, index=DATES)

    merged = merge_increment(backfill, existing)

    assert merged["MSFT"].tolist() == [10.0, 20.0, 30.0]
    assert merged["AAPL"].tolist() == [1.0, 2.0, 3.0]
    assert merged["NEW1"].tolist() == [7.0, 8.0, 9.0]


def test_rerun_overwrites_the_same_cells():
    """Re-running a day must correct its values, not duplicate the rows."""
    existing = pd.DataFrame({"AAPL": [1.0, 2.0]}, index=DATES[:2])
    corrected = pd.DataFrame({"AAPL": [99.0]}, index=DATES[1:2])

    merged = merge_increment(corrected, existing)

    assert len(merged) == 2
    assert merged["AAPL"].tolist() == [1.0, 99.0]


def test_nan_in_the_increment_does_not_erase_an_existing_value():
    """A ticker Yahoo failed to return must not blank out what we already have."""
    existing = pd.DataFrame({"AAPL": [1.0, 2.0]}, index=DATES[:2])
    gappy = pd.DataFrame({"AAPL": [np.nan, np.nan]}, index=DATES[:2])

    merged = merge_increment(gappy, existing)

    assert merged["AAPL"].tolist() == [1.0, 2.0]


def test_first_run_returns_the_increment_sorted():
    new_data = pd.DataFrame({"AAPL": [2.0, 1.0]}, index=DATES[[1, 0]])

    merged = merge_increment(new_data, None)

    assert list(merged.index) == list(DATES[:2])


def test_sparse_columns_are_dropped_and_reported():
    new_data = pd.DataFrame(
        {"GOOD": [1.0, 2.0, 3.0], "SPARSE": [1.0, np.nan, np.nan]}, index=DATES
    )

    cleaned, dropped = drop_sparse_columns(new_data, missing_threshold=0.3)

    assert dropped == ["SPARSE"]
    assert cleaned.columns.tolist() == ["GOOD"]
