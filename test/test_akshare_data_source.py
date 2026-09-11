"""Deterministic contract tests for the AkShare A-share source plugin."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
import requests

from quantmine.plugins.akshare import (
    AkShareAStockDataSourcePlugin,
    create_akshare_a_stock_data_source,
)
from quantmine.plugins.context import SourceContext
from quantmine.plugins.contracts import (
    DataBinding,
    MarketDataCapability,
)
from quantmine.storage.connections import ConnectionRegistry


def _context(tmp_path: Path) -> SourceContext:
    return SourceContext(
        connections=ConnectionRegistry({}),
        run_id=801,
        artifact_dir=tmp_path / "artifacts",
    )


def _binding(**overrides: object) -> DataBinding:
    values: dict[str, object] = {
        "connection_ref": None,
        "dataset": "akshare_a_daily",
        "start": "2024-01-02",
        "end": "2024-01-05",
        "tickers": ("600000", "000001"),
        "adjustment": "hfq",
    }
    values.update(overrides)
    return DataBinding(**values)


def test_akshare_plugin_converts_one_history_frame_per_ticker_to_wide_market_data(
    tmp_path: Path,
) -> None:
    calls: list[dict[str, str]] = []

    def history_loader(**kwargs: str) -> pd.DataFrame:
        calls.append(kwargs)
        if kwargs["symbol"] == "000001":
            return pd.DataFrame(
                {
                    "日期": ["2024-01-02", "2024-01-04"],
                    "收盘": [10.0, 12.0],
                    "成交量": [100.0, 120.0],
                }
            )
        return pd.DataFrame(
            {
                "日期": ["2024-01-03", "2024-01-04"],
                "收盘": [20.0, 21.0],
                "成交量": [200.0, 210.0],
            }
        )

    result = AkShareAStockDataSourcePlugin(
        history_loader=history_loader,
    ).load(_binding(), _context(tmp_path))

    assert calls == [
        {
            "symbol": "600000",
            "period": "daily",
            "start_date": "20240102",
            "end_date": "20240105",
            "adjust": "hfq",
        },
        {
            "symbol": "000001",
            "period": "daily",
            "start_date": "20240102",
            "end_date": "20240105",
            "adjust": "hfq",
        },
    ]
    assert list(result.market.close.index) == list(
        pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04"])
    )
    assert list(result.market.close.columns) == ["000001", "600000"]
    assert result.market.close.loc[pd.Timestamp("2024-01-04"), "000001"] == 12.0
    assert result.market.volume.loc[pd.Timestamp("2024-01-03"), "600000"] == 200.0
    assert result.metadata["source_kind"] == "akshare_stock_zh_a_hist"
    assert result.metadata["adjustment"] == "hfq"
    assert result.metadata["volume_unit"] == "lot"


def test_akshare_plugin_rejects_an_incomplete_provider_frame(tmp_path: Path) -> None:
    plugin = AkShareAStockDataSourcePlugin(
        history_loader=lambda **_: pd.DataFrame(
            {"日期": ["2024-01-02"], "收盘": [10.0]}
        ),
    )

    with pytest.raises(ValueError, match="missing required columns: 成交量"):
        plugin.load(_binding(tickers=("000001",)), _context(tmp_path))


def test_akshare_component_declares_api_capabilities_without_a_connection() -> None:
    component = create_akshare_a_stock_data_source()

    assert component.connection_ref is None
    assert not component.requires_connection
    assert component.capabilities == frozenset(
        {MarketDataCapability.CLOSE, MarketDataCapability.VOLUME}
    )
    assert component.retry_classifier is not None
    assert component.retry_classifier(
        requests.exceptions.ConnectionError("temporary disconnect")
    )
    assert not component.retry_classifier(
        ValueError("invalid provider schema")
    )
