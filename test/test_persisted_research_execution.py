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
    execute_persisted_research,
    required_research_connection_refs,
)
from quantmine.plugins import builtins as builtin_plugins
from quantmine.plugins import us_equity as us_equity_plugins
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
from quantmine.research_config import ResearchRunConfig


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

    assert required_research_connection_refs(
        _connection_config("shared_service", None),
        ic_component=ic_component,
        validation_component=validation_component,
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
