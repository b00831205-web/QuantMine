"""Stable contracts for composable research components.

The first migration step wraps the existing implementations with descriptors.
Existing calculation code remains untouched; later pipeline tasks can consume
the descriptors without knowing whether a source is Yahoo, AkShare, a local
file, or a compiled implementation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Mapping, TYPE_CHECKING, Protocol, runtime_checkable
import pandas as pd
from collections.abc import Callable

from ..datareader import DataSource, ConstituentsSource, MarketData

if TYPE_CHECKING:
    from .context import SourceContext

class MarketDataCapability(StrEnum): #标准化字段能力，因子包声明需要什么，数据源声明能提供什么，bundle在运行前比较二者，避免算到一半发现缺数据
    """Named market-data fields a component can provide or require."""
    CLOSE = 'close'
    VOLUME = 'volume'
    MARKET_CAP = 'market_cap'
    MEMBERSHIP = 'membership'
    CALENDAR = 'calendar'
    BENCHMARK = 'benchmark'
    FUNDAMENTALS = 'fundamentals'
    

@dataclass(frozen = True)
class PluginSpec:  #只保存入口路径和参数，不保存已创建的python对象
    """An explicit reference to one plugin factory.

    entry_point must use the form ``package.module:factory``. A deployment
    controls which module prefixes are trusted when resolving this reference.
    """
    entry_point : str
    params: Mapping[str, Any] = field(default_factory = dict)

@dataclass(frozen = True)
class VersionedDatasetBinding:
    """Serializable reference to one immutable dataset version"""
    connection_ref: str
    dataset: str
    market: str
    version: str

    def __post_init__(self) -> None:
        for label, value in (
            ("connection_ref", self.connection_ref),
            ("dataset", self.dataset),
            ("market", self.market),
            ("version", self.version)
        ): 
            if not value or value.strip() != value:
                raise ValueError(
                    f"{label} must be a non-empty trimmed string"
                )

            if "/" in value or "\\" in value or value in {".",".."}:
                raise ValueError(
                    f"{label} must be a safe path segment"
                )


@dataclass(frozen = True)
class DataBinding: #运行配置文件
    """Serializable description of one market-data request.

    ``connection_ref`` is only an alias such as ``cn_equity_postgres``.
    Actual DSNs and local roots remain in environment variables and are
    resolved by ``ConnectionRegistry`` at runtime.
    """
    connection_ref: str | None
    dataset: str
    version: str | None = None
    universe_dataset: str | None = None
    benchmark_dataset : str | None = None
    benchmark_ticker: str | None = None
    adjustment: str | None = None
    start: str | None = None
    end: str | None = None
    tickers: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)
    eligibility_binding: VersionedDatasetBinding | None = None

@dataclass(frozen = True)
class MarketDataBundle:  #数据源插件的统一输出，内部继续复用旧MarketData，同时可逐步加入成分股、交易日历、基准和元数据
    """Data returned by a source plugin for one reserach run"""

    market : MarketData
    universe: ConstituentsSource | None = None
    calendar: pd.DatetimeIndex | None = None
    benchmark: pd.Series | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    def require(self, *fields: str) -> None:
        """Delegate price-field validation to the existing MarketData object"""
        self.market.require(*fields) 

    def provides(self, capability: MarketDataCapability) -> bool:
            """Return whether this loaded bundle actually provides one capability."""
    
            return {
                MarketDataCapability.CLOSE: self.market.close is not None,
                MarketDataCapability.VOLUME: self.market.volume is not None,
                MarketDataCapability.MARKET_CAP: self.market.market_cap is not None,
                MarketDataCapability.MEMBERSHIP: self.universe is not None,
                MarketDataCapability.CALENDAR: self.calendar is not None,
                MarketDataCapability.BENCHMARK: self.benchmark is not None,
            }.get(capability, False)

@runtime_checkable
class DataSourcePlugin(Protocol): #新数据源运行时协议，统一要求实现load(binding, context)->MarketDataBundle
    """Runtime interface implemented by SQL, Parquet, Akshare, or API sources."""
    def load(
        self,
        binding: DataBinding,
        context: SourceContext
    ) -> MarketDataBundle:
        """Load one market_data bundle from the requested binding"""

@dataclass(frozen =True)
class DataSourceComponent: #bundle中的数据源描述。source用于旧接口兼容，plugin用于新接口；__post_init__()强制二选一，避免一个组件同时存在两条执行路径
    """A Stage-A source descriptor.

    ``source`` remains the legacy ``DataSource`` instance for compatibility.
    B2 will supply adapters that implement ``DataSourcePlugin`` and turn their
    output into ``MarketDataBundle``.
    """

    id: str
    capabilities: frozenset[MarketDataCapability]
    source: DataSource | None = None
    plugin: DataSourcePlugin | None = None
    connection_ref: str | None = None
    requires_connection: bool = False
    metadata: Mapping[str, Any] = field(default_factory=dict)
    retry_classifier: Callable[[Exception], bool] | None = field(
        default = None,
        repr = False,
        compare = False,
    )

    def __post_init__(self) -> None:
        if (self.source is None) == (self.plugin is None):
            raise ValueError(
                'DataSourceComponent requires exactly one of source or plugin.'
            )

        if (self.retry_classifier is not None and not callable(self.retry_classifier)):
            raise TypeError("retry_classifier must be None or callable")


@dataclass(frozen = True)
class FactorPackComponent: #因子包声明，包含requires与signals，不直接计算因子，只说明“这组因子是什么，需要什么输出”
    """A named collection of compatible factor implementations.

    This is a descriptor in the first migration step. The existing factor
    registry continues to calculate the factors; the descriptor makes input
    requirements explicit before a run starts.
    """
    id: str
    requires: frozenset[MarketDataCapability]
    signals: tuple[str, ...]
    metadata: Mapping[str, Any] = field(default_factory=dict)

@dataclass(frozen= True)
class UniverseComponent: #描述股票池规则和其提供的membership能力
    """Describes the point-in-time universe convention of a research bundle."""
    id : str
    provides: frozenset[MarketDataCapability] = frozenset({
        MarketDataCapability.MEMBERSHIP
    })
    metadata: Mapping[str, Any] = field(default_factory = dict,)
    plugin: UniversePlugin | None = None
    requires_connection: bool = False
    
@runtime_checkable
class UniversePlugin(Protocol):
    """Load a point-in-time membership source for one research run"""

    def load(
            self,
            binding: DataBinding,
            context: SourceContext,
    ) -> ConstituentsSource:
        ...
 