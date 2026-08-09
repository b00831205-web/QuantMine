"""Persistence helpers for Carhart four-factor attribution results.

The daily ``long_short`` return series is already stored in ``backtest_results``
(``quantile_rank = 0``), so attribution reads from the DB rather than re-running
the backtest. Results land in ``attribution_results`` (one row per regression
term), which the PDF report's section 03 reads back.
"""
from __future__ import annotations

import pandas as pd
from sqlalchemy import MetaData, Table, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import Engine


def load_long_short_returns(
    engine: Engine,
    run_id: int,
    test_id: str | None = None,
) -> dict[tuple[str, str, int, str], pd.Series]:
    """读回每个组合的多空日收益序列（``quantile_rank = 0``）。

    Returns:
        ``{(variant, factor, period, test_id): Series}``，Series 以 ``trade_date``
        为索引。key 带上 ``test_id`` 以便归因结果与来源回测行对齐。
    """
    table = Table("backtest_results", MetaData(), autoload_with=engine)
    conditions = [table.c.run_id == run_id, table.c.quantile_rank == 0]
    if test_id:
        conditions.append(table.c.test_id == test_id)
    statement = (
        select(
            table.c.variant_name,
            table.c.factor_name,
            table.c.period,
            table.c.test_id,
            table.c.trade_date,
            table.c.return_value,
        )
        .where(*conditions)
        .order_by(table.c.trade_date)
    )
    with engine.connect() as connection:
        rows = connection.execute(statement).mappings().all()

    grouped: dict[tuple[str, str, int, str], dict] = {}
    for row in rows:
        if row["return_value"] is None:
            continue
        key = (row["variant_name"], row["factor_name"], int(row["period"]), row["test_id"])
        grouped.setdefault(key, {})[row["trade_date"]] = float(row["return_value"])

    return {
        key: pd.Series(values).sort_index()
        for key, values in grouped.items()
        if values
    }


def save_attribution_results(engine: Engine, rows: pd.DataFrame) -> int:
    """Upsert attribution rows into ``attribution_results``.

    ``rows`` columns: run_id, variant_name, test_id, factor_name, period, term,
    coef, std_err, t_stat, p_value, ci_lo, ci_hi, r2, adj_r2, n, alpha_annual,
    maxlags.
    """
    if rows.empty:
        return 0
    records = rows.astype(object).where(pd.notna(rows), None).to_dict(orient="records")
    table = Table("attribution_results", MetaData(), autoload_with=engine)
    statement = pg_insert(table).values(records)
    statement = statement.on_conflict_do_update(
        index_elements=[
            "run_id",
            "variant_name",
            "test_id",
            "factor_name",
            "period",
            "term",
        ],
        set_={
            column: statement.excluded[column]
            for column in (
                "coef", "std_err", "t_stat", "p_value", "ci_lo", "ci_hi",
                "r2", "adj_r2", "n", "alpha_annual", "maxlags",
            )
        },
    )
    with engine.begin() as connection:
        connection.execute(statement)
    return len(records)
