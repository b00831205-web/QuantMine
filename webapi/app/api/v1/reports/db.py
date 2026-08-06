"""报告历史查询层：分页列表 + 写入一条生成记录。"""

from __future__ import annotations

from sqlalchemy import MetaData, Table, func, insert, select
from sqlalchemy.engine import Engine


def fetch_report_history(
    engine: Engine,
    *,
    page: int,
    page_size: int,
) -> tuple[list[dict], int]:
    metadata = MetaData()
    table = Table("report_history", metadata, autoload_with=engine)

    statement = (
        select(
            table.c.id,
            table.c.run_id,
            table.c.test_id,
            table.c.lang,
            table.c.ai,
            table.c.status,
            table.c.created_at,
        )
        .order_by(table.c.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    count_statement = select(func.count()).select_from(table)

    with engine.connect() as connection:
        rows = connection.execute(statement).mappings().all()
        total = connection.execute(count_statement).scalar_one()

    return [dict(row) for row in rows], total


def insert_report_history(
    engine: Engine,
    *,
    run_id: int,
    test_id: str | None,
    lang: str,
    ai: bool,
    status: str = "ready",
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
            status=status,
        )
        .returning(table.c.id)
    )

    with engine.begin() as connection:
        new_id = connection.execute(statement).scalar_one()
    return new_id
