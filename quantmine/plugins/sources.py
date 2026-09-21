"""Built-in runtime adapters for legacy, SQL, and Parquet data sources."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re
from typing import Mapping

import pandas as pd

from ..datareader import ConstituentsSource, DataSource, MarketData
from .context import SourceContext
from .contracts import (
    DataBinding,
    DataSourceComponent,
    MarketDataBundle,
    MarketDataCapability,
)

_BASE_VERSION = re.compile(r"(?P<date>\d{8})\Z")
_REVISION_VERSION = re.compile(r"\d{8}-r[1-9]\d*\Z")

_MARKET_DATA_FIELDS: Mapping[MarketDataCapability, str] = {
    MarketDataCapability.CLOSE: 'close',
    MarketDataCapability.VOLUME: 'volume',
    MarketDataCapability.MARKET_CAP: 'market_cap',
}

def _require_legacy_request(binding: DataBinding)-> None:
    if not binding.tickers:
        raise ValueError("LegacyDataSourcePlugin requires DataBinding.tickers to be set")

    if binding.start is None or binding.end is None:
        raise ValueError("LegacyDataSourcePlugin reuiqres DataBinding.start and DataBinding.end")

def _calendar_from_market_data(market: MarketData) -> pd.DatetimeIndex | None:
    for frame in (market.close, market.volume, market.market_cap):
        if frame is not None:
            return pd.DatetimeIndex(pd.to_datetime(frame.index)).sort_values()
    return None

def _market_data_from_frames(
        frames: Mapping[MarketDataCapability, pd.DataFrame]
) -> MarketData:
    invalid = set(frames) - set(_MARKET_DATA_FIELDS)
    if invalid:
        unsupported = ','.join(
            sorted(capability.value for capability in invalid)
        )
        raise ValueError(
            f"MarketData cannot hold unsupported fields: {unsupported}"
        )

    values = {
        field_name: frames.get(capability)
        for capability, field_name in _MARKET_DATA_FIELDS.items()
    }
    return MarketData(**values)

def _normalize_wide_frame(frame: pd.DataFrame) -> pd.DataFrame: #保证所有宽表都是日期递增、股票列排序，避免不同存储源产生不稳定顺序
    normalized = frame.copy()
    normalized.index = pd.DatetimeIndex(pd.to_datetime(normalized.index))
    return normalized.sort_index().sort_index(axis=1)

@dataclass(frozen=True)
class LegacyDataSourcePlugin: #把旧 DataSource.load(tickers, start, end) 包装成新协议
    """Adapt the existing ``DataSouce.load`` protocol to the plugin contract"""

    source: DataSource
    universe: ConstituentsSource | None = None
    metadata: Mapping[str, object] = field(default_factory = dict)

    def load(
            self,
            binding: DataBinding,
            context: SourceContext,
    )->MarketDataBundle:
        _require_legacy_request(binding)

        market = self.source.load(
            tickers = list(binding.tickers),
            start = binding.start,
            end = binding.end,
        )

        return MarketDataBundle(
            market = market,
            universe = self.universe,
            calendar = _calendar_from_market_data(market),
            metadata = {
                **self.metadata,
                "connection_ref": binding.connection_ref,
                "dataset": binding.dataset,
                "source_kind": "legacy"
            },
        )

@dataclass(frozen=True)
class SqlLongFormatDataSourcePlugin: #读取 SQL 长表（每行一个日期和股票），再 pivot 成因子计算要求的“日期 × 股票”宽表；重复行会明确报错，不会静默取任一条。
    """Load price fields from a long-format SQL table.

    The dataset named in ``DataBinding.dataset`` must contain one row per
    ``date_column`` and ``ticker_column``. Duplicate date/ticker rows raise
    during pivoting, which protects factor calculations from silently selecting
    arbitrary duplicate observations.
    """
    field_columns: Mapping[MarketDataCapability, str]
    date_column: str = 'date'
    ticker_column: str = 'ticker'
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.field_columns:
            raise ValueError("field_columns must define at least one market field")

        invalid = set(self.field_columns) - set(_MARKET_DATA_FIELDS)
        if invalid:
            unsupported = ",".join(
                sorted(capability.value for capability in invalid)
            )
            raise ValueError(
                f"SQL source declares unsupported MarketData fields: {unsupported}"
            )

    def load(
        self,
        binding: DataBinding,
        context: SourceContext,
    ) -> MarketDataBundle:
        if not binding.tickers:
            raise ValueError(
                "SqlLongFormatDataSourcePlugin requires DataBinding.tickers"
            )

        try:
            from sqlalchemy import MetaData, Table, select

        except ImportError as error:
            raise RuntimeError(
                "SQLAlchemy support is not installed"
                "Install qunatmine with its 'db' extra"
            ) from error

        connection_ref = _require_connection_ref(
            binding,
            "SqlLongFormatDataSourcePlugin"
        )

        engine = context.connections.sqlalchemy_engine(connection_ref)
        table = Table(
            binding.dataset,
            MetaData(),
            autoload_with=engine,
        )

        requested_columns = (
            self.date_column,
            self.ticker_column,
            *self.field_columns.values()
        )

        missing_columns = [column for column in requested_columns if column not in table.c]
        if missing_columns:
            missing = ",".join(sorted(missing_columns))
            raise ValueError(
                f"Dataset {binding.dataset!r} is missing required columns: {missing}"
            )

        statement = select(
            table.c[self.date_column],
            table.c[self.ticker_column],
            *(
                table.c[column] for column in self.field_columns.values()
            ),
        ).where(table.c[self.ticker_column].in_(binding.tickers))

        if binding.start is not None:
            statement = statement.where(table.c[self.date_column] >= pd.Timestamp(binding.start))

        if binding.end is not None:
            statement = statement.where(
                table.c[self.date_column] <= pd.Timestamp(binding.end)
            )
        with engine.connect() as connection:
            long_data = pd.read_sql(statement, connection)

        frames: dict[MarketDataCapability, pd.DataFrame] = {}
        for capability, value_column in self.field_columns.items():
            frame = long_data.pivot(
                index = self.date_column,
                columns=self.ticker_column,
                values = value_column,
            )
            frames[capability] = _normalize_wide_frame(frame)

        market = _market_data_from_frames(frames)

        return MarketDataBundle(
            market = market,
            calendar = _calendar_from_market_data(market),
            metadata = {
                **self.metadata,
                "connection_ref": binding.connection_ref,
                "dataset": binding.dataset,
                "source_kind": "sql_long_format"
            },
        )

@dataclass(frozen = True)
class ParquetWideFrameDataSourcePlugin: #读取宽表 Parquet；它只允许访问 <lake_root>/<dataset>/ 下的相对路径，防止运行配置越权读取任意本地文件。
    """Load wide date-by-ticker Parquet files from a named data lake.

    ``field_files`` maps a MarketData capability to a relative path under
    ``<parquet_root>/<binding.dataset>/``. Relative-path validation prevents a
    data binding from escaping its configured lake root.
    """

    field_files: Mapping[MarketDataCapability, str]
    metadata: Mapping[str, object] = field(default_factory= dict)

    def __post_init__(self)->None:
        if not self.field_files:
            raise ValueError("field_files must define at least one market field")

        invalid = set(self.field_files) - set(_MARKET_DATA_FIELDS)
        if invalid:
            unsupported = ",".join(sorted(capability.value for capability in invalid)
                                   )
            raise ValueError(
                f"Parquet source declares unsupported MarketData fields: {unsupported}"
            )
        absolute_paths = [
            path for path in self.field_files.values()
            if Path(path).is_absolute()
        ]
        if absolute_paths:
            paths = ",".join(sorted(absolute_paths))
            raise ValueError(
                f"Parquet field files must be relative paths: {paths}"
            )

    def load(
                self,
                binding: DataBinding,
                context: SourceContext
        ) -> MarketDataBundle:

            connection_ref = _require_connection_ref(
                binding,
                "ParquetWideFrameDataSourcePlugin"
            )

            lake_root = context.connections.parquet_root(connection_ref)
            dataset_root = (lake_root/binding.dataset).resolve()
            lake_root_resolved = lake_root.resolve()

            try:
                dataset_root.relative_to(lake_root_resolved)
            except ValueError as error:
                raise ValueError(
                    f"Dataset path {binding.dataset!r} escapes the configured lake root"
                ) from error

            
            frames: dict[MarketDataCapability, pd.DataFrame] = {}
            for capability, relative_file in self.field_files.items():
                path = (dataset_root / relative_file).resolve()

                try:
                    path.relative_to(dataset_root)
                except ValueError as error:
                    raise ValueError(
                        f"Field path {relative_file!r} escapes dataset"
                        f"{binding.dataset!r}"
                    ) from error

                if not path.is_file():
                    raise FileNotFoundError(
                        f"Parquet file for {capability.value!r} does not exist: {path}"
                    )

                frame = _normalize_wide_frame(pd.read_parquet(path))

                if binding.start is not None or binding.end is not None:
                    frame = frame.loc[binding.start:binding.end]

                if binding.tickers:
                    frame = frame.loc[:, list(binding.tickers)]

                frames[capability] = frame
            market = _market_data_from_frames(frames)

            return MarketDataBundle(
                market = market,
                calendar = _calendar_from_market_data(market),
                metadata = {
                    **self.metadata,
                    "connection_ref": binding.connection_ref,
                    "dataset": binding.dataset,
                    "source_kind": "parquet_wide_format"
                }
            )

@dataclass(frozen = True)
class VersionedParquetMarketDataSourcePlugin:
    """Load one immutable close-and-volume market-data publication.

    The binding version is resolved against the published version directories:

    * an explicit ``YYYYMMDD-rN`` request loads exactly that revision;
    * a base ``YYYYMMDD`` request resolves to the highest ``YYYYMMDD-rN`` through
      the same trading date, so a reader follows same-day repairs automatically;
    * an unknown date has no fallback and raises ``FileNotFoundError``.
    """

    close_file: str = "close.parquet"
    volume_file: str = "volume.parquet"
    metadata: Mapping[str, object] = field(default_factory=dict)
    def load(
            self,
            binding: DataBinding,
            context: SourceContext,
    ) -> MarketDataBundle:
        version = binding.version
        if (
            not isinstance(version, str)
            or not version
            or version.strip() != version
            or version in {".", ".."}
            or "/" in version
            or "\\" in version
        ):
            raise ValueError(
                "DataBinding.version must be a safe path segment"
            )

        connection_ref = _require_connection_ref(
            binding,
            "VersionedParquetMarketDataSourcePlugin",
        )
        versions_dir = (
            context.connections.parquet_root(connection_ref)
            / binding.dataset
            / "versions"
        ).resolve()
        resolved = _resolve_published_version(versions_dir, version)

        return ParquetWideFrameDataSourcePlugin(
            field_files = {
                MarketDataCapability.CLOSE: (
                    f"versions/{resolved}/{self.close_file}"
                ),
                MarketDataCapability.VOLUME:(
                    f"versions/{resolved}/{self.volume_file}"
                ),
            },
            metadata = {
                **self.metadata,
                "version": resolved,
                "requested_version": version,
            },
        ).load(binding, context)

def _resolve_published_version(
        versions_dir: Path,
        requested: str,
) -> str:
    """Return the immutable version directory a binding should actually read.

    An explicit ``YYYYMMDD-rN`` request is honoured exactly.  A base
    ``YYYYMMDD`` request resolves to the highest same-day revision, so research
    automatically follows the latest immutable repair publication.
    """

    revision_match = _REVISION_VERSION.fullmatch(requested)

    if revision_match is not None:
        if (versions_dir / requested).is_dir():
            return requested
        raise FileNotFoundError(
            f"market-data version {requested!r} does not exist under "
            f"{versions_dir}"
        )

    base_match = _BASE_VERSION.fullmatch(requested)
    if base_match is None:
        raise FileNotFoundError(
            f"market-data version {requested!r} does not exist under "
            f"{versions_dir}"
        )

    base = base_match.group("date")
    highest_revision = 0

    if versions_dir.is_dir():
        revision_pattern = re.compile(
            re.escape(base) + r"-r(?P<revision>[1-9]\d*)\Z"
        )
        for candidate in versions_dir.iterdir():
            if not candidate.is_dir():
                continue
            match = revision_pattern.fullmatch(candidate.name)
            if match is None:
                continue
            highest_revision = max(
                highest_revision,
                int(match.group("revision")),
            )

    if highest_revision:
        return f"{base}-r{highest_revision}"

    if (versions_dir / requested).is_dir():
        return requested

    raise FileNotFoundError(
        f"market-data version {requested!r} does not exist under "
        f"{versions_dir}"
    )

def _require_connection_ref(binding: DataBinding, source_name: str) -> str:
    if binding.connection_ref is None:
        raise ValueError(
            f"{source_name} requires DataBinding.connection_ref"
        )
    return binding.connection_ref

def create_versioned_parquet_market_data_source(
        *,
        close_file: str = "close.parquet",
        volume_file: str = "volume.parquet",
        metadata: Mapping[str, object] | None = None,
) -> DataSourceComponent:
    """Create the standard reader for immutable market-data publications."""

    return DataSourceComponent(
        id="versioned_parquet_market_data",
        capabilities = frozenset(
            {
                MarketDataCapability.CLOSE,
                MarketDataCapability.VOLUME,
            }
        ),
        plugin = VersionedParquetMarketDataSourcePlugin(
            close_file = close_file,
            volume_file = volume_file,
            metadata = dict(metadata or {}),
        ),
        requires_connection = True,
        metadata = {
            "storage": "parquet",
            "layout": "versioned_wide_frames",
        },
    )