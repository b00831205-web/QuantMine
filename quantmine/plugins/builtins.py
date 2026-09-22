"""Adapters exposing current built-ins through the research-bundle contracts."""

from __future__ import annotations

from ..datareader import YFinanceSource
from .contracts import (
    DataSourceComponent,
    FactorPackComponent,
    MarketDataCapability,
    UniverseComponent,
)

from .us_equity import (
    create_sp500_universe as _create_sp500_universe,
    create_us_technical_factor_pack as _create_us_techical_factor_pack,
    create_yfinance_data_source as _create_yfinance_data_source
)

def create_yfinance_data_source(**params) -> DataSourceComponent:
    return _create_yfinance_data_source(**params)

def create_sp500_universe() -> UniverseComponent:
    return _create_sp500_universe()

def create_us_technical_factor_pack() -> FactorPackComponent:
    return _create_us_techical_factor_pack()

def create_cn_a_share_price_volume_factor_pack() -> FactorPackComponent:
    """Describe the first A-share close-and-volume factor family"""

    from .. import factor_mining_cn, factor_mining
    _ = factor_mining_cn 

    return FactorPackComponent(
        id = "cn_a_share_price_volume_v1",
        requires = frozenset({
            MarketDataCapability.CLOSE,
            MarketDataCapability.VOLUME
        }),
        signals= (
            "CNMomentum20D",
            "CNReversal5D",
            "CNVolatility20D",
            "CNVolumeRatio20D",
            "TwentyDayVolatility",
            "TwentyDayNegVotality",
            "TwentyDayAvgVol",
            "VolPriceCorr"
        ),
        metadata={
            "market": "CN",
            "family": "price_volume"
        },
    )