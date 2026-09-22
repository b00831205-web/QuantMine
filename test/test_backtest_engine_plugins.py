"""Contract tests for replaceable portfolio-backtest engines."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from quantmine.datareader import MarketData
from quantmine.ic_calculator import ICVariant
from quantmine.plugins import backtest_engines as backtest_engine_module
from quantmine.plugins.backtest_engines import (
    BacktestComponent,
    BacktestPlugin,
    BacktestRequest,
    BacktestResult,
    PythonPositionBacktestPlugin,
    PythonQuantileBacktestPlugin,
    create_python_backtest_engine,
    create_python_position_backtest_engine,
    resolve_backtest_component,
    run_backtest_component,
)
from quantmine.plugins.context import SourceContext
from quantmine.plugins.contracts import MarketDataBundle, PluginSpec
from quantmine.plugins.market_rules import (
    create_a_stock_market_rules,
    create_unrestricted_market_rules,
)
from quantmine.storage.connections import ConnectionRegistry


def _close() -> pd.DataFrame:
    return pd.DataFrame(
        {"AAA": [10.0, 10.2], "BBB": [20.0, 19.8]},
        index=pd.date_range("2026-01-02", periods=2, freq="B"),
    )


def _variant() -> ICVariant:
    return ICVariant(train={}, test={}, transforms=[])


def _job(**overrides: object) -> dict[str, object]:
    job: dict[str, object] = {
        "id": "raw_quintile",
        "variant": "raw",
        "selection_test": "newey_raw",
    }
    job.update(overrides)
    return job


def _request(**overrides: object) -> BacktestRequest:
    values: dict[str, object] = {
        "close": _close(),
        "variants": {"raw": _variant()},
        "test_results": {},
        "config": {"jobs": []},
    }
    values.update(overrides)
    return BacktestRequest(**values)  # type: ignore[arg-type]


def _context(tmp_path: Path) -> SourceContext:
    return SourceContext(
        connections=ConnectionRegistry({}),
        run_id=1001,
        artifact_dir=tmp_path / "artifacts",
    )


class StubBacktestPlugin:
    def run(
        self,
        request: BacktestRequest,
        context: SourceContext,
    ) -> BacktestResult:
        del request, context
        return BacktestResult(
            job_results={"raw_quintile": {"status": "ok"}},
            metadata={"backend": "stub"},
        )


class StubMarketStateProvider:
    def status_on(
        self,
        trade_date: pd.Timestamp,
        ticker: str,
    ) -> dict[str, object]:
        del trade_date, ticker
        return {
            "is_suspended": False,
            "is_limit_up": False,
            "is_limit_down": False,
        }


def test_backtest_request_accepts_legacy_and_rich_market_inputs() -> None:
    close = _close()
    market_cap = close * 1_000_000
    market_data = MarketDataBundle(
        market=MarketData(close=close, market_cap=market_cap),
    )

    request = _request(
        close=close,
        market_cap=market_cap,
        market_data=market_data,
    )

    assert request.close is close
    assert request.market_cap is market_cap
    assert request.market_data is market_data
    assert request.market_rules is None
    assert request.market_state_provider is None


def test_backtest_request_accepts_optional_execution_constraints() -> None:
    market_rules = create_unrestricted_market_rules()
    market_state_provider = StubMarketStateProvider()

    request = _request(
        market_rules=market_rules,
        market_state_provider=market_state_provider,
    )

    assert request.market_rules is market_rules
    assert request.market_state_provider is market_state_provider


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"market_rules": object()}, "market_rules"),
        ({"market_state_provider": object()}, "market_state_provider"),
    ],
)
def test_backtest_request_rejects_invalid_execution_constraints(
    overrides: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(TypeError, match=message):
        _request(**overrides)


@pytest.mark.parametrize(
    "overrides",
    [
        {"market_rules": create_unrestricted_market_rules()},
        {"market_state_provider": StubMarketStateProvider()},
    ],
)
def test_backtest_request_allows_constraints_independently(
    overrides: dict[str, object],
) -> None:
    request = _request(**overrides)

    assert request.market_rules is overrides.get("market_rules")
    assert request.market_state_provider is overrides.get(
        "market_state_provider"
    )


def test_backtest_request_requires_nonempty_close() -> None:
    with pytest.raises(TypeError, match="close must be"):
        _request(close=object())

    with pytest.raises(ValueError, match="close must not be empty"):
        _request(close=pd.DataFrame())


def test_backtest_request_requires_variants() -> None:
    with pytest.raises(TypeError, match="variants must be a mapping"):
        _request(variants=[])

    with pytest.raises(ValueError, match="variants must not be empty"):
        _request(variants={})


@pytest.mark.parametrize("variant_id", ["", " raw", "raw "])
def test_backtest_request_rejects_invalid_variant_ids(
    variant_id: str,
) -> None:
    with pytest.raises(ValueError, match="variant id"):
        _request(variants={variant_id: _variant()})


def test_backtest_request_requires_ic_variants() -> None:
    with pytest.raises(TypeError, match="must be an ICVariant"):
        _request(variants={"raw": object()})


def test_backtest_request_validates_result_and_config_mappings() -> None:
    with pytest.raises(TypeError, match="test_results must be a mapping"):
        _request(test_results=[])

    with pytest.raises(TypeError, match="config must be a mapping"):
        _request(config=[])

    with pytest.raises(TypeError, match="jobs must be a list"):
        _request(config={"jobs": ()})


def test_backtest_request_accepts_valid_job_references() -> None:
    request = _request(
        test_results={"newey_raw": {"summary": object()}},
        config={"jobs": [_job()]},
    )

    assert request.config["jobs"] == [_job()]


def test_backtest_request_requires_mapping_jobs() -> None:
    with pytest.raises(TypeError, match="every backtest job"):
        _request(config={"jobs": [object()]})


def test_backtest_request_rejects_duplicate_job_ids() -> None:
    with pytest.raises(ValueError, match="duplicate backtest job id"):
        _request(
            test_results={"newey_raw": {}},
            config={"jobs": [_job(), _job()]},
        )


@pytest.mark.parametrize("job_id", ["", " raw", "raw "])
def test_backtest_request_rejects_invalid_job_ids(job_id: str) -> None:
    with pytest.raises(ValueError, match="backtest job id"):
        _request(
            test_results={"newey_raw": {}},
            config={"jobs": [_job(id=job_id)]},
        )


def test_backtest_request_rejects_unknown_variant_reference() -> None:
    with pytest.raises(ValueError, match="unavailable variant 'missing'"):
        _request(
            test_results={"newey_raw": {}},
            config={"jobs": [_job(variant="missing")]},
        )


def test_backtest_request_rejects_unknown_selection_test() -> None:
    with pytest.raises(ValueError, match="unavailable selection test 'missing'"):
        _request(
            test_results={"newey_raw": {}},
            config={"jobs": [_job(selection_test="missing")]},
        )


def test_backtest_request_validates_optional_market_inputs() -> None:
    with pytest.raises(TypeError, match="market_cap"):
        _request(market_cap=object())

    with pytest.raises(TypeError, match="market_data"):
        _request(market_data=object())


def test_backtest_result_accepts_normalized_job_results() -> None:
    result = BacktestResult(
        job_results={"raw_quintile": {"status": "ok"}},
        metadata={"backend": "python"},
    )

    assert result.job_results["raw_quintile"]["status"] == "ok"
    assert result.metadata == {"backend": "python"}


def test_backtest_result_validates_ids_and_payloads() -> None:
    with pytest.raises(ValueError, match="job id"):
        BacktestResult(job_results={" bad": {}})

    with pytest.raises(TypeError, match="must be a mapping"):
        BacktestResult(job_results={"job": object()})  # type: ignore[dict-item]


def test_backtest_protocol_and_component_accept_valid_plugin() -> None:
    plugin = StubBacktestPlugin()

    assert isinstance(plugin, BacktestPlugin)
    component = BacktestComponent(
        id="python_quantile_backtest",
        plugin=plugin,
        metadata={"backend": "python"},
    )

    assert component.plugin is plugin
    assert component.requires_connection is False


def test_backtest_component_rejects_non_plugin() -> None:
    with pytest.raises(TypeError, match="BacktestPlugin"):
        BacktestComponent(id="invalid", plugin=object())  # type: ignore[arg-type]


def test_backtest_component_requires_declared_connection() -> None:
    with pytest.raises(ValueError, match="connection_ref is required"):
        BacktestComponent(
            id="remote_backtest",
            plugin=StubBacktestPlugin(),
            requires_connection=True,
        )


def test_backtest_component_rejects_invalid_connection_ref() -> None:
    with pytest.raises(ValueError, match="connection_ref"):
        BacktestComponent(
            id="remote_backtest",
            plugin=StubBacktestPlugin(),
            connection_ref=" remote",
        )


def test_python_backtest_plugin_delegates_to_existing_workflow(
    monkeypatch,
    tmp_path: Path,
) -> None:
    close = _close()
    variant = _variant()
    test_results = {"newey_raw": {"summary": object()}}
    config = {"jobs": [_job()]}
    constituents = object()
    market_cap = close * 1_000_000
    expected = {"raw_quintile": {"job": {"status": "ok"}}}
    observed: dict[str, object] = {}

    def fake_workflow(**kwargs):
        observed.update(kwargs)
        return expected

    monkeypatch.setattr(
        backtest_engine_module,
        "run_backtest_workflow",
        fake_workflow,
    )
    request = BacktestRequest(
        close=close,
        variants={"raw": variant},
        test_results=test_results,
        config=config,
        constituents=constituents,
        market_cap=market_cap,
    )

    result = PythonQuantileBacktestPlugin().run(
        request,
        _context(tmp_path),
    )

    assert result.job_results is expected
    assert result.metadata == {
        "backend": "python",
        "model": "vectorized_quantile",
    }
    assert observed == {
        "close": close,
        "variants": {"raw": variant},
        "test_results": test_results,
        "backtest_config": config,
        "constituents": constituents,
        "market_cap": market_cap,
    }


def test_backtest_component_validates_returned_job_ids(
    tmp_path: Path,
) -> None:
    class IncompletePlugin:
        def run(self, request, context):
            del request, context
            return BacktestResult(job_results={})

    request = _request(
        test_results={"newey_raw": {}},
        config={"jobs": [_job()]},
    )

    with pytest.raises(ValueError, match="missing=.*raw_quintile"):
        run_backtest_component(
            BacktestComponent(id="incomplete", plugin=IncompletePlugin()),
            request,
            _context(tmp_path),
        )


def test_backtest_component_rejects_wrong_return_type(
    tmp_path: Path,
) -> None:
    class InvalidPlugin:
        def run(self, request, context):
            del request, context
            return {}

    with pytest.raises(TypeError, match="expected BacktestResult"):
        run_backtest_component(
            BacktestComponent(id="invalid", plugin=InvalidPlugin()),
            _request(),
            _context(tmp_path),
        )


def test_python_backtest_factory_and_allowlisted_resolution() -> None:
    component = create_python_backtest_engine()

    assert component.id == "python_quantile_backtest"
    assert component.requires_connection is False
    assert component.connection_ref is None
    assert component.metadata == {
        "backend": "python",
        "model": "vectorized_quantile",
    }
    assert isinstance(component.plugin, PythonQuantileBacktestPlugin)

    resolved = resolve_backtest_component(
        PluginSpec(
            "quantmine.plugins.backtest_engines:"
            "create_python_backtest_engine"
        ),
        allowed_module_prefixes=("quantmine",),
    )
    assert resolved.id == "python_quantile_backtest"


def test_python_backtest_factory_rejects_unknown_parameters() -> None:
    with pytest.raises(ValueError, match="unsupported.*unexpected"):
        create_python_backtest_engine(unexpected=True)


def _position_request(**overrides: object) -> BacktestRequest:
    close = pd.DataFrame(
        {
            "AAA": [10.0, 11.0],
            "BBB": [20.0, 20.0],
        },
        index=pd.DatetimeIndex(["2026-09-17", "2026-09-18"]),
    )
    factor = pd.DataFrame(
        {
            "AAA": [1.0, 1.0],
            "BBB": [2.0, 2.0],
        },
        index=close.index,
    )
    values: dict[str, object] = {
        "close": close,
        "variants": {
            "raw": ICVariant(
                train={},
                test={
                    "factors": {"toy": factor},
                    "forward_returns": {1: close.pct_change().shift(-1)},
                },
                transforms=[],
            )
        },
        "test_results": {
            "newey_raw": {
                "summary": pd.DataFrame(),
                "multiple_testing": None,
                "test_method": "newey_test",
                "sample_scope": "train",
            }
        },
        "config": {
            "initial_cash": 5_000.0,
            "gross_exposure": 0.9,
            "jobs": [
                {
                    "id": "raw_quintile",
                    "variant": "raw",
                    "selection_test": "newey_raw",
                    "part": 2,
                    "cost_per_trade": 0.0,
                    "selector": {"name": "bh", "params": {}},
                }
            ],
        },
        "market_rules": create_unrestricted_market_rules(),
    }
    values.update(overrides)
    return BacktestRequest(**values)  # type: ignore[arg-type]


def test_position_backtest_plugin_requires_market_rules(
    tmp_path: Path,
) -> None:
    request = _position_request(market_rules=None)

    with pytest.raises(ValueError, match="market-rules"):
        PythonPositionBacktestPlugin().run(
            request,
            _context(tmp_path),
        )


def test_position_backtest_plugin_handles_no_significant_factor(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        backtest_engine_module,
        "run_backtest_job",
        lambda **kwargs: {
            "status": "no_significant_factor",
            "selected_factor_periods": [],
            "ticker_history": {},
        },
    )
    monkeypatch.setattr(
        backtest_engine_module,
        "run_position_backtest",
        lambda **kwargs: pytest.fail(
            "position loop must not run without a selected factor"
        ),
    )

    result = PythonPositionBacktestPlugin().run(
        _position_request(),
        _context(tmp_path),
    )

    assert result.job_results == {
        "raw_quintile": {
            "status": "no_significant_factor",
            "selected_factor_periods": [],
            "group": None,
            "portfolio_results": {},
            "ticker_history": {},
        }
    }


def test_position_backtest_plugin_bridges_membership_to_position_loop(
    monkeypatch,
    tmp_path: Path,
) -> None:
    request = _position_request()
    dates = request.close.index
    history = [
        {
            "date": dates[0],
            "Q1": {"AAA": 1.0},
            "Q2": {"BBB": 1.0},
        }
    ]
    observed: dict[str, object] = {}
    position_result = object()

    def fake_membership_job(**kwargs):
        observed["membership_kwargs"] = kwargs
        return {
            "status": "ok",
            "selected_factor_periods": [("toy", 1)],
            "ticker_history": {("toy", 1): history},
        }

    def fake_position_backtest(**kwargs):
        observed["position_kwargs"] = kwargs
        return position_result

    monkeypatch.setattr(
        backtest_engine_module,
        "run_backtest_job",
        fake_membership_job,
    )
    monkeypatch.setattr(
        backtest_engine_module,
        "run_position_backtest",
        fake_position_backtest,
    )

    result = PythonPositionBacktestPlugin().run(
        request,
        _context(tmp_path),
    )

    job_result = result.job_results["raw_quintile"]
    assert job_result["status"] == "ok"
    assert job_result["group"] == "Q2"
    assert job_result["gross_exposure"] == 0.9
    assert job_result["initial_cash"] == 5_000.0
    assert job_result["portfolio_results"] == {
        ("toy", 1): position_result
    }
    assert result.metadata == {
        "backend": "python",
        "model": "position_based",
        "market_rules": "unrestricted_market_rules",
    }

    membership_kwargs = observed["membership_kwargs"]
    assert membership_kwargs["close"] is request.close
    assert membership_kwargs["variant"] is request.variants["raw"]
    assert membership_kwargs["constituents"] is None

    position_kwargs = observed["position_kwargs"]
    assert position_kwargs["close"].equals(request.close)
    assert position_kwargs["target_weights"].iloc[0].to_dict() == {
        "AAA": 0.0,
        "BBB": 0.9,
    }
    assert position_kwargs["initial_cash"] == 5_000.0
    assert position_kwargs["component"] is request.market_rules
    assert position_kwargs["market_state_provider"] is None


def test_python_position_backtest_factory_and_resolution() -> None:
    component = create_python_position_backtest_engine()

    assert component.id == "python_position_backtest"
    assert component.requires_connection is False
    assert component.connection_ref is None
    assert component.metadata == {
        "backend": "python",
        "model": "position_based",
    }
    assert isinstance(component.plugin, PythonPositionBacktestPlugin)

    resolved = resolve_backtest_component(
        PluginSpec(
            "quantmine.plugins.backtest_engines:"
            "create_python_position_backtest_engine"
        ),
        allowed_module_prefixes=("quantmine",),
    )
    assert resolved.id == "python_position_backtest"


def test_position_backtest_plugin_applies_a_stock_rules_end_to_end(
    monkeypatch,
    tmp_path: Path,
) -> None:
    class OpenMarketStateProvider:
        def status_on(self, trade_date, ticker):
            del trade_date, ticker
            return {
                "is_suspended": False,
                "is_limit_up": False,
                "is_limit_down": False,
            }

    base_request = _position_request()
    dates = base_request.close.index
    request = _position_request(
        market_rules=create_a_stock_market_rules(market="CN"),
        market_state_provider=OpenMarketStateProvider(),
    )
    monkeypatch.setattr(
        backtest_engine_module,
        "run_backtest_job",
        lambda **kwargs: {
            "status": "ok",
            "selected_factor_periods": [("toy", 1)],
            "ticker_history": {
                ("toy", 1): [
                    {
                        "date": dates[0],
                        "Q1": {"BBB": 1.0},
                        "Q2": {"AAA": 1.0},
                    },
                    {
                        "date": dates[1],
                        "Q1": {"AAA": 1.0},
                        "Q2": {"BBB": 1.0},
                    },
                ]
            },
        },
    )

    result = PythonPositionBacktestPlugin().run(
        request,
        _context(tmp_path),
    )

    portfolio = result.job_results["raw_quintile"][
        "portfolio_results"
    ][("toy", 1)]
    assert portfolio.positions["AAA"].tolist() == [400.0, 0.0]
    assert portfolio.positions["BBB"].tolist() == [0.0, 200.0]
    assert portfolio.executed_shares["AAA"].tolist() == [400.0, -400.0]
    assert portfolio.executed_shares["BBB"].tolist() == [0.0, 200.0]
    assert portfolio.fees.sum().sum() > 0
    assert portfolio.final_state.cash >= 0


def test_python_position_backtest_factory_rejects_unknown_parameters() -> None:
    with pytest.raises(ValueError, match="unsupported.*unexpected"):
        create_python_position_backtest_engine(unexpected=True)
