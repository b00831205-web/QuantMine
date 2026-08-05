from sqlalchemy import MetaData, Table, select, func
from sqlalchemy.engine import Engine
from datetime import date

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