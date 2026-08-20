"""Tests for safe, reproducible research-run configuration snapshots."""

from __future__ import annotations

import json

import pytest
from sqlalchemy import Column, Integer, JSON, MetaData, String, Table, create_engine

from quantmine.plugins.contracts import DataBinding
from quantmine.research_config import ResearchRunConfig
from quantmine.storage.runs import (
    ResearchRunStore,
    SQLAlchemyResearchRunStore,
    create_research_run,
    load_research_run_config,
)


def _binding() -> DataBinding:
    return DataBinding(
        connection_ref="cn_equity_lake",
        dataset="daily_prices",
        universe_dataset="index_membership",
        benchmark_ticker="000300",
        adjustment="qfq",
        start="2020-01-01",
        end="2024-12-31",
        tickers=("000001", "000002"),
        metadata={"market": "CN"},
    )


def test_research_run_config_round_trips_as_a_safe_json_snapshot() -> None:
    config = ResearchRunConfig.from_bundle_id(
        "us_equity_v1",
        _binding(),
        factor_parameters={"day": 10, "halflife": 5, "period": 20},
    )

    snapshot = config.to_snapshot()
    serialized = json.dumps(snapshot, sort_keys=True, allow_nan=False)
    restored = ResearchRunConfig.from_snapshot(json.loads(serialized))

    assert snapshot["schema_version"] == 1
    assert snapshot["data_binding"]["connection_ref"] == "cn_equity_lake"
    assert snapshot["data_binding"]["tickers"] == ["000001", "000002"]
    assert snapshot["bundle"]["data_source"]["entry_point"] == (
        "quantmine.plugins.builtins:create_yfinance_data_source"
    )
    assert "postgresql://" not in serialized
    assert restored == config


def test_research_run_config_rejects_non_json_factor_parameters() -> None:
    config = ResearchRunConfig.from_bundle_id(
        "us_equity_v1",
        _binding(),
        factor_parameters={"invalid": {"not", "json"}},
    )

    with pytest.raises(TypeError, match="JSON-serializable"):
        config.to_snapshot()


def test_research_run_config_persists_and_restores_from_research_runs() -> None:
    engine = create_engine("sqlite://")
    metadata = MetaData()
    Table(
        "research_runs",
        metadata,
        Column("run_id", Integer, primary_key=True, autoincrement=True),
        Column("config_snapshot", JSON, nullable=False),
        Column("git_commit", String),
    )
    metadata.create_all(engine)

    config = ResearchRunConfig.from_bundle_id(
        "us_equity_v1",
        _binding(),
        factor_parameters={"day": 5},
    )

    run_id = create_research_run(
        engine,
        config,
        git_commit="test-commit",
    )
    restored = load_research_run_config(engine, run_id)

    assert run_id == 1
    assert restored == config


def test_sqlalchemy_store_implements_the_research_run_store_contract() -> None:
    engine = create_engine("sqlite://")
    metadata = MetaData()
    Table(
        "research_runs",
        metadata,
        Column("run_id", Integer, primary_key=True, autoincrement=True),
        Column("config_snapshot", JSON, nullable=False),
        Column("git_commit", String),
    )
    metadata.create_all(engine)

    store = SQLAlchemyResearchRunStore(engine)
    config = ResearchRunConfig.from_bundle_id(
        "us_equity_v1",
        _binding(),
        factor_parameters={"day": 5},
    )

    assert isinstance(store, ResearchRunStore)
    assert store.load(store.create(config, git_commit="test-commit")) == config
