"""Tests for multi-session position-based backtesting."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from quantmine.plugins.context import SourceContext
from quantmine.plugins.market_rules import (
    create_a_stock_market_rules,
    create_unrestricted_market_rules,
)
from quantmine.storage.connections import ConnectionRegistry
from quantmine.workflows.portfolio_execution import PortfolioState
from quantmine.workflows.position_backtest import run_position_backtest


def _context(tmp_path: Path) -> SourceContext:
    return SourceContext(
        connections=ConnectionRegistry({}),
        run_id=701,
        artifact_dir=tmp_path / "artifacts",
    )


def _close() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "AAA": [10.0, 11.0, 12.0],
            "BBB": [20.0, 20.0, 20.0],
        },
        index=pd.DatetimeIndex(
            ["2026-09-17", "2026-09-18", "2026-09-21"],
            name="date",
        ),
    )


class OpenMarketStateProvider:
    def status_on(
        self,
        trade_date: pd.Timestamp,
        ticker: str,
    ) -> dict[str, bool]:
        del trade_date, ticker
        return {
            "is_suspended": False,
            "is_limit_up": False,
            "is_limit_down": False,
        }


def test_position_backtest_marks_positions_to_market_between_rebalances(
    tmp_path: Path,
) -> None:
    close = _close()
    weights = pd.DataFrame(
        {"AAA": [0.5], "BBB": [0.0]},
        index=close.index[:1],
    )

    result = run_position_backtest(
        close=close,
        target_weights=weights,
        initial_cash=1_000.0,
        component=create_unrestricted_market_rules(),
        context=_context(tmp_path),
    )

    assert result.equity_curve.tolist() == [1_000.0, 1_050.0, 1_100.0]
    assert pd.isna(result.daily_returns.iloc[0])
    assert result.daily_returns.iloc[1] == pytest.approx(0.05)
    assert result.daily_returns.iloc[2] == pytest.approx(1_100 / 1_050 - 1)
    assert result.cash_curve.tolist() == [500.0, 500.0, 500.0]
    assert result.positions["AAA"].tolist() == [50.0, 50.0, 50.0]
    assert result.sellable_positions["AAA"].tolist() == [0.0, 50.0, 50.0]
    assert result.requested_shares["AAA"].tolist() == [50.0]
    assert result.executed_shares["AAA"].tolist() == [50.0]
    assert result.fees["AAA"].tolist() == [0.0]
    assert result.final_state.positions["AAA"] == 50.0


def test_position_backtest_unlocks_a_stock_position_next_session(
    tmp_path: Path,
) -> None:
    close = pd.DataFrame(
        {"AAA": [10.0, 10.0], "BBB": [20.0, 20.0]},
        index=pd.DatetimeIndex(["2026-09-17", "2026-09-18"]),
    )
    weights = pd.DataFrame(
        {"AAA": [0.5, 0.0], "BBB": [0.0, 0.0]},
        index=close.index,
    )

    result = run_position_backtest(
        close=close,
        target_weights=weights,
        initial_cash=10_000.0,
        component=create_a_stock_market_rules(market="CN"),
        context=_context(tmp_path),
        market_state_provider=OpenMarketStateProvider(),
    )

    assert result.executed_shares["AAA"].tolist() == [500.0, -500.0]
    assert result.positions["AAA"].tolist() == [500.0, 0.0]
    assert result.sellable_positions["AAA"].tolist() == [0.0, 0.0]
    assert result.fees["AAA"].tolist() == pytest.approx([5.05, 7.55])
    assert result.cash_curve.tolist() == pytest.approx([4_994.95, 9_987.4])
    assert result.equity_curve.tolist() == pytest.approx(
        [9_994.95, 9_987.4]
    )


def test_position_backtest_accumulates_fees_across_rebalances(
    tmp_path: Path,
) -> None:
    close = _close()
    weights = pd.DataFrame(
        {
            "AAA": [0.5, 0.0],
            "BBB": [0.0, 0.0],
        },
        index=close.index[[0, 2]],
    )

    result = run_position_backtest(
        close=close,
        target_weights=weights,
        initial_cash=1_000.0,
        component=create_unrestricted_market_rules(
            commission_rate=0.01
        ),
        context=_context(tmp_path),
    )

    assert result.fees.sum().sum() == pytest.approx(11.0)
    assert result.final_state.positions["AAA"] == pytest.approx(0.0)
    assert result.final_state.cash == pytest.approx(1_089.0)
    assert result.equity_curve.iloc[-1] == pytest.approx(1_089.0)


def test_position_backtest_accepts_existing_initial_state(
    tmp_path: Path,
) -> None:
    close = _close().iloc[:1]
    empty_weights = pd.DataFrame(
        columns=close.columns,
        index=pd.DatetimeIndex([], name="date"),
        dtype=float,
    )
    index = close.columns.copy()
    state = PortfolioState(
        positions=pd.Series([100.0, 0.0], index=index),
        sellable_positions=pd.Series([100.0, 0.0], index=index),
        cash=500.0,
    )

    result = run_position_backtest(
        close=close,
        target_weights=empty_weights,
        initial_cash=0.0,
        initial_state=state,
        component=create_unrestricted_market_rules(),
        context=_context(tmp_path),
    )

    assert result.equity_curve.tolist() == [1_500.0]
    assert result.final_state is state
    assert result.requested_shares.empty


def test_position_backtest_values_missing_price_and_blocks_trade(
    tmp_path: Path,
) -> None:
    close = _close()
    close.loc[close.index[1], "AAA"] = float("nan")
    weights = pd.DataFrame(
        {
            "AAA": [0.5, 0.0, 0.0],
            "BBB": [0.0, 0.0, 0.0],
        },
        index=close.index,
    )

    result = run_position_backtest(
        close=close,
        target_weights=weights,
        initial_cash=1_000.0,
        component=create_unrestricted_market_rules(),
        context=_context(tmp_path),
    )

    assert result.valuation_prices["AAA"].tolist() == [10.0, 10.0, 12.0]
    assert result.tradable["AAA"].tolist() == [True, False, True]
    assert result.price_sources["AAA"].tolist() == [
        "observed",
        "last_observation",
        "observed",
    ]
    assert result.requested_shares["AAA"].tolist() == [50.0, -50.0, -50.0]
    assert result.executed_shares["AAA"].tolist() == [50.0, 0.0, -50.0]
    assert result.reasons["AAA"].tolist() == [
        "accepted",
        "price_unavailable",
        "accepted",
    ]
    assert result.positions["AAA"].tolist() == [50.0, 50.0, 0.0]
    assert result.equity_curve.tolist() == [1_000.0, 1_000.0, 1_100.0]


def test_position_backtest_blocks_prelisting_buy_until_price_exists(
    tmp_path: Path,
) -> None:
    close = _close()
    close.loc[close.index[:2], "AAA"] = float("nan")
    weights = pd.DataFrame(
        {
            "AAA": [0.5, 0.5, 0.5],
            "BBB": [0.0, 0.0, 0.0],
        },
        index=close.index,
    )

    result = run_position_backtest(
        close=close,
        target_weights=weights,
        initial_cash=1_000.0,
        component=create_unrestricted_market_rules(),
        context=_context(tmp_path),
    )

    assert result.valuation_prices["AAA"].tolist() == [1.0, 1.0, 12.0]
    assert result.tradable["AAA"].tolist() == [False, False, True]
    assert result.price_sources["AAA"].tolist() == [
        "unavailable_flat",
        "unavailable_flat",
        "observed",
    ]
    assert result.executed_shares["AAA"].tolist() == [0.0, 0.0, 1000 / 24]
    assert result.reasons["AAA"].tolist() == [
        "price_unavailable",
        "price_unavailable",
        "accepted",
    ]
    assert result.final_state.positions["AAA"] == pytest.approx(1000 / 24)


def test_position_backtest_rejects_unpriced_initial_holding(
    tmp_path: Path,
) -> None:
    close = _close().iloc[:1].copy()
    close.loc[close.index[0], "AAA"] = float("nan")
    state = PortfolioState(
        positions=pd.Series([100.0, 0.0], index=close.columns),
        sellable_positions=pd.Series([100.0, 0.0], index=close.columns),
        cash=500.0,
    )

    with pytest.raises(ValueError, match="held positions.*AAA"):
        run_position_backtest(
            close=close,
            target_weights=pd.DataFrame(
                columns=close.columns,
                index=pd.DatetimeIndex([]),
                dtype=float,
            ),
            initial_cash=0.0,
            initial_state=state,
            component=create_unrestricted_market_rules(),
            context=_context(tmp_path),
        )


def test_position_backtest_rejects_unknown_rebalance_date(
    tmp_path: Path,
) -> None:
    close = _close()
    weights = pd.DataFrame(
        {"AAA": [0.5], "BBB": [0.0]},
        index=pd.DatetimeIndex(["2026-09-22"]),
    )

    with pytest.raises(ValueError, match="dates unavailable"):
        run_position_backtest(
            close=close,
            target_weights=weights,
            initial_cash=1_000.0,
            component=create_unrestricted_market_rules(),
            context=_context(tmp_path),
        )


def test_position_backtest_rejects_unsorted_target_weights(
    tmp_path: Path,
) -> None:
    close = _close()
    weights = pd.DataFrame(
        {
            "AAA": [0.5, 0.0],
            "BBB": [0.0, 0.0],
        },
        index=close.index[[2, 0]],
    )

    with pytest.raises(ValueError, match="must be sorted"):
        run_position_backtest(
            close=close,
            target_weights=weights,
            initial_cash=1_000.0,
            component=create_unrestricted_market_rules(),
            context=_context(tmp_path),
        )
