"""Contract tests for runtime market-data source plugins."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest
from sqlalchemy import Column, Date, Float, MetaData, String, Table, insert

from quantmine.datareader import MarketData
from quantmine.plugins.context import SourceContext
from quantmine.plugins.contracts import DataBinding, MarketDataCapability
from quantmine.plugins.sources import (
    LegacyDataSourcePlugin,
    ParquetWideFrameDataSourcePlugin,
    SqlLongFormatDataSourcePlugin,
)
from quantmine.storage.connections import (
    ConnectionKind,
    ConnectionRegistry,
    DataConnectionConfig,
)


class InMemoryLegacySource:
    """Minimal implementation of the pre-plugin DataSource protocol."""

    def __init__(self) -> None:
        self.request: tuple[list[str], str, str] | None = None

    def load(self, tickers: list[str], start: str, end: str) -> MarketData:
        self.request = (tickers, start, end)
        index = pd.to_datetime(["2024-01-02", "2024-01-03"])
        return MarketData(
            close=pd.DataFrame(
                {ticker: [10.0, 11.0] for ticker in tickers},
                index=index,
            )
        )


def _context(tmp_path: Path, registry: ConnectionRegistry) -> SourceContext:
    return SourceContext(
        connections=registry,
        run_id=101,
        artifact_dir=tmp_path / "artifacts",
    )


def _binding(**overrides: object) -> DataBinding:
    values: dict[str, object] = {
        "connection_ref": "test_connection",
        "dataset": "daily_prices",
        "start": "2024-01-02",
        "end": "2024-01-03",
        "tickers": ("AAA", "BBB"),
    }
    values.update(overrides)
    return DataBinding(**values)


def test_legacy_adapter_converts_old_source_to_market_data_bundle(tmp_path: Path) -> None:
    source = InMemoryLegacySource()
    plugin = LegacyDataSourcePlugin(source=source)

    result = plugin.load(
        _binding(),
        _context(tmp_path, ConnectionRegistry({})),
    )

    assert source.request == (["AAA", "BBB"], "2024-01-02", "2024-01-03")
    assert result.market.close.loc[pd.Timestamp("2024-01-03"), "AAA"] == 11.0
    assert list(result.calendar) == list(pd.to_datetime(["2024-01-02", "2024-01-03"]))
    assert result.metadata["source_kind"] == "legacy"


def test_sql_long_format_plugin_returns_sorted_wide_frames(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("QUANTMINE_B2_SQL_URL", "sqlite://")
    registry = ConnectionRegistry(
        {
            "test_connection": DataConnectionConfig(
                kind=ConnectionKind.SQLALCHEMY,
                url_env="QUANTMINE_B2_SQL_URL",
            )
        }
    )
    engine = registry.sqlalchemy_engine("test_connection")
    metadata = MetaData()
    prices = Table(
        "daily_prices",
        metadata,
        Column("date", Date, nullable=False),
        Column("ticker", String, nullable=False),
        Column("close", Float, nullable=False),
        Column("volume", Float, nullable=False),
    )
    metadata.create_all(engine)

    with engine.begin() as connection:
        connection.execute(
            insert(prices),
            [
                {"date": date(2024, 1, 3), "ticker": "BBB", "close": 21.0, "volume": 210.0},
                {"date": date(2024, 1, 2), "ticker": "AAA", "close": 10.0, "volume": 100.0},
                {"date": date(2024, 1, 3), "ticker": "AAA", "close": 11.0, "volume": 110.0},
                {"date": date(2024, 1, 2), "ticker": "BBB", "close": 20.0, "volume": 200.0},
            ],
        )

    plugin = SqlLongFormatDataSourcePlugin(
        field_columns={
            MarketDataCapability.CLOSE: "close",
            MarketDataCapability.VOLUME: "volume",
        }
    )
    result = plugin.load(_binding(), _context(tmp_path, registry))

    assert list(result.market.close.index) == list(
        pd.to_datetime(["2024-01-02", "2024-01-03"])
    )
    assert list(result.market.close.columns) == ["AAA", "BBB"]
    assert result.market.close.loc[pd.Timestamp("2024-01-03"), "BBB"] == 21.0
    assert result.market.volume.loc[pd.Timestamp("2024-01-02"), "AAA"] == 100.0
    assert result.metadata["source_kind"] == "sql_long_format"


def test_sql_plugin_requires_a_connection_ref(tmp_path: Path) -> None:
    plugin = SqlLongFormatDataSourcePlugin(
        field_columns={MarketDataCapability.CLOSE: "close"},
    )

    with pytest.raises(ValueError, match="requires DataBinding.connection_ref"):
        plugin.load(
            _binding(connection_ref=None),
            _context(tmp_path, ConnectionRegistry({})),
        )


def test_parquet_wide_frame_plugin_slices_dates_and_tickers(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    lake_root = tmp_path / "lake"
    dataset_root = lake_root / "daily_prices"
    dataset_root.mkdir(parents=True)
    monkeypatch.setenv("QUANTMINE_B2_PARQUET_ROOT", str(lake_root))

    index = pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04"])
    pd.DataFrame(
        {"BBB": [20.0, 21.0, 22.0], "AAA": [10.0, 11.0, 12.0]},
        index=index,
    ).to_parquet(dataset_root / "close.parquet")
    pd.DataFrame(
        {"BBB": [200.0, 210.0, 220.0], "AAA": [100.0, 110.0, 120.0]},
        index=index,
    ).to_parquet(dataset_root / "volume.parquet")

    registry = ConnectionRegistry(
        {
            "test_connection": DataConnectionConfig(
                kind=ConnectionKind.PARQUET,
                root_env="QUANTMINE_B2_PARQUET_ROOT",
            )
        }
    )
    plugin = ParquetWideFrameDataSourcePlugin(
        field_files={
            MarketDataCapability.CLOSE: "close.parquet",
            MarketDataCapability.VOLUME: "volume.parquet",
        }
    )
    result = plugin.load(
        _binding(end="2024-01-03", tickers=("AAA",)),
        _context(tmp_path, registry),
    )

    assert list(result.market.close.columns) == ["AAA"]
    assert list(result.market.close.index) == list(
        pd.to_datetime(["2024-01-02", "2024-01-03"])
    )
    assert result.market.volume.loc[pd.Timestamp("2024-01-03"), "AAA"] == 110.0
    assert result.metadata["source_kind"] == "parquet_wide_format"


def test_parquet_plugin_rejects_paths_outside_the_dataset_root() -> None:
    with pytest.raises(ValueError, match="relative paths"):
        ParquetWideFrameDataSourcePlugin(
            field_files={
                MarketDataCapability.CLOSE: str(Path.cwd().resolve()),
            }
        )
