"""Tests for safe, reproducible research-run configuration snapshots."""

from __future__ import annotations

from dataclasses import replace
import json

import pytest
from sqlalchemy import Column, Integer, JSON, MetaData, String, Table, create_engine

from quantmine.plugins.contracts import DataBinding, VersionedDatasetBinding
from quantmine.research_config import (
    ResearchRunConfig,
    resolve_research_run_config_for_as_of_date,
)
from quantmine.storage.runs import (
    ResearchRunStore,
    SQLAlchemyResearchRunStore,
    create_research_run,
    get_or_create_research_run_for_batch,
    load_research_run_config,
)


def _binding() -> DataBinding:
    return DataBinding(
        connection_ref="cn_equity_lake",
        dataset="daily_prices",
        version="20260909",
        universe_dataset="index_membership",
        eligibility_binding=VersionedDatasetBinding(
            connection_ref="cn_eligibility_lake",
            dataset="cn_daily_eligibility",
            market="CN",
            version="history_v1",
        ),
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

    assert snapshot["schema_version"] == 3
    assert snapshot["data_binding"]["connection_ref"] == "cn_equity_lake"
    assert snapshot["data_binding"]["version"] == "20260909"
    assert snapshot["data_binding"]["tickers"] == ["000001", "000002"]
    assert snapshot["data_binding"]["eligibility_binding"] == {
        "connection_ref": "cn_eligibility_lake",
        "dataset": "cn_daily_eligibility",
        "market": "CN",
        "version": "history_v1",
    }
    assert snapshot["bundle"]["data_source"]["entry_point"] == (
        "quantmine.plugins.us_equity:create_yfinance_data_source"
    )
    assert "postgresql://" not in serialized
    assert restored == config


def test_research_run_config_allows_an_api_source_without_connection_ref() -> None:
    config = ResearchRunConfig.from_bundle_id(
        "us_equity_v1",
        DataBinding(
            connection_ref=None,
            dataset="yahoo_daily_prices",
            start="2024-01-01",
            end="2024-02-01",
            tickers=("AAA", "SPY"),
        ),
    )

    restored = ResearchRunConfig.from_snapshot(config.to_snapshot())

    assert restored.data_binding.connection_ref is None


def test_research_run_config_reads_a_v1_snapshot_without_eligibility_binding() -> None:
    config = ResearchRunConfig.from_bundle_id("us_equity_v1", _binding())
    legacy_snapshot = config.to_snapshot()
    legacy_snapshot["schema_version"] = 1
    legacy_snapshot["data_binding"].pop("eligibility_binding")
    legacy_snapshot["data_binding"].pop("version")

    restored = ResearchRunConfig.from_snapshot(legacy_snapshot)

    assert restored.data_binding.eligibility_binding is None
    assert restored.data_binding.version is None


def test_research_run_config_reads_a_v2_snapshot_without_market_data_version() -> None:
    config = ResearchRunConfig.from_bundle_id("us_equity_v1", _binding())
    legacy_snapshot = config.to_snapshot()
    legacy_snapshot["schema_version"] = 2
    legacy_snapshot["data_binding"].pop("version")

    restored = ResearchRunConfig.from_snapshot(legacy_snapshot)

    assert restored.data_binding.version is None


def test_research_run_config_resolves_as_of_date_dataset_versions() -> None:
    config = ResearchRunConfig.from_bundle_id(
        "cn_a_share_v1",
        replace(
            _binding(),
            version="{as_of_date}",
            eligibility_binding=VersionedDatasetBinding(
                connection_ref="cn_eligibility_lake",
                dataset="cn_daily_eligibility",
                market="CN",
                version="{as_of_date}",
            ),
        ),
    )

    resolved = resolve_research_run_config_for_as_of_date(
        config,
        as_of_date="2026-09-14 18:00:00+08:00",
    )

    assert config.data_binding.version == "{as_of_date}"
    assert config.data_binding.eligibility_binding.version == "{as_of_date}"
    assert resolved.data_binding.version == "20260914"
    assert resolved.data_binding.eligibility_binding.version == "20260914"


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


def _research_run_engine():
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
    return engine


def test_get_or_create_research_run_for_batch_reuses_one_matching_run() -> None:
    engine = _research_run_engine()
    config = ResearchRunConfig.from_bundle_id("us_equity_v1", _binding())

    first = get_or_create_research_run_for_batch(
        engine,
        config,
        batch_id="scheduled__2026-09-14",
        git_commit="test-commit",
    )
    second = get_or_create_research_run_for_batch(
        engine,
        config,
        batch_id="scheduled__2026-09-14",
        git_commit="test-commit",
    )

    assert first == second == 1
    metadata = MetaData()
    table = Table("research_runs", metadata, autoload_with=engine)
    with engine.connect() as connection:
        snapshots = connection.execute(
            table.select()
        ).mappings().all()
    assert len(snapshots) == 1
    assert snapshots[0]["config_snapshot"]["airflow_batch"] == (
        "scheduled__2026-09-14"
    )


def test_get_or_create_research_run_for_batch_rejects_changed_config() -> None:
    engine = _research_run_engine()
    original = ResearchRunConfig.from_bundle_id(
        "us_equity_v1",
        _binding(),
        factor_parameters={"day": 5},
    )
    changed = ResearchRunConfig.from_bundle_id(
        "us_equity_v1",
        _binding(),
        factor_parameters={"day": 10},
    )
    get_or_create_research_run_for_batch(
        engine,
        original,
        batch_id="manual__same-batch",
        git_commit="test-commit",
    )

    with pytest.raises(ValueError, match="different research configuration"):
        get_or_create_research_run_for_batch(
            engine,
            changed,
            batch_id="manual__same-batch",
            git_commit="test-commit",
        )
