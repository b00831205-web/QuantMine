"""Tests for named external market-data connections."""

from __future__ import annotations

import pytest

from quantmine.storage.connections import (
    ConnectionKind,
    ConnectionRegistry,
    DataConnectionConfig,
)


def test_parquet_root_resolves_named_environment_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("QUANTMINE_TEST_PARQUET_ROOT", str(tmp_path))
    registry = ConnectionRegistry(
        {
            "cn_equity_lake": DataConnectionConfig(
                kind=ConnectionKind.PARQUET,
                root_env="QUANTMINE_TEST_PARQUET_ROOT",
            )
        }
    )

    assert registry.connection_refs == ("cn_equity_lake",)
    assert registry.parquet_root("cn_equity_lake") == tmp_path


def test_parquet_connection_rejects_sqlalchemy_access() -> None:
    registry = ConnectionRegistry(
        {
            "lake": DataConnectionConfig(
                kind=ConnectionKind.PARQUET,
                root_env="QUANTMINE_TEST_PARQUET_ROOT",
            )
        }
    )

    with pytest.raises(ValueError, match="not a SQLAlchemy connection"):
        registry.sqlalchemy_engine("lake")


def test_sqlalchemy_connection_is_cached(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("QUANTMINE_TEST_SQL_URL", "sqlite://")
    registry = ConnectionRegistry(
        {
            "research_db": DataConnectionConfig(
                kind=ConnectionKind.SQLALCHEMY,
                url_env="QUANTMINE_TEST_SQL_URL",
            )
        }
    )

    first = registry.sqlalchemy_engine("research_db")
    second = registry.sqlalchemy_engine("research_db")

    assert first is second
    registry.dispose()


def test_connection_configuration_and_missing_environment_fail_loudly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(ValueError, match="requires root_env"):
        DataConnectionConfig(kind=ConnectionKind.PARQUET)

    monkeypatch.delenv("QUANTMINE_TEST_MISSING_ROOT", raising=False)
    registry = ConnectionRegistry(
        {
            "missing_lake": DataConnectionConfig(
                kind=ConnectionKind.PARQUET,
                root_env="QUANTMINE_TEST_MISSING_ROOT",
            )
        }
    )

    with pytest.raises(RuntimeError, match="not set"):
        registry.parquet_root("missing_lake")


def test_unknown_connection_reports_available_aliases() -> None:
    registry = ConnectionRegistry(
        {
            "known_lake": DataConnectionConfig(
                kind=ConnectionKind.PARQUET,
                root_env="QUANTMINE_TEST_PARQUET_ROOT",
            )
        }
    )

    with pytest.raises(KeyError, match="known_lake"):
        registry.parquet_root("missing_lake")


def test_registry_builds_one_named_connection_from_environment(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("QUANTMINE_CONNECTION_CN_EQUITY_LAKE_KIND", "parquet")
    monkeypatch.setenv(
        "QUANTMINE_CONNECTION_CN_EQUITY_LAKE_ROOT",
        str(tmp_path),
    )

    registry = ConnectionRegistry.from_environment(("cn_equity_lake",))

    assert registry.connection_refs == ("cn_equity_lake",)
    assert registry.parquet_root("cn_equity_lake") == tmp_path


def test_registry_environment_loader_rejects_missing_connection_kind(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("QUANTMINE_CONNECTION_MISSING_KIND_KIND", raising=False)

    with pytest.raises(RuntimeError, match="_KIND"):
        ConnectionRegistry.from_environment(("missing_kind",))
