"""Unit tests for turnover / transaction costs / daily expansion (hand-computed).

These pin down the cost-model semantics established during development:
1. cost = actual turnover * 2 * cost_per_trade (buy plus sell legs), NOT a flat
   100%-turnover assumption (that assumption once crushed the 1-day holding
   period to -58%/yr after costs)
2. long_short is charged on the sum of the Q1 and Q5 leg turnovers
3. expand_to_daily_returns: the window anchors on the rebalance day, costs are
   charged on the first trading day after each rebalance, and the initial
   position build counts as full turnover
"""
import numpy as np
import pandas as pd
import pytest

from quantmine.back_testing import (
    apply_transcation_cost,
    calculate_turnover,
    expand_to_daily_returns,
    performance_summary,
)


@pytest.fixture
def ticker_history():
    """Two rebalances: Q1 replaces half (0.5), Q5 keeps everything (0.0), other groups fully replaced (1.0)."""
    d1, d2 = pd.Timestamp("2024-01-02"), pd.Timestamp("2024-01-09")
    return [
        {"date": d1, "Q1": {"A", "B"}, "Q2": {"C"}, "Q3": {"D"}, "Q4": {"E"}, "Q5": {"F", "G"}},
        {"date": d2, "Q1": {"B", "X"}, "Q2": {"Y"}, "Q3": {"Z"}, "Q4": {"W"}, "Q5": {"F", "G"}},
    ]


def test_turnover_hand_computed(ticker_history):
    t_q1 = calculate_turnover(ticker_history, "Q1")
    t_q5 = calculate_turnover(ticker_history, "Q5")
    assert np.isnan(t_q1.iloc[0])              # turnover undefined for the first rebalance
    assert t_q1.iloc[1] == pytest.approx(0.5)  # {A,B}->{B,X}: half retained
    assert t_q5.iloc[1] == pytest.approx(0.0)  # fully retained


def test_cost_scales_with_actual_turnover(ticker_history):
    result_df = pd.DataFrame(
        {"Q1": [0.01, 0.01], "Q2": [0.01, 0.01], "Q3": [0.01, 0.01],
         "Q4": [0.01, 0.01], "Q5": [0.01, 0.01], "long_short": [0.0, 0.0]},
        index=[h["date"] for h in ticker_history],
    )
    after = apply_transcation_cost(result_df, ticker_history, cost_per_trade=0.001)
    # Q1 second period: 0.01 - 0.5*2*0.001 = 0.009 ; Q5 fully retained -> zero cost
    assert after["Q1"].iloc[1] == pytest.approx(0.009)
    assert after["Q5"].iloc[1] == pytest.approx(0.01)
    # long_short charged on both legs: 0 - (0.5+0.0)*2*0.001 = -0.001
    assert after["long_short"].iloc[1] == pytest.approx(-0.001)
    # The initial position build counts as full turnover, matching the daily
    # return expansion path.
    assert after["Q1"].iloc[0] == pytest.approx(0.008)


def test_expand_to_daily_returns_window_and_cost():
    dates = pd.date_range("2024-01-01", periods=5, freq="B")
    # A gains 10% every day; B is flat -- unambiguous hand computation
    close = pd.DataFrame(
        {"A": 100 * 1.1 ** np.arange(5), "B": [100.0] * 5},
        index=dates,
    )
    hold_a = {f"Q{i}": {"A"} for i in range(1, 6)}
    hold_b = {f"Q{i}": {"B"} for i in range(1, 6)}
    history = [
        {"date": dates[0], **hold_a},
        {"date": dates[2], **hold_b},   # start of the second window
        {"date": dates[4], **hold_b},   # terminal anchor (last segment is not expanded)
    ]
    daily = expand_to_daily_returns(history, close, cost_per_trade=0.001)

    # window 1 (holding A): days d1, d2; initial build turnover=1 -> 0.002 charged on d1
    assert daily.loc[dates[1], "Q1"] == pytest.approx(0.10 - 0.002)
    assert daily.loc[dates[2], "Q1"] == pytest.approx(0.10)
    # window 2 (holding B): A->B is full turnover -> 0.002 charged on d3, B returns 0
    assert daily.loc[dates[3], "Q1"] == pytest.approx(0.0 - 0.002)
    assert daily.loc[dates[4], "Q1"] == pytest.approx(0.0)
    # every trading day belongs to exactly one window
    assert list(daily.index) == list(dates[1:])
    # identical holdings on both legs -> long_short = Q5 - Q1 = 0
    assert (daily["long_short"].abs() < 1e-12).all()


def test_daily_expansion_with_no_complete_holding_window_is_empty():
    date = pd.Timestamp("2024-01-01")
    history = [
        {
            "date": date,
            **{f"Q{i}": {"A"} for i in range(1, 6)},
        }
    ]
    close = pd.DataFrame({"A": [100.0]}, index=[date])

    result = expand_to_daily_returns(history, close)

    assert result.empty
    assert list(result.columns) == [
        "Q1",
        "Q2",
        "Q3",
        "Q4",
        "Q5",
        "long_short",
    ]


def test_empty_turnover_and_performance_inputs_are_supported():
    turnover = calculate_turnover([], "Q1")
    summary, net_returns = performance_summary(pd.DataFrame(), periods=1)

    assert turnover.empty
    assert summary.empty
    assert net_returns.empty
