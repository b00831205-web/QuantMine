"""Database connection construction."""

import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
import pandas as pd

# quantmine/storage/database.py -> quantmine/storage -> quantmine -> repo root.
# Resolves to site-packages for a non-editable install, where no .env exists and
# the loader simply finds nothing.
_REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_env_file() -> None:
    """Fill missing connection variables from the repo-root ``.env``.

    The webapi already does this via python-dotenv, but hand-run scripts and
    pipeline steps did not, so forgetting ``set -a; . ./.env`` surfaced as
    "Set QUANTMINE_DATABASE_URL ..." even though the file was sitting right
    there. Parsed with the stdlib rather than python-dotenv: ``quantmine`` ships
    as an importable library, and this is not worth a runtime dependency (only
    ``webapi/.venv`` has dotenv anyway).

    Real environment variables always win -- this only fills gaps, so Docker and
    the Airflow DAG, which inject the values directly, are unaffected.
    """
    env_file = _REPO_ROOT / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export "):]
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def get_engine(database_url: str | None = None) -> Engine:
    """Create an engine from an explicit URL or ``QUANTMINE_DATABASE_URL``."""
    url = database_url or os.environ.get("QUANTMINE_DATABASE_URL")
    if not url:
        _load_env_file()
        url = os.environ.get("QUANTMINE_DATABASE_URL")
    if not url:
        raise RuntimeError(
            "Set QUANTMINE_DATABASE_URL before running database-backed tasks "
            f"(also looked for it in {_REPO_ROOT / '.env'})."
        )
    return create_engine(url, pool_pre_ping=True)


def get_pipeline_engine(database_url: str | None = None) -> Engine:
    """Create an engine for jobs that write, preferring the write role.

    ``QUANTMINE_DATABASE_URL`` is ``quantmine_web``, which is deliberately
    read-only on new tables -- it is the security boundary for the AI's
    query_database tool. Default privileges grant it SELECT only, so a writer
    that picks it up dies with ``permission denied for table`` deep inside
    SQLAlchemy, a long way from the actual mistake. Older tables like
    ``market_bars`` hide this: they carry explicit DML grants issued before the
    split, so the wrong role appears to work until a new table shows up.

    The Airflow DAG solves this by exporting the pipeline URL over
    ``QUANTMINE_DATABASE_URL`` before each task; this function is the
    equivalent for scripts run by hand.

    Returns:
        An engine bound to ``QUANTMINE_PIPELINE_DATABASE_URL`` when set,
        otherwise falling back to ``QUANTMINE_DATABASE_URL`` (single-role
        deployments such as Docker configure only the latter).
    """
    def _pick() -> str | None:
        return (
            database_url
            or os.environ.get("QUANTMINE_PIPELINE_DATABASE_URL")
            or os.environ.get("QUANTMINE_DATABASE_URL")
        )

    url = _pick()
    if not url:
        _load_env_file()
        url = _pick()
    if not url:
        raise RuntimeError(
            "Set QUANTMINE_PIPELINE_DATABASE_URL (or QUANTMINE_DATABASE_URL) "
            "before running database-writing tasks "
            f"(also looked for them in {_REPO_ROOT / '.env'})."
        )
    return create_engine(url, pool_pre_ping=True)

