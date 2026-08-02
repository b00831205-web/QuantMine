"""Persistence for research-run metadata."""

import subprocess

from sqlalchemy import MetaData, Table, insert ,select
from sqlalchemy.engine import Engine


def get_current_git_commit() -> str | None:
    """Return the current commit, or ``None`` outside a Git checkout."""
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip() or None


def create_run(
    engine: Engine,
    config_snapshot: dict,
    *,
    git_commit: str | None = None,
) -> int:
    """Create and return one ``research_runs`` identifier."""
    metadata = MetaData()
    research_runs = Table("research_runs", metadata, autoload_with=engine)

    statement = insert(research_runs).values(
        config_snapshot=config_snapshot,
        git_commit=git_commit or get_current_git_commit(),
    )
    with engine.begin() as connection:
        result = connection.execute(statement)
        return int(result.inserted_primary_key[0])

def find_run_id_by_airflow_batch(engine:Engine, args_batch):
    metadata = MetaData()
    table = Table('research_runs', metadata, autoload_with= engine)
    statement = (select(table.c.run_id).where(table.c.config_snapshot['airflow_batch'].astext == args_batch).order_by(table.c.run_id.desc())).limit(1)
    with engine.connect() as connection:
        result = connection.execute(statement).scalar_one_or_none()
    if result is None:
        raise LookupError(f'No research run found for airflow batch {args_batch!r}')
    return int(result)