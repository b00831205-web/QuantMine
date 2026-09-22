"""Tests for executing one persisted research configuration locally."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import ClassVar

import pandas as pd
import pytest

from quantmine import execution as execution_module
from quantmine.datareader import MarketData
from quantmine.execution import (
    build_backtest_request,
    execute_persisted_research,
    required_research_connection_refs,
)
from quantmine.ic_calculator import ICVariant
from quantmine.plugins import builtins as builtin_plugins
from quantmine.plugins import us_equity as us_equity_plugins
from quantmine.plugins.backtest_engines import (
    BacktestComponent,
    BacktestResult,
    PythonQuantileBacktestPlugin,
)
from quantmine.plugins.bundles import ResearchBundle
from quantmine.plugins.context import SourceContext
from quantmine.plugins.contracts import (
    DataBinding,
    DataSourceComponent,
    FactorPackComponent,
    MarketDataBundle,
    MarketDataCapability,
    PluginSpec,
    VersionedDatasetBinding,
)
from quantmine.plugins.ic_engines import (
    ICCalculationComponent,
    PythonICCalculationPlugin,
)
from quantmine.plugins.ic_validators import (
    ICValidationComponent,
    PythonICValidationPlugin,
)
from quantmine.plugins.market_rules import (
    MarketRulesComponent,
    UnrestrictedMarketRulesPlugin,
)
from quantmine.research_config import ResearchRunConfig
from quantmine.workflows.ic_research_artifacts import (
    ICResearchArtifacts,
    ICResearchPublication,
)
from quantmine.workflows.portfolio_execution import PortfolioState
from quantmine.workflows.position_backtest import PositionBacktestResult


class InMemoryStore:
    def __init__(self, config: ResearchRunConfig) -> None:
        self.config = config

    def create(
        self,
        config: ResearchRunConfig,
        *,
        git_commit: str | None = None,
    ) -> int:
        self.config = config
        return 701

    def load(self, run_id: int) -> ResearchRunConfig:
        assert run_id == 701
        return self.config


class InMemoryPlugin:
    def load(
        self,
        binding: DataBinding,
        context: SourceContext,
    ) -> MarketDataBundle:
        dates = pd.date_range("2024-01-01", periods=5, freq="B")
        return MarketDataBundle(
            market=MarketData(
                close=pd.DataFrame(
                    {"AAA": [10.0, 11.0, 12.0, 13.0, 14.0]},
                    index=dates,
                )
            )
        )


class DisposableConnections:
    def __init__(self) -> None:
        self.disposed = False

    def dispose(self) -> None:
        self.disposed = True


class StubMarketStateProvider:
    def __init__(self, name: str) -> None:
        self.name = name

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


class StubMembershipUniverse:
    def get_constituents(self, date: pd.Timestamp) -> list[str]:
        del date
        return ["AAA"]


class FixtureYFinanceSource:
    """Offline replacement that records the legacy Yahoo source request."""

    calls: ClassVar[list[tuple[tuple[str, ...], str, str]]] = []

    def __init__(self, **_: object) -> None:
        pass

    def load(
        self,
        tickers: list[str],
        start: str,
        end: str,
    ) -> MarketData:
        type(self).calls.append((tuple(tickers), start, end))
        dates = pd.date_range("2024-01-01", periods=30, freq="B")
        close = pd.DataFrame(
            {
                "AAA": range(100, 130),
                "BBB": range(200, 230),
                "SPY": range(300, 330),
            },
            index=dates,
            dtype=float,
        )
        volume = pd.DataFrame(
            {
                "AAA": range(1_000, 1_030),
                "BBB": range(2_000, 2_030),
                "SPY": range(3_000, 3_030),
            },
            index=dates,
            dtype=float,
        )
        return MarketData(close=close, volume=volume)


def create_execution_test_source() -> DataSourceComponent:
    return DataSourceComponent(
        id="execution_test_source",
        capabilities=frozenset({MarketDataCapability.CLOSE}),
        plugin=InMemoryPlugin(),
    )


def create_execution_test_factor_pack() -> FactorPackComponent:
    return FactorPackComponent(
        id="execution_test_factor_pack",
        requires=frozenset({MarketDataCapability.CLOSE}),
        signals=("momentum",),
    )


def _connection_config(
    market_connection_ref: str | None,
    eligibility_connection_ref: str | None,
) -> ResearchRunConfig:
    eligibility_binding = (
        None
        if eligibility_connection_ref is None
        else VersionedDatasetBinding(
            connection_ref=eligibility_connection_ref,
            dataset="daily_eligibility",
            market="CN",
            version="20260910",
        )
    )
    return ResearchRunConfig(
        bundle=ResearchBundle(
            id="connection_test_bundle",
            display_name="Connection test bundle",
            data_source=PluginSpec(
                "test_persisted_research_execution:create_execution_test_source"
            ),
            universe=None,
            factor_packs=(
                PluginSpec(
                    "test_persisted_research_execution:"
                    "create_execution_test_factor_pack"
                ),
            ),
        ),
        data_binding=DataBinding(
            connection_ref=market_connection_ref,
            dataset="prices",
            eligibility_binding=eligibility_binding,
        ),
        factor_parameters={},
    )


def _ic_artifacts(tmp_path: Path) -> ICResearchArtifacts:
    return ICResearchArtifacts(
        publication=ICResearchPublication(
            run_id=701,
            output_dir=tmp_path / "ic_research" / "701",
            manifest_path=(
                tmp_path / "ic_research" / "701" / "manifest.json"
            ),
            variant_count=1,
            test_count=0,
            variant_names=("raw",),
            test_ids=(),
        ),
        variants={"raw": ICVariant(train={}, test={}, transforms=[])},
        test_results={},
    )


def _market_rules_component() -> MarketRulesComponent:
    return MarketRulesComponent(
        id="unrestricted_market_rules",
        plugin=UnrestrictedMarketRulesPlugin(),
        market="US",
    )


def _position_backtest_result() -> PositionBacktestResult:
    dates = pd.DatetimeIndex(["2026-09-17", "2026-09-18"])
    columns = pd.Index(["AAA"])
    numeric = pd.DataFrame([[1.0], [1.0]], index=dates, columns=columns)
    shares = pd.DataFrame([[10.0], [0.0]], index=dates, columns=columns)

    return PositionBacktestResult(
        equity_curve=pd.Series([1_000.0, 1_010.0], index=dates, name="equity"),
        daily_returns=pd.Series([float("nan"), 0.01], index=dates, name="return"),
        cash_curve=pd.Series([900.0, 900.0], index=dates, name="cash"),
        positions=shares,
        sellable_positions=shares,
        requested_shares=shares,
        executed_shares=shares,
        fees=numeric,
        reasons=pd.DataFrame([[""], [""]], index=dates, columns=columns),
        final_state=PortfolioState(
            positions=pd.Series([1.0], index=columns),
            sellable_positions=pd.Series([1.0], index=columns),
            cash=900.0,
        ),
        valuation_prices=numeric,
        tradable=pd.DataFrame([[True], [True]], index=dates, columns=columns),
        price_sources=pd.DataFrame(
            [["observed"], ["observed"]],
            index=dates,
            columns=columns,
        ),
    )


def test_build_backtest_request_preserves_verified_inputs(
    tmp_path: Path,
) -> None:
    close = pd.DataFrame(
        {"AAA": [10.0, 11.0]},
        index=pd.date_range("2026-09-17", periods=2, freq="B"),
    )
    market_cap = close * 1_000_000
    universe = StubMembershipUniverse()
    market_data = MarketDataBundle(
        market=MarketData(close=close, market_cap=market_cap),
        universe=universe,
    )
    artifacts = _ic_artifacts(tmp_path)
    market_rules = _market_rules_component()

    request = build_backtest_request(
        _connection_config(None, None),
        market_data,
        artifacts,
        market_rules,
    )

    assert request.close is close
    assert request.market_cap is market_cap
    assert request.market_data is market_data
    assert request.variants is artifacts.variants
    assert request.test_results is artifacts.test_results
    assert request.constituents is universe
    assert request.market_rules is market_rules
    assert request.market_state_provider is None


def test_build_backtest_request_discovers_bundle_market_state_provider(
    tmp_path: Path,
) -> None:
    provider = StubMarketStateProvider("bundle")
    market_data = MarketDataBundle(
        market=MarketData(close=pd.DataFrame({"AAA": [10.0]})),
        universe=provider,
    )

    request = build_backtest_request(
        _connection_config(None, None),
        market_data,
        _ic_artifacts(tmp_path),
        _market_rules_component(),
    )

    assert request.constituents is provider
    assert request.market_state_provider is provider


def test_build_backtest_request_prefers_explicit_market_state_provider(
    tmp_path: Path,
) -> None:
    bundle_provider = StubMarketStateProvider("bundle")
    explicit_provider = StubMarketStateProvider("explicit")
    market_data = MarketDataBundle(
        market=MarketData(close=pd.DataFrame({"AAA": [10.0]})),
        universe=bundle_provider,
    )

    request = build_backtest_request(
        _connection_config(None, None),
        market_data,
        _ic_artifacts(tmp_path),
        _market_rules_component(),
        market_state_provider=explicit_provider,
    )

    assert request.constituents is bundle_provider
    assert request.market_state_provider is explicit_provider


def test_build_backtest_request_requires_close_prices(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="close"):
        build_backtest_request(
            _connection_config(None, None),
            MarketDataBundle(market=MarketData()),
            _ic_artifacts(tmp_path),
            _market_rules_component(),
        )


def test_required_research_connections_supports_connection_free_source() -> None:
    assert required_research_connection_refs(
        _connection_config(None, None)
    ) == ()


def test_required_research_connections_includes_market_connection() -> None:
    assert required_research_connection_refs(
        _connection_config("cn_market", None)
    ) == ("cn_market",)


def test_required_research_connections_includes_eligibility_connection() -> None:
    assert required_research_connection_refs(
        _connection_config("cn_market", "cn_eligibility")
    ) == ("cn_market", "cn_eligibility")


def test_required_research_connections_deduplicates_aliases() -> None:
    assert required_research_connection_refs(
        _connection_config("cn_lake", "cn_lake")
    ) == ("cn_lake",)


def test_required_research_connections_include_engine_components() -> None:
    ic_component = ICCalculationComponent(
        id="remote_ic",
        plugin=PythonICCalculationPlugin(),
        connection_ref="ic_service",
        requires_connection=True,
    )
    validation_component = ICValidationComponent(
        id="remote_validation",
        plugin=PythonICValidationPlugin(),
        connection_ref="validation_service",
        requires_connection=True,
    )

    assert required_research_connection_refs(
        _connection_config("cn_market", "cn_eligibility"),
        ic_component=ic_component,
        validation_component=validation_component,
    ) == (
        "cn_market",
        "cn_eligibility",
        "ic_service",
        "validation_service",
    )


def test_required_research_connections_include_backtest_components() -> None:
    backtest_component = BacktestComponent(
        id="remote_backtest",
        plugin=PythonQuantileBacktestPlugin(),
        connection_ref="backtest_service",
        requires_connection=True,
    )
    market_rules_component = MarketRulesComponent(
        id="remote_market_rules",
        plugin=UnrestrictedMarketRulesPlugin(),
        market="CN",
        connection_ref="market_rules_service",
        requires_connection=True,
    )

    assert required_research_connection_refs(
        _connection_config("cn_market", "cn_eligibility"),
        backtest_component=backtest_component,
        market_rules_component=market_rules_component,
    ) == (
        "cn_market",
        "cn_eligibility",
        "backtest_service",
        "market_rules_service",
    )


def test_required_research_connections_deduplicate_engine_aliases() -> None:
    ic_component = ICCalculationComponent(
        id="remote_ic",
        plugin=PythonICCalculationPlugin(),
        connection_ref="shared_service",
    )
    validation_component = ICValidationComponent(
        id="remote_validation",
        plugin=PythonICValidationPlugin(),
        connection_ref="shared_service",
    )
    backtest_component = BacktestComponent(
        id="remote_backtest",
        plugin=PythonQuantileBacktestPlugin(),
        connection_ref="shared_service",
    )
    market_rules_component = MarketRulesComponent(
        id="remote_market_rules",
        plugin=UnrestrictedMarketRulesPlugin(),
        market="CN",
        connection_ref="shared_service",
    )

    assert required_research_connection_refs(
        _connection_config("shared_service", None),
        ic_component=ic_component,
        validation_component=validation_component,
        backtest_component=backtest_component,
        market_rules_component=market_rules_component,
    ) == ("shared_service",)


def test_persisted_run_execution_uses_env_connections_and_configured_plugins(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("QUANTMINE_CONNECTION_TEST_CONNECTION_KIND", "parquet")
    monkeypatch.setenv("QUANTMINE_CONNECTION_TEST_CONNECTION_ROOT", str(tmp_path))

    config = ResearchRunConfig(
        bundle=ResearchBundle(
            id="execution_test_bundle",
            display_name="Execution test bundle",
            data_source=PluginSpec(
                "test_persisted_research_execution:create_execution_test_source"
            ),
            universe=None,
            factor_packs=(
                PluginSpec(
                    "test_persisted_research_execution:"
                    "create_execution_test_factor_pack"
                ),
            ),
        ),
        data_binding=DataBinding(
            connection_ref="test_connection",
            dataset="in_memory_prices",
            tickers=("AAA",),
        ),
        factor_parameters={"day": 2},
    )

    result = execute_persisted_research(
        InMemoryStore(config),
        701,
        artifact_root=tmp_path / "artifacts",
        allowed_module_prefixes=(
            "quantmine",
            "test_persisted_research_execution",
        ),
    )

    assert set(result.factors) == {"momentum"}
    assert (tmp_path / "artifacts" / "701").is_dir()
    publication_dir = tmp_path / "artifacts" / "factor_research" / "701"
    assert (publication_dir / "manifest.json").is_file()
    assert (publication_dir / "momentum.parquet").is_file()


def test_default_us_bundle_runs_end_to_end_with_the_legacy_source_adapter(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """The default US bundle remains executable after config persistence.

    Yahoo Finance itself is replaced only at the network boundary.  The test
    still resolves the production bundle, uses the legacy-source adapter, and
    executes its real registered technical factors.
    """

    FixtureYFinanceSource.calls.clear()
    monkeypatch.setattr(builtin_plugins, "YFinanceSource", FixtureYFinanceSource)
    monkeypatch.setattr(us_equity_plugins, "YFinanceSource", FixtureYFinanceSource)

    original_config = ResearchRunConfig.from_bundle_id(
        "us_equity_v1",
        DataBinding(
            connection_ref=None,
            dataset="us_daily_prices",
            start="2024-01-01",
            end="2024-02-09",
            tickers=("AAA", "BBB", "SPY"),
        ),
        factor_parameters={"day": 5, "halflife": 2, "period": 3},
    )
    persisted_config = ResearchRunConfig.from_snapshot(
        original_config.to_snapshot())

    result = execute_persisted_research(
        InMemoryStore(persisted_config),
        701,
        artifact_root=tmp_path / "artifacts",
    )

    assert FixtureYFinanceSource.calls == [
        (("AAA", "BBB", "SPY"), "2024-01-01", "2024-02-09")
    ]
    assert result.requested_signals == (
        "momentum",
        "ShortTermReversal",
        "TwentyDayVolatility",
        "TwentyDayNegVotality",
        "TwentyDayAvgVol",
        "VolPriceCorr",
    )
    assert not result.pending
    assert set(result.factors) == set(result.requested_signals)
    assert (tmp_path / "artifacts" / "701").is_dir()
    publication_dir = tmp_path / "artifacts" / "factor_research" / "701"
    assert (publication_dir / "manifest.json").is_file()
    assert {
        path.name
        for path in publication_dir.glob("*.parquet")
    } == {
        f"{signal}.parquet"
        for signal in result.requested_signals
    }


def test_persisted_ic_execution_loads_one_run_snapshot_and_verified_inputs(
    monkeypatch,
    tmp_path: Path,
) -> None:
    config = _connection_config("cn_market", "cn_eligibility")
    config = ResearchRunConfig(
        bundle=config.bundle,
        data_binding=config.data_binding,
        factor_parameters=config.factor_parameters,
        ic_engine=config.ic_engine,
        ic_research={
            "train_end": "2026-06-30",
            "test_start": "2026-07-01",
            "periods": [1, 5],
            "processors": [],
            "tests": [],
        },
    )
    connections = DisposableConnections()
    dates = pd.date_range("2026-01-02", periods=5, freq="B")
    close = pd.DataFrame(
        {"000001": [10.0, 10.2, 10.1, 10.4, 10.5]},
        index=dates,
    )
    factor = close.pct_change()
    resolved_bundle = object()
    observed: dict[str, object] = {}
    ic_component = ICCalculationComponent(
        id="remote_ic",
        plugin=PythonICCalculationPlugin(),
        connection_ref="ic_service",
        requires_connection=True,
    )
    validation_component = ICValidationComponent(
        id="remote_validation",
        plugin=PythonICValidationPlugin(),
        connection_ref="validation_service",
        requires_connection=True,
    )

    monkeypatch.setattr(
        execution_module,
        "resolve_ic_calculation_component",
        lambda spec, *, allowed_module_prefixes: (
            observed.update(
                ic_spec=spec,
                ic_allowlist=allowed_module_prefixes,
            )
            or ic_component
        ),
    )
    monkeypatch.setattr(
        execution_module,
        "resolve_ic_validation_component",
        lambda spec, *, allowed_module_prefixes: (
            observed.update(
                validation_spec=spec,
                validation_allowlist=allowed_module_prefixes,
            )
            or validation_component
        ),
    )

    monkeypatch.setattr(
        execution_module.ConnectionRegistry,
        "from_environment",
        lambda refs: observed.update(connection_refs=refs) or connections,
    )
    monkeypatch.setattr(
        execution_module,
        "resolve_research_bundle_definition",
        lambda definition, *, allowed_module_prefixes: (
            observed.update(
                bundle_definition=definition,
                bundle_allowlist=allowed_module_prefixes,
            )
            or resolved_bundle
        ),
        raising=False,
    )
    monkeypatch.setattr(
        execution_module,
        "load_research_market_data",
        lambda bundle, binding, context: (
            observed.update(
                resolved_bundle=bundle,
                binding=binding,
                market_context=context,
            )
            or MarketDataBundle(market=MarketData(close=close))
        ),
        raising=False,
    )
    monkeypatch.setattr(
        execution_module,
        "load_factor_research_artifacts",
        lambda *, root, run_id: (
            observed.update(factor_root=root, factor_run_id=run_id)
            or SimpleNamespace(factors={"momentum": factor})
        ),
        raising=False,
    )
    monkeypatch.setattr(
        execution_module,
        "run_persisted_ic_workflow",
        lambda **kwargs: (
            observed.update(workflow_kwargs=kwargs)
            or ({"raw": object()}, {"newey_raw": object()})
        ),
        raising=False,
    )
    monkeypatch.setattr(
        execution_module,
        "publish_ic_research_artifacts",
        lambda variants, test_results, *, run_id, root: observed.update(
            published_variants=variants,
            published_test_results=test_results,
            publication_run_id=run_id,
            publication_root=root,
        ),
        raising=False,
    )

    variants, test_results = execution_module.execute_persisted_ic_research(
        InMemoryStore(config),
        701,
        artifact_root=tmp_path / "artifacts",
        allowed_module_prefixes=("quantmine", "vendor_ic"),
    )

    assert set(variants) == {"raw"}
    assert set(test_results) == {"newey_raw"}
    assert observed["connection_refs"] == (
        "cn_market",
        "cn_eligibility",
        "ic_service",
        "validation_service",
    )
    assert observed["bundle_definition"] == config.bundle
    assert observed["bundle_allowlist"] == ("quantmine", "vendor_ic")
    assert observed["resolved_bundle"] is resolved_bundle
    assert observed["binding"] == config.data_binding
    assert observed["factor_root"] == tmp_path / "artifacts" / "factor_research"
    assert observed["factor_run_id"] == 701

    workflow_kwargs = observed["workflow_kwargs"]
    assert workflow_kwargs["config"] == config
    assert workflow_kwargs["close"] is close
    assert workflow_kwargs["factors"]["momentum"] is factor
    assert workflow_kwargs["context"] is observed["market_context"]
    assert workflow_kwargs["membership"] is None
    assert workflow_kwargs["allowed_module_prefixes"] == (
        "quantmine",
        "vendor_ic",
    )
    assert workflow_kwargs["ic_component"] is ic_component
    assert workflow_kwargs["validation_component"] is validation_component
    assert observed["published_variants"] is variants
    assert observed["published_test_results"] is test_results
    assert observed["publication_run_id"] == 701
    assert observed["publication_root"] == (
        tmp_path / "artifacts" / "ic_research"
    )
    assert connections.disposed is True


def test_persisted_ic_execution_disposes_connections_when_workflow_fails(
    monkeypatch,
    tmp_path: Path,
) -> None:
    config = _connection_config(None, None)
    config = ResearchRunConfig(
        bundle=config.bundle,
        data_binding=config.data_binding,
        factor_parameters=config.factor_parameters,
        ic_engine=config.ic_engine,
        ic_research={"periods": [1]},
    )
    connections = DisposableConnections()

    monkeypatch.setattr(
        execution_module.ConnectionRegistry,
        "from_environment",
        lambda refs: connections,
    )
    monkeypatch.setattr(
        execution_module,
        "resolve_research_bundle_definition",
        lambda *args, **kwargs: object(),
        raising=False,
    )
    monkeypatch.setattr(
        execution_module,
        "load_research_market_data",
        lambda *args, **kwargs: MarketDataBundle(
            market=MarketData(
                close=pd.DataFrame(
                    {"AAA": [1.0]},
                    index=pd.date_range("2026-01-02", periods=1),
                )
            )
        ),
        raising=False,
    )
    monkeypatch.setattr(
        execution_module,
        "load_factor_research_artifacts",
        lambda **kwargs: SimpleNamespace(
            factors={"momentum": pd.DataFrame({"AAA": [1.0]})}
        ),
        raising=False,
    )
    monkeypatch.setattr(
        execution_module,
        "run_persisted_ic_workflow",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("IC failed")),
        raising=False,
    )

    with pytest.raises(RuntimeError, match="IC failed"):
        execution_module.execute_persisted_ic_research(
            InMemoryStore(config),
            701,
            artifact_root=tmp_path / "artifacts",
        )

    assert connections.disposed is True


def test_persisted_backtest_execution_resolves_and_runs_components(
    monkeypatch,
    tmp_path: Path,
) -> None:
    config = _connection_config("cn_market", "cn_eligibility")
    connections = DisposableConnections()
    observed: dict[str, object] = {}
    close = pd.DataFrame(
        {"AAA": [10.0, 11.0]},
        index=pd.date_range("2026-09-17", periods=2, freq="B"),
    )
    provider = StubMarketStateProvider("bundle")
    market_data = MarketDataBundle(
        market=MarketData(close=close),
        universe=provider,
    )
    ic_artifacts = _ic_artifacts(tmp_path)
    backtest_component = BacktestComponent(
        id="remote_backtest",
        plugin=PythonQuantileBacktestPlugin(),
        connection_ref="backtest_service",
        requires_connection=True,
    )
    market_rules_component = MarketRulesComponent(
        id="remote_market_rules",
        plugin=UnrestrictedMarketRulesPlugin(),
        market="CN",
        connection_ref="market_rules_service",
        requires_connection=True,
    )
    expected = BacktestResult(
        job_results={},
        metadata={"backend": "stub"},
    )

    monkeypatch.setattr(
        execution_module,
        "resolve_backtest_component",
        lambda spec, *, allowed_module_prefixes: (
            observed.update(
                backtest_spec=spec,
                backtest_allowlist=allowed_module_prefixes,
            )
            or backtest_component
        ),
    )
    monkeypatch.setattr(
        execution_module,
        "resolve_market_rules_component",
        lambda spec, *, allowed_module_prefixes: (
            observed.update(
                market_rules_spec=spec,
                market_rules_allowlist=allowed_module_prefixes,
            )
            or market_rules_component
        ),
    )
    monkeypatch.setattr(
        execution_module.ConnectionRegistry,
        "from_environment",
        lambda refs: observed.update(connection_refs=refs) or connections,
    )
    monkeypatch.setattr(
        execution_module,
        "resolve_research_bundle_definition",
        lambda definition, *, allowed_module_prefixes: (
            observed.update(
                bundle_definition=definition,
                bundle_allowlist=allowed_module_prefixes,
            )
            or object()
        ),
    )
    monkeypatch.setattr(
        execution_module,
        "load_research_market_data",
        lambda bundle, binding, context: (
            observed.update(
                resolved_bundle=bundle,
                binding=binding,
                market_context=context,
            )
            or market_data
        ),
    )
    monkeypatch.setattr(
        execution_module,
        "load_ic_research_artifacts",
        lambda *, root, run_id: (
            observed.update(ic_root=root, ic_run_id=run_id)
            or ic_artifacts
        ),
    )
    monkeypatch.setattr(
        execution_module,
        "run_backtest_component",
        lambda component, request, context: (
            observed.update(
                executed_component=component,
                request=request,
                execution_context=context,
            )
            or expected
        ),
    )

    actual = execution_module.execute_persisted_backtest(
        InMemoryStore(config),
        701,
        artifact_root=tmp_path / "artifacts",
        allowed_module_prefixes=("quantmine", "vendor_backtest"),
    )

    assert actual is expected
    assert observed["backtest_spec"] == config.backtest_engine
    assert observed["market_rules_spec"] == config.market_rules
    assert observed["backtest_allowlist"] == (
        "quantmine",
        "vendor_backtest",
    )
    assert observed["market_rules_allowlist"] == (
        "quantmine",
        "vendor_backtest",
    )
    assert observed["connection_refs"] == (
        "cn_market",
        "cn_eligibility",
        "backtest_service",
        "market_rules_service",
    )
    assert observed["bundle_definition"] == config.bundle
    assert observed["binding"] == config.data_binding
    assert observed["ic_root"] == tmp_path / "artifacts" / "ic_research"
    assert observed["ic_run_id"] == 701
    assert observed["executed_component"] is backtest_component
    assert observed["execution_context"] is observed["market_context"]

    request = observed["request"]
    assert request.market_data is market_data
    assert request.market_rules is market_rules_component
    assert request.market_state_provider is provider
    assert request.variants is ic_artifacts.variants
    assert request.test_results is ic_artifacts.test_results
    assert connections.disposed is True


def test_persisted_backtest_execution_disposes_connections_on_failure(
    monkeypatch,
    tmp_path: Path,
) -> None:
    config = _connection_config(None, None)
    connections = DisposableConnections()

    monkeypatch.setattr(
        execution_module.ConnectionRegistry,
        "from_environment",
        lambda refs: connections,
    )
    monkeypatch.setattr(
        execution_module,
        "load_ic_research_artifacts",
        lambda **kwargs: _ic_artifacts(tmp_path),
    )
    monkeypatch.setattr(
        execution_module,
        "run_backtest_component",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            RuntimeError("backtest failed")
        ),
    )

    with pytest.raises(RuntimeError, match="backtest failed"):
        execution_module.execute_persisted_backtest(
            InMemoryStore(config),
            701,
            artifact_root=tmp_path / "artifacts",
            allowed_module_prefixes=(
                "quantmine",
                "test_persisted_research_execution",
            ),
        )

    assert connections.disposed is True


def test_position_backtest_outputs_are_published_and_run_is_indexed(
    monkeypatch,
    tmp_path: Path,
) -> None:
    first = _position_backtest_result()
    second = _position_backtest_result()
    result = BacktestResult(
        job_results={
            "top_quantile": {
                "portfolio_results": {
                    ("momentum", 5): first,
                    ("value", 20): second,
                }
            }
        }
    )
    observed: dict[str, object] = {}

    monkeypatch.setattr(
        execution_module,
        "publish_position_backtest_artifact",
        lambda portfolio_result, **kwargs: (
            observed.setdefault("publications", []).append(
                (portfolio_result, kwargs)
            )
            or SimpleNamespace(**kwargs)
        ),
    )
    monkeypatch.setattr(
        execution_module,
        "publish_position_backtest_run_manifest",
        lambda **kwargs: observed.update(run_manifest=kwargs),
    )

    publications = execution_module._publish_position_backtest_results(
        result,
        run_id=701,
        root=tmp_path / "position_backtests",
    )

    assert len(publications) == 2
    assert observed["publications"] == [
        (
            first,
            {
                "run_id": 701,
                "job_id": "top_quantile",
                "factor_name": "momentum",
                "period": 5,
                "root": tmp_path / "position_backtests",
            },
        ),
        (
            second,
            {
                "run_id": 701,
                "job_id": "top_quantile",
                "factor_name": "value",
                "period": 20,
                "root": tmp_path / "position_backtests",
            },
        ),
    ]
    assert observed["run_manifest"] == {
        "root": tmp_path / "position_backtests",
        "run_id": 701,
    }


def test_legacy_backtest_outputs_do_not_publish_position_artifacts(
    monkeypatch,
    tmp_path: Path,
) -> None:
    result = BacktestResult(
        job_results={
            "legacy": {
                "portfolio_results": {
                    ("momentum", 5): {"annual_return": 0.1},
                }
            }
        }
    )

    monkeypatch.setattr(
        execution_module,
        "publish_position_backtest_artifact",
        lambda *args, **kwargs: pytest.fail("legacy output was published"),
    )
    monkeypatch.setattr(
        execution_module,
        "publish_position_backtest_run_manifest",
        lambda *args, **kwargs: pytest.fail("legacy run was indexed"),
    )

    assert execution_module._publish_position_backtest_results(
        result,
        run_id=701,
        root=tmp_path / "position_backtests",
    ) == ()
