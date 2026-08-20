"""Adapters exposing current built-ins through the research-bundle contracts."""

from __future__ import annotations

from ..datareader import YFinanceSource
from .contracts import (
    DataSourceComponent,
    FactorPackComponent,
    MarketDataCapability,
    UniverseComponent,
)

def create_yfinance_data_source(**params) -> DataSourceComponent:
    """Return the existing Yahoo implementation with explicit capabilities"""

    return DataSourceComponent(
        id = 'yfinance',
        source = YFinanceSource(**params),
        capabilities = frozenset({
            MarketDataCapability.CLOSE,
            MarketDataCapability.VOLUME,
        }),
        metadata = {
            'market': 'US',
            'adjustment': 'provider_default',
        },
    )

def create_sp500_universe() -> UniverseComponent:
    """Describe the existing point-in-time S&P 500 membership convention."""
    return UniverseComponent(
        id = 'sp500_membership',
        metadata = {
            'index_name' : 'SP500',
            'benchmark_ticker': 'SPY'
        }
    )

def create_us_technical_factor_pack() -> FactorPackComponent:
    """Describe the currently registered US price/volume factors.

    The import preserves the existing registration side effect. No factor is
    calculated merely by resolving a research bundle.
    """

    from .. import factor_mining
    _ = factor_mining
    return FactorPackComponent(
        id = 'us_technical_v1',
        requires = frozenset({
            MarketDataCapability.CLOSE,
            MarketDataCapability.VOLUME
        }),
        signals = (
            'momentum',
            'ShortTermReversal',
            'TwentyDayVolatility',
            'TwentyDayNegVotality',
            'TwentyDayAvgVol',
            'VolPriceCorr',
        ),
        metadata = {
            'registry_module': 'quantmine.factor_mining',
        }
    )
