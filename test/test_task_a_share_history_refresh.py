"""Tests for the one-off A-share historical market-data task."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TASK_PATH = PROJECT_ROOT / "pipelines" / "task_a_share_history_refresh.py"


def _load_task_module():
    spec = importlib.util.spec_from_file_location(
        "task_a_share_history_refresh_under_test",
        TASK_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _config(*, checkpoint_connection_ref: str | None = None):
    return SimpleNamespace(
        binding=SimpleNamespace(connection_ref="provider_input"),
        reference_binding=SimpleNamespace(connection_ref="cn_reference"),
        output_connection_ref="cn_market_data",
        policy=SimpleNamespace(
            checkpoint_connection_ref=checkpoint_connection_ref,
        ),
        publication=SimpleNamespace(version="bars_v1"),
    )


class _Connections:
    def __init__(self) -> None:
        self.disposed = False

    def dispose(self) -> None:
        self.disposed = True


def test_required_connection_refs_includes_checkpoint_connection() -> None:
    task = _load_task_module()

    assert task.required_connection_refs(
        _config(checkpoint_connection_ref="cn_market_checkpoint")
    ) == (
        "provider_input",
        "cn_reference",
        "cn_market_data",
        "cn_market_checkpoint",
    )


def test_required_connection_refs_omits_none_and_deduplicates() -> None:
    task = _load_task_module()
    config = _config(checkpoint_connection_ref=None)
    config.output_connection_ref = "cn_reference"

    assert task.required_connection_refs(config) == (
        "provider_input",
        "cn_reference",
    )


def test_main_loads_config_runs_history_refresh_and_disposes_connections(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    task = _load_task_module()
    config = _config()
    connections = _Connections()
    observed: dict[str, object] = {}
    config_path = tmp_path / "config.yaml"
    env_path = tmp_path / ".env"
    monkeypatch.setenv(
        "QUANTMINE_PLUGIN_ALLOWED_PREFIXES",
        "quantmine,external_cn_source",
    )
    monkeypatch.setattr(
        task,
        "load_environment_file",
        lambda path: observed.setdefault("env_path", path),
    )
    monkeypatch.setattr(
        task,
        "load_a_share_history_refresh_config",
        lambda path: (
            observed.setdefault("config_path", path),
            config,
        )[1],
    )

    class _Registry:
        @classmethod
        def from_environment(cls, refs):
            observed["connection_refs"] = refs
            return connections

    def fake_run(context, *, config, allowed_module_prefixes):
        observed["context"] = context
        observed["config"] = config
        observed["allowed_module_prefixes"] = allowed_module_prefixes
        return SimpleNamespace(
            date_count=1_500,
            ticker_count=5_000,
            output_dir=tmp_path / "published",
        )

    monkeypatch.setattr(task, "ConnectionRegistry", _Registry)
    monkeypatch.setattr(
        task,
        "run_configured_a_share_history_refresh",
        fake_run,
    )

    task.main(
        [
            "--config",
            str(config_path),
            "--env-file",
            str(env_path),
        ]
    )

    assert observed["env_path"] == env_path
    assert observed["config_path"] == config_path
    assert observed["connection_refs"] == (
        "provider_input",
        "cn_reference",
        "cn_market_data",
    )
    assert observed["config"] is config
    assert observed["allowed_module_prefixes"] == (
        "quantmine",
        "external_cn_source",
    )
    context = observed["context"]
    assert context.connections is connections
    assert context.artifact_dir == (
        PROJECT_ROOT
        / "data"
        / "artifacts"
        / "a_share_history"
        / "bars_v1"
    )
    assert connections.disposed is True
    output = capsys.readouterr().out
    assert "version=bars_v1" in output
    assert "dates=1500" in output
    assert "tickers=5000" in output


def test_main_disposes_connections_when_history_refresh_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    task = _load_task_module()
    config = _config()
    connections = _Connections()
    monkeypatch.setattr(task, "load_environment_file", lambda path: None)
    monkeypatch.setattr(
        task,
        "load_a_share_history_refresh_config",
        lambda path: config,
    )

    class _Registry:
        @classmethod
        def from_environment(cls, refs):
            return connections

    monkeypatch.setattr(task, "ConnectionRegistry", _Registry)
    monkeypatch.setattr(
        task,
        "run_configured_a_share_history_refresh",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            RuntimeError("history collection failed")
        ),
    )

    with pytest.raises(RuntimeError, match="history collection failed"):
        task.main(
            [
                "--config",
                str(tmp_path / "config.yaml"),
                "--env-file",
                str(tmp_path / ".env"),
            ]
        )

    assert connections.disposed is True
