"""Transformation and PostgreSQL persistence for cleaned daily market bars."""

from collections.abc import Iterator
from datetime import date

import pandas as pd
from sqlalchemy import MetaData, Table, func ,select, desc
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import Engine


def build_market_bars(
    close: pd.DataFrame,
    volume: pd.DataFrame,
    source_run_id: int,
) -> pd.DataFrame:
    """Convert wide close/volume frames into database-ready long rows."""
    close_long = (
        close.rename_axis("trade_date")
        .rename_axis("ticker", axis="columns")
        .stack(future_stack=True)
        .rename("close")
        .reset_index()
    )
    volume_long = (
        volume.rename_axis("trade_date")
        .rename_axis("ticker", axis="columns")
        .stack(future_stack=True)
        .rename("volume")
        .reset_index()
    )
    market_bars = close_long.merge(
        volume_long,
        on=["trade_date", "ticker"],
        how="outer",
        validate="one_to_one",
    )
    market_bars = market_bars.dropna(
        subset=["close", "volume"],
        how="all",
    )
    market_bars["source_run_id"] = source_run_id
    return market_bars


def build_latest_snapshot(market_bars: pd.DataFrame) -> pd.DataFrame:
    """Return all ticker observations from the latest date in the input."""
    if market_bars.empty:
        return market_bars.copy()
    latest_date = market_bars["trade_date"].max()
    return market_bars.loc[
        market_bars["trade_date"] == latest_date,
        ["trade_date", "ticker", "close", "volume", "source_run_id"],
    ].copy()


def _record_batches(
    frame: pd.DataFrame,
    batch_size: int,
) -> Iterator[list[dict]]:
    records = frame.astype(object).where(pd.notna(frame), None).to_dict(
        orient="records"
    )
    for start in range(0, len(records), batch_size):
        yield records[start : start + batch_size]


def upsert_market_bars(
    engine: Engine,
    market_bars: pd.DataFrame,
    *,
    batch_size: int = 5_000,
) -> int:
    """Insert or update historical bars in bounded batches."""
    if market_bars.empty:
        return 0

    metadata = MetaData()
    table = Table("market_bars", metadata, autoload_with=engine)
    written = 0

    with engine.begin() as connection:
        for rows in _record_batches(market_bars, batch_size):
            statement = pg_insert(table).values(rows)
            statement = statement.on_conflict_do_update(
                index_elements=["trade_date", "ticker"],
                set_={
                    "close": statement.excluded.close,
                    "volume": statement.excluded.volume,
                    "source_run_id": statement.excluded.source_run_id,
                    "updated_at": func.now(),
                },
            )
            connection.execute(statement)
            written += len(rows)
    return written


def upsert_latest_snapshot(
    engine: Engine,
    latest_snapshot: pd.DataFrame,
) -> int:
    """Upsert one latest observation per ticker without regressing its date."""
    if latest_snapshot.empty:
        return 0

    metadata = MetaData()
    table = Table("market_latest", metadata, autoload_with=engine)
    rows = (
        latest_snapshot.astype(object)
        .where(pd.notna(latest_snapshot), None)
        .to_dict(orient="records")
    )
    statement = pg_insert(table).values(rows)
    statement = statement.on_conflict_do_update(
        index_elements=["ticker"],
        set_={
            "trade_date": statement.excluded.trade_date,
            "close": statement.excluded.close,
            "volume": statement.excluded.volume,
            "source_run_id": statement.excluded.source_run_id,
            "updated_at": func.now(),
        },
        where=statement.excluded.trade_date >= table.c.trade_date,
    )
    with engine.begin() as connection:
        connection.execute(statement)
    return len(rows)

def fetch_market_bars(engine: Engine, 
                      symbols: list[str], 
                      start_date, 
                      end_date)-> pd.DataFrame:
    metadata = MetaData()
    table = Table('market_bars', metadata, autoload_with= engine)
    statement = (select(table.c.trade_date, table.c.ticker, table.c.close)
                 .where(start_date <=table.c.trade_date , table.c.trade_date <= end_date, table.c.ticker.in_(symbols))
                 .order_by(table.c.trade_date, table.c.ticker))
    with engine.connect() as connection:
        result = connection.execute(statement).mappings().all()
    return pd.DataFrame(result, columns=['trade_date', 'ticker', 'close'])

def fetch_latest_market_trade_date(engine:Engine)->date|None:
    metadata = MetaData()
    table = Table('market_bars', metadata, autoload_with=engine)
    statement = select(func.max(table.c.trade_date))
    with engine.connect() as conn:
        result = conn.execute(statement).scalar_one_or_none()
    return result

def switch_to_week(df: pd.DataFrame):
    working = df.dropna(subset = ['close']).copy()
    working['trade_date'] = pd.to_datetime(working['trade_date'])
    working = working.sort_values(['ticker', 'trade_date'])

    working['bucket'] = working['trade_date'].dt.to_period('W-FRI')

    weekly = (
        working.groupby(['ticker', 'bucket'], as_index = False)
        .tail(1)
        .drop(columns='bucket')
        .sort_values(['trade_date', 'ticker'])
    )
    return weekly

def switch_to_month(df: pd.DataFrame):
    working = df.dropna(subset = ['close']).copy()
    working['trade_date'] = pd.to_datetime(working['trade_date'])
    working = working.sort_values(['ticker', 'trade_date'])

    working['bucket'] = working['trade_date'].dt.to_period('M')

    monthly = (
        working.groupby(['ticker', 'bucket'], as_index = False)
        .tail(1)
        .drop(columns='bucket')
        .sort_values(['trade_date', 'ticker'])
    )
    return monthly