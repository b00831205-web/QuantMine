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
import pandas as pd

from dataclasses import dataclass, replace
from collections.abc import Sequence

from ..datareader import MarketData
from ..plugins.contracts import (
    DataBinding,
    DataSourceComponent,
    MarketDataBundle
)

from .market_data_publication import (
    MarketDataPublication,
    MarketDataPublishSpec,
    load_latest_market_data_before,
    publish_market_data_bundle,
)

from .market_data_checkpoints import (
    load_market_data_batch_checkpoint,
    save_market_data_batch_checkpoint,
)

import time
from ..resilience import RetryPolicy, Sleeper, retry_call
from hashlib import sha256
import json
import logging

_LOGGER = logging.getLogger(__name__)

@dataclass(frozen = True)
class MarketDataRefreshPolicy:
    """Execution policy for bounded, recoverabl market-data loading."""

    batch_size: int = 50
    max_retries: int = 3
    checkpoint_connection_ref: str | None = None
    resume: bool = True

    def __post_init__(self) -> None:
        if (
            not isinstance(self.batch_size, int)
            or isinstance(self.batch_size, bool)
            or self.batch_size <= 0
        ):
            raise ValueError("batch_size must be a positive integer")

        if (
            not isinstance(self.max_retries, int)
            or isinstance(self.max_retries, bool)
            or self.max_retries < 0
        ):
            raise ValueError("max_retries must be non-negative integer")


        if self.checkpoint_connection_ref is not None and(
            not isinstance(self.checkpoint_connection_ref, str)
            or not self.checkpoint_connection_ref
            or self.checkpoint_connection_ref.strip()
            != self.checkpoint_connection_ref
        ):
            raise ValueError(
                "checkpoint_connection_ref must be None "
                "or a non-empty trimmed string"
            )

        if not isinstance(self.resume, bool):
            raise TypeError("resume must be a bool")

def partition_data_binding(
        binding: DataBinding,
        *,
        batch_size: int,
) -> tuple[DataBinding, ...]:
    """Split one ticker-bound request into deterministic batches"""

    if not isinstance(binding, DataBinding):
        raise TypeError(
            "binding must be a DataBinding"
        )

    if (
        not isinstance(batch_size, int)
        or isinstance(batch_size, bool)
        or batch_size <= 0
    ):
        raise ValueError("batch_size must be a positive integer")

    if not binding.tickers:
        raise ValueError("binding.tickers must not be empty when batching market data")

    return tuple(
        replace(
            binding,
            tickers = binding.tickers[offset: offset + batch_size]
        )
        for offset in range(0, len(binding.tickers), batch_size)
    )

def merge_market_data_batches(
        batches: Sequence[MarketDataBundle],
) -> MarketDataBundle:
    """Merge ticker-partitioned market-data bundles by columns."""

    if not batches:
        raise ValueError("batches must not be empty")

    if any(
        not isinstance(batch, MarketDataBundle)
        for batch in batches
    ):
        raise TypeError(
            "every batch must be a MarketDataBundle"
        )

    first = batches[0]

    if any(batch.universe is not None for batch in batches):
        raise ValueError(
            "batched market-data loading does not merge universe objects."
        )

    if any(batch.benchmark is not None for batch in batches):
        raise ValueError(
            "batched market-data loading does not merge benchmark series"
        )

    return MarketDataBundle(
        market=MarketData(
            close = _merge_optional_market_field(
                batches,
                field_name = "close"
            ),
            volume = _merge_optional_market_field(
                batches,
                field_name = "volume"
            ),
            market_cap = _merge_optional_market_field(
                batches,
                field_name = "market_cap"
            ),
        ),
        calendar = _merge_batch_calendars(batches),
        metadata = dict(first.metadata)
    )

def _normalize_history_field(
        frame: pd.DataFrame | None,
        *,
        label: str,
) -> pd.DataFrame | None:
    if frame is None:
        return None
    if not isinstance(frame, pd.DataFrame):
        raise TypeError(f"{label} must be a pandas DataFrame")

    normalized = frame.copy()
    normalized.index = pd.DatetimeIndex(
        pd.to_datetime(normalized.index, errors="raise")
    )
    if normalized.index.tz is not None:
        normalized.index = normalized.index.tz_localize(None)

    if normalized.index.hasnans:
        raise ValueError(f"{label} contains missing dates")

    if normalized.index.has_duplicates:
        raise ValueError(f"{label} contains duplicate dates")

    normalized.columns = pd.Index(
        str(column).strip() for column in normalized.columns
    )
    if any(not column for column in normalized.columns):
        raise ValueError(f"{label} contains an empty ticker")

    if normalized.columns.has_duplicates:
        raise ValueError(f"{label} contains duplicate tickers")

    try:
        normalized = normalized.apply(pd.to_numeric, errors="raise")

    except (TypeError, ValueError) as error:
        raise ValueError(f"{label} contains non-numeric values") from error

    return normalized.sort_index().sort_index(axis = 1)

def _append_history_field(
        history: pd.DataFrame | None,
        delta: pd.DataFrame | None,
        *,
        label: str,
        history_dates: pd.DatetimeIndex,
        delta_dates: pd.DatetimeIndex,
) -> pd.DataFrame | None:
    if (history is None) != (delta is None):
        raise ValueError(
            f"history and delta have inconsistent {label} availability"
        )

    if history is None:
        return None

    if not history.index.equals(history_dates):
        raise ValueError(
            f"history {label} dates must match history close dates"
        )

    if not delta.index.equals(delta_dates):
        raise ValueError(
            f"delta {label} dates must match delta close dates"
        )

    columns = history.columns.union(delta.columns).sort_values()
    return pd.concat(
        [
            history.reindex(columns = columns),
            delta.reindex(columns = columns),
        ],
        axis = 0
    )

def append_market_data_history(
        history: MarketDataBundle,
        delta: MarketDataBundle,
) -> MarketDataBundle:
    """Append a strictly later market-data dekta to one historical bundle."""

    if not isinstance(history, MarketDataBundle):
        raise TypeError("history must be a MarketDataBundle")

    if not isinstance(delta, MarketDataBundle):
        raise TypeError("delta must be a MarketDataBundle")

    if (
        history.universe is not None or delta.universe is not None
    ):
        raise ValueError(
            "history append does not merge universe objects"
        )

    if (
        history.benchmark is not None or delta.benchmark is not None
    ):
        raise ValueError(
            "history append does not merge benchmark series"
        )

    history_close = _normalize_history_field(
        history.market.close,
        label = "history close"
    )
    delta_close = _normalize_history_field(
        delta.market.close,
        label = "delta close"
    )
    if history_close is None or delta_close is None:
        raise ValueError("history and delta both require close data")

    if history_close.empty or delta_close.empty:
        raise ValueError("history and delta close data must not be empty")

    overlapping_dates = history_close.index.intersection(delta_close.index)
    if not overlapping_dates.empty:
        raise ValueError(
            "history and delta contain overlapping dates: "
            f"{overlapping_dates.strftime('%Y-%m-%d').tolist()}"
        )
    if delta_close.index.min() <= history_close.index.max():
        raise ValueError(
            "delta market data must begin after history market data"
        )
    history_volume = _normalize_history_field(
        history.market.volume,
        label ="history volume"
    )
    delta_volume = _normalize_history_field(
        delta.market.volume,
        label = "delta volumn",
    )
    history_market_cap = _normalize_history_field(
        history.market.market_cap,
        label = "history market_cap"
    )
    delta_market_cap = _normalize_history_field(
        delta.market.market_cap,
        label = "delta market_cap",
    )
    return MarketDataBundle(
        market = MarketData(
            close=_append_history_field(
                history_close,
                delta_close,
                label = "close",
                history_dates = history_close.index,
                delta_dates = delta_close.index
            ),
            volume = _append_history_field(
                history_volume,
                delta_volume,
                label="volume",
                history_dates = history_close.index,
                delta_dates = delta_close.index,
            ),
            market_cap = _append_history_field(
                history_market_cap,
                delta_market_cap,
                label = "market_cap",
                history_dates = history_close.index,
                delta_dates = delta_close.index,
            ),
        ),
        calendar = pd.DatetimeIndex(
            history_close.index.append(delta_close.index)
        ),
        metadata = dict(history.metadata)
    )

def publish_cumulative_market_data(
        context: SourceContext,
        *,
        delta: MarketDataBundle,
        output_connection_ref: str,
        spec: MarketDataPublishSpec,
        as_of_date: pd.Timestamp | str,
) -> MarketDataPublication:
    """Publish a new immutable full-history version from one market-data delta."""

    if not isinstance(context, SourceContext):
        raise TypeError("context must be a SourceContext")

    if not isinstance(delta, MarketDataBundle):
        raise TypeError("delta must be a MarketDataBundle")

    if not isinstance(spec, MarketDataPublishSpec):
        raise TypeError("spec must be a MarketDataPublishSpec")

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

    publication_delta = MarketDataBundle(
        market = MarketData(
            close = delta.market.close,
            volume = delta.market.volume,
        ),
        calendar = delta.calendar,
        metadata = dict(delta.metadata),
    )

    previous = load_latest_market_data_before(
        output_root,
        dataset_id= spec.dataset_id,
        as_of_date=as_of_date
    )
    cumulative = (
        publication_delta if previous is None
        else append_market_data_history(previous[1], publication_delta)
    )

    return publish_market_data_bundle(
        cumulative,
        root = output_root,
        spec = spec,
    )

def load_market_data_batches(
        context: SourceContext,
        *,
        source_component: DataSourceComponent,
        binding: DataBinding,
        policy: MarketDataRefreshPolicy,
        sleeper: Sleeper = time.sleep,
        publish_spec: MarketDataPublishSpec | None = None
) -> MarketDataBundle:
    """Load ticker batches with component-specific retry classification."""

    if not isinstance(context, SourceContext):
        raise TypeError("context must be a SourceContext")

    if not isinstance(source_component, DataSourceComponent):
        raise TypeError(
            "source_component must be a DataSourceComponent"
        )

    if not isinstance(binding, DataBinding):
        raise TypeError("binding must be a DataBinding")

    if not isinstance(policy, MarketDataRefreshPolicy):
        raise TypeError(
            "policy must be a MarketDataRefreshPolicy"
        )

    if not callable(sleeper):
        raise TypeError("sleeper must be callable")

    batch_bindings = partition_data_binding(
        binding,
        batch_size = policy.batch_size,
    )

    total_batches = len(batch_bindings)

    _LOGGER.info(
        "market-data refresh started: source=%s tickers=%d batches=%d "
        "batch_size=%d resume=%s",
        source_component.id,
        len(binding.tickers),
        total_batches,
        policy.batch_size,
        policy.resume
    )

    checkpoint_root = None
    checkpoint_id = None

    if policy.checkpoint_connection_ref is not None:
        if publish_spec is None:
            raise ValueError(
                "publish_spec is required when checkpointing is enabled"
            )

        checkpoint_root = context.connections.writable_parquet_root(
            policy.checkpoint_connection_ref
        )
        checkpoint_id = market_data_checkpoint_id(
            source_component=source_component,
            binding = binding,
            publish_spec = publish_spec,
            policy = policy
        )

    loaded_batches: list[MarketDataBundle] = []



    for batch_number, batch_binding in enumerate(
        batch_bindings,
        start = 1,
    ):
        _LOGGER.info(
                "market-data batch %d/%d started: tickers=%d",
                batch_number,
                total_batches,
                len(batch_binding.tickers)
            )

        bundle = None

        if (
            checkpoint_root is not None
            and checkpoint_id is not None
            and policy.resume
        ):
            bundle = load_market_data_batch_checkpoint(
                checkpoint_root,
                checkpoint_id = checkpoint_id,
                batch_number = batch_number,
                binding = batch_binding,
            )

        if bundle is not None:
            _LOGGER.info(
                "market-data batch %d/%d restored from checkpoint",
                batch_number,
                total_batches,
            )

        if bundle is None:
        
            def load_batch(
                    current_binding: DataBinding = batch_binding,
            ) -> MarketDataBundle:
                return load_data_source_component(
                    source_component,
                    current_binding,
                    context,
                )

            classifier = source_component.retry_classifier

            if classifier is None or policy.max_retries == 0:
                bundle = load_batch()

            else:
                bundle = retry_call(
                    load_batch,
                    label = (
                        f"market-data batch "
                        f"{batch_number}/{len(batch_bindings)}"
                    ),
                    policy = RetryPolicy(
                        attempts = policy.max_retries +1,
                    ),
                    should_retry = classifier,
                    sleeper = sleeper,
                )

            if (
                checkpoint_root is not None
                and checkpoint_id is not None
            ):
                save_market_data_batch_checkpoint(
                    checkpoint_root,
                    checkpoint_id = checkpoint_id,
                    batch_number = batch_number,
                    binding = batch_binding,
                    bundle = bundle
                )

        loaded_batches.append(bundle)

        _LOGGER.info(
            "market-data batch %d/%d completed",
            batch_number,
            total_batches,
        )

    merged = merge_market_data_batches(loaded_batches)
    _LOGGER.info(
        "market-data refresh completed: source=%s batches=%d",
        source_component.id,
        total_batches,
    )
    return merged



def refresh_market_data(
        context: SourceContext,
        *,
        source_component: DataSourceComponent,
        binding: DataBinding,
        output_connection_ref: str,
        publish_spec: MarketDataPublishSpec,
        policy: MarketDataRefreshPolicy | None = None
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

    if policy is None:
        bundle = load_data_source_component(
            source_component,
            binding,
            context,
        )

    else:
        bundle = load_market_data_batches(
            context,
            source_component=source_component,
            binding = binding,
            policy = policy,
            publish_spec=publish_spec
        )

    return publish_market_data_bundle(
        bundle,
        root = output_root,
        spec = publish_spec
    )

def _merge_optional_market_field(
        batches: Sequence[MarketDataBundle],
        *,
        field_name: str,
) -> pd.DataFrame | None:
    frames = [
        getattr(batch.market, field_name)
        for batch in batches
    ]

    if all(frame is None for frame in frames):
        return None

    if any(frame is None for frame in frames):
        raise ValueError(
            f"market-data batches provide inconsistent {field_name}"
        )

    merged = pd.concat(
        frames,
        axis = 1,
        join = "outer",
        sort = False,
    )

    if merged.columns.has_duplicates:
        raise ValueError(
            f"market-data batches contain duplicate {field_name} tickers"
        )

    return merged.sort_index().sort_index(axis=1)

def _merge_batch_calendars(
        batches: Sequence[MarketDataBundle],
) -> pd.DatetimeIndex | None:
    calendars = [batch.calendar for batch in batches]

    if all(calendar is None for calendar in calendars):
        return None

    if any(calendar is None for calendar in calendars):
        raise ValueError(
            "market-data batches provide inconsistent calendars"
        )

    merged = pd.DatetimeIndex([])

    for calendar in calendars:
        merged = merged.union(pd.DatetimeIndex(calendar))

    return merged.sort_values()

def market_data_checkpoint_id(
        *,
        source_component: DataSourceComponent,
        binding: DataBinding,
        publish_spec: MarketDataPublishSpec,
        policy: MarketDataRefreshPolicy,
) -> str:
    """Return a stable identity for one complete batched refresh request."""

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

    if not isinstance(policy, MarketDataRefreshPolicy):
        raise TypeError(
            "policy must be a MarketDataRefreshPolicy"
        )

    payload = {
        "source_component_id": source_component.id,
        "binding": {
            "connection_ref": binding.connection_ref,
            "dataset": binding.dataset,
            "version": binding.version,
            "start": binding.start,
            "end": binding.end,
            "tickers": list(binding.tickers),
            "adjustment": binding.adjustment,
            "metadata": dict(binding.metadata),
        },
        "publication": {
            "dataset_id": publish_spec.dataset_id,
            "market": publish_spec.market,
            "version": publish_spec.version,
            "source": publish_spec.source,
            "frequency": publish_spec.frequency,
            "adjustment": publish_spec.adjustment,
            "schema_version": publish_spec.schema_version,
        },
        "batch_size": policy.batch_size,
    }

    try:
        serialized = json.dumps(
            payload,
            ensure_ascii = False,
            sort_keys= True,
            separators=(",", ":"),
        )

    except (TypeError, ValueError) as error:
        raise TypeError(
            "market-data checkpoint identity must be JSON serializable"
        ) from error

    return sha256(serialized.encode("utf-8")).hexdigest()
