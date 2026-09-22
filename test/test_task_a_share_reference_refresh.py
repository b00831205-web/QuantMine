"""Tests for the A-share reference refresh command entry point."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

from quantmine.dataset_versions import AS_OF_DATE_VERSION
from quantmine.plugins.contracts import VersionedDatasetBinding


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TASK_PATH = PROJECT_ROOT / "pipelines" / "task_a_share_reference_refresh.py"


def _load_task_module():
    spec = importlib.util.spec_from_file_location(
        "task_a_share_reference_refresh_for_test",
        TASK_PATH,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _binding() -> VersionedDatasetBinding:
    return VersionedDatasetBinding(
        connection_ref="cn_reference",
        dataset="cn_a_share_reference",
        market="CN",
        version="20260906",
    )


class _Connections:
    def __init__(self) -> None:
        self.disposed = False

    def dispose(self) -> None:
        self.disposed = True


def test_main_loads_runtime_config_runs_refresh_and_disposes_connections(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    task = _load_task_module()
    config_path = tmp_path / "config.yaml"
    env_path = tmp_path / ".env"
    binding = _binding()
    connections = _Connections()
    observed: dict[str, object] = {}

    monkeypatch.setattr(
        task,
        "load_environment_file",
        lambda path: observed.setdefault("env_path", path),
    )
    monkeypatch.setattr(
        task,
        "load_a_share_daily_pipeline_config",
        lambda path: (
            observed.setdefault("config_path", path),
            SimpleNamespace(reference_binding=binding),
        )[1],
    )

    class _Registry:
        @classmethod
        def from_environment(cls, refs):
            observed["connection_refs"] = refs
            return connections

    def fake_refresh(context, *, binding):
        observed["context"] = context
        observed["binding"] = binding
        return SimpleNamespace(
            listing_count=3,
            session_count=4,
            output_dir=tmp_path / "published",
        )

    monkeypatch.setattr(task, "ConnectionRegistry", _Registry)
    monkeypatch.setattr(
        task,
        "refresh_akshare_a_stock_reference",
        fake_refresh,
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
    assert observed["connection_refs"] == ("cn_reference",)
    assert observed["binding"] is binding
    assert observed["context"].connections is connections
    assert connections.disposed is True
    output = capsys.readouterr().out
    assert "version=20260906" in output
    assert "listings=3" in output
    assert "sessions=4" in output


def test_main_disposes_connections_when_refresh_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    task = _load_task_module()
    binding = _binding()
    connections = _Connections()

    monkeypatch.setattr(task, "load_environment_file", lambda path: True)
    monkeypatch.setattr(
        task,
        "load_a_share_daily_pipeline_config",
        lambda path: SimpleNamespace(reference_binding=binding),
    )

    class _Registry:
        @classmethod
        def from_environment(cls, refs):
            return connections

    def fail_refresh(context, *, binding):
        raise RuntimeError("collection failed")

    monkeypatch.setattr(task, "ConnectionRegistry", _Registry)
    monkeypatch.setattr(
        task,
        "refresh_akshare_a_stock_reference",
        fail_refresh,
    )

    with pytest.raises(RuntimeError, match="collection failed"):
        task.main(
            [
                "--config",
                str(tmp_path / "config.yaml"),
                "--env-file",
                str(tmp_path / ".env"),
            ]
        )

    assert connections.disposed is True


def test_main_resolves_a_dynamic_reference_version_from_date(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    task = _load_task_module()
    dynamic_binding = VersionedDatasetBinding(
        connection_ref="cn_reference",
        dataset="cn_a_share_reference",
        market="CN",
        version=AS_OF_DATE_VERSION,
    )
    connections = _Connections()
    observed: dict[str, object] = {}

    monkeypatch.setattr(task, "load_environment_file", lambda path: None)
    monkeypatch.setattr(
        task,
        "load_a_share_daily_pipeline_config",
        lambda path: SimpleNamespace(reference_binding=dynamic_binding),
    )

    class _Registry:
        @classmethod
        def from_environment(cls, refs):
            return connections

    def fake_refresh(context, *, binding):
        observed["binding"] = binding
        return SimpleNamespace(
            listing_count=3,
            session_count=4,
            output_dir=tmp_path / "published",
        )

    monkeypatch.setattr(task, "ConnectionRegistry", _Registry)
    monkeypatch.setattr(
        task,
        "refresh_akshare_a_stock_reference",
        fake_refresh,
    )

    task.main(
        [
            "--date",
            "2026-09-09",
            "--config",
            str(tmp_path / "config.yaml"),
        ]
    )

    assert observed["binding"].version == "20260909"


def test_main_requires_date_for_a_dynamic_reference_version(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    task = _load_task_module()
    dynamic_binding = VersionedDatasetBinding(
        connection_ref="cn_reference",
        dataset="cn_a_share_reference",
        market="CN",
        version=AS_OF_DATE_VERSION,
    )
    monkeypatch.setattr(task, "load_environment_file", lambda path: None)
    monkeypatch.setattr(
        task,
        "load_a_share_daily_pipeline_config",
        lambda path: SimpleNamespace(reference_binding=dynamic_binding),
    )

    with pytest.raises(SystemExit):
        task.main(["--config", str(tmp_path / "config.yaml")])

    assert "--date is required" in capsys.readouterr().err
