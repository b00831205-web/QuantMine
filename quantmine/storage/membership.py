"""PostgreSQL persistence for point-in-time index membership.

Pure IO: the decision of what to write lives in ``quantmine.universe``. Every
write funnels tickers through ``canonical_ticker`` so the table stays in the
yfinance convention that ``market_bars`` uses.
"""

from datetime import date
from pathlib import Path

import pandas as pd
from sqlalchemy import MetaData, Table, and_, func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import Engine

from ..universe import canonical_ticker

DEFAULT_INDEX = "SP500"

# Vendored point-in-time baseline. Wikipedia publishes only today's
# constituents, so without this a fresh install starts every spell at "today",
# the downloader asks for one lookback window of history, and every window the
# research config trains on comes back empty. See the adjacent .LICENSE for
# provenance.
BASELINE_CSV = Path(__file__).with_name("sp500_ticker_start_end.csv")
# The date the snapshot last asserted its open spells were still members; it
# becomes their ``last_seen``. Read from the upstream file's git history, which
# vendoring discards -- so this constant must be updated whenever the CSV is
# refreshed, or newly-closed spells get an end_date from the wrong week.
BASELINE_SNAPSHOT_DATE = date(2026, 6, 8)


def _table(engine: Engine) -> Table:
    return Table("index_membership", MetaData(), autoload_with=engine)


def fetch_open_spells(
    engine: Engine,
    index_name: str = DEFAULT_INDEX,
) -> list[dict]:
    """Return the still-open membership spells, newest start first.

    Returns:
        Dicts with ``ticker``, ``start_date``, ``last_seen``, and
        ``missing_scrapes`` -- exactly the shape ``diff_universe`` consumes.
    """
    table = _table(engine)
    statement = (
        select(
            table.c.ticker,
            table.c.start_date,
            table.c.last_seen,
            table.c.missing_scrapes,
        )
        .where(table.c.index_name == index_name, table.c.end_date.is_(None))
        .order_by(table.c.start_date.desc(), table.c.ticker)
    )
    with engine.connect() as connection:
        return [dict(row) for row in connection.execute(statement).mappings()]


def fetch_membership(
    engine: Engine,
    index_name: str = DEFAULT_INDEX,
) -> pd.DataFrame:
    """Return every membership spell as a ``MembershipTableSource`` table.

    Returns:
        Columns ``ticker``, ``start_date``, ``end_date``. Empty with those
        columns when the index has no rows, so callers can construct a source
        without special-casing a fresh database.
    """
    table = _table(engine)
    statement = (
        select(table.c.ticker, table.c.start_date, table.c.end_date)
        .where(table.c.index_name == index_name)
        .order_by(table.c.ticker, table.c.start_date)
    )
    with engine.connect() as connection:
        rows = connection.execute(statement).mappings().all()
    return pd.DataFrame(rows, columns=["ticker", "start_date", "end_date"])


def fetch_members_on(
    engine: Engine,
    as_of: date,
    index_name: str = DEFAULT_INDEX,
) -> set[str]:
    """Return the tickers whose spell covers ``as_of``, both bounds inclusive."""
    table = _table(engine)
    statement = select(table.c.ticker).where(
        table.c.index_name == index_name,
        table.c.start_date <= as_of,
        or_(table.c.end_date.is_(None), table.c.end_date >= as_of),
    )
    with engine.connect() as connection:
        return {row[0] for row in connection.execute(statement)}


def load_baseline(path: Path = BASELINE_CSV) -> pd.DataFrame:
    """Read the vendored membership snapshot, validating its columns.

    Args:
        path: CSV to read; defaults to the vendored baseline.

    Returns:
        Columns ``ticker``, ``start_date``, ``end_date``, the dates parsed.

    Raises:
        ValueError: If a column is missing or a ``start_date`` will not parse.
            A spell with no start is not a spell, and silently dropping it
            would quietly shrink the historical universe.
    """
    table = pd.read_csv(path)
    missing = {"ticker", "start_date", "end_date"}.difference(table.columns)
    if missing:
        raise ValueError(f"{path} is missing columns: {sorted(missing)}")
    table["start_date"] = pd.to_datetime(table["start_date"], errors="coerce")
    table["end_date"] = pd.to_datetime(table["end_date"], errors="coerce")
    unparsed = table["start_date"].isna()
    if unparsed.any():
        raise ValueError(
            f"{path} has {unparsed.sum()} rows with an unparseable start_date"
        )
    return table


def seed_baseline(
    engine: Engine,
    *,
    index_name: str = DEFAULT_INDEX,
    path: Path = BASELINE_CSV,
    snapshot_date: date = BASELINE_SNAPSHOT_DATE,
) -> int:
    """Load the vendored point-in-time baseline into an empty membership table.

    Returns:
        The number of spells written.
    """
    return upsert_spells(
        engine,
        load_baseline(path),
        index_name=index_name,
        source=f"fja05680/sp500:{path.name}",
        snapshot_date=snapshot_date,
    )


def upsert_spells(
    engine: Engine,
    spells: pd.DataFrame,
    *,
    index_name: str = DEFAULT_INDEX,
    source: str,
    snapshot_date: date,
) -> int:
    """Bulk-load membership spells, used by the CSV/repo importer.

    Args:
        spells: Rows with ``ticker``, ``start_date``, and optional ``end_date``.
        index_name: Index these spells belong to.
        source: Provenance string recorded on every row.
        snapshot_date: The date the snapshot asserts its open spells were still
            members on -- normally the upstream repo's last commit date, not
            today.

    Returns:
        The number of rows written.

    Notes:
        ``last_seen`` is set to ``snapshot_date`` on open spells and left NULL
        on closed ones. This is load-bearing, not bookkeeping: when the wiki
        reconciliation later closes one of these spells it writes
        ``end_date = last_seen``, so a NULL here would fall back to
        ``start_date`` and retroactively end a decades-long membership on its
        first day.

        Conflicting rows have their ``end_date`` overwritten, which is what
        re-importing a refreshed upstream snapshot should do: learning about
        exits recorded since last time is the whole point. ``missing_scrapes``
        is left alone -- an import observes history, not today's list.
    """
    if spells.empty:
        return 0

    rows = []
    for record in spells.to_dict(orient="records"):
        end_date = record.get("end_date")
        is_open = end_date is None or pd.isna(end_date)
        rows.append(
            {
                "index_name": index_name,
                "ticker": canonical_ticker(record["ticker"]),
                "start_date": pd.Timestamp(record["start_date"]).date(),
                "end_date": None if is_open else pd.Timestamp(end_date).date(),
                "last_seen": snapshot_date if is_open else None,
                "source": source,
            }
        )

    table = _table(engine)
    statement = pg_insert(table).values(rows)
    statement = statement.on_conflict_do_update(
        index_elements=["index_name", "ticker", "start_date"],
        set_={
            "end_date": statement.excluded.end_date,
            # GREATEST keeps a live scrape's newer observation from being
            # rewound by re-importing an older snapshot.
            "last_seen": func.greatest(
                func.coalesce(table.c.last_seen, statement.excluded.last_seen),
                statement.excluded.last_seen,
            ),
            "source": statement.excluded.source,
            "updated_at": func.now(),
        },
    )
    with engine.begin() as connection:
        connection.execute(statement)
    return len(rows)


def apply_diff(
    engine: Engine,
    diff,
    as_of: date,
    *,
    index_name: str = DEFAULT_INDEX,
    source: str,
) -> dict[str, int]:
    """Persist one ``UniverseDiff`` atomically.

    Args:
        diff: The ``UniverseDiff`` produced for ``as_of``.
        as_of: Date the scrape describes.
        index_name: Index being updated.
        source: Provenance recorded on newly opened spells.

    Returns:
        Counts per kind: ``opened``, ``confirmed``, ``pending``, ``closed``.

    Notes:
        One transaction for the whole diff. A partial apply is the worst
        outcome here -- it would leave exits recorded without the matching
        additions, and the next run would diff against that skewed state and
        compound it.
    """
    table = _table(engine)
    counts = {
        "opened": len(diff.opened),
        "confirmed": len(diff.confirmed),
        "pending": len(diff.pending),
        "closed": len(diff.closed),
    }

    with engine.begin() as connection:
        if diff.opened:
            insert = pg_insert(table).values(
                [
                    {
                        "index_name": index_name,
                        "ticker": ticker,
                        "start_date": as_of,
                        "end_date": None,
                        "last_seen": as_of,
                        "missing_scrapes": 0,
                        "source": source,
                    }
                    for ticker in diff.opened
                ]
            )
            # A ticker can reappear on a date it already has a spell for when a
            # run is replayed; re-confirming is the right no-op there.
            connection.execute(
                insert.on_conflict_do_update(
                    index_elements=["index_name", "ticker", "start_date"],
                    set_={
                        "last_seen": as_of,
                        "missing_scrapes": 0,
                        "updated_at": func.now(),
                    },
                )
            )

        if diff.confirmed:
            connection.execute(
                table.update()
                .where(
                    table.c.index_name == index_name,
                    table.c.end_date.is_(None),
                    table.c.ticker.in_(diff.confirmed),
                )
                .values(last_seen=as_of, missing_scrapes=0, updated_at=func.now())
            )

        if diff.pending:
            connection.execute(
                table.update()
                .where(
                    table.c.index_name == index_name,
                    table.c.end_date.is_(None),
                    table.c.ticker.in_(diff.pending),
                )
                .values(
                    missing_scrapes=table.c.missing_scrapes + 1,
                    updated_at=func.now(),
                )
            )

        for ticker, start_date, end_date in diff.closed:
            connection.execute(
                table.update()
                .where(
                    and_(
                        table.c.index_name == index_name,
                        table.c.ticker == ticker,
                        table.c.start_date == start_date,
                    )
                )
                .values(end_date=end_date, updated_at=func.now())
            )

    return counts
