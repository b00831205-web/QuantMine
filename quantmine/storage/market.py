"""Transformation and PostgreSQL persistence for cleaned daily market bars."""

from collections.abc import Iterator
from datetime import date

import pandas as pd
from sqlalchemy import MetaData, Table, func, select, desc, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import Engine


def build_market_bars(
    close: pd.DataFrame,
    volume: pd.DataFrame,
    source_run_id: int,
    shares: pd.DataFrame | None = None,
    market_cap: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Convert wide close/volume frames into database-ready long rows.

    Args:
        close: Wide date-by-ticker close prices.
        volume: Wide date-by-ticker volumes.
        source_run_id: Research run that produced this load.
        shares: Optional wide share counts, aligned onto ``close``.
        market_cap: Optional wide market caps, aligned onto ``close``.

    Returns:
        Long rows keyed by ``(trade_date, ticker)``. The ``shares_outstanding``
        and ``market_cap`` columns are always present, filled with NA when the
        corresponding frame is omitted.
    """
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
    if shares is not None:
        aligned_shares = shares.reindex(
            index=close.index, columns = close.columns
        )
        shares_long = (
            aligned_shares.rename_axis('trade_date')
            .rename_axis('ticker', axis = 'columns')
            .stack(future_stack=True)
            .rename('shares_outstanding')
            .reset_index()
        )
        market_bars = market_bars.merge(shares_long, on=['trade_date', 'ticker'], how = 'left')
    if market_cap is not None:
        aligned_cap = market_cap.reindex(
            index = close.index, columns = close.columns
        )
        cap_long = (
            aligned_cap.rename_axis('trade_date')
            .rename_axis('ticker', axis = 'columns')
            .stack(future_stack = True)
            .rename('market_cap')
            .reset_index())
        market_bars = market_bars.merge(
            cap_long, on = ['trade_date', 'ticker'], how='left'
        )
    # 未传 shares/market_cap 时也保证列存在, 否则下游 snapshot/upsert 会 KeyError
    for col in ("shares_outstanding", "market_cap"):
        if col not in market_bars.columns:
            market_bars[col] = pd.NA
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
        ["trade_date", "ticker", "close", "volume",
         "shares_outstanding", "market_cap", "source_run_id"],
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
                    'shares_outstanding': statement.excluded.shares_outstanding,
                    "source_run_id": statement.excluded.source_run_id,
                    'market_cap': statement.excluded.market_cap,
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
            "shares_outstanding": statement.excluded.shares_outstanding,
            "market_cap": statement.excluded.market_cap,
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
    """Read closes for the given tickers over an inclusive date range.

    Returns:
        Long rows ``[trade_date, ticker, close]`` sorted by date then ticker,
        empty when nothing matches. Only ``close`` is selected; consumers that
        need market cap read the processed parquet instead.
    """
    metadata = MetaData()
    table = Table('market_bars', metadata, autoload_with= engine)
    statement = (select(table.c.trade_date, table.c.ticker, table.c.close)
                 .where(start_date <=table.c.trade_date , table.c.trade_date <= end_date, table.c.ticker.in_(symbols))
                 .order_by(table.c.trade_date, table.c.ticker))
    with engine.connect() as connection:
        result = connection.execute(statement).mappings().all()
    return pd.DataFrame(result, columns=['trade_date', 'ticker', 'close'])

def fetch_ticker_coverage(engine: Engine) -> pd.DataFrame:
    """Return what history each ticker already has, one row per ticker.

    The download planner needs per-ticker bounds, not the single global
    watermark ``max(trade_date)``. A name added to the index today has no rows
    at all, yet the global watermark reports the database current through
    yesterday -- so a watermark-driven download never reaches back for that
    name's past, and every lookback factor stays NaN for it.

    Returns:
        Columns ``ticker``, ``first_date``, ``last_date``, ``observations``;
        empty with those columns when ``market_bars`` has no rows.
    """
    statement = text(
        """
        SELECT ticker,
               MIN(trade_date) AS first_date,
               MAX(trade_date) AS last_date,
               COUNT(*)        AS observations
        FROM market_bars
        GROUP BY ticker
        """
    )
    with engine.connect() as connection:
        rows = connection.execute(statement).mappings().all()
    return pd.DataFrame(
        rows, columns=["ticker", "first_date", "last_date", "observations"]
    )


def fetch_trading_calendar(
    engine: Engine,
    benchmark: str = "SPY",
) -> list[date]:
    """Return the distinct trade dates observed for ``benchmark``.

    The benchmark is downloaded on every run alongside the universe, so its
    date index is a free, self-maintaining trading calendar -- no exchange
    calendar dependency, and it automatically matches whatever Yahoo actually
    returns (holidays, half days, and all).

    Returns:
        Sorted trade dates, empty when the benchmark has no rows yet.
    """
    statement = text(
        "SELECT DISTINCT trade_date FROM market_bars "
        "WHERE ticker = :benchmark ORDER BY trade_date"
    )
    with engine.connect() as connection:
        return [
            row[0]
            for row in connection.execute(statement, {"benchmark": benchmark})
        ]


def fetch_ticker_trade_dates(
    engine: Engine,
    tickers: list[str],
) -> dict[str, set[date]]:
    """Return the trade dates held for each of ``tickers``.

    Deliberately takes an explicit list rather than scanning the table: pulling
    every date for every ticker means ~1.65M rows, while the gap detector only
    ever flags a handful. Callers should narrow with ``find_gap_candidates``
    first, which needs nothing but the row counts already in coverage.

    Returns:
        ``{ticker: {date, ...}}``, omitting tickers with no rows.
    """
    if not tickers:
        return {}
    statement = text(
        "SELECT ticker, trade_date FROM market_bars WHERE ticker = ANY(:tickers)"
    )
    dates: dict[str, set[date]] = {}
    with engine.connect() as connection:
        for ticker, trade_date in connection.execute(
            statement, {"tickers": list(tickers)}
        ):
            dates.setdefault(ticker, set()).add(trade_date)
    return dates


def fetch_latest_market_trade_date(engine:Engine)->date|None:
    """Return the most recent trade date in ``market_bars``, or None if empty."""
    metadata = MetaData()
    table = Table('market_bars', metadata, autoload_with=engine)
    statement = select(func.max(table.c.trade_date))
    with engine.connect() as conn:
        result = conn.execute(statement).scalar_one_or_none()
    return result


def fetch_market_breadth(engine: Engine) -> dict | None:
    """最新交易日上涨/下跌家数与市场宽度（上涨家数占比）。

    对每只 ticker 取最近两个交易日的收盘价比较；只有最新一天没有
    前一交易日的 ticker 不参与统计。
    """
    statement = text(
        """
        WITH ranked AS (
            SELECT ticker, trade_date, close,
                   ROW_NUMBER() OVER (
                       PARTITION BY ticker ORDER BY trade_date DESC
                   ) AS rn
            FROM market_bars
        ),
        cur AS (SELECT ticker, close FROM ranked WHERE rn = 1),
        prev AS (SELECT ticker, close FROM ranked WHERE rn = 2)
        SELECT
            (SELECT MAX(trade_date) FROM ranked WHERE rn = 1) AS latest_date,
            COUNT(*) FILTER (WHERE cur.close > prev.close) AS advancers,
            COUNT(*) FILTER (WHERE cur.close < prev.close) AS decliners,
            COUNT(*) AS total
        FROM cur JOIN prev USING (ticker)
        """
    )
    with engine.connect() as connection:
        row = connection.execute(statement).mappings().first()
    if row is None or not row["total"]:
        return None
    total = int(row["total"])
    advancers = int(row["advancers"] or 0)
    decliners = int(row["decliners"] or 0)
    return {
        "latest_date": row["latest_date"],
        "advancers": advancers,
        "decliners": decliners,
        "total": total,
        "breadth": round(advancers / total, 4) if total else 0.0,
    }

def switch_to_week(df: pd.DataFrame):
    """Downsample long bars to weekly by keeping each ticker's last close.

    Buckets on weeks ending Friday and takes the last observation present, so
    a holiday-shortened week resolves to its actual last trading day rather
    than being dropped.
    """
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
    """Downsample long bars to monthly by keeping each ticker's last close."""
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
