"""A-share universe binding for generic historical market-data refresh."""

from __future__ import annotations

from dataclasses import replace, dataclass
from typing import Any, Mapping

import pandas as pd

from ..plugins.context import SourceContext
from ..plugins.contracts import (
    DataBinding,
    DataSourceComponent,
    PluginSpec,
    VersionedDatasetBinding,
)
from .a_share_reference import ParquetAStockReferenceLoader
from .market_data_publication import (
    MarketDataPublication,
    MarketDataPublishSpec,
)
from .market_data_refresh import refresh_market_data

from collections.abc import Iterable
from ..plugins.loader import resolve_plugin

A_SHARE_HISTORY_REFRESH_CONFIG_VERSION = 1

@dataclass(frozen = True)
class AStockHistoryRefreshConfig:
    source: PluginSpec
    binding: DataBinding
    reference_binding: VersionedDatasetBinding
    output_connection_ref: str
    publication: MarketDataPublishSpec

    def __post_init__(self) -> None:
        if self.binding.start is None or self.binding.end is None:
            raise ValueError(
                "binding.start and binding.end are required"
            )

        start = pd.Timestamp(self.binding.start).normalize()
        end = pd.Timestamp(self.binding.end).normalize()
        if end < start:
            raise ValueError(
                "binding.end must not be before binding.start"
            )

        if self.binding.tickers:
            raise ValueError(
                "binding.tickers must be empty; "
                "tickers are derived from the security master"
            )

        if self.reference_binding.market != "CN":
            raise ValueError(
                "reference_binding.market must be CN"
            )

        if self.publication.market != "CN":
            raise ValueError("publication.market must be CN")

        if self.publication.adjustment != self.binding.adjustment:
            raise ValueError(
                "publication.adjustment must match binding.adjustment"
            )

        if (
            not self.output_connection_ref
            or self.output_connection_ref.strip()
            != self.output_connection_ref
        ):
            raise ValueError(
                "output_connection_ref must be a non-empty trimmed string"
            )

    @classmethod
    def from_mapping(
        cls,
        value: Mapping[str, Any],
    )->"AStockHistoryRefreshConfig":
        payload = _mapping(
            value,
            label = "A-share history refresh config"
        )
        version = payload.get("schema_version")
        if version != A_SHARE_HISTORY_REFRESH_CONFIG_VERSION:
            raise ValueError(
                "Unsupported A-share history refresh config "
                f"schema version {version!r}; expected "
                f"{A_SHARE_HISTORY_REFRESH_CONFIG_VERSION}"
            )

        source = _mapping(
            payload.get("source"),
            label="source"
        )
        binding = _mapping(
            payload.get("binding"),
            label = "binding"
        )
        reference = _mapping(
            payload.get("reference_binding"),
            label = "reference_binding"
        )
        publication = _mapping(
            payload.get("publication"),
            label = "publication",
        )

        return cls(
            source = PluginSpec(
                entry_point=_string(
                    source.get("entry_point"),
                    label = "source.entry_point",
                ),
                params = _mapping(
                    source.get("params", {}),
                    label = "source.params",
                ),
            ),
            binding = DataBinding(
                connection_ref= _optional_string(
                    binding.get("connection_ref"),
                    label = "binding.connection_ref",
                ),
                dataset = _string(
                    binding.get("dataset"),
                    label = "binding.dataset",
                ),
                start = _string(
                    binding.get("start"),
                    label = "binding.start",
                ),
                end = _string(
                    binding.get("end"),
                    label = "binding.end",
                ),
                adjustment = _optional_string(
                    binding.get("adjustment"),
                    label = "binding.adjustment",
                ),
                metadata= _mapping(
                    binding.get("metadata", {}),
                    label = "binding.metadata",
                ),
            ),
            reference_binding = VersionedDatasetBinding(
                connection_ref=_string(
                    reference.get("connection_ref"),
                    label = "reference_binding.connection_ref",
                ),
                dataset = _string(
                    reference.get("dataset"),
                    label = "reference_binding.dataset",
                ),
                market = _string(
                    reference.get("market"),
                    label = "reference_binding.market",
                ),
                version = _string(
                    reference.get("version"),
                    label = "reference_binding.version",
                ),
            ),
            output_connection_ref = _string(
                payload.get("output_connection_ref"),
                label = "output_conncetion_ref",
            ),
            publication = MarketDataPublishSpec(
                dataset_id = _string(
                    publication.get("dataset_id"),
                    label = "publication.dataset_id",
                ),
                market = _string(
                    publication.get("market"),
                    label = "publication.market"
                ),
                version = _string(
                    publication.get("version"),
                    label = "publication.version",
                ),
                source = _string(
                    publication.get("source"),
                    label = "publication.source",
                ),
                frequency = _string(
                    publication.get("frequency"),
                    label = "publication.frequency",
                ),
                adjustment = _optional_string(
                    publication.get("adjustment"),
                    label = "publication.adjustment",
                ),
                schema_version = _string(
                    publication.get(
                        "schema_version",
                        "market_data_bundle_v1"
                    ),
                    label = "publication.schema_version",
                )
            )

        )
    def to_mapping(self) -> dict[str, object]:
        return {
            "schema_version": A_SHARE_HISTORY_REFRESH_CONFIG_VERSION,
            "source": {
                "entry_point": self.source.entry_point,
                "params": dict(self.source.params),
            },
            "binding": {
                "connection_ref": self.binding.connection_ref,
                "dataset": self.binding.dataset,
                "start": self.binding.start,
                "end": self.binding.end,
                "adjustment": self.binding.adjustment,
                "metadata": dict(self.binding.metadata),
            },
            "reference_binding": {
                "connection_ref": self.reference_binding.connection_ref,
                "dataset": self.reference_binding.dataset,
                "market": self.reference_binding.market,
                "version": self.reference_binding.version,
            },
            "output_connection_ref": self.output_connection_ref,
            "publication": {
                "dataset_id": self.publication.dataset_id,
                "market": self.publication.market,
                "version": self.publication.version,
                "source": self.publication.source,
                "frequency": self.publication.frequency,
                "adjustment": self.publication.adjustment,
                "schema_version": self.publication.schema_version,
            }
        }
def _mapping(
        value: object,
        *,
        label: str,
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{label} must be a YAML object")
    return dict(value)

def _string(
        value: object,
        *,
        label: str,
) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value.strip() != value
    ):
        raise TypeError(
            f"{label} must be a non-empty trimmed string"
        )
    return value

def _optional_string(
        value: object,
        *,
        label: str,
) -> str | None:
    if value is None:
        return None

    return _string(value, label = label)

def refresh_a_share_historical_market_data(
        context: SourceContext,
        *,
        source_component: DataSourceComponent,
        binding: DataBinding,
        reference_binding: VersionedDatasetBinding,
        output_connection_ref: str,
        publish_spec: MarketDataPublishSpec,
) -> MarketDataPublication:
    """Derive the historical A-share universe and publish market data"""

    if not isinstance(binding, DataBinding):
        raise TypeError("binding must be a DataBinding")

    if not isinstance(reference_binding, VersionedDatasetBinding):
        raise TypeError(
            "reference_binding must be a VersionedDatasetBinding"
        )

    if binding.start is None or binding.end is None:
        raise ValueError(
            "binding.start and binding.end are required"
        )

    if reference_binding.market != "CN":
        raise ValueError(
            "reference_binding.market must be 'CN'"
        )

    if publish_spec.market != "CN":
        raise ValueError(
            "publish_spec.market must be 'CN'"
        )

    if publish_spec.adjustment != binding.adjustment:
        raise ValueError(
            "publish_spec.adjustment must match binding.adjustment"
        )

    reference = ParquetAStockReferenceLoader(
        context = context,
        connection_ref = reference_binding.connection_ref,
        dataset = reference_binding.dataset,
        version = reference_binding.version,
    ).load()

    tickers = reference.security_master.tickers_during(
        binding.start,
        binding.end,
    )

    if not tickers:
        raise ValueError(
            "security master contains no A-share tickers "
            "during the requested history window"
        )

    resolved_binding = replace(
        binding,
        tickers = tickers
    )

    return refresh_market_data(
        context,
        source_component = source_component,
        binding = resolved_binding,
        output_connection_ref = output_connection_ref,
        publish_spec = publish_spec,
    )

def run_configured_a_share_history_refresh(
        context: SourceContext,
        *,
        config: AStockHistoryRefreshConfig,
        allowed_module_prefixes: Iterable[str] | None = ("quantmine")
) -> MarketDataPublication:
    """Resolve the configured source plugin and run one history refresh."""

    if not isinstance(config, AStockHistoryRefreshConfig):
        raise TypeError(
            "config must be an AStockHistoryRefreshConfig"
        )

    source_component = resolve_plugin(
        config.source,
        allowed_module_prefixes = allowed_module_prefixes,
    )

    if not isinstance(source_component, DataSourceComponent):
        raise TypeError(
            f"source factory {config.source.entry_point} "
            "must return DataSourceComponent"
        )

    return refresh_a_share_historical_market_data(
        context,
        source_component=source_component,
        binding = config.binding,
        reference_binding = config.reference_binding,
        output_connection_ref=config.output_connection_ref,
        publish_spec=config.publication
    )