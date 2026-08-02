"""Database connection construction."""

import os

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine


def get_engine(database_url: str | None = None) -> Engine:
    """Create an engine from an explicit URL or ``QUANTMINE_DATABASE_URL``."""
    url = database_url or os.environ.get("QUANTMINE_DATABASE_URL")
    if not url:
        raise RuntimeError(
            "Set QUANTMINE_DATABASE_URL before running database-backed tasks."
        )
    return create_engine(url, pool_pre_ping=True)
