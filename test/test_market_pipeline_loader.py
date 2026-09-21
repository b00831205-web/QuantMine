"""YAML loading for persistent market-pipeline definitions."""

from pathlib import Path

import pytest
import yaml

from quantmine.market_pipeline_loader import (
    load_market_pipeline_definitions,
)
from quantmine.market_pipeline_config import PipelineStageKind
from quantmine.plugins.contracts import PluginSpec
from quantmine.research_config import ResearchRunConfig


def _write(tmp_path: Path, content: str) -> Path:
    path = tmp_path / "pipelines.yaml"
    path.write_text(content, encoding="utf-8")
    return path


def test_loads_multiple_market_pipeline_definitions(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        """
market_pipelines:
  - schema_version: 1
    id: cn_daily
    dag_id: quantmine_cn_daily
    display_name: China A-share daily
    schedule: "0 18 * * 1-5"
    connection_refs: [cn_raw]
    stages:
      - id: session_gate
        kind: session_gate
        plugin:
          entry_point: local_plugins:create_cn_gate
      - id: production
        upstream: [session_gate]
        plugin:
          entry_point: local_plugins:create_cn_production
          params:
            market: CN
  - schema_version: 1
    id: us_daily
    dag_id: quantmine_us_daily
    display_name: US equity daily
    schedule: "0 18 * * 1-5"
    stages:
      - id: session_gate
        kind: session_gate
        plugin:
          entry_point: local_plugins:create_us_gate
""",
    )

    definitions = load_market_pipeline_definitions(path)

    assert [definition.id for definition in definitions] == [
        "cn_daily",
        "us_daily",
    ]
    assert definitions[0].connection_refs == ("cn_raw",)
    assert definitions[0].ordered_stage_ids == (
        "session_gate",
        "production",
    )
    assert definitions[0].stages[1].plugin.params == {"market": "CN"}


def test_missing_market_pipelines_section_returns_empty_tuple(
    tmp_path: Path,
) -> None:
    path = _write(tmp_path, "momentum:\n  day: 20\n")

    assert load_market_pipeline_definitions(path) == ()


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ("market_pipelines: {}\n", "must be a YAML list"),
        (
            """
market_pipelines:
  - schema_version: 1
    id: duplicate
    dag_id: first_dag
    display_name: First
    schedule: "@daily"
    stages:
      - id: run
        plugin: {entry_point: local_plugins:create_run}
  - schema_version: 1
    id: duplicate
    dag_id: second_dag
    display_name: Second
    schedule: "@daily"
    stages:
      - id: run
        plugin: {entry_point: local_plugins:create_run}
""",
            "duplicate market pipeline id",
        ),
        (
            """
market_pipelines:
  - schema_version: 1
    id: first
    dag_id: duplicate_dag
    display_name: First
    schedule: "@daily"
    stages:
      - id: run
        plugin: {entry_point: local_plugins:create_run}
  - schema_version: 1
    id: second
    dag_id: duplicate_dag
    display_name: Second
    schedule: "@daily"
    stages:
      - id: run
        plugin: {entry_point: local_plugins:create_run}
""",
            "duplicate Airflow dag_id",
        ),
    ],
)
def test_rejects_invalid_pipeline_collections(
    tmp_path: Path,
    content: str,
    message: str,
) -> None:
    with pytest.raises((TypeError, ValueError), match=message):
        load_market_pipeline_definitions(_write(tmp_path, content))


def test_example_config_defines_the_a_share_daily_pipeline() -> None:
    example_path = Path(__file__).parents[1] / "config.example.yaml"

    definitions = load_market_pipeline_definitions(example_path)
    definitions_by_id = {
        definition.id: definition for definition in definitions
    }

    definition = definitions_by_id["cn_a_share_daily"]
    assert definition.dag_id == "quantmine_cn_a_share_daily"
    assert definition.ordered_stage_ids == (
        "session_gate",
        "reference_refresh",
        "daily_production",
        "market_data_refresh",
        "coverage_audit",
        "history_backfill",
        "repair_publication",
        "research_readiness_gate",
        "factor_research",
        "ic_research",
        "backtest",
    )
    assert definition.connection_refs == (
        "cn_raw",
        "cn_reference",
        "cn_status",
        "cn_eligibility",
        "cn_market_data",
        "cn_market_checkpoint",
        "research_db",
    )
    assert definition.stages[0].plugin.entry_point == (
        "quantmine.plugins.market_stages:create_exchange_calendar_session_gate"
    )
    assert definition.stages[0].plugin.params == {"calendar_name": "XSHG"}
    assert definition.stages[1].plugin.entry_point == (
        "quantmine.plugins.market_stages:create_a_share_reference_refresh"
    )
    assert definition.stages[2].plugin.entry_point == (
        "quantmine.plugins.market_stages:create_a_share_daily_production"
    )
    assert definition.stages[3].plugin.entry_point == (
        "quantmine.plugins.market_stages:"
        "create_a_share_cumulative_market_data_refresh"
    )
    assert definition.stages[3].upstream == ("daily_production",)
    assert definition.stages[4].plugin.entry_point == (
        "quantmine.plugins.market_stages:"
        "create_a_share_market_data_coverage_audit"
    )
    assert definition.stages[4].upstream == ("market_data_refresh",)
    assert definition.stages[5].plugin.entry_point == (
        "quantmine.plugins.market_stages:create_a_share_history_backfill"
    )
    assert definition.stages[5].upstream == ("coverage_audit",)
    assert definition.stages[6].plugin.entry_point == (
        "quantmine.plugins.market_stages:create_a_share_repair_publication"
    )
    assert definition.stages[6].upstream == ("history_backfill",)
    assert definition.stages[7].plugin.entry_point == (
        "quantmine.plugins.market_stages:create_research_readiness_gate"
    )
    assert definition.stages[7].kind is PipelineStageKind.SESSION_GATE
    assert definition.stages[7].upstream == ("repair_publication",)
    assert definition.stages[7].plugin.params == {
        "market_data_connection_ref": "cn_market_data",
        "dataset_id": "cn_a_share_daily_bars",
        "market": "CN",
        "plan_connection_ref": "cn_market_checkpoint",
    }
    assert definition.stages[8].plugin.entry_point == (
        "quantmine.plugins.research_stages:"
        "create_persisted_factor_research_stage"
    )
    assert definition.stages[8].upstream == ("research_readiness_gate",)
    assert definition.stages[9].plugin.entry_point == (
        "quantmine.plugins.ic_stages:create_persisted_ic_research_stage"
    )
    assert definition.stages[9].upstream == ("factor_research",)
    assert definition.stages[10].plugin.entry_point == (
        "quantmine.plugins.backtest_stage:create_persisted_backtest_stage"
    )
    assert definition.stages[10].upstream == ("ic_research",)
    assert definition.stages[8].plugin.params[
        "research_run_connection_ref"
    ] == "research_db"
    assert definition.stages[9].plugin.params == {
        "research_run_connection_ref": "research_db"
    }
    assert definition.stages[10].plugin.params == {
        "research_run_connection_ref": "research_db"
    }

    research_config = definition.stages[8].plugin.params["config"]
    assert research_config["schema_version"] == 6
    assert research_config["bundle"]["id"] == "cn_a_share_v1"
    assert research_config["data_binding"]["connection_ref"] == (
        "cn_market_data"
    )
    assert research_config["data_binding"]["version"] == "{as_of_date}"
    assert research_config["data_binding"]["eligibility_binding"] == {
        "connection_ref": "cn_eligibility",
        "dataset": "cn_a_share_eligibility",
        "market": "CN",
        "version": "{as_of_date}",
    }
    assert research_config["ic_engine"]["entry_point"] == (
        "quantmine.plugins.ic_engines:"
        "create_python_ic_calculation_engine"
    )
    assert research_config["validation_engine"]["entry_point"] == (
        "quantmine.plugins.ic_validators:"
        "create_python_ic_validation_engine"
    )
    assert research_config["backtest_engine"]["entry_point"] == (
        "quantmine.plugins.backtest_engines:"
        "create_python_position_backtest_engine"
    )
    assert research_config["market_rules"] == {
        "entry_point": (
            "quantmine.plugins.market_rules:"
            "create_a_stock_market_rules"
        ),
        "params": {
            "market": "CN",
            "lot_size": 100,
            "commission_rate": 0.0003,
            "minimum_commission": 5.0,
            "stamp_duty_rate": 0.0005,
            "transfer_fee_rate": 0.00001,
        },
    }
    assert [
        job["id"] for job in research_config["backtest"]["jobs"]
    ] == [
        "raw_quintile",
        "orthogonalized_quintile",
    ]
    raw_example = yaml.safe_load(
        example_path.read_text(encoding="utf-8")
    )
    assert raw_example["backtest"]["jobs"][-1]["id"] == "mcap_quintile"
    assert research_config["backtest"]["initial_cash"] == 1000000.0
    assert research_config["backtest"]["gross_exposure"] == 1.0
    assert all(
        job["position_group"] == "Q5"
        for job in research_config["backtest"]["jobs"]
    )
    assert research_config["ic_research"]["periods"] == [1, 5, 20]

    restored_research_config = ResearchRunConfig.from_snapshot(
        research_config
    )
    assert restored_research_config.bundle.id == "cn_a_share_v1"
    assert restored_research_config.data_binding.version == "{as_of_date}"
    assert restored_research_config.validation_engine == PluginSpec(
        "quantmine.plugins.ic_validators:"
        "create_python_ic_validation_engine"
    )
    assert restored_research_config.backtest_engine == PluginSpec(
        "quantmine.plugins.backtest_engines:"
        "create_python_position_backtest_engine"
    )
    assert restored_research_config.market_rules == PluginSpec(
        "quantmine.plugins.market_rules:create_a_stock_market_rules",
        params={
            "market": "CN",
            "lot_size": 100,
            "commission_rate": 0.0003,
            "minimum_commission": 5.0,
            "stamp_duty_rate": 0.0005,
            "transfer_fee_rate": 0.00001,
        },
    )
    assert restored_research_config.backtest == research_config["backtest"]
    assert restored_research_config.ic_research["periods"] == [1, 5, 20]
    assert definition.stages[1].plugin.params["config"] == (
        definition.stages[2].plugin.params["config"]
    )
    market_data_config = definition.stages[3].plugin.params["config"]
    assert market_data_config["source"]["params"] == {
        "default_adjustment": "hfq",
        "request_interval_seconds": 0.5,
    }
    assert market_data_config["binding"]["start"] == "{as_of_date}"
    assert market_data_config["binding"]["end"] == "{as_of_date}"
    assert market_data_config["reference_binding"]["version"] == (
        "{as_of_date}"
    )
    assert market_data_config["publication"]["version"] == "{as_of_date}"
