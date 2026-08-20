from __future__ import annotations


from .context import SourceContext
from .contracts import (
    DataBinding,
    DataSourceComponent,
    MarketDataBundle,
    MarketDataCapability,
)

from .sources import LegacyDataSourcePlugin


def _validate_declared_capabilities( #防止插件“虚报能力”，例如它说提供close，但返回的MarketDataBundle.market.close是空，会立即失败
        component: DataSourceComponent,
        bundle: MarketDataBundle
) -> None:
    missing = sorted((
        capability for capability in component.capabilities if not bundle.provides(capability)
    ), key = lambda capability: capability.value)

    if missing:
        names = ",".join(capability.value for capability in missing)
        raise ValueError(
            f"Data source component {component.id!r} declares capabilities"
            f"not provided by its loaded MarketDataBundle: {names}"
        )

def load_data_source_component( #检验component锁定的connection_ref与本次binding一致；若是新插件，调用plugin.load()，若是旧数据源，自动经过LegacyDataSourcePlugin
        component: DataSourceComponent,
        binding: DataBinding,
        context: SourceContext
) -> MarketDataBundle:
    """Load and validate market data for one resolved source component.

    A component may lock itself to a particular connection alias. This prevents
    a user-provided binding from redirecting an approved plugin to another
    configured data store.

    ``FUNDAMENTALS`` is intentionally excluded until MarketDataBundle receives
    a dedicated fundamentals field in a later stage.
    """

    if (
        component.connection_ref is not None 
        and component.connection_ref != binding.connection_ref
    ):
        raise ValueError(
            f"Data Source component {component.id!r} requires connection_ref"
            f"{component.connection_ref!r}, but the binding requested"
            f" {binding.connection_ref!r}"
        )

    if component.plugin is not None:
        bundle = component.plugin.load(binding, context)
    else:
        assert component.source is not None
        bundle = LegacyDataSourcePlugin(component.source).load(
            binding, context
        )

    if not isinstance(bundle, MarketDataBundle):
        raise TypeError(
            f" Data source component {component.id!r} returned"
            f"{type(bundle).__name__}; expected MarketDataBundle"
        )
    _validate_declared_capabilities(component,bundle)
    return bundle