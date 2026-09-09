"""Source-neutral historical market-data materialization."""

from __future__ import annotations

from ..plugins.context import SourceContext
from ..plugins.contracts import (
    DataBinding,
    DataSourceComponent,
)
from ..plugins.runtime import load_data_source_component
from .market_data_publication import (
    MarketDataPublication,
    MarketDataPublishSpec,
    publish_market_data_bundle
)

def refresh_market_data(
        context: SourceContext,
        *,
        source_component: DataSourceComponent,
        binding: DataBinding,
        output_connection_ref: str,
        publish_spec: MarketDataPublishSpec
) -> MarketDataPublication:
    """Load one source component and publish its normalized market data"""

    if not isinstance(context, SourceContext):
        raise TypeError("context must be a SourceContext")

    if not isinstance(source_component, DataSourceComponent):
        raise TypeError(
            "source_component must be a DataSourceComponent"
        )

    if not isinstance(binding, DataBinding):
        raise TypeError("binding must be a DataBinding")

    if not isinstance(publish_spec, MarketDataPublishSpec):
        raise TypeError(
            "publish_spec must be a MarketDataPublishSpec"
        )

    if (
        not isinstance(output_connection_ref, str)
        or not output_connection_ref
        or output_connection_ref.strip() != output_connection_ref
    ):
        raise ValueError(
            "output_connection_ref must be a non-empty trimmed string"
        )

    output_root = context.connections.writable_parquet_root(
        output_connection_ref
    )

    bundle = load_data_source_component(
        source_component,
        binding,
        context,
    )

    return publish_market_data_bundle(
        bundle,
        root = output_root,
        spec = publish_spec
    )