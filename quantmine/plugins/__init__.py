"""Composable research-bundle primitives."""

from .bundles import (
    DEFAULT_RESEARCH_BUNDLES,
    ResearchBundle,
    ResolvedResearchBundle,
    get_research_bundle,
    resolve_research_bundle,
    resolve_research_bundle_definition
)

from .contracts import (
    DataBinding,
    DataSourceComponent,
    DataSourcePlugin,
    FactorPackComponent,
    MarketDataBundle,
    MarketDataCapability,
    PluginSpec,
    UniverseComponent
)

from .sources import(
    LegacyDataSourcePlugin,
    ParquetWideFrameDataSourcePlugin,
    SqlLongFormatDataSourcePlugin
)

from .catalog import ResearchBundleCatalog, load_research_bundle_catalog


from .loader import PluginResolutionError, resolve_plugin

from .runtime import load_data_source_component

__all__ = (
    "DEFAULT_RESEARCH_BUNDLES",
    "DataBinding",
    "DataSourceComponent",
    "DataSourcePlugin",
    "FactorPackComponent",
    "MarketDataBundle",
    "MarketDataCapability",
    "PluginResolutionError",
    "PluginSpec",
    "ResearchBundle",
    "ResolvedResearchBundle",
    "UniverseComponent",
    "get_research_bundle",
    "resolve_plugin",
    "resolve_research_bundle",
    "LegacyDataSourcePlugin",
    "ParquetWideFrameDataSourcePlugin",
    "SqlLongFormatDataSourcePlugin",
    "load_data_source_component",
    "resolve_research_bundle_definition",
    "ResearchBundleCatalog",
    "load_research_bundle_catalog"
)
