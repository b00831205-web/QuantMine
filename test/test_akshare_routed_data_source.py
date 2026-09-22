"""Contract tests for the routed AkShare A-share history source."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from quantmine.plugins.akshare_routed import (
    AkShareRoutedAStockDataSourcePlugin,
    create_akshare_routed_a_stock_data_source,
)
from quantmine.plugins.context import SourceContext
from quantmine.plugins.contracts import DataBinding, MarketDataCapability
from quantmine.resilience import RetryPolicy
from quantmine.storage.connections import ConnectionRegistry


def _context(tmp_path: Path) -> SourceContext:
    return SourceContext(
        connections=ConnectionRegistry({}),
        run_id=901,
        artifact_dir=tmp_path / "artifacts",
    )


def test_routed_source_uses_tencent_symbols_for_sh_sz_and_beijing(
    tmp_path: Path,
) -> None:
    tencent_calls: list[dict[str, str]] = []

    def tencent_loader(**kwargs: str) -> pd.DataFrame:
        tencent_calls.append(kwargs)
        return pd.DataFrame(
            {"date": ["2024-01-02"], "close": [10.0], "volume": [123.0]}
        )

    plugin = AkShareRoutedAStockDataSourcePlugin(
        tencent_history_loader=tencent_loader,
        sleeper=lambda _: None,
    )
    binding = DataBinding(
        connection_ref=None,
        dataset="cn_history",
        start="2024-01-02",
        end="2024-01-02",
        tickers=("000001", "600000", "920000"),
        adjustment="hfq",
    )

    result = plugin.load(binding, _context(tmp_path))

    assert [call["symbol"] for call in tencent_calls] == [
        "sz000001",
        "sh600000",
        "bj920000",
    ]
    assert result.market.volume.loc[
        pd.Timestamp("2024-01-02"), "000001"
    ] == 123.0
    assert result.market.volume.loc[
        pd.Timestamp("2024-01-02"), "920000"
    ] == 123.0
    assert result.metadata["volume_unit"] == "share"
    assert result.metadata["providers"] == ["tencent"]


def test_routed_factory_converts_retry_policy_mapping() -> None:
    component = create_akshare_routed_a_stock_data_source(
        retry_policy={
            "attempts": 4,
            "initial_delay_seconds": 10.0,
            "backoff_multiplier": 2.0,
            "max_delay_seconds": 60.0,
        }
    )

    assert component.id == "akshare_routed_a_stock_daily"
    assert component.capabilities == frozenset(
        {MarketDataCapability.CLOSE, MarketDataCapability.VOLUME}
    )
    assert component.plugin.retry_policy == RetryPolicy(
        attempts=4,
        initial_delay_seconds=10.0,
        backoff_multiplier=2.0,
        max_delay_seconds=60.0,
    )


def test_routed_source_falls_back_to_sina_when_tencent_is_empty(
    tmp_path: Path,
) -> None:
    sina_calls: list[dict[str, str]] = []

    def tencent_loader(**kwargs: str) -> pd.DataFrame:
        del kwargs
        return pd.DataFrame(columns=["date", "close", "volume"])

    def sina_loader(**kwargs: str) -> pd.DataFrame:
        sina_calls.append(kwargs)
        return pd.DataFrame(
            {"date": ["2026-08-04"], "close": [88.0], "volume": [456.0]}
        )

    plugin = AkShareRoutedAStockDataSourcePlugin(
        tencent_history_loader=tencent_loader,
        sina_history_loader=sina_loader,
        sleeper=lambda _: None,
    )
    binding = DataBinding(
        connection_ref=None,
        dataset="cn_history",
        start="2026-08-01",
        end="2026-09-15",
        tickers=("001232",),
        adjustment="hfq",
    )

    result = plugin.load(binding, _context(tmp_path))

    assert sina_calls == [
        {
            "symbol": "sz001232",
            "start_date": "20260801",
            "end_date": "20260915",
            "adjust": "hfq",
        }
    ]
    assert result.market.close.loc[
        pd.Timestamp("2026-08-04"), "001232"
    ] == 88.0
    assert result.metadata["providers"] == ["sina"]
    assert result.metadata["empty_response_fallbacks"] == [
        "sina",
        "eastmoney",
    ]


def test_routed_source_uses_eastmoney_when_sina_has_no_decodable_data(
    tmp_path: Path,
) -> None:
    class JSONDecodeError(ValueError):
        pass

    eastmoney_calls: list[dict[str, str]] = []

    def empty_tencent(**kwargs: str) -> pd.DataFrame:
        del kwargs
        return pd.DataFrame(columns=["date", "close", "volume"])

    def unavailable_sina(**kwargs: str) -> pd.DataFrame:
        del kwargs
        raise JSONDecodeError("No value to decode")

    def eastmoney_loader(**kwargs: str) -> pd.DataFrame:
        eastmoney_calls.append(kwargs)
        return pd.DataFrame(
            {"日期": ["2025-01-16"], "收盘": [0.92], "成交量": [456.0]}
        )

    plugin = AkShareRoutedAStockDataSourcePlugin(
        tencent_history_loader=empty_tencent,
        sina_history_loader=unavailable_sina,
        eastmoney_history_loader=eastmoney_loader,
        sleeper=lambda _: None,
    )
    binding = DataBinding(
        connection_ref=None,
        dataset="cn_history",
        start="2005-01-01",
        end="2025-03-05",
        tickers=("600083",),
        adjustment="hfq",
    )

    result = plugin.load(binding, _context(tmp_path))

    assert eastmoney_calls == [
        {
            "symbol": "600083",
            "start_date": "20050101",
            "end_date": "20250305",
            "adjust": "hfq",
        }
    ]
    assert result.market.close.loc[
        pd.Timestamp("2025-01-16"), "600083"
    ] == 0.92
    assert result.market.volume.loc[
        pd.Timestamp("2025-01-16"), "600083"
    ] == 45600.0
    assert result.metadata["providers"] == ["eastmoney"]
