"""A-share universe binding for generic historical market-data refresh."""

from __future__ import annotations

from dataclasses import replace, dataclass, field
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
from .market_data_refresh import refresh_market_data, MarketDataRefreshPolicy, load_market_data_batches, publish_cumulative_market_data
from ..dataset_versions import (
    AS_OF_DATE_VERSION, resolve_versioned_dataset_binding
)

from collections.abc import Iterable
from ..plugins.loader import resolve_plugin

A_SHARE_HISTORY_REFRESH_CONFIG_VERSION = 2
_SUPPORTED_CONFIG_VERSIONS = frozenset({1,2})

@dataclass(frozen = True)
class AStockDailyMarketDataPublicationTemplate:
    dataset_id: str
    market: str
    version: str
    source: str
    frequency: str
    adjustment: str | None
    schema_version: str = "market_data_bundle_v1"

    def resolve(
            self,
            *,
            as_of_date:pd.Timestamp | str,
    ) -> MarketDataPublishSpec:
        date = pd.Timestamp(as_of_date)
        if pd.isna(date):
            raise ValueError("as_of_date must not be NaT")

        return MarketDataPublishSpec(
            dataset_id = self.dataset_id,
            market= self.market,
            version = date.strftime("%Y%m%d"),
            source = self.source,
            frequency= self.frequency,
            adjustment= self.adjustment,
            schema_version= self.schema_version,
        )

@dataclass(frozen=True)
class ResolvedAStockDailyMarketDataRefreshConfig:
    source: PluginSpec
    binding: DataBinding
    reference_binding: VersionedDatasetBinding
    output_connection_ref: str
    publication: MarketDataPublishSpec
    policy: MarketDataRefreshPolicy

@dataclass(frozen = True)
class AStockHistoryRefreshConfig:
    source: PluginSpec
    binding: DataBinding
    reference_binding: VersionedDatasetBinding
    output_connection_ref: str
    publication: MarketDataPublishSpec
    policy: MarketDataRefreshPolicy = field(
        default_factory = MarketDataRefreshPolicy
    )

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
        if version not in _SUPPORTED_CONFIG_VERSIONS:
            raise ValueError(
                "Unsupported A-share history refresh config "
                f"schema version {version!r}; expected "
                f"{sorted(_SUPPORTED_CONFIG_VERSIONS)}"
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
        policy = _mapping(
            payload.get("policy", {}),
            label = "policy"
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
                label = "output_connection_ref",
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
                ),
            ),
            policy = MarketDataRefreshPolicy(
                batch_size = _integer(
                    policy.get("batch_size", 50),
                    label = "policy.batch_size",
                ),
                max_retries = _integer(
                    policy.get("max_retries", 3),
                    label = "policy.max_retries",
                ),
                checkpoint_connection_ref = _optional_string(
                    policy.get("checkpoint_connection_ref"),
                    label = "policy.checkpoint_connection_ref",
                ),
                resume = _boolean(
                    policy.get("resume", True),
                    label = "policy.resume"
                ),
            ),
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
            },
            "policy": {
                "batch_size": self.policy.batch_size,
                "max_retries": self.policy.max_retries,
                "checkpoint_connection_ref": (
                    self.policy.checkpoint_connection_ref
                ),
                "resume": self.policy.resume
            }
        }

A_SHARE_DAILY_MARKET_DATA_REFRESH_CONFIG_VERSION = 1

@dataclass(frozen=True)
class AStockDailyMarketDataRefreshConfig:
    """Persistent template for one scheduled cumulative A-share refresh."""

    source: PluginSpec
    binding: DataBinding
    reference_binding: VersionedDatasetBinding
    output_connection_ref: str
    publication: AStockDailyMarketDataPublicationTemplate
    policy: MarketDataRefreshPolicy = field(
        default_factory= MarketDataRefreshPolicy
    )
    def __post_init__(self) -> None:


        if (
             self.binding.start != AS_OF_DATE_VERSION
            or self.binding.end != AS_OF_DATE_VERSION
            or self.reference_binding.version != AS_OF_DATE_VERSION
            or self.publication.version != AS_OF_DATE_VERSION
        ):
            raise ValueError(
                "daily refresh dates must all use '{as_of_date}'"
                )

        if self.binding.start != AS_OF_DATE_VERSION:
            raise ValueError(
                "daily binding.start must be '{as_of_date}'"
            )

        if self.binding.end != AS_OF_DATE_VERSION:
            raise ValueError(
                "daily binding.end must be '{as_of_date}'"
            )

        if self.binding.tickers:
            raise ValueError(
                "binding.tickers must be empty; "
                "ticker are derived from the security master"
            )

        if self.reference_binding.market != "CN":
            raise ValueError("reference_binding.market must be CN")

        if self.reference_binding.version != AS_OF_DATE_VERSION:
            raise ValueError(
                "daily reference_binding.version must be '{as_of_date}'"
            )
        if self.publication.market != "CN":
            raise ValueError("publication.market must be CN")

        if self.publication.version != AS_OF_DATE_VERSION:
            raise ValueError(
                "daily publication.version must be '{as_of_date}'"
            )

        if self.publication.adjustment != self.binding.adjustment:
            raise ValueError(
                "publication.adjustment must match binding.adjustment"
            )

        if (
            not self.output_connection_ref
            or self.output_connection_ref.strip() != self.output_connection_ref
        ):
            raise ValueError(
                "output_connection_ref must be a non-empty trimmed string"
            )

    @classmethod
    def from_mapping(
        cls,
        value: Mapping[str, Any],
    ) -> "AStockDailyMarketDataRefreshConfig":
        payload = _mapping(
            value,
            label = "A-share daily market-data refresh config"
        )

        if payload.get("schema_version") != A_SHARE_DAILY_MARKET_DATA_REFRESH_CONFIG_VERSION:
            raise ValueError(
                "Unsupported A-share daily market-data refresh config "
                f"schema version {payload.get('schema_version')!r}"
            )

        source = _mapping(payload.get("source"), label = "source")
        binding = _mapping(payload.get("binding"), label = "binding")
        reference = _mapping(
            payload.get("reference_binding"),
            label = "reference_binding",
        )
        publication = _mapping(
            payload.get("publication"),
            label = "publication",
        )
        policy = _mapping(payload.get("policy", {}), label= "policy")

        if binding.get("tickers", []) not in ([], ()):
            raise ValueError(
                "binding.tickers must be omitted or an empty list"
            )

        return cls(
            source=PluginSpec(
                entry_point=_string(
                    source.get("entry_point"),
                    label="source.entry_point",
                ),
                params=_mapping(
                    source.get("params", {}),
                    label="source.params",
                ),
            ),
            binding=DataBinding(
                connection_ref=_optional_string(
                    binding.get("connection_ref"),
                    label="binding.connection_ref",
                ),
                dataset=_string(
                    binding.get("dataset"),
                    label="binding.dataset",
                ),
                start=_string(
                    binding.get("start"),
                    label="binding.start",
                ),
                end=_string(
                    binding.get("end"),
                    label="binding.end",
                ),
                adjustment=_optional_string(
                    binding.get("adjustment"),
                    label="binding.adjustment",
                ),
                metadata=_mapping(
                    binding.get("metadata", {}),
                    label="binding.metadata",
                ),
            ),
            reference_binding=VersionedDatasetBinding(
                connection_ref=_string(
                    reference.get("connection_ref"),
                    label="reference_binding.connection_ref",
                ),
                dataset=_string(
                    reference.get("dataset"),
                    label="reference_binding.dataset",
                ),
                market=_string(
                    reference.get("market"),
                    label="reference_binding.market",
                ),
                version=_string(
                    reference.get("version"),
                    label="reference_binding.version",
                ),
            ),
            output_connection_ref=_string(
                payload.get("output_connection_ref"),
                label="output_connection_ref",
            ),
            publication=AStockDailyMarketDataPublicationTemplate(
                dataset_id=_string(
                    publication.get("dataset_id"),
                    label="publication.dataset_id",
                ),
                market=_string(
                    publication.get("market"),
                    label="publication.market",
                ),
                version=_string(
                    publication.get("version"),
                    label="publication.version",
                ),
                source=_string(
                    publication.get("source"),
                    label="publication.source",
                ),
                frequency=_string(
                    publication.get("frequency"),
                    label="publication.frequency",
                ),
                adjustment=_optional_string(
                    publication.get("adjustment"),
                    label="publication.adjustment",
                ),
                schema_version=_string(
                    publication.get(
                        "schema_version",
                        "market_data_bundle_v1",
                    ),
                    label="publication.schema_version",
                ),
            ),
            policy=MarketDataRefreshPolicy(
                batch_size=_integer(
                    policy.get("batch_size", 50),
                    label="policy.batch_size",
                ),
                max_retries=_integer(
                    policy.get("max_retries", 3),
                    label="policy.max_retries",
                ),
                checkpoint_connection_ref=_optional_string(
                    policy.get("checkpoint_connection_ref"),
                    label="policy.checkpoint_connection_ref",
                ),
                resume=_boolean(
                    policy.get("resume", True),
                    label="policy.resume",
                ),
            ),
        )

    def to_mapping(self) -> dict[str, object]:
        return {
            "schema_version": (
                A_SHARE_DAILY_MARKET_DATA_REFRESH_CONFIG_VERSION
            ),
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
            },
            "policy": {
                "batch_size": self.policy.batch_size,
                "max_retries": self.policy.max_retries,
                "checkpoint_connection_ref": (
                    self.policy.checkpoint_connection_ref
                ),
                "resume": self.policy.resume,
            },
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
        policy: MarketDataRefreshPolicy | None = None,
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
        policy=policy
    )

def refresh_a_share_cumulative_market_data(
        context: SourceContext,
        *,
        source_component: DataSourceComponent,
        binding: DataBinding,
        reference_binding: VersionedDatasetBinding,
        output_connection_ref: str,
        publish_spec: MarketDataPublishSpec,
        policy: MarketDataRefreshPolicy | None = None
) -> MarketDataPublication:
    """Fetch one A-share session and publish a cumulative immutable version."""

    if not isinstance(context, SourceContext):
        raise TypeError("context must be a SourceContext")

    if not isinstance(source_component, DataSourceComponent):
        raise TypeError("source_component must be a DataSourceComponent")

    if not isinstance(binding, DataBinding):
        raise TypeError("binding must be a DataBinding")

    if not isinstance(reference_binding, VersionedDatasetBinding):
        raise TypeError(
            "reference_binding must be a VersionedDatasetBinding"
        )

    if not isinstance(publish_spec, MarketDataPublishSpec):
        raise TypeError("publish_spec must be a MarketDataPublishSpec")

    if binding.start is None or binding.end is None:
        raise ValueError("binding.start and binding.end are required")

    start = pd.Timestamp(binding.start).normalize()
    end = pd.Timestamp(binding.end).normalize()
    if start != end:
        raise ValueError(
            "cumulative A-share refresh requires one trading session"
        )

    if binding.tickers:
        raise ValueError(
            "binding.tickers must be empty; "
            "tickers are derived from the security master"
        )

    if reference_binding.market != "CN":
        raise ValueError("reference_binding.market must be 'CN'")

    if publish_spec.market != "CN":
        raise ValueError("publish_spec.market must be 'CN'")

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

    tickers = reference.security_master.tickers_during(start, end)
    if not tickers:
        raise ValueError(
            "security master contains no A-share tickers "
            "during the requested session"
        )

    resolved_binding = replace(binding, tickers = tickers)
    resolved_policy = policy or MarketDataRefreshPolicy()

    delta = load_market_data_batches(
        context,
        source_component=source_component,
        binding = resolved_binding,
        policy = resolved_policy,
        publish_spec = publish_spec,
    )

    return publish_cumulative_market_data(
        context,
        delta=delta,
        output_connection_ref=output_connection_ref,
        spec =publish_spec,
        as_of_date=end
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
        publish_spec=config.publication,
        policy = config.policy,
    )

def run_configured_a_share_cumulative_refresh(
        context: SourceContext,
        *,
        config: AStockDailyMarketDataRefreshConfig,
        as_of_date: pd.Timestamp | str,
        allowed_module_prefixes: Iterable[str] | None = ("quantmine",),
)-> MarketDataPublication:
    if not isinstance(config, AStockDailyMarketDataRefreshConfig):
        raise TypeError(
            "config must be an AStockDailyMarketDataRefreshConfig"
        )

    source_component = resolve_plugin(
        config.source,
        allowed_module_prefixes=allowed_module_prefixes,
    )

    if not isinstance(source_component, DataSourceComponent):
        raise TypeError(
            f"source factory {config.source.entry_point} "
            "must return DataSourceComponent"
        )

    resolved = resolve_a_share_daily_market_data_refresh_config(
        config,
        as_of_date=as_of_date,
    )

    return refresh_a_share_cumulative_market_data(
        context,
        source_component=source_component,
        binding = resolved.binding,
        reference_binding= resolved.reference_binding,
        output_connection_ref= resolved.output_connection_ref,
        publish_spec = resolved.publication,
        policy = resolved.policy,
    )

def resolve_a_share_daily_market_data_refresh_config(
        config: AStockDailyMarketDataRefreshConfig,
        *,
        as_of_date: pd.Timestamp | str,
) -> ResolvedAStockDailyMarketDataRefreshConfig:
    if not isinstance(config, AStockDailyMarketDataRefreshConfig):
        raise TypeError(
            "config must be an AStockDailyMarketDataRefreshConfig"
        )

    date = pd.Timestamp(as_of_date)
    if pd.isna(date):
        raise ValueError("as_of_date must not be NaT")

    date = date.normalize()
    date_text = date.date().isoformat()

    return ResolvedAStockDailyMarketDataRefreshConfig(
        source=config.source,
        binding=replace(
            config.binding,
            start=date_text,
            end=date_text,
        ),
        reference_binding=resolve_versioned_dataset_binding(
            config.reference_binding,
            as_of_date=date,
        ),
        output_connection_ref=config.output_connection_ref,
        publication=config.publication.resolve(as_of_date=date),
        policy=config.policy,
    )

def _integer(
        value: object,
        *,
        label: str,
) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{label} must be an integer")

    return value

def _boolean(
        value: object,
        *,
        label: str
) -> bool:
    if not isinstance(value, bool):
        raise TypeError(f"{label} must be a bool")

    return value
