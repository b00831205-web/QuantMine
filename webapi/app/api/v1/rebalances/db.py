import pandas as pd
from sqlalchemy import MetaData, Table, func, select, text
from sqlalchemy.engine import Engine
from datetime import date

from .holdings import resolve_ticker_history_path

def fetch_rebalance_rows(
    engine: Engine,
    *,
    backtest_job: str | None,
    variant: str | None,
    factor: str | None,
    trade_date: date | None,
    page: int,
    page_size: int,
) -> list[dict]:
    metadata = MetaData()
    table = Table("backtest_results", metadata, autoload_with=engine)

    conditions = []
    if backtest_job:
        conditions.append(table.c.backtest_id == backtest_job)
    if variant:
        conditions.append(table.c.variant_name == variant)
    if factor:
        conditions.append(table.c.factor_name == factor)
    if trade_date:
        conditions.append(table.c.trade_date == trade_date)

    statement = (
        select(
            table.c.backtest_id,
            table.c.variant_name,
            table.c.factor_name,
            table.c.period,
            table.c.trade_date,
            table.c.quantile_rank,
            table.c.return_value,
            table.c.run_id
        )
        .where(*conditions)
        .order_by(table.c.trade_date.desc(), table.c.quantile_rank)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    with engine.connect() as connection:
        rows = connection.execute(statement).mappings().all()
    return [dict(row) for row in rows]

def count_rebalance_rows(
    engine: Engine,
    *,
    backtest_job: str | None,
    variant: str | None,
    factor: str | None,
    trade_date: date | None,
) -> int:
    metadata = MetaData()
    table = Table("backtest_results", metadata, autoload_with=engine)
    conditions = []
    if backtest_job:
        conditions.append(table.c.backtest_id == backtest_job)
    if variant:
        conditions.append(table.c.variant_name == variant)
    if factor:
        conditions.append(table.c.factor_name == factor)
    if trade_date:
        conditions.append(table.c.trade_date == trade_date)

    statement = select(func.count()).select_from(table).where(*conditions)
    with engine.connect() as connection:
        return connection.execute(statement).scalar_one()

def fetch_rebalance_return_rows(
        engine: Engine,
        *,
        backtest_id: str,
        variant_name: str,
        factor_name: str,
        period: int,
        quantile_rank: int,
) -> list[dict]:
    metadata = MetaData()
    table = Table('backtest_results', metadata, autoload_with=engine)
    statement = (
        select(table.c.trade_date, table.c.return_value)
        .where(table.c.backtest_id == backtest_id,
               table.c.variant_name == variant_name,
               table.c.factor_name == factor_name,
               table.c.period == period,
               table.c.quantile_rank == quantile_rank)
               .order_by(table.c.trade_date.asc())
    )
    with engine.connect() as connection:
        rows = connection.execute(statement).mappings().all()
    return [dict(row) for row in rows]

def fetch_rebalance_detail_row(
        engine: Engine,
        *,
        run_id: int,
        backtest_id: str,
        variant_name: str,
        factor_name: str,
        period: int,
        trade_date: str,
        quantile_rank: int,
) -> dict|None:
    metadata = MetaData()
    table = Table('backtest_results', metadata, autoload_with= engine)
    statement=(
        select(
            table.c.backtest_id,
            table.c.variant_name,
            table.c.factor_name,
            table.c.period,
            table.c.trade_date,
            table.c.quantile_rank,
            table.c.return_value
        )
        .where(
            table.c.run_id == run_id,
            table.c.backtest_id == backtest_id,
            table.c.variant_name == variant_name,
            table.c.factor_name == factor_name,
            table.c.period == period,
            table.c.trade_date == date.fromisoformat(trade_date),
            table.c.quantile_rank == quantile_rank,
        )
        .limit(1)
    )
    with engine.connect() as connection:
        row = connection.execute(statement).mappings().first()
    return dict(row) if row else None

def fetch_ticker_history_path(
        engine: Engine,
        *,
        run_id: int,
        variant_name: str,
        backtest_id: str,
        factor_name: str,
        period: int
) -> str | None:
    metadata = MetaData()
    table = Table('backtest_artifacts', metadata, autoload_with=engine)
    artifact_key = f'{factor_name}__{period}'
    statement = (
        select(table.c.path)
        .where(
            table.c.run_id == run_id,
            table.c.variant_name == variant_name,
            table.c.backtest_id == backtest_id,
            table.c.artifact_type == 'ticker_history',
            table.c.artifact_key == artifact_key,
        )
        .limit(1)
    )
    with engine.connect() as connection:
        return connection.execute(statement).scalar_one_or_none()

def fetch_next_rebalance_date(
        engine: Engine,
        *,
        run_id: int,
        backtest_id: str,
        variant_name: str,
        factor_name: str,
        period: int,
        quantile_rank: int,
        trade_date: str
): 
    metadata = MetaData()
    table = Table('backtest_results', metadata, autoload_with=engine)
    statement = (
        select(table.c.trade_date)
        .where(
            table.c.run_id == run_id,
            table.c.backtest_id == backtest_id,
            table.c.variant_name == variant_name,
            table.c.factor_name == factor_name,
            table.c.period == period,
            table.c.quantile_rank == quantile_rank,
            table.c.trade_date > date.fromisoformat(trade_date)
        )
        .order_by(table.c.trade_date.asc())
        .limit(1)
    )
    with engine.connect() as connection:
        return connection.execute(statement).scalar_one_or_none()

def fetch_market_closes(
        engine: Engine,
        symbols: list[str],
        dates: list[date],
) -> list[dict]:
    if not symbols or not dates:
        return []
    metadata = MetaData()
    table = Table('market_bars', metadata, autoload_with=engine)
    statement = select(table.c.ticker, table.c.trade_date, table.c.close).where(
        table.c.ticker.in_(symbols),
        table.c.trade_date.in_(dates),
    )
    with engine.connect() as connection:
        rows = connection.execute(statement).mappings().all()
    return [dict(row) for row in rows]


def fetch_turnover_excess_map(
    engine: Engine,
    run_ids: set[int],
) -> dict[tuple, dict]:
    """Fetch turnover/excess metrics at once; key=(run_id, backtest_id, variant, factor, period, rank)."""
    if not run_ids:
        return {}
    metadata = MetaData()
    table = Table("backtest_metrics", metadata, autoload_with=engine)
    statement = (
        select(
            table.c.run_id,
            table.c.backtest_id,
            table.c.variant_name,
            table.c.factor_name,
            table.c.period,
            table.c.quantile_rank,
            table.c.metric_name,
            table.c.metric_value,
        )
        .where(
            table.c.run_id.in_(run_ids),
            table.c.metric_name.in_(["turnover", "excess"]),
        )
    )
    with engine.connect() as connection:
        rows = connection.execute(statement).mappings().all()
    result: dict[tuple, dict] = {}
    for r in rows:
        key = (
            r["run_id"], r["backtest_id"], r["variant_name"],
            r["factor_name"], r["period"], r["quantile_rank"],
        )
        result.setdefault(key, {})[r["metric_name"]] = r["metric_value"]
    return result


def fetch_next_dates_map(engine: Engine) -> dict[tuple, date | None]:
    """Compute each rebalance date's next date in one pass with a window function (dates as str in the key)."""
    statement = text(
        """
        SELECT run_id, backtest_id, variant_name, factor_name, period,
               quantile_rank, trade_date,
               LEAD(trade_date) OVER (
                   PARTITION BY run_id, backtest_id, variant_name,
                                factor_name, period, quantile_rank
                   ORDER BY trade_date
               ) AS next_date
        FROM backtest_results
        """
    )
    with engine.connect() as connection:
        rows = connection.execute(statement).mappings().all()
    result: dict[tuple, date | None] = {}
    for r in rows:
        key = (
            r["run_id"], r["backtest_id"], r["variant_name"],
            r["factor_name"], r["period"], r["quantile_rank"],
            str(r["trade_date"]),
        )
        result[key] = r["next_date"]
    return result


def fetch_spy_closes(engine: Engine, dates: set[date]) -> dict[date, float | None]:
    if not dates:
        return {}
    metadata = MetaData()
    table = Table("market_bars", metadata, autoload_with=engine)
    statement = select(table.c.trade_date, table.c.close).where(
        table.c.ticker == "SPY",
        table.c.trade_date.in_(sorted(dates)),
    )
    with engine.connect() as connection:
        rows = connection.execute(statement).mappings().all()
    return {
        r["trade_date"]: float(r["close"]) if r["close"] is not None else None
        for r in rows
    }


def fetch_holdings_count_map(
    engine: Engine,
    run_ids: set[int],
) -> dict[tuple, int]:
    """Count holdings per rebalance date/quantile from the ticker_history parquet in one pass."""
    if not run_ids:
        return {}
    metadata = MetaData()
    table = Table("backtest_artifacts", metadata, autoload_with=engine)
    statement = (
        select(
            table.c.run_id,
            table.c.backtest_id,
            table.c.variant_name,
            table.c.artifact_key,
            table.c.path,
            table.c.metadata,
        )
        .where(
            table.c.run_id.in_(run_ids),
            table.c.artifact_type == "ticker_history",
        )
    )
    with engine.connect() as connection:
        rows = connection.execute(statement).mappings().all()

    result: dict[tuple, int] = {}
    for r in rows:
        meta = r["metadata"] or {}
        factor_name = meta.get("factor_name")
        period = meta.get("period")
        if not factor_name or period is None:
            # 兜底：从 artifact_key "factor__period" 解析
            parts = (r["artifact_key"] or "").rsplit("__", 1)
            if len(parts) != 2:
                continue
            factor_name, period = parts[0], parts[1]
        try:
            period = int(period)
        except (TypeError, ValueError):
            continue
        path = resolve_ticker_history_path(
            run_id=r["run_id"],
            backtest_id=r["backtest_id"],
            factor_name=factor_name,
            period=period,
        )
        if not path:
            continue
        df = pd.read_parquet(path)
        counts = df.groupby(["trade_date", "quantile_rank"]).size()
        for (trade_date, rank), count in counts.items():
            date_str = (
                str(trade_date.date())
                if hasattr(trade_date, "date")
                else str(trade_date)
            )
            key = (
                r["run_id"], r["backtest_id"], r["variant_name"],
                factor_name, period, int(rank), date_str,
            )
            result[key] = int(count)
    return result
