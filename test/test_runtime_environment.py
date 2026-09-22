"""Runtime loading of local deployment environment variables."""

import os
from pathlib import Path

import pytest

from quantmine.runtime_environment import load_environment_file


def test_environment_file_fills_missing_values_without_overriding_process_env(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("QUANTMINE_CONNECTION_CN_RAW_KIND", raising=False)
    monkeypatch.setenv(
        "QUANTMINE_CONNECTION_CN_RAW_URL",
        "postgresql://injected",
    )
    env_file = tmp_path / ".env"
    env_file.write_text(
        """
# local deployment configuration
export QUANTMINE_CONNECTION_CN_RAW_KIND=sqlalchemy
QUANTMINE_CONNECTION_CN_RAW_URL=postgresql://from-file
""",
        encoding="utf-8",
    )

    loaded = load_environment_file(env_file)

    assert loaded is True
    assert (
        __import__("os").environ["QUANTMINE_CONNECTION_CN_RAW_KIND"]
        == "sqlalchemy"
    )
    assert (
        __import__("os").environ["QUANTMINE_CONNECTION_CN_RAW_URL"]
        == "postgresql://injected"
    )


def test_missing_optional_environment_file_is_ignored(tmp_path: Path) -> None:
    assert load_environment_file(tmp_path / "missing.env") is False


@pytest.mark.skipif(
    os.name == "nt",
    reason="Windows environment variable names are case-insensitive",
)
def test_environment_file_merges_configured_proxy_bypass_hosts_into_both_cases(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("NO_PROXY", "localhost,127.0.0.1")
    monkeypatch.setenv("no_proxy", "10.0.0.0/8")
    monkeypatch.delenv("QUANTMINE_NO_PROXY_HOSTS", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text(
        "QUANTMINE_NO_PROXY_HOSTS=push2his.eastmoney.com,example.test\n",
        encoding="utf-8",
    )

    loaded = load_environment_file(env_file)

    assert loaded is True
    expected = {
        "localhost",
        "127.0.0.1",
        "10.0.0.0/8",
        "push2his.eastmoney.com",
        "example.test",
    }
    assert set(__import__("os").environ["NO_PROXY"].split(",")) == expected
    assert set(__import__("os").environ["no_proxy"].split(",")) == expected


def test_environment_file_deduplicates_proxy_bypass_hosts(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("NO_PROXY", "localhost,push2his.eastmoney.com")
    monkeypatch.setenv("no_proxy", "localhost")
    monkeypatch.setenv(
        "QUANTMINE_NO_PROXY_HOSTS",
        "push2his.eastmoney.com",
    )
    env_file = tmp_path / ".env"
    env_file.write_text(
        "QUANTMINE_NO_PROXY_HOSTS=push2his.eastmoney.com\n",
        encoding="utf-8",
    )

    load_environment_file(env_file)

    assert (
        __import__("os").environ["NO_PROXY"]
        == "localhost,push2his.eastmoney.com"
    )
    assert (
        __import__("os").environ["no_proxy"]
        == "localhost,push2his.eastmoney.com"
    )
