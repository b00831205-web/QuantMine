"""Unit tests for quantile_backtest (synthetic data, hand-computed expectations).

These tests preserve the old-vs-new architecture equivalence verification
(element-wise diff = 0 against the legacy composite-column implementation) as a
permanent regression suite: the correctness evidence survives even though the
legacy implementation has been deleted.

Bugs from the development history that these tests pin down:
1. curr_date must be read inside the rebalance loop (it once sat outside the
   loop referencing an undefined index)
2. results must be stored inside the period loop (an indentation bug once kept
   only the last period per factor)
3. available_tickers must intersect in factor-column order (set iteration
   order made tied-rank bucket boundaries drift between runs)
4. ticker_history structure: {'date':..., 'Q1': set, ..., 'Q5': set}
"""
import numpy as np
import pandas as pd
import pandas.testing as pdt
import pytest

from quantmine.back_testing import quantile_backtest
from quantmine.datareader import StaticUniverse
from quantmine.weighting import mcap_weight

N_DAYS = 12
TICKERS = [f"T{i}" for i in range(10)]


@pytest.fixture
def dates():
    return pd.date_range("2024-01-01", periods=N_DAYS, freq="B")


@pytest.fixture
def synthetic_factors(dates):
    """Factor value equals the ticker ordinal: T0=0, T1=1, ... ranking is fully determined, no ties."""
    values = {t: float(i) for i, t in enumerate(TICKERS)}
    df = pd.DataFrame({t: [v] * N_DAYS for t, v in values.items()}, index=dates)
    return {"toy": df}


@pytest.fixture
def synthetic_forward_returns(dates):
    """Forward return equals ordinal/100: group means are hand-computable."""
    df = pd.DataFrame({t: [i / 100] * N_DAYS for i, t in enumerate(TICKERS)},
                      index=dates)
    return {1: df, 5: df}


def test_quantile_means_match_hand_computation(synthetic_factors, synthetic_forward_returns):
    result, _ = quantile_backtest(None, synthetic_factors, ["toy"], synthetic_forward_returns)
    df = result[("toy", 1)]
    # ascending split into 5 groups of 2: Q1={T0,T1} -> mean 0.005, Q5={T8,T9} -> mean 0.085
    assert df["Q1"].iloc[0] == pytest.approx(0.005)
    assert df["Q3"].iloc[0] == pytest.approx(0.045)
    assert df["Q5"].iloc[0] == pytest.approx(0.085)
    assert df["long_short"].iloc[0] == pytest.approx(0.08)


def test_all_factor_period_combinations_present(synthetic_factors, synthetic_forward_returns):
    """Historical indentation bug: only the last period per factor was kept."""
    result, history = quantile_backtest(None, synthetic_factors, ["toy"], synthetic_forward_returns)
    assert set(result.keys()) == {("toy", 1), ("toy", 5)}
    assert set(history.keys()) == {("toy", 1), ("toy", 5)}


def test_selected_factor_periods_restricts_backtest(
    synthetic_factors,
    synthetic_forward_returns,
):
    """A selector-approved pair must not trigger other holding periods."""
    result, history = quantile_backtest(
        constituents=None,
        factors=synthetic_factors,
        significant_factor_list=["toy"],
        forward_returns=synthetic_forward_returns,
        selected_factor_periods=[("toy", 5)],
    )

    assert set(result) == {("toy", 5)}
    assert set(history) == {("toy", 5)}


def test_rebalance_dates_follow_period_stride(synthetic_factors, synthetic_forward_returns, dates):
    result, _ = quantile_backtest(None, synthetic_factors, ["toy"], synthetic_forward_returns)
    assert len(result[("toy", 1)]) == N_DAYS
    assert list(result[("toy", 5)].index) == list(dates[::5])


def test_ticker_history_structure(synthetic_factors, synthetic_forward_returns):
    _, history = quantile_backtest(None, synthetic_factors, ["toy"], synthetic_forward_returns)
    snap = history[("toy", 1)][0]
    assert set(snap.keys()) == {"date", "Q1", "Q2", "Q3", "Q4", "Q5"}
    assert snap["Q1"] == {"T0", "T1"}
    assert snap["Q5"] == {"T8", "T9"}


def test_constituents_filtering_excludes_non_members(synthetic_factors, synthetic_forward_returns):
    """Tickers outside the universe must not enter any bucket (point-in-time filtering)."""
    universe = StaticUniverse(TICKERS[:5])  # only T0-T4 allowed
    _, history = quantile_backtest(universe, synthetic_factors, ["toy"], synthetic_forward_returns)
    snap = history[("toy", 1)][0]
    members = set().union(*(snap[f"Q{i}"] for i in range(1, 6)))
    assert members == set(TICKERS[:5])


def test_membership_dataframe_is_auto_wrapped(synthetic_factors, synthetic_forward_returns):
    """A raw (ticker, start_date, end_date) table also works (auto-wrapped)."""
    table = pd.DataFrame({
        "ticker": TICKERS[:5],
        "start_date": ["2020-01-01"] * 5,
        "end_date": [None] * 5,
    })
    _, history = quantile_backtest(table, synthetic_factors, ["toy"], synthetic_forward_returns)
    snap = history[("toy", 1)][0]
    members = set().union(*(snap[f"Q{i}"] for i in range(1, 6)))
    assert members == set(TICKERS[:5])


def test_all_nan_cross_section_skipped(synthetic_factors, synthetic_forward_returns, dates):
    factors = {"toy": synthetic_factors["toy"].copy()}
    factors["toy"].loc[dates[0]] = np.nan
    result, _ = quantile_backtest(None, factors, ["toy"], synthetic_forward_returns)
    assert dates[0] not in result[("toy", 1)].index


def test_date_missing_from_forward_returns_skipped(synthetic_factors, synthetic_forward_returns, dates):
    fwd = {1: synthetic_forward_returns[1].drop(index=dates[0])}
    result, _ = quantile_backtest(None, synthetic_factors, ["toy"], fwd)
    assert dates[0] not in result[("toy", 1)].index


def test_deterministic_across_runs(synthetic_factors, synthetic_forward_returns):
    """Historical set-iteration-order bug: results drifted between runs."""
    universe = StaticUniverse(TICKERS)
    r1, h1 = quantile_backtest(universe, synthetic_factors, ["toy"], synthetic_forward_returns)
    r2, h2 = quantile_backtest(universe, synthetic_factors, ["toy"], synthetic_forward_returns)
    for key in r1:
        pdt.assert_frame_equal(r1[key], r2[key])
        assert h1[key] == h2[key]


def test_nan_factor_values_and_missing_return_columns_are_excluded(dates):
    factor = pd.DataFrame(
        {
            "A": [1.0] * len(dates),
            "B": [2.0] * len(dates),
            "C": [3.0] * len(dates),
            "D": [4.0] * len(dates),
            "E": [5.0] * len(dates),
            "NAN": [np.nan] * len(dates),
            "NO_RETURN": [6.0] * len(dates),
        },
        index=dates,
    )
    forward = pd.DataFrame(
        {ticker: [0.01] * len(dates) for ticker in ["A", "B", "C", "D", "E"]},
        index=dates,
    )

    _, history = quantile_backtest(
        None,
        {"toy": factor},
        ["toy"],
        {1: forward},
    )

    members = set().union(
        *(history[("toy", 1)][0][f"Q{i}"] for i in range(1, 6))
    )
    assert members == {"A", "B", "C", "D", "E"}


def test_mcap_weighting_uses_cap_proportional_weights(
    synthetic_factors, synthetic_forward_returns, dates,
):
    """mcap 加权: 组收益按调仓日市值加权, 明显区别于等权。

    Q1={T0,T1} 收益 {0.00, 0.01}; 给市值 T0=1, T1=3
      → 加权 = (0.00*1 + 0.01*3)/4 = 0.0075  (等权是 0.005)
    Q5={T8,T9} 收益 {0.08, 0.09}; 给市值 T8=1, T9=4
      → 加权 = (0.08*1 + 0.09*4)/5 = 0.088   (等权是 0.085)
    """
    caps = {t: 1.0 for t in TICKERS}
    caps["T0"], caps["T1"] = 1.0, 3.0
    caps["T8"], caps["T9"] = 1.0, 4.0
    market_cap = pd.DataFrame(
        {t: [caps[t]] * N_DAYS for t in TICKERS}, index=dates,
    )

    result, _ = quantile_backtest(
        None, synthetic_factors, ["toy"], synthetic_forward_returns,
        weight_fn=mcap_weight, market_cap=market_cap,
    )
    df = result[("toy", 1)]
    assert df["Q1"].iloc[0] == pytest.approx(0.0075)
    assert df["Q5"].iloc[0] == pytest.approx(0.088)
    assert df["long_short"].iloc[0] == pytest.approx(0.088 - 0.0075)
    # 与等权明显不同, 证明确实走了市值加权
    assert df["Q1"].iloc[0] != pytest.approx(0.005)


def test_cross_section_smaller_than_group_count_is_skipped(dates):
    factor = pd.DataFrame(
        {"A": [1.0] * len(dates), "B": [2.0] * len(dates)},
        index=dates,
    )
    forward = pd.DataFrame(
        {"A": [0.01] * len(dates), "B": [0.02] * len(dates)},
        index=dates,
    )

    result, history = quantile_backtest(
        None,
        {"toy": factor},
        ["toy"],
        {1: forward},
        part=5,
    )

    assert result == {}
    assert history == {}
