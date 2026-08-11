"""Report history query layer: paginated list + write one generation record."""

from __future__ import annotations

from sqlalchemy import MetaData, Table, exists, func, insert, or_, select, update
from sqlalchemy.engine import Engine


def fetch_report_history(
    engine: Engine,
    *,
    page: int,
    page_size: int,
    run_id: int | None = None,
) -> tuple[list[dict], int]:
    metadata = MetaData()
    table = Table("report_history", metadata, autoload_with=engine)
    test_results = Table("test_results", metadata, autoload_with=engine)
    backtest_metrics = Table("backtest_metrics", metadata, autoload_with=engine)

    test_data_exists = exists(
        select(1).where(
            test_results.c.run_id == table.c.run_id,
            or_(table.c.test_id.is_(None), test_results.c.test_id == table.c.test_id),
        )
    )
    backtest_data_exists = exists(
        select(1).where(
            backtest_metrics.c.run_id == table.c.run_id,
            or_(table.c.test_id.is_(None), backtest_metrics.c.test_id == table.c.test_id),
        )
    )

    statement = (
        select(
            table.c.id,
            table.c.run_id,
            table.c.test_id,
            table.c.lang,
            table.c.ai,
            table.c.artifact_type,
            table.c.artifact_path,
            table.c.artifact_size,
            table.c.status,
            table.c.created_at,
            or_(test_data_exists, backtest_data_exists).label("data_available"),
        )
        .order_by(table.c.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    count_statement = select(func.count()).select_from(table)
    if run_id is not None:
        statement = statement.where(table.c.run_id == run_id)
        count_statement = count_statement.where(table.c.run_id == run_id)

    with engine.connect() as connection:
        rows = connection.execute(statement).mappings().all()
        total = connection.execute(count_statement).scalar_one()

    return [dict(row) for row in rows], total


def fetch_report_history_item(engine: Engine, report_id: int) -> dict | None:
    table = Table("report_history", MetaData(), autoload_with=engine)
    statement = select(table).where(table.c.id == report_id)
    with engine.connect() as connection:
        row = connection.execute(statement).mappings().first()
    return dict(row) if row else None


def insert_report_history(
    engine: Engine,
    *,
    run_id: int,
    test_id: str | None,
    lang: str,
    ai: bool,
    artifact_type: str = "pdf",
    status: str = "failed",
) -> int:
    metadata = MetaData()
    table = Table("report_history", metadata, autoload_with=engine)

    statement = (
        insert(table)
        .values(
            run_id=run_id,
            test_id=test_id,
            lang=lang,
            ai=ai,
            artifact_type=artifact_type,
            status=status,
        )
        .returning(table.c.id)
    )

    with engine.begin() as connection:
        new_id = connection.execute(statement).scalar_one()
    return new_id


def finalize_report_history(
    engine: Engine,
    report_id: int,
    *,
    artifact_path: str | None,
    artifact_size: int | None,
    status: str,
) -> None:
    table = Table("report_history", MetaData(), autoload_with=engine)
    statement = (
        update(table)
        .where(table.c.id == report_id)
        .values(
            artifact_path=artifact_path,
            artifact_size=artifact_size,
            status=status,
        )
    )
    with engine.begin() as connection:
        connection.execute(statement)
