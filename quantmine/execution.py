from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from .plugins.backtest_engines import BacktestComponent, BacktestRequest
from .plugins.bundles import resolve_research_bundle_definition
from .plugins.context import SourceContext
from .plugins.contracts import MarketDataBundle
from .plugins.ic_engines import (
    ICCalculationComponent,
    resolve_ic_calculation_component,
)
from .plugins.ic_validators import (
    ICValidationComponent,
    resolve_ic_validation_component,
)
from .plugins.market_rules import MarketRulesComponent, MarketStateProvider
from .plugins.backtest_engines import BacktestRequest, BacktestResult, BacktestComponent, resolve_backtest_component, run_backtest_component
from .plugins.market_rules import MarketRulesComponent, MarketStateProvider, resolve_market_rules_component
from .research import (
    FactorResearchResult,
    load_research_market_data,
    run_configured_research,
)
from .research_config import ResearchRunConfig
from .storage.connections import ConnectionRegistry
from .storage.runs import ResearchRunStore
from .workflows.factor_research_artifacts import (
    load_factor_research_artifacts,
    publish_factor_research_artifacts,
)
from .workflows.ic import run_persisted_ic_workflow
from .workflows.ic_research_artifacts import (
    publish_ic_research_artifacts,
    ICResearchArtifacts,
    load_ic_research_artifacts,
)



def execute_persisted_research(
        store: ResearchRunStore,
        run_id: int,
        *,
        artifact_root: Path,
        allowed_module_prefixes: Iterable[str] | None = ("quantmine",),
) -> FactorResearchResult:
    """Execute one persisted run through the shared plugin pipeline.

    The configuration supplies only a connection alias. The registry resolves
    its actual DSN or Parquet root from the current deployment environment.
    """

    config = store.load(run_id)
    artifact_dir = artifact_root / str(run_id)
    artifact_dir.mkdir(parents = True, exist_ok = True)


    connections = ConnectionRegistry.from_environment(
        required_research_connection_refs(config)
    )

    context = SourceContext(
        connections = connections,
        run_id = run_id,
        artifact_dir = artifact_dir,
    )

    try: 
        result = run_configured_research(
            config,
            context,
            allowed_module_prefixes=allowed_module_prefixes,
        )
        publish_factor_research_artifacts(
            result,
            run_id = run_id,
            root = artifact_root / "factor_research"
        )
        return result

    finally:
        connections.dispose()

def execute_persisted_ic_research(
        store: ResearchRunStore,
        run_id: int,
        *,
        artifact_root: Path,
        allowed_module_prefixes: Iterable[str] | None = ("quantmine",),
):
    """Execute IC from one persisted run and its verified factor artifacts."""

    config = store.load(run_id)
    artifact_dir = artifact_root / str(run_id)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    ic_component = resolve_ic_calculation_component(
        config.ic_engine,
        allowed_module_prefixes= allowed_module_prefixes
    )
    validation_component = resolve_ic_validation_component(
        config.validation_engine,
        allowed_module_prefixes= allowed_module_prefixes,
    )


    connections = ConnectionRegistry.from_environment(required_research_connection_refs(config, ic_component= ic_component, validation_component= validation_component))
    context = SourceContext(connections= connections, run_id= run_id, artifact_dir= artifact_dir,)

    try:
        resolved_bundle = resolve_research_bundle_definition(
            config.bundle,
            allowed_module_prefixes= allowed_module_prefixes,
        )
        market_data = load_research_market_data(
            resolved_bundle,
            config.data_binding,
            context,
        )
        market_data.require("close")

        factor_artifacts = load_factor_research_artifacts(
            root = artifact_root / "factor_research",
            run_id = run_id,
        )

        variants, test_results =  run_persisted_ic_workflow(
            config=config,
            close=market_data.market.close,
            factors=factor_artifacts.factors,
            context= context,
            membership=None,
            allowed_module_prefixes= allowed_module_prefixes,
            ic_component= ic_component,
            validation_component= validation_component
        )

        publish_ic_research_artifacts(
            variants,
            test_results,
            run_id = run_id,
            root = artifact_root / "ic_research"
        )

        return variants, test_results
    finally:
        connections.dispose()

def execute_persisted_backtest(
        store: ResearchRunStore,
        run_id: int,
        *,
        artifact_root: Path,
        allowed_module_prefixes: Iterable[str] | None = ("quantmine",),
) -> BacktestResult:
    """Execute backtest from persisted configuration and verified artifacts"""

    config = store.load(run_id)

    backtest_component = resolve_backtest_component(config.backtest_engine, allowed_module_prefixes= allowed_module_prefixes)
    market_rules_component = resolve_market_rules_component(config.market_rules, allowed_module_prefixes=allowed_module_prefixes)
    connections = ConnectionRegistry.from_environment(required_research_connection_refs(config, backtest_component=backtest_component, market_rules_component=market_rules_component))

    artifact_dir = artifact_root / str(run_id)
    artifact_dir.mkdir(parents=True, exist_ok=True)

    context = SourceContext(
        connections= connections,
        run_id = run_id,
        artifact_dir= artifact_dir
    )

    try:
        resolved_bundle = resolve_research_bundle_definition(
            config.bundle,
            allowed_module_prefixes= allowed_module_prefixes,
        )
        market_data = load_research_market_data(
            resolved_bundle,
            config.data_binding,
            context
        )
        ic_artifacts = load_ic_research_artifacts(
            root = artifact_root / "ic_research",
            run_id = run_id,
        )
        request = build_backtest_request(config, market_data, ic_artifacts, market_rules_component)
        return run_backtest_component(
            backtest_component,
            request,
            context,
        )
    finally:
        connections.dispose()





def build_backtest_request(
        config: ResearchRunConfig,
        market_data: MarketDataBundle,
        ic_artifacts: ICResearchArtifacts,
        market_rules_component: MarketRulesComponent,
        *,
        market_state_provider: MarketStateProvider | None = None
) -> BacktestRequest:
    """Assemble verified persisted inputs for one backtest engine."""

    market_data.require("close")

    active_market_state_provider = market_state_provider
    if active_market_state_provider is None and isinstance(market_data.universe, MarketStateProvider):
        active_market_state_provider = market_data.universe

    return BacktestRequest(
        close = market_data.market.close,
        variants= ic_artifacts.variants,
        test_results= ic_artifacts.test_results,
        config = config.backtest,
        constituents= market_data.universe,
        market_cap = market_data.market.market_cap,
        market_data= market_data,
        market_rules = market_rules_component,
        market_state_provider= active_market_state_provider
    )


def required_research_connection_refs(
        config: ResearchRunConfig,
        *,
        ic_component: ICCalculationComponent | None = None,
        validation_component: ICValidationComponent | None = None,
        backtest_component: BacktestComponent | None = None,
        market_rules_component: MarketRulesComponent | None = None
) -> tuple[str, ...]:
    """Return every external connection required by one research run."""

    eligibility_binding = config.data_binding.eligibility_binding

    candidates = (
        config.data_binding.connection_ref,
        (
            eligibility_binding.connection_ref
            if eligibility_binding is not None
            else None
        ),
        (
            ic_component.connection_ref if ic_component is not None else None
        ),
        (
            validation_component.connection_ref if validation_component is not None
            else None
        ),
        (
            backtest_component.connection_ref if backtest_component is not None else None
        ),
        (
            market_rules_component.connection_ref if market_rules_component is not None else None
        )
    )

    return tuple(
        dict.fromkeys(
            connection_ref for connection_ref in candidates
            if connection_ref is not None
        )
    )
