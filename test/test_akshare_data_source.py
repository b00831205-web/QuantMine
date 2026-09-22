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
from quantmine.resilience import RetryPolicy
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


def test_akshare_plugin_throttles_between_ticker_requests(
    tmp_path: Path,
) -> None:
    sleeps: list[float] = []

    def history_loader(**kwargs: str) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "日期": ["2024-01-02"],
                "收盘": [10.0],
                "成交量": [100.0],
            }
        )

    plugin = AkShareAStockDataSourcePlugin(
        history_loader=history_loader,
        request_interval_seconds=0.5,
        sleeper=sleeps.append,
    )

    plugin.load(_binding(), _context(tmp_path))

    assert sleeps == [0.5]


def test_akshare_plugin_retries_only_the_failed_ticker_request(
    tmp_path: Path,
) -> None:
    attempts: list[str] = []
    sleeps: list[float] = []

    def history_loader(**kwargs: str) -> pd.DataFrame:
        attempts.append(kwargs["symbol"])
        if len(attempts) == 1:
            raise requests.exceptions.ConnectionError(
                "temporary provider disconnect"
            )
        return pd.DataFrame(
            {
                "日期": ["2024-01-02"],
                "收盘": [10.0],
                "成交量": [100.0],
            }
        )

    plugin = AkShareAStockDataSourcePlugin(
        history_loader=history_loader,
        sleeper=sleeps.append,
    )

    result = plugin.load(
        _binding(tickers=("000001",)),
        _context(tmp_path),
    )

    assert attempts == ["000001", "000001"]
    assert sleeps == [1.0]
    assert result.market.close.loc[
        pd.Timestamp("2024-01-02"), "000001"
    ] == 10.0


def test_akshare_plugin_uses_configured_http_retry_policy(
    tmp_path: Path,
) -> None:
    attempts: list[str] = []
    sleeps: list[float] = []

    def history_loader(**kwargs: str) -> pd.DataFrame:
        attempts.append(kwargs["symbol"])
        if len(attempts) < 3:
            raise requests.exceptions.ConnectionError(
                "temporary provider disconnect"
            )
        return pd.DataFrame(
            {
                "日期": ["2024-01-02"],
                "收盘": [10.0],
                "成交量": [100.0],
            }
        )

    plugin = AkShareAStockDataSourcePlugin(
        history_loader=history_loader,
        retry_policy=RetryPolicy(
            attempts=4,
            initial_delay_seconds=10.0,
            backoff_multiplier=3.0,
            max_delay_seconds=60.0,
        ),
        sleeper=sleeps.append,
    )

    plugin.load(
        _binding(tickers=("000001",)),
        _context(tmp_path),
    )

    assert attempts == ["000001", "000001", "000001"]
    assert sleeps == [10.0, 30.0]


def test_akshare_plugin_records_an_exhausted_transient_ticker_and_continues(
    tmp_path: Path,
) -> None:
    attempts: list[str] = []

    def history_loader(**kwargs: str) -> pd.DataFrame:
        ticker = kwargs["symbol"]
        attempts.append(ticker)
        if ticker == "000001":
            raise requests.exceptions.ConnectionError("provider disconnected")
        return pd.DataFrame(
            {
                "日期": ["2024-01-02"],
                "收盘": [10.0],
                "成交量": [100.0],
            }
        )

    result = AkShareAStockDataSourcePlugin(
        history_loader=history_loader,
        continue_on_transient_failure=True,
        retry_policy=RetryPolicy(attempts=2),
        sleeper=lambda _: None,
    ).load(_binding(), _context(tmp_path))

    assert attempts == ["600000", "000001", "000001"]
    assert list(result.market.close.columns) == ["600000"]
    assert result.metadata["failed_tickers"] == ("000001",)


def test_akshare_factory_converts_retry_policy_mapping() -> None:
    component = create_akshare_a_stock_data_source(
        retry_policy={
            "attempts": 5,
            "initial_delay_seconds": 15.0,
            "backoff_multiplier": 2.0,
            "max_delay_seconds": 120.0,
        }
    )

    assert component.plugin.retry_policy == RetryPolicy(
        attempts=5,
        initial_delay_seconds=15.0,
        backoff_multiplier=2.0,
        max_delay_seconds=120.0,
    )


@pytest.mark.parametrize("value", [-0.1, True, "0.5"])
def test_akshare_plugin_rejects_invalid_request_interval(value: object) -> None:
    with pytest.raises((TypeError, ValueError), match="request_interval_seconds"):
        AkShareAStockDataSourcePlugin(
            request_interval_seconds=value,
        )
