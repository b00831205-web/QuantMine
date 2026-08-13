"""Holdings carry the weights the backtest used, not an assumed 1/n."""

import pandas as pd

from quantmine.storage.backtest import build_ticker_history_rows


def test_weights_survive_into_the_long_frame():
    """Under mcap weighting the member list alone does not describe the portfolio."""
    history = [
        {
            "date": pd.Timestamp("2026-01-05"),
            "Q1": {"AAA": 0.7, "BBB": 0.3},
        }
    ]

    rows = build_ticker_history_rows(history)

    assert list(rows.columns) == ["trade_date", "quantile_rank", "ticker", "weight"]
    assert rows.set_index("ticker")["weight"].to_dict() == {"AAA": 0.7, "BBB": 0.3}


def test_members_are_sorted_for_deterministic_parquet():
    history = [{"date": pd.Timestamp("2026-01-05"), "Q2": {"ZZZ": 0.5, "AAA": 0.5}}]

    rows = build_ticker_history_rows(history)

    assert rows["ticker"].tolist() == ["AAA", "ZZZ"]


def test_legacy_set_snapshots_still_load_with_null_weights():
    """Runs recorded before weights were kept were equal-weighted.

    Writing null rather than inventing a number lets the reader apply the
    equal-weight fallback knowingly, instead of a stored value that was never
    actually computed.
    """
    history = [{"date": pd.Timestamp("2026-01-05"), "Q1": {"AAA", "BBB"}}]

    rows = build_ticker_history_rows(history)

    assert rows["ticker"].tolist() == ["AAA", "BBB"]
    assert rows["weight"].isna().all()
