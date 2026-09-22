"""Scheduler-facing entrypoint for the A-share daily production pipeline."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from quantmine.dataset_versions import AS_OF_DATE_VERSION

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TASK_PATH = PROJECT_ROOT / "pipelines" / "task_a_share_daily_pipeline.py"


def _load_task_module():
    spec = importlib.util.spec_from_file_location(
        "task_a_share_daily_pipeline_under_test",
        TASK_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_config(path: Path) -> None:
    path.write_text(
        """
a_share_daily_pipeline:
  schema_version: 1
  raw_connection_ref: cn_raw
  reference_binding:
    connection_ref: cn_reference
    dataset: cn_a_share_reference
    market: CN
    version: "20260830"
  status_binding:
    connection_ref: cn_status
    dataset: cn_daily_market_status
    market: CN
    version: history_v1
  eligibility_binding:
    connection_ref: cn_eligibility
    dataset: cn_a_share_eligibility
    market: CN
    version: history_v1
  eligibility_rule_version: cn_equity_v1
""".strip(),
        encoding="utf-8",
    )


def test_loads_a_share_pipeline_section_and_deduplicates_connection_refs(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "a-share.yaml"
    _write_config(config_path)
    task = _load_task_module()

    config = task.load_a_share_daily_pipeline_config(config_path)

    assert config.raw_connection_ref == "cn_raw"
    assert task.required_connection_refs(config) == (
        "cn_raw",
        "cn_reference",
        "cn_status",
        "cn_eligibility",
    )


def test_main_builds_context_from_environment_and_runs_one_day(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = tmp_path / "a-share.yaml"
    _write_config(config_path)
    task = _load_task_module()
    captured: dict[str, object] = {}
    registry = object()

    def fake_registry_from_environment(refs: tuple[str, ...]) -> object:
        captured["connection_refs"] = refs
        return registry

    def fake_run(context, *, config, as_of_date, collector=None):
        captured["context"] = context
        captured["config"] = config
        captured["as_of_date"] = as_of_date
        captured["collector"] = collector
        return object()

    monkeypatch.setattr(
        task.ConnectionRegistry,
        "from_environment",
        fake_registry_from_environment,
    )
    monkeypatch.setattr(task, "run_a_share_daily_pipeline", fake_run)

    task.main(
        [
            "--date",
            "2024-01-02",
            "--batch",
            "scheduled__2024-01-02",
            "--config",
            str(config_path),
        ]
    )

    context = captured["context"]
    assert captured["connection_refs"] == (
        "cn_raw",
        "cn_reference",
        "cn_status",
        "cn_eligibility",
    )
    assert context.connections is registry
    assert context.run_id == 0
    assert context.artifact_dir == (
        PROJECT_ROOT
        / "data"
        / "artifacts"
        / "a_share_daily"
        / "scheduled__2024-01-02"
    )
    assert captured["as_of_date"] == "2024-01-02"
    assert captured["collector"] is None


def test_config_requires_the_a_share_daily_pipeline_section(tmp_path: Path) -> None:
    config_path = tmp_path / "missing-section.yaml"
    config_path.write_text("ic_research: {}\n", encoding="utf-8")
    task = _load_task_module()

    with pytest.raises(KeyError, match="a_share_daily_pipeline"):
        task.load_a_share_daily_pipeline_config(config_path)


def test_project_environment_loader_fills_only_missing_variables(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        "A_SHARE_TEST_MISSING=from_file\n"
        "A_SHARE_TEST_PRESENT=from_file\n",
        encoding="utf-8",
    )
    task = _load_task_module()
    monkeypatch.delenv("A_SHARE_TEST_MISSING", raising=False)
    monkeypatch.setenv("A_SHARE_TEST_PRESENT", "from_process")

    task.load_project_environment(env_path)

    assert task.os.environ["A_SHARE_TEST_MISSING"] == "from_file"
    assert task.os.environ["A_SHARE_TEST_PRESENT"] == "from_process"


def test_example_config_contains_valid_a_share_daily_pipeline() -> None:
    example_path = PROJECT_ROOT / "config.example.yaml"
    task = _load_task_module()

    config = task.load_a_share_daily_pipeline_config(example_path)

    assert config.raw_connection_ref == "cn_raw"
    assert config.eligibility_binding.dataset == (
        "cn_a_share_eligibility"
    )


@pytest.mark.parametrize("filename", ["config.yaml", "config.example.yaml"])
def test_project_configs_declare_the_a_share_spot_coverage_policy(
    filename: str,
) -> None:
    task = _load_task_module()

    config = task.load_a_share_daily_pipeline_config(PROJECT_ROOT / filename)

    assert config.spot_coverage_policy.max_missing_count == 5
    assert config.spot_coverage_policy.max_missing_ratio == 0.001
    assert config.reference_binding.version == AS_OF_DATE_VERSION
