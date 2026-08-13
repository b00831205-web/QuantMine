"""The holdings endpoint reports stored weights, falling back only when absent."""

import pandas as pd

from app.api.v1.rebalances.holdings import fetch_holdings


def _write(tmp_path, frame):
    path = tmp_path / "ticker_history.parquet"
    frame.to_parquet(path)
    return str(path)


def test_stored_weights_are_returned_as_they_were_computed(tmp_path):
    """A market-cap-weighted run must not be reported as equal-weighted.

    The returns shown beside these holdings were produced by these weights;
    deriving 1/n instead would describe a portfolio that was never held.
    """
    path = _write(
        tmp_path,
        pd.DataFrame(
            {
                "trade_date": ["2026-01-05"] * 2,
                "quantile_rank": [1, 1],
                "ticker": ["AAA", "BBB"],
                "weight": [0.75, 0.25],
            }
        ),
    )

    holdings = fetch_holdings(path, "2026-01-05", 1)

    assert holdings == [
        {"symbol": "AAA", "weight": 0.75, "quantile": "Q1"},
        {"symbol": "BBB", "weight": 0.25, "quantile": "Q1"},
    ]


def test_artifacts_without_a_weight_column_fall_back_to_equal(tmp_path):
    """Older runs predate weight persistence and were equal-weighted."""
    path = _write(
        tmp_path,
        pd.DataFrame(
            {
                "trade_date": ["2026-01-05"] * 4,
                "quantile_rank": [1] * 4,
                "ticker": ["AAA", "BBB", "CCC", "DDD"],
            }
        ),
    )

    holdings = fetch_holdings(path, "2026-01-05", 1)

    assert [h["weight"] for h in holdings] == [0.25] * 4


def test_a_null_inside_a_weighted_set_is_no_position(tmp_path):
    """The scheme found no market cap for that name, so nothing was held.

    The backtest drops NaN weights when computing the group return, so filling
    1/n here would both invent a position and push the column over 100% -- the
    remaining weights already sum to one on their own.
    """
    path = _write(
        tmp_path,
        pd.DataFrame(
            {
                "trade_date": ["2026-01-05"] * 3,
                "quantile_rank": [1, 1, 1],
                "ticker": ["AAA", "BBB", "CCC"],
                "weight": [0.6, 0.4, None],
            }
        ),
    )

    holdings = fetch_holdings(path, "2026-01-05", 1)

    assert [h["weight"] for h in holdings] == [0.6, 0.4, 0.0]
    assert sum(h["weight"] for h in holdings) == 1.0


def test_long_short_rank_is_labelled_ls(tmp_path):
    path = _write(
        tmp_path,
        pd.DataFrame(
            {
                "trade_date": ["2026-01-05"],
                "quantile_rank": [0],
                "ticker": ["AAA"],
                "weight": [1.0],
            }
        ),
    )

    assert fetch_holdings(path, "2026-01-05", 0)[0]["quantile"] == "LS"
