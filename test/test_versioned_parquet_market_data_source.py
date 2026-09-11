"""Tests for loading immutable market-data publications into research."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from quantmine.plugins.context import SourceContext
from quantmine.plugins.contracts import (
    DataBinding,
    MarketDataCapability,
)
from quantmine.plugins.runtime import load_data_source_component
from quantmine.plugins.sources import (
    create_versioned_parquet_market_data_source,
)
from quantmine.storage.connections import (
    ConnectionKind,
    ConnectionRegistry,
    DataConnectionConfig,
)


def _context(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> SourceContext:
    monkeypatch.setenv("QUANTMINE_TEST_MARKET_ROOT", str(tmp_path))
    return SourceContext(
        connections=ConnectionRegistry(
            {
                "market_lake": DataConnectionConfig(
                    kind=ConnectionKind.PARQUET,
                    root_env="QUANTMINE_TEST_MARKET_ROOT",
                )
            }
        ),
        run_id=17,
        artifact_dir=tmp_path / "artifacts",
    )


def _write_version(tmp_path: Path) -> None:
    version_root = (
        tmp_path
        / "cn_a_share_daily_bars"
        / "versions"
        / "20260909"
    )
    version_root.mkdir(parents=True)
    dates = pd.to_datetime(["2024-01-02", "2024-01-03"])
    pd.DataFrame(
        {
            "000001": [10.0, 11.0],
            "600000": [20.0, 21.0],
        },
        index=dates,
    ).to_parquet(version_root / "close.parquet")
    pd.DataFrame(
        {
            "000001": [1_000, 1_100],
            "600000": [2_000, 2_100],
        },
        index=dates,
    ).to_parquet(version_root / "volume.parquet")


def test_versioned_parquet_component_loads_requested_slice(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _write_version(tmp_path)
    component = create_versioned_parquet_market_data_source()

    bundle = load_data_source_component(
        component,
        DataBinding(
            connection_ref="market_lake",
            dataset="cn_a_share_daily_bars",
            version="20260909",
            start="2024-01-03",
            end="2024-01-03",
            tickers=("600000",),
        ),
        _context(monkeypatch, tmp_path),
    )

    assert bundle.market.close.to_dict() == {"600000": {pd.Timestamp("2024-01-03"): 21.0}}
    assert bundle.market.volume.to_dict() == {"600000": {pd.Timestamp("2024-01-03"): 2_100}}
    assert bundle.calendar.equals(pd.DatetimeIndex(["2024-01-03"]))
    assert bundle.metadata["version"] == "20260909"
    assert component.capabilities == frozenset(
        {
            MarketDataCapability.CLOSE,
            MarketDataCapability.VOLUME,
        }
    )
    assert component.requires_connection is True


def test_versioned_parquet_component_requires_a_version(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    component = create_versioned_parquet_market_data_source()

    with pytest.raises(ValueError, match="DataBinding.version"):
        load_data_source_component(
            component,
            DataBinding(
                connection_ref="market_lake",
                dataset="cn_a_share_daily_bars",
            ),
            _context(monkeypatch, tmp_path),
        )


@pytest.mark.parametrize("version", ["../secret", "versions/other", ".", ".."])
def test_versioned_parquet_component_rejects_unsafe_versions(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    version: str,
) -> None:
    component = create_versioned_parquet_market_data_source()

    with pytest.raises(ValueError, match="safe path segment"):
        load_data_source_component(
            component,
            DataBinding(
                connection_ref="market_lake",
                dataset="cn_a_share_daily_bars",
                version=version,
            ),
            _context(monkeypatch, tmp_path),
        )
