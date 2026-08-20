"""Research-bundle composition and preflight compatibility checks."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Iterable, Mapping

from .contracts import (
    DataSourceComponent,
    FactorPackComponent,
    PluginSpec,
    UniverseComponent,
    MarketDataCapability
)
from .loader import PluginResolutionError, resolve_plugin

@dataclass(frozen=True)
class ResearchBundle: #纯声明对象
    """A market-aware default composition.

    A bundle supplies consistent defaults, but callers can replace its data
    source or factor packs without changing core research code.
    """

    id: str
    display_name: str
    data_source: PluginSpec
    universe: PluginSpec | None
    factor_packs: tuple[PluginSpec, ...]
    defaults: Mapping[str, Any] = field(default_factory=dict)

    def with_overrides( #允许替换数据源或因子包，但不改动默认bundle
            self,
            *,
            data_source: PluginSpec | None = None,
            factor_packs = tuple[PluginSpec, ...]
    ) -> "ResearchBundle":
        '''return a copied bundle with selected components replaced.'''
        return replace(
            self,
            data_source = (data_source if data_source is not None else self.data_source),
            factor_packs = (
                factor_packs if factor_packs is not None else self.factor_packs
            ),
        )

@dataclass(frozen = True)
class ResolvedResearchBundle: #解析后的对象，内部已有真实DataSourceComponent、FactorPackComponent
    '''A bundle after factories have been called and checked'''

    definition: ResearchBundle
    data_source: DataSourceComponent
    universe: UniverseComponent | None
    factor_packs: tuple[FactorPackComponent, ...]

US_EQUITY_V1 = ResearchBundle( #当前美股默认bundle
    id = 'us_equity_v1',
    display_name = 'US equities (Yahoo Finance / S&P 500)',
    data_source = PluginSpec(
        'quantmine.plugins.builtins:create_yfinance_data_source'
    ),
    universe = PluginSpec(
        'quantmine.plugins.builtins:create_sp500_universe'
    ),
    factor_packs = (
        PluginSpec(
            'quantmine.plugins.builtins:create_us_technical_factor_pack'
        ),
    ),
    defaults= {
        'benchmark_ticker': 'SPY',
        'market' : 'US',
        'currency': 'USD'
    },
)

DEFAULT_RESEARCH_BUNDLES: dict[str, ResearchBundle] = {
    US_EQUITY_V1.id: US_EQUITY_V1,
}
def get_research_bundle(bundle_id: str) -> ResearchBundle: #从已注册bundle取默认定义
    '''Return a registered bundle or raise a configuration error'''
    try:
        return DEFAULT_RESEARCH_BUNDLES[bundle_id]

    except KeyError as error:
        known = ','.join(sorted(DEFAULT_RESEARCH_BUNDLES))

        raise PluginResolutionError(
            f"unknown research bundle '{bundle_id}'; available: {known}"
        ) from error

def _expect_component( #确认工厂返回类型正确，例如数据源工厂不能误返回因子包
        value: object,
        expected_type: type,
        label: str
):
    if not isinstance(value, expected_type):
        raise PluginResolutionError(
            f"{label} factory returned {type(value).__name__},"
            f"expected {expected_type.__name__}"

        )
    return value

def _validate_compatibility( #核心预检：用因子包 requires - 数据源/股票池capabilities得到缺失字段，缺失即组织运行
        available_capabilities: frozenset[MarketDataCapability],
        factor_packs: Iterable[FactorPackComponent],
) -> None:
    """Reject unsupported data/factor combinations before a run starts"""

    for factor_pack in factor_packs:
        missing = factor_pack.requires - available_capabilities
        if missing:
            missing_names = ','.join(
                sorted(capability.value for capability in missing)
            )
            raise PluginResolutionError(
                f"factor pack '{factor_pack.id}' requires unavailable data: {missing_names}"
                f'{missing_names}'
            )

def resolve_research_bundle( #按bundle ID解析，适合常规本地调用
        bundle_id: str,
        *,
        data_source_override: PluginSpec | None = None,
        factor_packs_override: tuple[PluginSpec, ...] | None = None,
        allowed_module_prefixes: Iterable[str] | None = ('quantmine',),
) -> ResolvedResearchBundle:
    """resolve one bundle and validate all component dependencies"""

    definition = get_research_bundle(bundle_id).with_overrides(
        data_source = data_source_override,
        factor_packs=factor_packs_override
    )
    data_source = _expect_component(
        resolve_plugin(
            definition.data_source,
            allowed_module_prefixes = allowed_module_prefixes,
        ),
        DataSourceComponent,
        'data source'
    )

    universe = None
    if definition.universe is not None:
        universe = _expect_component(
            resolve_plugin(
                definition.universe,
                allowed_module_prefixes= allowed_module_prefixes
            ),
            UniverseComponent,
            'universe'
        )

    factor_packs = tuple(
        _expect_component(
            resolve_plugin(
                spec,
                allowed_module_prefixes = allowed_module_prefixes
            ),
            FactorPackComponent,
            'factor pack',
        )
        for spec in definition.factor_packs
    )
    available_capabilities = data_source.capabilities
    if universe is not None:
        available_capabilities = (
            available_capabilities | universe.provides
        )
    
    _validate_compatibility(available_capabilities, factor_packs)
    return ResolvedResearchBundle(
        definition = definition,
        data_source = data_source,
        universe = universe,
        factor_packs = factor_packs,
    )

def resolve_research_bundle(
        bundle_id: str,
        *,
        data_source_override: PluginSpec | None = None,
        factor_packs_override: tuple[PluginSpec, ...] | None = None,
        allowed_module_prefixes: Iterable[str] | None = ("quantmine",),
) -> ResolvedResearchBundle:
    """Resolve a registered bundle with optional caller overrides"""

    definition = get_research_bundle(bundle_id).with_overrides(
        data_source = data_source_override,
        factor_packs = factor_packs_override
    )

    return resolve_research_bundle_definition(
        definition,
        allowed_module_prefixes = allowed_module_prefixes
    )

def resolve_research_bundle_definition( #按完整researchbundle定义解析，适合从数据库快照恢复后运行
    definition: ResearchBundle,
    *,
    allowed_module_prefixes: Iterable[str] | None = ("quantmine",),
) -> ResolvedResearchBundle:
    """Resolve one explicit bundle definition and validate compatibility.

    Unlike ``resolve_research_bundle``, this accepts a snapshot-restored
    ResearchBundle and therefore does not depend on the current in-memory
    default-bundle registry.
    """

    data_source = _expect_component(
        resolve_plugin(
            definition.data_source,
            allowed_module_prefixes = allowed_module_prefixes,
        ),
        DataSourceComponent,
        "data source"
    )

    universe = None
    if definition.universe is not None:
        universe = _expect_component(
            resolve_plugin(
                definition.universe,
                allowed_module_prefixes=allowed_module_prefixes
            ),
            UniverseComponent,
            "universe",
        )

    factor_packs = tuple(
        _expect_component(
            resolve_plugin(
                spec,
                allowed_module_prefixes=allowed_module_prefixes
            ),
            FactorPackComponent,
            "factor pack",
        )
        for spec in definition.factor_packs
    )

    available_capabilities = data_source.capabilities
    if universe is not None:
        available_capabilities = (
            available_capabilities | universe.provides
        )

    _validate_compatibility(
        available_capabilities,
        factor_packs,
    )

    return ResolvedResearchBundle(
        definition = definition,
        data_source= data_source,
        universe = universe,
        factor_packs = factor_packs
    )