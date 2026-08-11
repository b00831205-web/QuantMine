"""Tests for task_1's coverage sourcing.

Replaces the old ``determine_download_start`` tests. That function returned one
global watermark for the whole table, which is precisely the behaviour the
per-ticker planner exists to fix -- see test_download_plan.py.

What still matters here is the fallback path: when the database is unreachable,
task_1 must reconstruct per-ticker coverage from the processed parquet. Reporting
"no coverage" instead would make the planner conclude nothing was ever downloaded
and queue an eleven-year full history for the entire universe.
"""
import numpy as np
import pandas as pd

from pipelines.task_1 import COVERAGE_COLUMNS, coverage_from_parquet


def write_close(processed_dir, frame):
    processed_dir.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(processed_dir / "processed_close.parquet")


def test_coverage_is_per_ticker_not_a_single_watermark(tmp_path):
    """Two tickers with different histories must report different bounds."""
    index = pd.to_datetime(["2026-07-20", "2026-07-21", "2026-07-22"])
    write_close(tmp_path, pd.DataFrame(
        {"OLD": [1.0, 2.0, 3.0], "NEW": [np.nan, np.nan, 9.0]}, index=index
    ))

    coverage = coverage_from_parquet(tmp_path).set_index("ticker")

    assert coverage.loc["OLD", "first_date"] == pd.Timestamp("2026-07-20")
    assert coverage.loc["NEW", "first_date"] == pd.Timestamp("2026-07-22")
    assert coverage.loc["OLD", "last_date"] == coverage.loc["NEW", "last_date"]
    assert coverage.loc["NEW", "observations"] == 1


def test_all_nan_ticker_is_reported_as_absent(tmp_path):
    """A column present but never populated has no coverage to speak of."""
    index = pd.to_datetime(["2026-07-20", "2026-07-21"])
    write_close(tmp_path, pd.DataFrame(
        {"REAL": [1.0, 2.0], "EMPTY": [np.nan, np.nan]}, index=index
    ))

    assert coverage_from_parquet(tmp_path)["ticker"].tolist() == ["REAL"]


def test_missing_parquet_returns_the_empty_shape(tmp_path):
    coverage = coverage_from_parquet(tmp_path)

    assert coverage.empty
    assert list(coverage.columns) == COVERAGE_COLUMNS


def test_interior_gap_does_not_shrink_the_reported_span(tmp_path):
    """first/last bound the span; holes inside are P2's problem, not P1's."""
    index = pd.to_datetime(["2026-07-20", "2026-07-21", "2026-07-22"])
    write_close(tmp_path, pd.DataFrame({"T": [1.0, np.nan, 3.0]}, index=index))

    row = coverage_from_parquet(tmp_path).iloc[0]

    assert row["first_date"] == pd.Timestamp("2026-07-20")
    assert row["last_date"] == pd.Timestamp("2026-07-22")
    assert row["observations"] == 2
