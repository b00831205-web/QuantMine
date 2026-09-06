"""Tests for loading the A-share eligibility universe from a named Parquet lake."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from quantmine.plugins.a_share import (
    ParquetAStockEligibilityUniversePlugin,
    create_cn_a_share_eligibility_universe,
)
from quantmine.plugins.context import SourceContext
from quantmine.plugins.contracts import DataBinding, VersionedDatasetBinding
from quantmine.storage.connections import (
    ConnectionKind,
    ConnectionRegistry,
    DataConnectionConfig,
)
from quantmine.workflows.eligibility import (
    EligibilityDataTier,
    EligibilityPublishSpec,
    publish_daily_eligibility,
)


def _eligibility_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": ["2024-01-02", "2024-01-02"],
            "ticker": ["000001", "000002"],
            "is_listed": [True, True],
            "is_st": [False, True],
            "is_suspended": [False, False],
            "listing_days": [100, 100],
            "is_limit_up": [False, False],
            "is_limit_down": [False, False],
        }
    )


def _context(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> SourceContext:
    lake_root = tmp_path / "lake"
    lake_root.mkdir()
    monkeypatch.setenv("QUANTMINE_CN_UNIVERSE_ROOT", str(lake_root))
    registry = ConnectionRegistry(
        {
            "cn_universe_lake": DataConnectionConfig(
                kind=ConnectionKind.PARQUET,
                root_env="QUANTMINE_CN_UNIVERSE_ROOT",
            )
        }
    )
    return SourceContext(
        connections=registry,
        run_id=1101,
        artifact_dir=tmp_path / "artifacts",
    )


def test_parquet_eligibility_plugin_loads_the_named_universe_dataset(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    context = _context(monkeypatch, tmp_path)
    dataset_root = context.connections.parquet_root("cn_universe_lake") / "cn_daily_eligibility"
    dataset_root.mkdir()
    _eligibility_frame().to_parquet(dataset_root / "eligibility.parquet")

    universe = ParquetAStockEligibilityUniversePlugin().load(
        DataBinding(
            connection_ref="cn_universe_lake",
            dataset="akshare_daily",
            universe_dataset="cn_daily_eligibility",
        ),
        context,
    )

    assert universe.get_constituents(pd.Timestamp("2024-01-02")) == {"000001"}


def test_parquet_eligibility_plugin_loads_a_versioned_eligibility_binding(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    context = _context(monkeypatch, tmp_path)
    published = _eligibility_frame().assign(is_tradable=[True, False])
    publish_daily_eligibility(
        published,
        root=context.connections.parquet_root("cn_universe_lake"),
        spec=EligibilityPublishSpec(
            dataset_id="cn_daily_eligibility",
            version="history_v1",
            market="CN",
            data_tier=EligibilityDataTier.RECONSTRUCTED,
            source="fixture",
            rule_version="cn_eligibility_rules_v1",
        ),
    )

    universe = ParquetAStockEligibilityUniversePlugin().load(
        DataBinding(
            connection_ref=None,
            dataset="daily_prices",
            eligibility_binding=VersionedDatasetBinding(
                connection_ref="cn_universe_lake",
                dataset="cn_daily_eligibility",
                market="CN",
                version="history_v1",
            ),
        ),
        context,
    )

    assert universe.get_constituents(pd.Timestamp("2024-01-02")) == {"000001"}


def test_parquet_eligibility_plugin_rejects_missing_dataset_or_path_escape(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    context = _context(monkeypatch, tmp_path)
    plugin = ParquetAStockEligibilityUniversePlugin()

    with pytest.raises(ValueError, match="DataBinding.universe_dataset"):
        plugin.load(
            DataBinding(connection_ref="cn_universe_lake", dataset="prices"),
            context,
        )

    with pytest.raises(ValueError, match="escapes the configured lake root"):
        plugin.load(
            DataBinding(
                connection_ref="cn_universe_lake",
                dataset="prices",
                universe_dataset="../escape",
            ),
            context,
        )


def test_cn_eligibility_component_declares_its_connection_requirement() -> None:
    component = create_cn_a_share_eligibility_universe()

    assert component.requires_connection
    assert component.plugin is not None
