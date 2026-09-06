"""Runtime loading of local deployment environment variables."""

from pathlib import Path

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

