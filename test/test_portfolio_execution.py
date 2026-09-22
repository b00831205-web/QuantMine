"""Tests for single-session position and cash transitions."""

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
from quantmine.workflows.portfolio_execution import (
    PortfolioState,
    execute_target_weights,
)


def _series(values: list[float]) -> pd.Series:
    return pd.Series(values, index=pd.Index(["AAA", "BBB"], name="ticker"))


def _context(tmp_path: Path) -> SourceContext:
    return SourceContext(
        connections=ConnectionRegistry({}),
        run_id=701,
        artifact_dir=tmp_path / "artifacts",
    )


class StubMarketStateProvider:
    def __init__(self, states: dict[str, dict[str, bool]]) -> None:
        self.states = states

    def status_on(
        self,
        trade_date: pd.Timestamp,
        ticker: str,
    ) -> dict[str, bool]:
        del trade_date
        return self.states[ticker]


def _open_market_provider(**overrides: bool) -> StubMarketStateProvider:
    default = {
        "is_suspended": False,
        "is_limit_up": False,
        "is_limit_down": False,
    }
    return StubMarketStateProvider(
        {
            ticker: {**default, **overrides}
            for ticker in ("AAA", "BBB")
        }
    )


def test_portfolio_state_starts_next_session_with_positions_sellable() -> None:
    state = PortfolioState(
        positions=_series([500.0, 200.0]),
        sellable_positions=_series([0.0, 100.0]),
        cash=1_000.0,
    )

    next_session = state.start_next_session()

    assert next_session.positions.tolist() == [500.0, 200.0]
    assert next_session.sellable_positions.tolist() == [500.0, 200.0]
    assert next_session.cash == 1_000.0
    assert next_session.positions is not state.positions
    assert next_session.sellable_positions is not state.positions


def test_portfolio_state_rejects_invalid_balances() -> None:
    with pytest.raises(ValueError, match="positions must be non-negative"):
        PortfolioState(
            positions=_series([-1.0, 0.0]),
            sellable_positions=_series([0.0, 0.0]),
            cash=0.0,
        )

    with pytest.raises(ValueError, match="must not exceed positions"):
        PortfolioState(
            positions=_series([100.0, 0.0]),
            sellable_positions=_series([101.0, 0.0]),
            cash=0.0,
        )

    with pytest.raises(ValueError, match="cash must be non-negative"):
        PortfolioState(
            positions=_series([0.0, 0.0]),
            sellable_positions=_series([0.0, 0.0]),
            cash=-1.0,
        )


def test_unrestricted_rebalance_preserves_equity_without_fees(
    tmp_path: Path,
) -> None:
    result = execute_target_weights(
        component=create_unrestricted_market_rules(),
        context=_context(tmp_path),
        trade_date=pd.Timestamp("2026-09-18"),
        target_weights=_series([0.5, 0.25]),
        prices=_series([10.0, 20.0]),
        state=PortfolioState(
            positions=_series([0.0, 0.0]),
            sellable_positions=_series([0.0, 0.0]),
            cash=1_000.0,
        ),
    )

    assert result.requested_shares.tolist() == [50.0, 12.5]
    assert result.constraints.executable_shares.tolist() == [50.0, 12.5]
    assert result.state.positions.tolist() == [50.0, 12.5]
    assert result.state.sellable_positions.tolist() == [0.0, 0.0]
    assert result.state.cash == pytest.approx(250.0)
    assert result.equity_before == pytest.approx(1_000.0)
    assert result.equity_after == pytest.approx(1_000.0)


def test_unrestricted_rebalance_deducts_fees_from_equity(
    tmp_path: Path,
) -> None:
    result = execute_target_weights(
        component=create_unrestricted_market_rules(commission_rate=0.01),
        context=_context(tmp_path),
        trade_date=pd.Timestamp("2026-09-18"),
        target_weights=_series([0.5, 0.0]),
        prices=_series([10.0, 20.0]),
        state=PortfolioState(
            positions=_series([0.0, 0.0]),
            sellable_positions=_series([0.0, 0.0]),
            cash=1_000.0,
        ),
    )

    assert result.constraints.fees.tolist() == [5.0, 0.0]
    assert result.state.cash == pytest.approx(495.0)
    assert result.equity_after == pytest.approx(995.0)


def test_a_stock_rebalance_rounds_buys_and_keeps_them_unsellable(
    tmp_path: Path,
) -> None:
    result = execute_target_weights(
        component=create_a_stock_market_rules(market="CN"),
        context=_context(tmp_path),
        trade_date=pd.Timestamp("2026-09-18"),
        target_weights=_series([0.55, 0.0]),
        prices=_series([10.0, 20.0]),
        state=PortfolioState(
            positions=_series([0.0, 0.0]),
            sellable_positions=_series([0.0, 0.0]),
            cash=10_000.0,
        ),
        market_state_provider=_open_market_provider(),
    )

    assert result.requested_shares.tolist() == [550.0, 0.0]
    assert result.constraints.executable_shares.tolist() == [500.0, 0.0]
    assert result.state.positions.tolist() == [500.0, 0.0]
    assert result.state.sellable_positions.tolist() == [0.0, 0.0]
    assert result.constraints.fees.iloc[0] == pytest.approx(5.05)
    assert result.state.cash == pytest.approx(4_994.95)
    assert result.equity_after == pytest.approx(9_994.95)


def test_a_stock_rebalance_enforces_t_plus_one(
    tmp_path: Path,
) -> None:
    same_day_state = PortfolioState(
        positions=_series([500.0, 0.0]),
        sellable_positions=_series([0.0, 0.0]),
        cash=5_000.0,
    )
    kwargs = {
        "component": create_a_stock_market_rules(market="CN"),
        "context": _context(tmp_path),
        "target_weights": _series([0.0, 0.0]),
        "prices": _series([10.0, 20.0]),
        "market_state_provider": _open_market_provider(),
    }

    blocked = execute_target_weights(
        trade_date=pd.Timestamp("2026-09-18"),
        state=same_day_state,
        **kwargs,
    )
    sold = execute_target_weights(
        trade_date=pd.Timestamp("2026-09-21"),
        state=same_day_state.start_next_session(),
        **kwargs,
    )

    assert blocked.constraints.executable_shares.tolist() == [0.0, 0.0]
    assert blocked.state.positions.tolist() == [500.0, 0.0]
    assert sold.constraints.executable_shares.tolist() == [-500.0, 0.0]
    assert sold.state.positions.tolist() == [0.0, 0.0]
    assert sold.state.sellable_positions.tolist() == [0.0, 0.0]
    assert sold.state.cash == pytest.approx(9_992.45)


@pytest.mark.parametrize(
    "blocked_state",
    [
        {"is_suspended": True},
        {"is_limit_up": True},
    ],
)
def test_a_stock_rebalance_blocks_unbuyable_security(
    tmp_path: Path,
    blocked_state: dict[str, bool],
) -> None:
    result = execute_target_weights(
        component=create_a_stock_market_rules(market="CN"),
        context=_context(tmp_path),
        trade_date=pd.Timestamp("2026-09-18"),
        target_weights=_series([0.5, 0.0]),
        prices=_series([10.0, 20.0]),
        state=PortfolioState(
            positions=_series([0.0, 0.0]),
            sellable_positions=_series([0.0, 0.0]),
            cash=10_000.0,
        ),
        market_state_provider=_open_market_provider(**blocked_state),
    )

    assert result.constraints.executable_shares.tolist() == [0.0, 0.0]
    assert result.state.cash == 10_000.0
    assert result.state.positions.tolist() == [0.0, 0.0]


def test_a_stock_rebalance_blocks_limit_down_sale(tmp_path: Path) -> None:
    result = execute_target_weights(
        component=create_a_stock_market_rules(market="CN"),
        context=_context(tmp_path),
        trade_date=pd.Timestamp("2026-09-18"),
        target_weights=_series([0.0, 0.0]),
        prices=_series([10.0, 20.0]),
        state=PortfolioState(
            positions=_series([500.0, 0.0]),
            sellable_positions=_series([500.0, 0.0]),
            cash=5_000.0,
        ),
        market_state_provider=_open_market_provider(is_limit_down=True),
    )

    assert result.constraints.executable_shares.tolist() == [0.0, 0.0]
    assert result.state.positions.tolist() == [500.0, 0.0]
    assert result.state.cash == 5_000.0


@pytest.mark.parametrize(
    ("target_weights", "message"),
    [
        (_series([-0.1, 0.0]), "non-negative"),
        (_series([0.8, 0.3]), "sum above one"),
    ],
)
def test_rebalance_rejects_invalid_target_weights(
    tmp_path: Path,
    target_weights: pd.Series,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        execute_target_weights(
            component=create_unrestricted_market_rules(),
            context=_context(tmp_path),
            trade_date=pd.Timestamp("2026-09-18"),
            target_weights=target_weights,
            prices=_series([10.0, 20.0]),
            state=PortfolioState(
                positions=_series([0.0, 0.0]),
                sellable_positions=_series([0.0, 0.0]),
                cash=1_000.0,
            ),
        )


def test_rebalance_rejects_market_result_that_overspends_cash(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="negative cash"):
        execute_target_weights(
            component=create_unrestricted_market_rules(
                commission_rate=0.01
            ),
            context=_context(tmp_path),
            trade_date=pd.Timestamp("2026-09-18"),
            target_weights=_series([1.0, 0.0]),
            prices=_series([10.0, 20.0]),
            state=PortfolioState(
                positions=_series([0.0, 0.0]),
                sellable_positions=_series([0.0, 0.0]),
                cash=1_000.0,
            ),
        )


def test_rebalance_blocks_buy_when_price_is_not_tradable(
    tmp_path: Path,
) -> None:
    result = execute_target_weights(
        component=create_unrestricted_market_rules(
            commission_rate=0.01
        ),
        context=_context(tmp_path),
        trade_date=pd.Timestamp("2026-09-18"),
        target_weights=_series([0.5, 0.0]),
        prices=_series([10.0, 20.0]),
        state=PortfolioState(
            positions=_series([0.0, 0.0]),
            sellable_positions=_series([0.0, 0.0]),
            cash=1_000.0,
        ),
        tradable=pd.Series(
            [False, True],
            index=_series([0.0, 0.0]).index,
            dtype=bool,
        ),
    )

    assert result.requested_shares.tolist() == [50.0, 0.0]
    assert result.constraints.executable_shares.tolist() == [0.0, 0.0]
    assert result.constraints.fees.tolist() == [0.0, 0.0]
    assert result.constraints.reasons.tolist() == [
        "price_unavailable",
        "no_order",
    ]
    assert result.constraints.metadata["price_unavailable_tickers"] == [
        "AAA"
    ]
    assert result.state.positions.tolist() == [0.0, 0.0]
    assert result.state.cash == 1_000.0
    assert result.equity_after == 1_000.0


def test_rebalance_blocks_sale_when_price_is_not_tradable(
    tmp_path: Path,
) -> None:
    result = execute_target_weights(
        component=create_unrestricted_market_rules(
            commission_rate=0.01
        ),
        context=_context(tmp_path),
        trade_date=pd.Timestamp("2026-09-18"),
        target_weights=_series([0.0, 0.0]),
        prices=_series([10.0, 20.0]),
        state=PortfolioState(
            positions=_series([50.0, 0.0]),
            sellable_positions=_series([50.0, 0.0]),
            cash=500.0,
        ),
        tradable=pd.Series(
            [False, True],
            index=_series([0.0, 0.0]).index,
            dtype=bool,
        ),
    )

    assert result.requested_shares.tolist() == [-50.0, 0.0]
    assert result.constraints.executable_shares.tolist() == [0.0, 0.0]
    assert result.constraints.fees.tolist() == [0.0, 0.0]
    assert result.constraints.reasons.iloc[0] == "price_unavailable"
    assert result.state.positions.tolist() == [50.0, 0.0]
    assert result.state.sellable_positions.tolist() == [50.0, 0.0]
    assert result.state.cash == 500.0
    assert result.equity_after == 1_000.0


def test_non_tradable_security_without_order_remains_no_order(
    tmp_path: Path,
) -> None:
    result = execute_target_weights(
        component=create_unrestricted_market_rules(),
        context=_context(tmp_path),
        trade_date=pd.Timestamp("2026-09-18"),
        target_weights=_series([0.5, 0.0]),
        prices=_series([10.0, 20.0]),
        state=PortfolioState(
            positions=_series([50.0, 0.0]),
            sellable_positions=_series([50.0, 0.0]),
            cash=500.0,
        ),
        tradable=pd.Series(
            [False, True],
            index=_series([0.0, 0.0]).index,
            dtype=bool,
        ),
    )

    assert result.requested_shares.tolist() == [0.0, 0.0]
    assert result.constraints.reasons.tolist() == ["no_order", "no_order"]
    assert "price_unavailable_tickers" not in result.constraints.metadata


@pytest.mark.parametrize(
    "tradable",
    [
        [True, False],
        pd.Series(
            [1, 0],
            index=pd.Index(["AAA", "BBB"], name="ticker"),
        ),
        pd.Series(
            [True, False],
            index=pd.Index(["BBB", "AAA"], name="ticker"),
            dtype=bool,
        ),
    ],
)
def test_rebalance_rejects_invalid_tradability(
    tmp_path: Path,
    tradable: object,
) -> None:
    with pytest.raises((TypeError, ValueError), match="tradable"):
        execute_target_weights(
            component=create_unrestricted_market_rules(),
            context=_context(tmp_path),
            trade_date=pd.Timestamp("2026-09-18"),
            target_weights=_series([0.5, 0.0]),
            prices=_series([10.0, 20.0]),
            state=PortfolioState(
                positions=_series([0.0, 0.0]),
                sellable_positions=_series([0.0, 0.0]),
                cash=1_000.0,
            ),
            tradable=tradable,  # type: ignore[arg-type]
        )
