"""Contract tests for Carhart attribution persistence helpers."""

import pandas as pd
from sqlalchemy import create_engine, text

from quantmine.storage.attribution import load_long_short_returns


def _engine_with_long_short(rows: list[dict]):
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE backtest_results (
                    run_id INTEGER NOT NULL,
                    variant_name TEXT NOT NULL,
                    backtest_id TEXT NOT NULL,
                    test_id TEXT NOT NULL,
                    factor_name TEXT NOT NULL,
                    period INTEGER NOT NULL,
                    quantile_rank INTEGER NOT NULL,
                    trade_date DATE NOT NULL,
                    return_value FLOAT
                )
                """
            )
        )
        connection.execute(
            text(
                "INSERT INTO backtest_results (run_id, variant_name, backtest_id, "
                "test_id, factor_name, period, quantile_rank, trade_date, "
                "return_value) VALUES (:run_id, :variant_name, :backtest_id, "
                ":test_id, :factor_name, :period, :quantile_rank, :trade_date, "
                ":return_value)"
            ),
            rows,
        )
    return engine


def _row(backtest_id: str, trade_date: str, return_value: float, **overrides):
    row = {
        "run_id": 1, "variant_name": "orthogonalized", "backtest_id": backtest_id,
        "test_id": "newey_orthogonalized", "factor_name": "TwentyDayAvgVol",
        "period": 5, "quantile_rank": 0, "trade_date": trade_date,
        "return_value": return_value,
    }
    row.update(overrides)
    return row


def test_two_jobs_sharing_a_variant_keep_separate_series():
    """Equal- and market-cap-weighted jobs are the same variant over the same
    factor and period, so their long-short returns land on identical dates.
    Keyed without the backtest id they collapse into one dict and the later row
    overwrites the earlier one -- the regression then runs on a series that is
    neither portfolio."""
    engine = _engine_with_long_short([
        _row("orthogonalized_quintile", "2026-01-02", 0.010),
        _row("orthogonalized_quintile", "2026-01-05", 0.020),
        _row("mcap_quintile", "2026-01-02", 0.003),
        _row("mcap_quintile", "2026-01-05", 0.004),
    ])

    groups = load_long_short_returns(engine, 1)

    assert len(groups) == 2
    equal = groups[(
        "orthogonalized", "orthogonalized_quintile", "TwentyDayAvgVol", 5,
        "newey_orthogonalized",
    )]
    mcap = groups[(
        "orthogonalized", "mcap_quintile", "TwentyDayAvgVol", 5,
        "newey_orthogonalized",
    )]
    assert equal.tolist() == [0.010, 0.020]
    assert mcap.tolist() == [0.003, 0.004]


def test_only_long_short_rows_are_loaded():
    """Quantile rows share every other key field; pulling them in would turn one
    portfolio's series into a mixture of its own buckets."""
    engine = _engine_with_long_short([
        _row("mcap_quintile", "2026-01-02", 0.003),
        _row("mcap_quintile", "2026-01-02", 0.500, quantile_rank=1),
    ])

    groups = load_long_short_returns(engine, 1)

    assert len(groups) == 1
    series = next(iter(groups.values()))
    assert series.tolist() == [0.003]


def test_test_id_filter_narrows_to_one_selection_test():
    engine = _engine_with_long_short([
        _row("mcap_quintile", "2026-01-02", 0.003),
        _row("raw_quintile", "2026-01-02", 0.007,
             variant_name="raw", test_id="newey_raw"),
    ])

    groups = load_long_short_returns(engine, 1, test_id="newey_raw")

    assert list(groups) == [
        ("raw", "raw_quintile", "TwentyDayAvgVol", 5, "newey_raw"),
    ]


def test_returns_are_sorted_by_date_regardless_of_row_order():
    engine = _engine_with_long_short([
        _row("mcap_quintile", "2026-01-05", 0.004),
        _row("mcap_quintile", "2026-01-02", 0.003),
    ])

    series = next(iter(load_long_short_returns(engine, 1).values()))

    assert series.index.tolist() == sorted(series.index.tolist())
    assert series.tolist() == [0.003, 0.004]
    assert isinstance(series, pd.Series)
