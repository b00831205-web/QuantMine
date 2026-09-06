"""Collect and publish one immutable Akshare A-share reference version."""

from __future__ import annotations

from ..plugins.context import SourceContext
from ..plugins.contracts import VersionedDatasetBinding
from .a_share_reference_publication import (
    AStockReferencePublication,
    AStockReferencePublishSpec,
    publish_a_stock_reference,
)

from .akshare_a_share_reference import (
    AkShareAStockReferenceCollector,
)

def refresh_akshare_a_stock_reference(
        context: SourceContext,
        *,
        binding: VersionedDatasetBinding,
        collector: AkShareAStockReferenceCollector | None = None,
) -> AStockReferencePublication:
    """Collect all reference inputs before publishing one immutable version.

    Collection completes before the destination is touched. Therefore, if any
    AkShare exchange or calendar request fails, no partial version is published.
    """

    if not isinstance(binding, VersionedDatasetBinding):
        raise TypeError(
            "binding must be a VersionedDatasetBinding"
        )

    if binding.market != "CN":
        raise ValueError(
            "A-share reference binding market must be 'CN'"
        )

    reference = (collector or AkShareAStockReferenceCollector()).collect()

    root = context.connections.parquet_root(
        binding.connection_ref
    )

    return publish_a_stock_reference(
        reference.security_master,
        reference.trading_calendar,
        root = root,
        spec = AStockReferencePublishSpec(
            dataset_id = binding.dataset,
            market = binding.market,
            version = binding.version,
            source = "akshare+sse_official",
        ),
    )
