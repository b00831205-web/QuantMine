"""Tests for A-share universe binding before generic market-data refresh."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from quantmine.datareader import MarketData
from quantmine.plugins.context import SourceContext
from quantmine.plugins.contracts import (
    DataBinding,
    DataSourceComponent,
    MarketDataBundle,
    MarketDataCapability,
    VersionedDatasetBinding,
)
from quantmine.storage.connections import (
    ConnectionKind,
    ConnectionRegistry,
    DataConnectionConfig,
)
from quantmine.workflows.a_share_market_data_refresh import (
    AStockHistoryRefreshConfig,
    refresh_a_share_cumulative_market_data,
    refresh_a_share_historical_market_data,
    run_configured_a_share_history_refresh,
)
from quantmine.plugins.contracts import PluginSpec
from quantmine.workflows import a_share_market_data_refresh as refresh_module
from quantmine.workflows.market_data_publication import MarketDataPublishSpec
from quantmine.workflows.market_data_refresh import MarketDataRefreshPolicy


class RecordingAStockSource:
    def __init__(self) -> None:
        self.bindings: list[DataBinding] = []

    def load(
        self,
        binding: DataBinding,
        context: SourceContext,
    ) -> MarketDataBundle:
        del context
        self.bindings.append(binding)
        dates = pd.to_datetime(["2024-01-02", "2024-01-03"])
        close = pd.DataFrame(
            {
                ticker: [10.0 + offset, 11.0 + offset]
                for offset, ticker in enumerate(binding.tickers)
            },
            index=dates,
        )
        volume = pd.DataFrame(
            {
                ticker: [1_000 + offset, 1_100 + offset]
                for offset, ticker in enumerate(binding.tickers)
            },
            index=dates,
        )
        return MarketDataBundle(
            market=MarketData(close=close, volume=volume)
        )


class DailyRecordingAStockSource:
    """Return exactly the requested single-session panel."""

    def __init__(self) -> None:
        self.bindings: list[DataBinding] = []

    def load(
        self,
        binding: DataBinding,
        context: SourceContext,
    ) -> MarketDataBundle:
        del context
        self.bindings.append(binding)
        date = pd.Timestamp(binding.start).normalize()
        close = pd.DataFrame(
            {
                ticker: [10.0 + offset + date.day]
                for offset, ticker in enumerate(binding.tickers)
            },
            index=pd.DatetimeIndex([date], name="date"),
        )
        volume = pd.DataFrame(
            {
                ticker: [1_000 + offset]
                for offset, ticker in enumerate(binding.tickers)
            },
            index=pd.DatetimeIndex([date], name="date"),
        )
        return MarketDataBundle(
            market=MarketData(close=close, volume=volume)
        )


def _write_reference(root: Path) -> None:
    version_root = root / "cn_reference" / "versions" / "reference_v1"
    version_root.mkdir(parents=True)
    pd.DataFrame(
        {
            "listing_id": ["A-1", "B-1", "C-1", "D-1", "E-1"],
            "ticker": ["000001", "000002", "000003", "000004", "000004"],
            "list_date": [
                "2020-01-01",
                "2020-01-01",
                "2024-02-01",
                "2020-01-01",
                "2024-01-03",
            ],
            "delist_date": [
                None,
                "2024-01-02",
                None,
                "2023-01-01",
                None,
            ],
            "exchange": ["SZSE"] * 5,
            "security_type": ["COMMON_STOCK"] * 5,
        }
    ).to_parquet(version_root / "security_master.parquet", index=False)
    pd.DataFrame(
        {"date": pd.to_datetime(["2024-01-02", "2024-01-03"])}
    ).to_parquet(version_root / "trading_calendar.parquet", index=False)


def _publish_spec(*, version: str) -> MarketDataPublishSpec:
    return MarketDataPublishSpec(
        dataset_id="cn_a_share_daily_bars",
        market="CN",
        version=version,
        source="fixture",
        frequency="daily",
        adjustment="hfq",
    )


def test_a_share_refresh_derives_window_tickers_then_uses_generic_refresh(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    reference_root = tmp_path / "reference_lake"
    output_root = tmp_path / "market_data_lake"
    output_root.mkdir()
    _write_reference(reference_root)
    monkeypatch.setenv("QUANTMINE_TEST_CN_REFERENCE_ROOT", str(reference_root))
    monkeypatch.setenv("QUANTMINE_TEST_CN_MARKET_DATA_ROOT", str(output_root))
    context = SourceContext(
        connections=ConnectionRegistry(
            {
                "cn_reference": DataConnectionConfig(
                    kind=ConnectionKind.PARQUET,
                    root_env="QUANTMINE_TEST_CN_REFERENCE_ROOT",
                    read_only=True,
                ),
                "cn_market_data": DataConnectionConfig(
                    kind=ConnectionKind.PARQUET,
                    root_env="QUANTMINE_TEST_CN_MARKET_DATA_ROOT",
                    read_only=False,
                ),
            }
        ),
        run_id=201,
        artifact_dir=tmp_path / "artifacts",
    )
    source = RecordingAStockSource()
    component = DataSourceComponent(
        id="recording_a_stock_source",
        capabilities=frozenset(
            {
                MarketDataCapability.CLOSE,
                MarketDataCapability.VOLUME,
            }
        ),
        plugin=source,
    )
    binding = DataBinding(
        connection_ref=None,
        dataset="provider_request",
        start="2024-01-02",
        end="2024-01-31",
        adjustment="hfq",
    )

    publication = refresh_a_share_historical_market_data(
        context,
        source_component=component,
        binding=binding,
        reference_binding=VersionedDatasetBinding(
            connection_ref="cn_reference",
            dataset="cn_reference",
            market="CN",
            version="reference_v1",
        ),
        output_connection_ref="cn_market_data",
        publish_spec=MarketDataPublishSpec(
            dataset_id="cn_a_share_daily_bars",
            market="CN",
            version="bars_v1",
            source="fixture",
            frequency="daily",
            adjustment="hfq",
        ),
    )

    assert binding.tickers == ()
    assert len(source.bindings) == 1
    assert source.bindings[0].tickers == ("000001", "000004")
    assert publication.ticker_count == 2
    assert publication.output_dir == (
        output_root
        / "cn_a_share_daily_bars"
        / "versions"
        / "bars_v1"
    )


def test_a_share_cumulative_refresh_publishes_full_history_from_daily_delta(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    reference_root = tmp_path / "reference_lake"
    output_root = tmp_path / "market_data_lake"
    output_root.mkdir()
    _write_reference(reference_root)
    monkeypatch.setenv("QUANTMINE_TEST_CN_REFERENCE_ROOT", str(reference_root))
    monkeypatch.setenv("QUANTMINE_TEST_CN_MARKET_DATA_ROOT", str(output_root))
    context = SourceContext(
        connections=ConnectionRegistry(
            {
                "cn_reference": DataConnectionConfig(
                    kind=ConnectionKind.PARQUET,
                    root_env="QUANTMINE_TEST_CN_REFERENCE_ROOT",
                    read_only=True,
                ),
                "cn_market_data": DataConnectionConfig(
                    kind=ConnectionKind.PARQUET,
                    root_env="QUANTMINE_TEST_CN_MARKET_DATA_ROOT",
                    read_only=False,
                ),
            }
        ),
        run_id=202,
        artifact_dir=tmp_path / "artifacts",
    )
    source = DailyRecordingAStockSource()
    component = DataSourceComponent(
        id="daily_recording_a_stock_source",
        capabilities=frozenset(
            {MarketDataCapability.CLOSE, MarketDataCapability.VOLUME}
        ),
        plugin=source,
    )
    reference_binding = VersionedDatasetBinding(
        connection_ref="cn_reference",
        dataset="cn_reference",
        market="CN",
        version="reference_v1",
    )

    first = refresh_a_share_cumulative_market_data(
        context,
        source_component=component,
        binding=DataBinding(
            connection_ref=None,
            dataset="provider_request",
            start="2024-01-02",
            end="2024-01-02",
            adjustment="hfq",
        ),
        reference_binding=reference_binding,
        output_connection_ref="cn_market_data",
        publish_spec=_publish_spec(version="20240102"),
    )
    second = refresh_a_share_cumulative_market_data(
        context,
        source_component=component,
        binding=DataBinding(
            connection_ref=None,
            dataset="provider_request",
            start="2024-01-03",
            end="2024-01-03",
            adjustment="hfq",
        ),
        reference_binding=reference_binding,
        output_connection_ref="cn_market_data",
        publish_spec=_publish_spec(version="20240103"),
    )

    assert first.date_count == 1
    assert second.date_count == 2
    assert source.bindings[0].tickers == ("000001",)
    assert source.bindings[1].tickers == ("000001", "000004")
    close = pd.read_parquet(second.close_path)
    assert close.index.equals(
        pd.DatetimeIndex(["2024-01-02", "2024-01-03"], name="date")
    )
    assert close.columns.tolist() == ["000001", "000004"]
    assert pd.isna(close.loc[pd.Timestamp("2024-01-02"), "000004"])


def test_a_share_refresh_requires_a_bounded_history_window(
    tmp_path: Path,
) -> None:
    source = RecordingAStockSource()
    context = SourceContext(
        connections=ConnectionRegistry({}),
        run_id=202,
        artifact_dir=tmp_path / "artifacts",
    )

    with pytest.raises(
        ValueError,
        match="binding.start and binding.end",
    ):
        refresh_a_share_historical_market_data(
            context,
            source_component=DataSourceComponent(
                id="recording_a_stock_source",
                capabilities=frozenset(
                    {
                        MarketDataCapability.CLOSE,
                        MarketDataCapability.VOLUME,
                    }
                ),
                plugin=source,
            ),
            binding=DataBinding(
                connection_ref=None,
                dataset="provider_request",
            ),
            reference_binding=VersionedDatasetBinding(
                connection_ref="cn_reference",
                dataset="cn_reference",
                market="CN",
                version="reference_v1",
            ),
            output_connection_ref="cn_market_data",
            publish_spec=MarketDataPublishSpec(
                dataset_id="cn_a_share_daily_bars",
                market="CN",
                version="bars_v1",
                source="fixture",
                frequency="daily",
            ),
        )

    assert source.bindings == []


def test_a_share_refresh_forwards_policy_to_generic_refresh(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    reference_root = tmp_path / "reference_lake"
    _write_reference(reference_root)
    monkeypatch.setenv("QUANTMINE_TEST_CN_REFERENCE_ROOT", str(reference_root))
    context = SourceContext(
        connections=ConnectionRegistry(
            {
                "cn_reference": DataConnectionConfig(
                    kind=ConnectionKind.PARQUET,
                    root_env="QUANTMINE_TEST_CN_REFERENCE_ROOT",
                    read_only=True,
                ),
            }
        ),
        run_id=205,
        artifact_dir=tmp_path / "artifacts",
    )
    component = DataSourceComponent(
        id="configured_source",
        capabilities=frozenset(
            {
                MarketDataCapability.CLOSE,
                MarketDataCapability.VOLUME,
            }
        ),
        plugin=RecordingAStockSource(),
    )
    binding = DataBinding(
        connection_ref=None,
        dataset="provider_request",
        start="2024-01-02",
        end="2024-01-31",
        adjustment="hfq",
    )
    publish_spec = MarketDataPublishSpec(
        dataset_id="cn_a_share_daily_bars",
        market="CN",
        version="bars_v1",
        source="fixture",
        frequency="daily",
        adjustment="hfq",
    )
    policy = MarketDataRefreshPolicy(
        batch_size=25,
        max_retries=4,
        checkpoint_connection_ref="cn_checkpoint",
        resume=False,
    )
    marker = SimpleNamespace(name="publication")
    dispatched: list[dict[str, object]] = []

    def fake_refresh(context_arg, **kwargs):
        dispatched.append({"context": context_arg, **kwargs})
        return marker

    monkeypatch.setattr(refresh_module, "refresh_market_data", fake_refresh)

    result = refresh_a_share_historical_market_data(
        context,
        source_component=component,
        binding=binding,
        reference_binding=VersionedDatasetBinding(
            connection_ref="cn_reference",
            dataset="cn_reference",
            market="CN",
            version="reference_v1",
        ),
        output_connection_ref="cn_market_data",
        publish_spec=publish_spec,
        policy=policy,
    )

    assert result is marker
    assert dispatched[0]["policy"] is policy
    assert dispatched[0]["binding"].tickers == ("000001", "000004")


def test_configured_history_refresh_resolves_source_then_dispatches(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source = RecordingAStockSource()
    component = DataSourceComponent(
        id="configured_source",
        capabilities=frozenset(
            {
                MarketDataCapability.CLOSE,
                MarketDataCapability.VOLUME,
            }
        ),
        plugin=source,
    )
    config = AStockHistoryRefreshConfig(
        source=PluginSpec("external_cn_source:create_source"),
        binding=DataBinding(
            connection_ref=None,
            dataset="provider_request",
            start="2024-01-02",
            end="2024-01-31",
            adjustment="hfq",
        ),
        reference_binding=VersionedDatasetBinding(
            connection_ref="cn_reference",
            dataset="cn_reference",
            market="CN",
            version="reference_v1",
        ),
        output_connection_ref="cn_market_data",
        publication=MarketDataPublishSpec(
            dataset_id="cn_a_share_daily_bars",
            market="CN",
            version="bars_v1",
            source="external_provider",
            frequency="daily",
            adjustment="hfq",
        ),
    )
    context = SourceContext(
        connections=ConnectionRegistry({}),
        run_id=203,
        artifact_dir=tmp_path / "artifacts",
    )
    marker = SimpleNamespace(name="publication")
    resolved: list[tuple[PluginSpec, tuple[str, ...]]] = []
    dispatched: list[dict[str, object]] = []

    def fake_resolve(spec, *, allowed_module_prefixes):
        resolved.append((spec, tuple(allowed_module_prefixes)))
        return component

    def fake_refresh(context_arg, **kwargs):
        dispatched.append({"context": context_arg, **kwargs})
        return marker

    monkeypatch.setattr(refresh_module, "resolve_plugin", fake_resolve)
    monkeypatch.setattr(
        refresh_module,
        "refresh_a_share_historical_market_data",
        fake_refresh,
    )

    result = run_configured_a_share_history_refresh(
        context,
        config=config,
        allowed_module_prefixes=("quantmine", "external_cn_source"),
    )

    assert result is marker
    assert resolved == [
        (
            config.source,
            ("quantmine", "external_cn_source"),
        )
    ]
    assert dispatched == [
        {
            "context": context,
            "source_component": component,
            "binding": config.binding,
            "reference_binding": config.reference_binding,
            "output_connection_ref": config.output_connection_ref,
            "publish_spec": config.publication,
            "policy": config.policy,
        }
    ]


def test_configured_history_refresh_rejects_wrong_source_factory_type(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config = AStockHistoryRefreshConfig.from_mapping(
        {
            "schema_version": 1,
            "source": {
                "entry_point": "bad_plugin:create_source",
                "params": {},
            },
            "binding": {
                "connection_ref": None,
                "dataset": "provider_request",
                "start": "2024-01-02",
                "end": "2024-01-31",
                "adjustment": "hfq",
                "metadata": {},
            },
            "reference_binding": {
                "connection_ref": "cn_reference",
                "dataset": "cn_reference",
                "market": "CN",
                "version": "reference_v1",
            },
            "output_connection_ref": "cn_market_data",
            "publication": {
                "dataset_id": "cn_a_share_daily_bars",
                "market": "CN",
                "version": "bars_v1",
                "source": "bad_provider",
                "frequency": "daily",
                "adjustment": "hfq",
                "schema_version": "market_data_bundle_v1",
            },
        }
    )
    context = SourceContext(
        connections=ConnectionRegistry({}),
        run_id=204,
        artifact_dir=tmp_path / "artifacts",
    )
    monkeypatch.setattr(
        refresh_module,
        "resolve_plugin",
        lambda *args, **kwargs: object(),
    )

    with pytest.raises(
        TypeError,
        match="must return DataSourceComponent",
    ):
        run_configured_a_share_history_refresh(
            context,
            config=config,
            allowed_module_prefixes=("bad_plugin",),
        )
