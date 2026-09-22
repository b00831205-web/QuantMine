"""Contract tests for replaceable market-specific trading rules."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from quantmine.plugins.a_share import AStockEligibilityUniverse
from quantmine.plugins.context import SourceContext
from quantmine.plugins.contracts import PluginSpec
from quantmine.plugins.market_rules import (
    AStockMarketRulesPlugin,
    MarketRulesComponent,
    MarketRulesPlugin,
    MarketStateProvider,
    TradeConstraintRequest,
    TradeConstraintResult,
    UnrestrictedMarketRulesPlugin,
    apply_market_rules_component,
    create_a_stock_market_rules,
    create_unrestricted_market_rules,
    load_market_state_frame,
    resolve_market_rules_component,
)
from quantmine.storage.connections import ConnectionRegistry


def _series(values: list[float]) -> pd.Series:
    return pd.Series(values, index=pd.Index(["AAA", "BBB"], name="ticker"))


def _request(**overrides: object) -> TradeConstraintRequest:
    values: dict[str, object] = {
        "trade_date": pd.Timestamp("2026-09-18"),
        "requested_shares": _series([100.0, -100.0]),
        "prices": _series([10.0, 20.0]),
        "positions": _series([0.0, 200.0]),
        "sellable_positions": _series([0.0, 100.0]),
        "cash": 100_000.0,
        "market_state": pd.DataFrame(
            {
                "suspended": [False, False],
                "limit_up": [False, False],
                "limit_down": [False, False],
            },
            index=pd.Index(["AAA", "BBB"], name="ticker"),
        ),
    }
    values.update(overrides)
    return TradeConstraintRequest(**values)  # type: ignore[arg-type]


def _result(**overrides: object) -> TradeConstraintResult:
    values: dict[str, object] = {
        "executable_shares": _series([100.0, -100.0]),
        "fees": _series([5.0, 10.0]),
        "reasons": pd.Series(
            ["accepted", "accepted"],
            index=pd.Index(["AAA", "BBB"], name="ticker"),
        ),
        "metadata": {"market": "CN"},
    }
    values.update(overrides)
    return TradeConstraintResult(**values)  # type: ignore[arg-type]


def _a_share_state() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "is_suspended": [False, False],
            "is_limit_up": [False, False],
            "is_limit_down": [False, False],
        },
        index=pd.Index(["AAA", "BBB"], name="ticker"),
    )


class StubMarketRulesPlugin:
    def apply(self, request, context):
        del request, context
        return _result()


class ResultMarketRulesPlugin:
    def __init__(self, result: object) -> None:
        self.result = result

    def apply(self, request, context):
        del request, context
        return self.result


def _context(tmp_path: Path) -> SourceContext:
    return SourceContext(
        connections=ConnectionRegistry({}),
        run_id=1001,
        artifact_dir=tmp_path / "artifacts",
    )


def _component(result: object) -> MarketRulesComponent:
    return MarketRulesComponent(
        id="test_market_rules",
        plugin=ResultMarketRulesPlugin(result),
        market="TEST",
    )


def test_trade_constraint_request_accepts_aligned_market_state() -> None:
    request = _request(metadata={"source": "backtest"})

    assert request.trade_date == pd.Timestamp("2026-09-18")
    assert request.requested_shares.index.tolist() == ["AAA", "BBB"]
    assert request.metadata == {"source": "backtest"}


def test_trade_constraint_request_rejects_nat_date() -> None:
    with pytest.raises((TypeError, ValueError), match="trade_date"):
        _request(trade_date=pd.NaT)


@pytest.mark.parametrize("cash", [-1.0, float("nan")])
def test_trade_constraint_request_rejects_invalid_cash(cash: float) -> None:
    with pytest.raises(ValueError, match="cash must be non-negative"):
        _request(cash=cash)


@pytest.mark.parametrize("cash", [True, "1000"])
def test_trade_constraint_request_rejects_non_real_cash(cash: object) -> None:
    with pytest.raises(TypeError, match="cash must be a real number"):
        _request(cash=cash)


@pytest.mark.parametrize(
    "field",
    ["requested_shares", "prices", "positions", "sellable_positions"],
)
def test_trade_constraint_request_requires_series(field: str) -> None:
    with pytest.raises(TypeError, match=field):
        _request(**{field: [1.0, 2.0]})


def test_trade_constraint_request_rejects_duplicate_tickers() -> None:
    duplicate = pd.Series([1.0, 2.0], index=["AAA", "AAA"])

    with pytest.raises(ValueError, match="requested_shares index must be unique"):
        _request(requested_shares=duplicate)


@pytest.mark.parametrize("field", ["prices", "positions", "sellable_positions"])
def test_trade_constraint_request_rejects_misaligned_series(field: str) -> None:
    misaligned = pd.Series([1.0, 2.0], index=["BBB", "AAA"])

    with pytest.raises(ValueError, match=rf"{field} index must match"):
        _request(**{field: misaligned})


def test_trade_constraint_request_rejects_nonpositive_prices() -> None:
    with pytest.raises(ValueError, match="prices must contain positive values"):
        _request(prices=_series([10.0, 0.0]))


@pytest.mark.parametrize("field", ["positions", "sellable_positions"])
def test_trade_constraint_request_rejects_negative_positions(field: str) -> None:
    with pytest.raises(ValueError, match=rf"{field} must contain non-negative"):
        _request(**{field: _series([0.0, -1.0])})


def test_trade_constraint_request_rejects_unsellable_excess() -> None:
    with pytest.raises(ValueError, match="must not exceed positions"):
        _request(
            positions=_series([100.0, 100.0]),
            sellable_positions=_series([101.0, 100.0]),
        )


def test_trade_constraint_request_requires_market_state_coverage() -> None:
    market_state = pd.DataFrame(
        {"suspended": [False]},
        index=pd.Index(["AAA"], name="ticker"),
    )

    with pytest.raises(ValueError, match=r"does not cover.*BBB"):
        _request(market_state=market_state)


def test_trade_constraint_request_rejects_duplicate_market_state() -> None:
    market_state = pd.DataFrame(
        {"suspended": [False, False]},
        index=["AAA", "AAA"],
    )

    with pytest.raises(ValueError, match="market_state index must be unique"):
        _request(market_state=market_state)


def test_trade_constraint_result_accepts_aligned_outputs() -> None:
    result = _result()

    assert result.executable_shares.tolist() == [100.0, -100.0]
    assert result.fees.tolist() == [5.0, 10.0]
    assert result.metadata == {"market": "CN"}


@pytest.mark.parametrize("field", ["fees", "reasons"])
def test_trade_constraint_result_rejects_misaligned_outputs(field: str) -> None:
    value = pd.Series([1.0, 2.0], index=["BBB", "AAA"])

    with pytest.raises(ValueError, match=rf"{field} index must match"):
        _result(**{field: value})


def test_market_rules_protocol_and_component_accept_valid_plugin() -> None:
    plugin = StubMarketRulesPlugin()

    assert isinstance(plugin, MarketRulesPlugin)
    component = MarketRulesComponent(
        id="cn_a_share_rules",
        plugin=plugin,
        market="CN",
        metadata={"settlement": "T+1"},
    )

    assert component.plugin is plugin
    assert component.market == "CN"
    assert component.requires_connection is False


def test_market_rules_component_rejects_non_plugin() -> None:
    with pytest.raises(TypeError, match="MarketRulesPlugin"):
        MarketRulesComponent(
            id="invalid",
            plugin=object(),  # type: ignore[arg-type]
            market="CN",
        )


@pytest.mark.parametrize("component_id", ["", " rules", "rules "])
def test_market_rules_component_rejects_invalid_id(component_id: str) -> None:
    with pytest.raises(ValueError, match="component id"):
        MarketRulesComponent(
            id=component_id,
            plugin=StubMarketRulesPlugin(),
            market="CN",
        )


@pytest.mark.parametrize("market", ["", " CN", "CN "])
def test_market_rules_component_rejects_invalid_market(market: str) -> None:
    with pytest.raises(ValueError, match="market must be"):
        MarketRulesComponent(
            id="rules",
            plugin=StubMarketRulesPlugin(),
            market=market,
        )


def test_market_rules_component_rejects_invalid_connection_ref() -> None:
    with pytest.raises(ValueError, match="connection_ref"):
        MarketRulesComponent(
            id="rules",
            plugin=StubMarketRulesPlugin(),
            market="CN",
            connection_ref=" database",
        )


def test_market_rules_component_requires_declared_connection() -> None:
    with pytest.raises(ValueError, match="connection_ref is required"):
        MarketRulesComponent(
            id="rules",
            plugin=StubMarketRulesPlugin(),
            market="CN",
            requires_connection=True,
        )


def test_market_rules_component_requires_boolean_connection_flag() -> None:
    with pytest.raises(TypeError, match="requires_connection must be a bool"):
        MarketRulesComponent(
            id="rules",
            plugin=StubMarketRulesPlugin(),
            market="CN",
            requires_connection=1,  # type: ignore[arg-type]
        )


def test_apply_market_rules_component_returns_valid_result(
    tmp_path: Path,
) -> None:
    expected = _result()

    actual = apply_market_rules_component(
        _component(expected),
        _request(),
        _context(tmp_path),
    )

    assert actual is expected


def test_apply_market_rules_component_rejects_wrong_return_type(
    tmp_path: Path,
) -> None:
    with pytest.raises(TypeError, match="expected TradeConstraintResult"):
        apply_market_rules_component(
            _component({}),
            _request(),
            _context(tmp_path),
        )


def test_apply_market_rules_component_rejects_request_index_mismatch(
    tmp_path: Path,
) -> None:
    index = ["BBB", "AAA"]
    result = TradeConstraintResult(
        executable_shares=pd.Series([-100.0, 100.0], index=index),
        fees=pd.Series([10.0, 5.0], index=index),
        reasons=pd.Series(["accepted", "accepted"], index=index),
    )

    with pytest.raises(ValueError, match="index that does not match"):
        apply_market_rules_component(
            _component(result),
            _request(),
            _context(tmp_path),
        )


def test_apply_market_rules_component_rejects_missing_quantity(
    tmp_path: Path,
) -> None:
    result = _result(executable_shares=_series([float("nan"), -100.0]))

    with pytest.raises(ValueError, match="missing executable"):
        apply_market_rules_component(
            _component(result),
            _request(),
            _context(tmp_path),
        )


@pytest.mark.parametrize(
    ("requested", "executable"),
    [
        ([100.0, -100.0], [-1.0, -100.0]),
        ([100.0, -100.0], [100.0, 1.0]),
        ([0.0, -100.0], [1.0, -100.0]),
    ],
)
def test_apply_market_rules_component_rejects_reversed_or_unsolicited_trade(
    requested: list[float],
    executable: list[float],
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="reversed the requested"):
        apply_market_rules_component(
            _component(_result(executable_shares=_series(executable))),
            _request(requested_shares=_series(requested)),
            _context(tmp_path),
        )


def test_apply_market_rules_component_rejects_excess_quantity(
    tmp_path: Path,
) -> None:
    result = _result(executable_shares=_series([101.0, -100.0]))

    with pytest.raises(ValueError, match="exceeding the request"):
        apply_market_rules_component(
            _component(result),
            _request(),
            _context(tmp_path),
        )


@pytest.mark.parametrize("fee", [-1.0, float("nan")])
def test_apply_market_rules_component_rejects_invalid_fees(
    fee: float,
    tmp_path: Path,
) -> None:
    result = _result(fees=_series([fee, 10.0]))

    with pytest.raises(ValueError, match="invalid negative or missing fees"):
        apply_market_rules_component(
            _component(result),
            _request(),
            _context(tmp_path),
        )


def test_unrestricted_market_rules_passes_orders_and_calculates_fees(
    tmp_path: Path,
) -> None:
    plugin = UnrestrictedMarketRulesPlugin(commission_rate=0.001)

    result = plugin.apply(_request(), _context(tmp_path))

    pd.testing.assert_series_equal(
        result.executable_shares,
        _series([100.0, -100.0]),
    )
    pd.testing.assert_series_equal(result.fees, _series([1.0, 2.0]))
    assert result.reasons.tolist() == ["accepted", "accepted"]
    assert result.metadata == {
        "market_rules": "unrestricted",
        "commission_rate": 0.001,
    }


def test_unrestricted_market_rules_marks_zero_order(
    tmp_path: Path,
) -> None:
    request = _request(requested_shares=_series([0.0, -100.0]))

    result = UnrestrictedMarketRulesPlugin().apply(
        request,
        _context(tmp_path),
    )

    assert result.reasons.tolist() == ["no_order", "accepted"]
    assert result.fees.tolist() == [0.0, 0.0]


@pytest.mark.parametrize("commission_rate", [True, "0.001"])
def test_unrestricted_market_rules_requires_numeric_commission(
    commission_rate: object,
) -> None:
    with pytest.raises(TypeError, match="commission_rate must be a real"):
        UnrestrictedMarketRulesPlugin(
            commission_rate=commission_rate,  # type: ignore[arg-type]
        )


@pytest.mark.parametrize("commission_rate", [-0.001, float("nan")])
def test_unrestricted_market_rules_rejects_invalid_commission(
    commission_rate: float,
) -> None:
    with pytest.raises(ValueError, match="commission_rate must be non-negative"):
        UnrestrictedMarketRulesPlugin(commission_rate=commission_rate)


def test_unrestricted_market_rules_factory_uses_configured_values() -> None:
    component = create_unrestricted_market_rules(
        market="US",
        commission_rate=0.0005,
    )

    assert component.id == "unrestricted_market_rules"
    assert component.market == "US"
    assert component.requires_connection is False
    assert component.connection_ref is None
    assert component.metadata == {
        "model": "unrestricted",
        "commission_rate": 0.0005,
    }
    assert isinstance(component.plugin, UnrestrictedMarketRulesPlugin)
    assert component.plugin.commission_rate == 0.0005


def test_unrestricted_market_rules_factory_rejects_unknown_parameters() -> None:
    with pytest.raises(ValueError, match="unsupported.*unexpected"):
        create_unrestricted_market_rules(unexpected=True)


def test_market_rules_component_resolves_allowlisted_factory() -> None:
    component = resolve_market_rules_component(
        PluginSpec(
            "quantmine.plugins.market_rules:"
            "create_unrestricted_market_rules",
            params={"market": "US", "commission_rate": 0.001},
        ),
        allowed_module_prefixes=("quantmine",),
    )

    assert component.market == "US"
    assert isinstance(component.plugin, UnrestrictedMarketRulesPlugin)
    assert component.plugin.commission_rate == 0.001


def test_market_rules_resolver_rejects_wrong_component_type() -> None:
    with pytest.raises(TypeError, match="expected MarketRulesComponent"):
        resolve_market_rules_component(
            PluginSpec(
                "quantmine.plugins.backtest_engines:"
                "create_python_backtest_engine"
            ),
            allowed_module_prefixes=("quantmine",),
        )


def test_a_stock_market_rules_accepts_default_configuration() -> None:
    plugin = AStockMarketRulesPlugin()

    assert plugin.lot_size == 100
    assert plugin.commission_rate == 0.0003
    assert plugin.minimum_commission == 5.0
    assert plugin.stamp_duty_rate == 0.0005
    assert plugin.transfer_fee_rate == 0.00001


@pytest.mark.parametrize("lot_size", [True, 100.0, "100"])
def test_a_stock_market_rules_requires_integer_lot_size(
    lot_size: object,
) -> None:
    with pytest.raises(TypeError, match="lot_size must be an integer"):
        AStockMarketRulesPlugin(lot_size=lot_size)  # type: ignore[arg-type]


@pytest.mark.parametrize("lot_size", [0, -100])
def test_a_stock_market_rules_requires_positive_lot_size(
    lot_size: int,
) -> None:
    with pytest.raises(ValueError, match="lot_size must be positive"):
        AStockMarketRulesPlugin(lot_size=lot_size)


@pytest.mark.parametrize(
    "field",
    [
        "commission_rate",
        "minimum_commission",
        "stamp_duty_rate",
        "transfer_fee_rate",
    ],
)
def test_a_stock_market_rules_requires_numeric_cost_parameters(
    field: str,
) -> None:
    with pytest.raises(TypeError, match=rf"{field} must be a real number"):
        AStockMarketRulesPlugin(**{field: True})


@pytest.mark.parametrize(
    "field",
    [
        "commission_rate",
        "minimum_commission",
        "stamp_duty_rate",
        "transfer_fee_rate",
    ],
)
@pytest.mark.parametrize("value", [-0.01, float("nan")])
def test_a_stock_market_rules_rejects_invalid_cost_parameters(
    field: str,
    value: float,
) -> None:
    with pytest.raises(ValueError, match=rf"{field} must be non-negative"):
        AStockMarketRulesPlugin(**{field: value})


def test_a_stock_market_rules_requires_all_market_state_columns(
    tmp_path: Path,
) -> None:
    state = _a_share_state().drop(columns="is_limit_down")
    request = _request(market_state=state)

    with pytest.raises(ValueError, match="missing required columns.*is_limit_down"):
        AStockMarketRulesPlugin().apply(request, _context(tmp_path))


def test_a_stock_market_rules_rejects_missing_market_state_values(
    tmp_path: Path,
) -> None:
    state = _a_share_state()
    state["is_limit_up"] = state["is_limit_up"].astype("boolean")
    state.loc["AAA", "is_limit_up"] = pd.NA
    request = _request(market_state=state)

    with pytest.raises(ValueError, match="is_limit_up.*missing values"):
        AStockMarketRulesPlugin().apply(request, _context(tmp_path))


def test_a_stock_market_rules_requires_boolean_market_state(
    tmp_path: Path,
) -> None:
    state = _a_share_state()
    state["is_suspended"] = [0, 1]
    request = _request(market_state=state)

    with pytest.raises(TypeError, match="is_suspended.*boolean"):
        AStockMarketRulesPlugin().apply(request, _context(tmp_path))


def test_a_stock_market_rules_normalizes_state_to_request_index(
    monkeypatch,
    tmp_path: Path,
) -> None:
    observed: dict[str, object] = {}
    expected = _result()

    def fake_apply_rules(self, request, state):
        del self, request
        observed["state"] = state
        return expected

    monkeypatch.setattr(
        AStockMarketRulesPlugin,
        "_apply_rules",
        fake_apply_rules,
    )
    state = pd.concat(
        [
            _a_share_state().iloc[::-1],
            pd.DataFrame(
                {
                    "is_suspended": [False],
                    "is_limit_up": [False],
                    "is_limit_down": [False],
                },
                index=["EXTRA"],
            ),
        ]
    )

    actual = AStockMarketRulesPlugin().apply(
        _request(market_state=state),
        _context(tmp_path),
    )

    assert actual is expected
    normalized = observed["state"]
    assert isinstance(normalized, pd.DataFrame)
    assert normalized.index.tolist() == ["AAA", "BBB"]


def test_a_stock_market_rules_blocks_suspended_orders(
    tmp_path: Path,
) -> None:
    state = _a_share_state()
    state["is_suspended"] = [True, True]

    result = AStockMarketRulesPlugin().apply(
        _request(market_state=state),
        _context(tmp_path),
    )

    assert result.executable_shares.tolist() == [0.0, 0.0]
    assert result.reasons.tolist() == ["suspended", "suspended"]


def test_a_stock_market_rules_blocks_limit_up_buy_and_limit_down_sell(
    tmp_path: Path,
) -> None:
    state = _a_share_state()
    state["is_limit_up"] = [True, False]
    state["is_limit_down"] = [False, True]

    result = AStockMarketRulesPlugin().apply(
        _request(market_state=state),
        _context(tmp_path),
    )

    assert result.executable_shares.tolist() == [0.0, 0.0]
    assert result.reasons.tolist() == ["limit_up", "limit_down"]


def test_a_stock_market_rules_allows_limit_up_sell_and_limit_down_buy(
    tmp_path: Path,
) -> None:
    state = _a_share_state()
    state["is_limit_up"] = [True, False]
    state["is_limit_down"] = [False, True]
    request = _request(
        requested_shares=_series([-100.0, 100.0]),
        positions=_series([100.0, 0.0]),
        sellable_positions=_series([100.0, 0.0]),
        market_state=state,
    )

    result = AStockMarketRulesPlugin().apply(
        request,
        _context(tmp_path),
    )

    assert result.executable_shares.tolist() == [-100.0, 100.0]
    assert result.reasons.tolist() == ["accepted", "accepted"]


def test_a_stock_market_rules_rounds_buy_orders_to_lots(
    tmp_path: Path,
) -> None:
    request = _request(
        requested_shares=_series([150.0, 50.0]),
        positions=_series([0.0, 0.0]),
        sellable_positions=_series([0.0, 0.0]),
        market_state=_a_share_state(),
    )

    result = AStockMarketRulesPlugin().apply(
        request,
        _context(tmp_path),
    )

    assert result.executable_shares.tolist() == [100.0, 0.0]
    assert result.reasons.tolist() == [
        "lot_size_adjusted",
        "lot_size_adjusted",
    ]


def test_a_stock_market_rules_caps_sells_at_t_plus_one_quantity(
    tmp_path: Path,
) -> None:
    request = _request(
        requested_shares=_series([-200.0, -200.0]),
        positions=_series([300.0, 300.0]),
        sellable_positions=_series([0.0, 150.0]),
        market_state=_a_share_state(),
    )

    result = AStockMarketRulesPlugin().apply(
        request,
        _context(tmp_path),
    )

    assert result.executable_shares.tolist() == [0.0, -100.0]
    assert result.reasons.tolist() == [
        "sellable_limited",
        "sellable_and_lot_size_adjusted",
    ]


def test_a_stock_market_rules_prevents_short_position(
    tmp_path: Path,
) -> None:
    request = _request(
        requested_shares=_series([-300.0, 0.0]),
        positions=_series([100.0, 0.0]),
        sellable_positions=_series([100.0, 0.0]),
        market_state=_a_share_state(),
    )

    result = AStockMarketRulesPlugin().apply(
        request,
        _context(tmp_path),
    )

    assert result.executable_shares.tolist() == [-100.0, 0.0]
    assert result.reasons.tolist() == ["sellable_limited", "no_order"]


def test_a_stock_market_rules_rounds_partial_sell_to_lot(
    tmp_path: Path,
) -> None:
    request = _request(
        requested_shares=_series([-150.0, 0.0]),
        positions=_series([300.0, 0.0]),
        sellable_positions=_series([300.0, 0.0]),
        market_state=_a_share_state(),
    )

    result = AStockMarketRulesPlugin().apply(
        request,
        _context(tmp_path),
    )

    assert result.executable_shares.tolist() == [-100.0, 0.0]
    assert result.reasons.tolist() == ["lot_size_adjusted", "no_order"]


@pytest.mark.parametrize("quantity", [50.0, 250.0])
def test_a_stock_market_rules_allows_complete_odd_lot_liquidation(
    quantity: float,
    tmp_path: Path,
) -> None:
    request = _request(
        requested_shares=_series([-quantity, 0.0]),
        positions=_series([quantity, 0.0]),
        sellable_positions=_series([quantity, 0.0]),
        market_state=_a_share_state(),
    )

    result = AStockMarketRulesPlugin().apply(
        request,
        _context(tmp_path),
    )

    assert result.executable_shares.tolist() == [-quantity, 0.0]
    assert result.reasons.tolist() == ["accepted", "no_order"]
    expected_fee = max(quantity * 10.0 * 0.0003, 5.0)
    expected_fee += quantity * 10.0 * 0.0005
    expected_fee += quantity * 10.0 * 0.00001
    assert result.fees.tolist() == pytest.approx([expected_fee, 0.0])
    assert result.metadata == {
        "market_rules": "cn_a_share",
        "lot_size": 100,
        "fees_applied": True,
        "commission_rate": 0.0003,
        "minimum_commission": 5.0,
        "stamp_duty_rate": 0.0005,
        "transfer_fee_rate": 0.00001,
        "cash_before_trades": 100_000.0,
        "cash_after_trades": pytest.approx(
            100_000.0 + quantity * 10.0 - expected_fee
        ),
    }


def test_a_stock_market_rules_applies_default_buy_and_sell_fees(
    tmp_path: Path,
) -> None:
    result = AStockMarketRulesPlugin().apply(
        _request(market_state=_a_share_state()),
        _context(tmp_path),
    )

    # Buy: 5 minimum commission + 0.01 transfer fee.
    # Sell: 5 minimum commission + 1 stamp duty + 0.02 transfer fee.
    assert result.fees.tolist() == pytest.approx([5.01, 6.02])


def test_a_stock_market_rules_uses_proportional_commission_above_minimum(
    tmp_path: Path,
) -> None:
    request = _request(
        requested_shares=_series([1000.0, -1000.0]),
        prices=_series([100.0, 100.0]),
        positions=_series([0.0, 1000.0]),
        sellable_positions=_series([0.0, 1000.0]),
        market_state=_a_share_state(),
    )

    result = AStockMarketRulesPlugin().apply(
        request,
        _context(tmp_path),
    )

    assert result.fees.tolist() == pytest.approx([31.0, 81.0])


def test_a_stock_market_rules_supports_configurable_cost_rates(
    tmp_path: Path,
) -> None:
    plugin = AStockMarketRulesPlugin(
        commission_rate=0.001,
        minimum_commission=0.0,
        stamp_duty_rate=0.002,
        transfer_fee_rate=0.003,
    )

    result = plugin.apply(
        _request(market_state=_a_share_state()),
        _context(tmp_path),
    )

    assert result.fees.tolist() == pytest.approx([4.0, 12.0])


def test_a_stock_market_rules_does_not_charge_blocked_orders(
    tmp_path: Path,
) -> None:
    state = _a_share_state()
    state["is_suspended"] = [True, True]

    result = AStockMarketRulesPlugin().apply(
        _request(market_state=state),
        _context(tmp_path),
    )

    assert result.executable_shares.tolist() == [0.0, 0.0]
    assert result.fees.tolist() == [0.0, 0.0]


def test_a_stock_market_rules_preserves_orders_when_cash_is_sufficient(
    tmp_path: Path,
) -> None:
    request = _request(
        requested_shares=_series([100.0, 0.0]),
        prices=_series([10.0, 20.0]),
        positions=_series([0.0, 0.0]),
        sellable_positions=_series([0.0, 0.0]),
        cash=2_000.0,
        market_state=_a_share_state(),
    )

    result = AStockMarketRulesPlugin().apply(
        request,
        _context(tmp_path),
    )

    assert result.executable_shares.tolist() == [100.0, 0.0]
    assert result.reasons.tolist() == ["accepted", "no_order"]
    assert result.metadata["cash_after_trades"] == pytest.approx(994.99)


def test_a_stock_market_rules_scales_buys_proportionally_to_cash(
    tmp_path: Path,
) -> None:
    plugin = AStockMarketRulesPlugin(
        commission_rate=0.0,
        minimum_commission=0.0,
        stamp_duty_rate=0.0,
        transfer_fee_rate=0.0,
    )
    request = _request(
        requested_shares=_series([1000.0, 1000.0]),
        prices=_series([10.0, 20.0]),
        positions=_series([0.0, 0.0]),
        sellable_positions=_series([0.0, 0.0]),
        cash=15_000.0,
        market_state=_a_share_state(),
    )

    result = plugin.apply(request, _context(tmp_path))

    assert result.executable_shares.tolist() == [500.0, 500.0]
    assert result.reasons.tolist() == ["cash_limited", "cash_limited"]
    assert result.metadata["cash_after_trades"] == pytest.approx(0.0)


def test_a_stock_market_rules_drops_buy_below_affordable_lot(
    tmp_path: Path,
) -> None:
    plugin = AStockMarketRulesPlugin(
        commission_rate=0.0,
        minimum_commission=0.0,
        stamp_duty_rate=0.0,
        transfer_fee_rate=0.0,
    )
    request = _request(
        requested_shares=_series([100.0, 100.0]),
        prices=_series([10.0, 20.0]),
        positions=_series([0.0, 0.0]),
        sellable_positions=_series([0.0, 0.0]),
        cash=999.0,
        market_state=_a_share_state(),
    )

    result = plugin.apply(request, _context(tmp_path))

    assert result.executable_shares.tolist() == [0.0, 0.0]
    assert result.reasons.tolist() == ["cash_limited", "cash_limited"]
    assert result.metadata["cash_after_trades"] == pytest.approx(999.0)


def test_a_stock_market_rules_uses_same_day_sell_proceeds_for_buys(
    tmp_path: Path,
) -> None:
    request = _request(
        requested_shares=_series([100.0, -100.0]),
        prices=_series([10.0, 20.0]),
        positions=_series([0.0, 100.0]),
        sellable_positions=_series([0.0, 100.0]),
        cash=0.0,
        market_state=_a_share_state(),
    )

    result = AStockMarketRulesPlugin().apply(
        request,
        _context(tmp_path),
    )

    assert result.executable_shares.tolist() == [100.0, -100.0]
    assert result.metadata["cash_after_trades"] == pytest.approx(988.97)


def test_a_stock_market_rules_includes_minimum_fee_in_affordability(
    tmp_path: Path,
) -> None:
    request = _request(
        requested_shares=_series([100.0, 0.0]),
        prices=_series([10.0, 20.0]),
        positions=_series([0.0, 0.0]),
        sellable_positions=_series([0.0, 0.0]),
        cash=1_004.0,
        market_state=_a_share_state(),
    )

    result = AStockMarketRulesPlugin().apply(
        request,
        _context(tmp_path),
    )

    assert result.executable_shares.tolist() == [0.0, 0.0]
    assert result.fees.tolist() == [0.0, 0.0]
    assert result.reasons.tolist() == ["cash_limited", "no_order"]
    assert result.metadata["cash_after_trades"] == pytest.approx(1_004.0)


def test_a_stock_market_rules_factory_uses_default_configuration() -> None:
    component = create_a_stock_market_rules()

    assert component.id == "cn_a_share_market_rules"
    assert component.market == "CN"
    assert component.requires_connection is False
    assert component.connection_ref is None
    assert isinstance(component.plugin, AStockMarketRulesPlugin)
    assert component.plugin == AStockMarketRulesPlugin()
    assert component.metadata == {
        "model": "cn_a_share_cash_constrained",
        "lot_size": 100,
        "commission_rate": 0.0003,
        "minimum_commission": 5.0,
        "stamp_duty_rate": 0.0005,
        "transfer_fee_rate": 0.00001,
    }


def test_a_stock_market_rules_factory_maps_custom_configuration() -> None:
    component = create_a_stock_market_rules(
        market="CN",
        lot_size=200,
        commission_rate=0.001,
        minimum_commission=2.0,
        stamp_duty_rate=0.002,
        transfer_fee_rate=0.003,
    )

    assert component.plugin == AStockMarketRulesPlugin(
        lot_size=200,
        commission_rate=0.001,
        minimum_commission=2.0,
        stamp_duty_rate=0.002,
        transfer_fee_rate=0.003,
    )
    assert component.metadata == {
        "model": "cn_a_share_cash_constrained",
        "lot_size": 200,
        "commission_rate": 0.001,
        "minimum_commission": 2.0,
        "stamp_duty_rate": 0.002,
        "transfer_fee_rate": 0.003,
    }


def test_a_stock_market_rules_factory_rejects_non_cn_market() -> None:
    with pytest.raises(ValueError, match="requires market='CN'"):
        create_a_stock_market_rules(market="US")


def test_a_stock_market_rules_factory_rejects_unknown_parameters() -> None:
    with pytest.raises(ValueError, match="unsupported.*unexpected"):
        create_a_stock_market_rules(unexpected=True)


def test_a_stock_market_rules_resolves_allowlisted_factory() -> None:
    component = resolve_market_rules_component(
        PluginSpec(
            "quantmine.plugins.market_rules:"
            "create_a_stock_market_rules",
            params={
                "market": "CN",
                "lot_size": 200,
                "minimum_commission": 2.0,
            },
        ),
        allowed_module_prefixes=("quantmine",),
    )

    assert component.id == "cn_a_share_market_rules"
    assert component.market == "CN"
    assert isinstance(component.plugin, AStockMarketRulesPlugin)
    assert component.plugin.lot_size == 200
    assert component.plugin.minimum_commission == 2.0


class StubMarketStateProvider:
    def status_on(self, trade_date, ticker):
        del trade_date
        return {
            "is_suspended": ticker == "BBB",
            "is_limit_up": ticker == "AAA",
            "is_limit_down": False,
        }


def test_market_state_provider_protocol_and_frame_adapter() -> None:
    provider = StubMarketStateProvider()

    assert isinstance(provider, MarketStateProvider)
    frame = load_market_state_frame(
        provider,
        trade_date=pd.Timestamp("2026-09-19"),
        tickers=["AAA", "BBB"],
    )

    assert frame.index.name == "ticker"
    assert frame.index.tolist() == ["AAA", "BBB"]
    assert frame.to_dict(orient="index") == {
        "AAA": {
            "is_suspended": False,
            "is_limit_up": True,
            "is_limit_down": False,
        },
        "BBB": {
            "is_suspended": True,
            "is_limit_up": False,
            "is_limit_down": False,
        },
    }


def test_market_state_frame_rejects_invalid_provider() -> None:
    with pytest.raises(TypeError, match="MarketStateProvider"):
        load_market_state_frame(
            object(),  # type: ignore[arg-type]
            trade_date=pd.Timestamp("2026-09-19"),
            tickers=["AAA"],
        )


@pytest.mark.parametrize("trade_date", ["2026-09-19", pd.NaT])
def test_market_state_frame_rejects_invalid_date(trade_date: object) -> None:
    with pytest.raises((TypeError, ValueError), match="trade_date"):
        load_market_state_frame(
            StubMarketStateProvider(),
            trade_date=trade_date,  # type: ignore[arg-type]
            tickers=["AAA"],
        )


@pytest.mark.parametrize(
    "tickers",
    [["AAA", "AAA"], [""], [" AAA"], [1]],
)
def test_market_state_frame_rejects_invalid_tickers(
    tickers: list[object],
) -> None:
    with pytest.raises(ValueError, match="tickers"):
        load_market_state_frame(
            StubMarketStateProvider(),
            trade_date=pd.Timestamp("2026-09-19"),
            tickers=tickers,  # type: ignore[arg-type]
        )


def test_market_state_frame_requires_mapping_status() -> None:
    class InvalidProvider:
        def status_on(self, trade_date, ticker):
            del trade_date, ticker
            return []

    with pytest.raises(TypeError, match="status_on.*mapping"):
        load_market_state_frame(
            InvalidProvider(),
            trade_date=pd.Timestamp("2026-09-19"),
            tickers=["AAA"],
        )


def test_a_stock_universe_implements_market_state_provider() -> None:
    frame = pd.DataFrame(
        {
            "date": ["2026-09-19", "2026-09-19"],
            "ticker": ["AAA", "BBB"],
            "is_listed": [True, True],
            "is_st": [False, False],
            "is_suspended": [False, True],
            "listing_days": [100, 100],
            "is_limit_up": [True, False],
            "is_limit_down": [False, True],
        }
    )
    universe = AStockEligibilityUniverse.from_frame(frame)

    assert isinstance(universe, MarketStateProvider)
    state = load_market_state_frame(
        universe,
        trade_date=pd.Timestamp("2026-09-19"),
        tickers=["AAA", "BBB"],
    )

    assert state.to_dict(orient="index") == {
        "AAA": {
            "is_suspended": False,
            "is_limit_up": True,
            "is_limit_down": False,
        },
        "BBB": {
            "is_suspended": True,
            "is_limit_up": False,
            "is_limit_down": True,
        },
    }
