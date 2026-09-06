"""Bundle-scoped research orchestration before IC, validation, and backtests."""

from __future__ import annotations
from dataclasses import dataclass, replace
from typing import Any, Mapping

from .factor_register import build_param_pool, calculate_all_factors
from .plugins.bundles import ResolvedResearchBundle
from .plugins.context import SourceContext
from .plugins.contracts import (
    DataBinding,
    MarketDataBundle,
    MarketDataCapability,
)
from .plugins.runtime import load_data_source_component

_DIRECT_MARKET_FIELDS: dict[MarketDataCapability, str] ={
    MarketDataCapability.CLOSE: 'close',
    MarketDataCapability.VOLUME: 'volume',
    MarketDataCapability.MARKET_CAP: 'market_cap',
}

from collections.abc import Iterable

from .plugins.bundles import (
    ResolvedResearchBundle,
    resolve_research_bundle_definition
)

from .research_config import ResearchRunConfig
import pandas as pd
from .datareader import MarketData
from .plugins.runtime import (
    load_data_source_component,
    load_universe_component,
)


@dataclass(frozen = True)
class FactorResearchResult:
    """Output of one bundle-scoped data-load and factor_computation run"""
    market_data: MarketDataBundle
    requested_signals: tuple[str, ...]
    pending: Mapping[str, str]
    factors: Mapping[str, Any]

def _requested_signals(
        bundle: ResolvedResearchBundle,
) -> tuple[str, ...]:
    signals = tuple(
        dict.fromkeys(
            signal
            for factor_pack in bundle.factor_packs
            for signal in factor_pack.signals
        )
    )

    if not signals:
        raise ValueError(
            f"Research bundle {bundle.definition.id!r} has no factor signals"
        )

    return signals

def _validate_runtime_factor_requirements(
        bundle: ResolvedResearchBundle,
        market_data: MarketDataBundle
) -> None:
    required = {
        capability
        for factor_pack in bundle.factor_packs
        for capability in factor_pack.requires
    }

    fields = [
        _DIRECT_MARKET_FIELDS[capability]
        for capability in required
        if capability in _DIRECT_MARKET_FIELDS
    ]
    if fields:
        market_data.require(*fields)


def run_factor_research(
        bundle: ResolvedResearchBundle,
        binding: DataBinding,
        context: SourceContext,
        *,
        factor_parameters: Mapping[str, Any] | None = None 
) -> FactorResearchResult:
    """Load bundle data and compute only its requested factor_pack signals"""

    market_data = load_data_source_component(
        bundle.data_source,
        binding,
        context
    )
    active_universe = market_data.universe

    if bundle.universe is not None:
        resolved_universe = load_universe_component(
            bundle.universe,
            binding, 
            context,
        )
        if resolved_universe is not None:
            active_universe = resolved_universe

    if active_universe is not None:
        market_data = _apply_universe(market_data, active_universe)

    requested_signals = _requested_signals(bundle)
    _validate_runtime_factor_requirements(bundle, market_data)

    pool = build_param_pool(
        market_data.market,
        tickers = list(binding.tickers) if binding.tickers else None,
        **dict(factor_parameters or {})
    )

    pending, completed = calculate_all_factors(
        pool, factor_names = requested_signals
    )

    factors = {
        signal_name: completed[signal_name]
        for signal_name in requested_signals
        if completed.get(signal_name) is not None
    }

    return FactorResearchResult(
        market_data = market_data,
        requested_signals = requested_signals,
        pending = pending,
        factors = factors
    )

def run_configured_research(
        config: ResearchRunConfig,
        context: SourceContext,
        *,
        allowed_module_prefixes: Iterable[str] | None = ("quantmine,"),
) -> FactorResearchResult:
    """Run a persisted or local config through one plugin-defined pipeline.

    The allow-list is deployment policy, so it is intentionally supplied at
    runtime instead of being persisted in ResearchRunConfig.
    """

    bundle = resolve_research_bundle_definition(
        config.bundle,
        allowed_module_prefixes=allowed_module_prefixes
    )

    return run_factor_research(
        bundle,
        config.data_binding,
        context,
        factor_parameters= config.factor_parameters
    )

def _membership_mask(
        frame: pd.DataFrame,
        universe: object,
) -> pd.DataFrame:
    return pd.DataFrame({
        ticker: [
            ticker in universe.get_constituents(pd.Timestamp(date))
            for date in frame.index
        ]
        for ticker in frame.columns
    }, index= frame.index)

def _apply_universe(
        market_data: MarketDataBundle,
        universe: object,
) -> MarketDataBundle:
    market = market_data.market

    def masked(frame: pd.DataFrame | None) -> pd.DataFrame | None:
        if frame is None:
            return None
        return frame.where(_membership_mask(frame,universe))

    return replace(
        market_data,
        market = MarketData(
            close = masked(market.close),
            volume = masked(market.volume),
            market_cap = masked(market.market_cap),
        ),
        universe = universe
    )