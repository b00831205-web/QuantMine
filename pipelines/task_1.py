"""Download the market-data increment required by the daily pipeline."""

import argparse
import json
import os
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from quantmine.data_acquisition import data_acquisition
from quantmine.download_plan import (
    DEFAULT_LOOKBACK_DAYS,
    build_download_plan,
    build_gap_jobs,
    contiguous_gaps,
    find_gap_candidates,
    gap_key,
    summarize,
)
from quantmine.storage.database import get_engine
from quantmine.storage.market import (
    fetch_ticker_coverage,
    fetch_ticker_trade_dates,
    fetch_trading_calendar,
)
from quantmine.storage.membership import fetch_membership


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ANALYSIS_START = pd.Timestamp("2015-01-01")
# Ledger of tickers that returned nothing, so the ~195 historical members with
# no recoverable Yahoo history are not re-requested on every single run.
ATTEMPTS_FILE = "download_attempts.json"


def load_membership(membership_path: Path | None = None) -> pd.DataFrame:
    """Return the membership table, preferring the database over the CSV.

    ``index_membership`` is the maintained source: ``task_0_universe`` refreshes
    it daily, so it knows about index changes the CSV snapshot has not caught up
    to. The CSV is kept as a fallback for a database that was never seeded --
    see ``scripts/import_index_membership.py``.

    Args:
        membership_path: CSV to fall back to. When None, an unseeded database
            is an error rather than a silent fallback.

    Returns:
        Columns ``ticker``, ``start_date``, ``end_date``.
    """
    try:
        membership = fetch_membership(get_engine())
    except Exception as error:  # unreachable DB, missing table
        if membership_path is None:
            raise
        print(f"index_membership unavailable ({error}); falling back to CSV")
        membership = pd.DataFrame()

    if not membership.empty:
        return membership

    if membership_path is None:
        raise RuntimeError(
            "index_membership is empty and no CSV fallback was given. Seed it "
            "with scripts/import_index_membership.py"
        )
    print(f"index_membership is empty; falling back to {membership_path}")
    return pd.read_csv(membership_path)


def load_relevant_tickers(
    membership: pd.DataFrame,
    *,
    start_date: pd.Timestamp,
    end_date: pd.Timestamp,
) -> list[str]:
    """Select members whose membership overlaps the requested date window.

    Names whose spell ended before ``start_date`` are dropped, which is what
    keeps delisted tickers from being requested forever: their absence from the
    download is decided by the membership table, not by whether Yahoo returned
    data. Yahoo returns an empty column for a rate-limited live ticker too, so
    inferring delisting from missing data would shrink the universe on every
    run.
    """
    required = {"ticker", "start_date", "end_date"}
    missing = required.difference(membership.columns)
    if missing:
        raise ValueError(
            f"Membership table is missing columns: {sorted(missing)}"
        )

    membership = membership.copy()
    membership["start_date"] = pd.to_datetime(
        membership["start_date"],
        errors="coerce",
    )
    membership["end_date"] = pd.to_datetime(
        membership["end_date"],
        errors="coerce",
    )
    overlaps_window = (
        membership["start_date"].fillna(pd.Timestamp.min) <= end_date
    ) & (
        membership["end_date"].isna()
        | (membership["end_date"] >= start_date)
    )
    tickers = {
        str(ticker).replace(".", "-")
        for ticker in membership.loc[overlaps_window, "ticker"].dropna()
    }
    tickers.add("SPY")
    return sorted(tickers)


COVERAGE_COLUMNS = ["ticker", "first_date", "last_date", "observations"]


def coverage_from_parquet(processed_dir: Path) -> pd.DataFrame:
    """Derive per-ticker coverage from the cleaned close parquet.

    Used only when the database is unreachable. Reporting "no coverage" in that
    case would be far worse than useless: the planner would conclude nothing has
    ever been downloaded and queue an eleven-year full history for all 500
    tickers. The processed frame is date-by-ticker, so each column's first and
    last valid index carry the same information at the same granularity.
    """
    close_path = processed_dir / "processed_close.parquet"
    if not close_path.exists():
        return pd.DataFrame(columns=COVERAGE_COLUMNS)

    close = pd.read_parquet(close_path)
    rows = []
    for ticker in close.columns:
        column = close[ticker]
        first, last = column.first_valid_index(), column.last_valid_index()
        if first is None or last is None:
            continue
        rows.append(
            {
                "ticker": str(ticker),
                "first_date": pd.Timestamp(first),
                "last_date": pd.Timestamp(last),
                "observations": int(column.notna().sum()),
            }
        )
    return pd.DataFrame(rows, columns=COVERAGE_COLUMNS)


def plan_gap_jobs(
    coverage: pd.DataFrame,
    *,
    as_of: pd.Timestamp,
    attempts: dict,
    max_candidates: int,
) -> list:
    """Find interior holes in per-ticker history and turn them into jobs.

    Runs entirely off the database; returns nothing when it is unreachable,
    because gap repair is catch-up work and must never block the daily
    increment. Two phases: a count-based sweep that needs no dates, then a
    per-date query for the few tickers it flags.
    """
    try:
        engine = get_engine()
        calendar = fetch_trading_calendar(engine)
        if not calendar:
            print("no benchmark calendar yet; skipping gap detection")
            return []
        candidates = find_gap_candidates(coverage, calendar)[:max_candidates]
        if not candidates:
            return []
        observed = fetch_ticker_trade_dates(engine, candidates)
    except Exception as error:  # unreachable DB, missing table
        print(f"gap detection unavailable ({error})")
        return []

    bounds = coverage.set_index("ticker")
    gaps = {}
    for ticker in candidates:
        windows = contiguous_gaps(
            observed.get(ticker, set()),
            calendar,
            pd.Timestamp(bounds.loc[ticker, "first_date"]),
            pd.Timestamp(bounds.loc[ticker, "last_date"]),
        )
        if windows:
            gaps[ticker] = windows
    return build_gap_jobs(gaps, as_of=as_of, attempts=attempts)


def load_coverage(processed_dir: Path) -> pd.DataFrame:
    """Return per-ticker coverage, preferring the database."""
    try:
        coverage = fetch_ticker_coverage(get_engine())
    except Exception as error:  # unreachable DB, missing table
        print(f"market_bars coverage unavailable ({error}); reading parquet")
        return coverage_from_parquet(processed_dir)
    if coverage.empty:
        # A fresh database with parquet history already on disk: trust the
        # files rather than re-downloading everything.
        return coverage_from_parquet(processed_dir)
    return coverage


def load_attempts(processed_dir: Path) -> dict:
    """Read the download-attempt ledger, tolerating a missing or corrupt file."""
    path = processed_dir / ATTEMPTS_FILE
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        # A damaged ledger should cost some redundant requests, not the run.
        return {}


def record_attempts(
    processed_dir: Path,
    attempts: dict,
    *,
    job,
    returned: set[str],
    as_of: pd.Timestamp,
) -> dict:
    """Update the ledger after a job: reset on data, increment on nothing.

    Args:
        attempts: The ledger being updated, modified in place and returned.
        job: The ``DownloadJob`` that just ran.
        returned: Tickers that actually came back with at least one value.
        as_of: Date of this attempt.

    Notes:
        Gap jobs are keyed per window, not per ticker. A live ticker with one
        unfillable hole in 2019 must not accumulate whole-ticker failures --
        that would eventually rest it and stop its daily increment. Success
        clears the counter outright rather than decrementing, so a name that
        recovers is immediately a first-class citizen again.
    """
    stamp = as_of.strftime("%Y-%m-%d")
    is_gap = job.reason == "fill gap"
    for ticker in job.tickers:
        key = gap_key(ticker, job.start, job.end) if is_gap else ticker
        if ticker in returned:
            attempts.pop(key, None)
            continue
        record = attempts.get(key, {"attempts": 0})
        record["attempts"] = int(record.get("attempts", 0)) + 1
        record["last_attempt"] = stamp
        attempts[key] = record
    (processed_dir / ATTEMPTS_FILE).write_text(
        json.dumps(attempts, indent=2, sort_keys=True), encoding="utf-8"
    )
    return attempts


def run_job(job, *, index: int, processed_dir: Path) -> set[str]:
    """Download one window and write it to its own staging files.

    Args:
        job: The ``DownloadJob`` to execute.
        index: 1-based job number, used in the staging filenames.
        processed_dir: Directory the staging parquet files go into.

    Returns:
        The tickers that actually came back with at least one close.

    Notes:
        One file set per job, rather than one combined frame, because jobs
        cover different date ranges. Concatenating a 10-year backfill with a
        1-day increment produces a frame indexed over 10 years in which the
        incremental tickers are ~100% NaN -- and ``task_2`` drops any column
        above its missing-data threshold, so the entire daily universe would be
        thrown away. Scoring each job against its own date range keeps that
        check meaningful.
    """
    # yfinance treats ``end`` as exclusive, so request one day beyond the job.
    exclusive_end = job.end + pd.Timedelta(days=1)
    close, volume, shares, market_cap = data_acquisition(
        tickers=list(job.tickers),
        start_date=job.start.strftime("%Y-%m-%d"),
        end_date=exclusive_end.strftime("%Y-%m-%d"),
        shares_start_date=job.start.strftime("%Y-%m-%d"),
        batch_size=20,  # 小批次 + 串行下载, 降低触发Yahoo限流的概率
    )
    for frame, name in (
        (close, "close"),
        (volume, "volume"),
        (shares, "shares"),
        (market_cap, "market_cap"),
    ):
        if frame is not None and not frame.empty:
            frame.to_parquet(processed_dir / f"{name}.part{index:02d}.parquet")

    if close is None or close.empty:
        return set()
    return {str(t) for t in close.columns[close.notna().any()]}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download the next raw market-data increment",
    )
    parser.add_argument("--date", required=True)
    parser.add_argument("--batch", required=True)
    parser.add_argument(
        "--lookback-days",
        type=int,
        default=DEFAULT_LOOKBACK_DAYS,
        help="Pre-membership history fetched alongside a backfill",
    )
    parser.add_argument(
        "--max-jobs",
        type=int,
        default=12,
        help="Cap on download jobs per run; the rest wait for the next run so "
             "one catch-up cannot stall the daily pipeline for hours",
    )
    parser.add_argument(
        "--max-gap-candidates",
        type=int,
        default=25,
        help="Tickers to inspect per run for interior gaps",
    )
    parser.add_argument(
        "--skip-gaps",
        action="store_true",
        help="Skip interior-gap detection entirely",
    )
    args = parser.parse_args()

    processed_dir = PROJECT_ROOT / "data" / "processed"
    processed_dir.mkdir(parents=True, exist_ok=True)
    requested_date = pd.Timestamp(args.date).normalize()

    default_membership_path = (
        PROJECT_ROOT.parent / "sp500" / "sp500_ticker_start_end.csv"
    )
    membership_path = Path(
        os.environ.get("SP500_MEMBERSHIP_CSV", default_membership_path)
    ).expanduser()

    attempts = load_attempts(processed_dir)
    coverage = load_coverage(processed_dir)
    jobs = build_download_plan(
        load_membership(membership_path if membership_path.exists() else None),
        coverage,
        as_of=requested_date,
        analysis_start=ANALYSIS_START,
        lookback_days=args.lookback_days,
        attempts=attempts,
    )
    if not args.skip_gaps:
        # Appended, not merged into the sort: gap repair is the lowest-value
        # work here, and the plan is truncated from the end.
        jobs += plan_gap_jobs(
            coverage,
            as_of=requested_date,
            attempts=attempts,
            max_candidates=args.max_gap_candidates,
        )
    if not jobs:
        print(f"{args.batch} is current; no market-data download is needed")
        return

    print(f"[{args.batch}] download plan ({len(jobs)} jobs):")
    print(summarize(jobs))
    if len(jobs) > args.max_jobs:
        # Safe to truncate only because the plan is priority-sorted: the daily
        # increment is job 1, so a backlog of historical backfills can never
        # crowd out today's prices.
        print(
            f"[{args.batch}] running the first {args.max_jobs}; "
            f"{len(jobs) - args.max_jobs} deferred to the next run"
        )
        jobs = jobs[: args.max_jobs]

    for index, job in enumerate(jobs, start=1):
        print(f"[{args.batch}] job {index}/{len(jobs)}: {job}")
        returned = run_job(job, index=index, processed_dir=processed_dir)
        missing = set(job.tickers) - returned
        if missing:
            print(f"[{args.batch}]   no data for {len(missing)}: "
                  f"{sorted(missing)[:10]}{' ...' if len(missing) > 10 else ''}")
        attempts = record_attempts(
            processed_dir, attempts,
            job=job, returned=returned, as_of=requested_date,
        )
    print(f"[{args.batch}] wrote staging files to {processed_dir}")


if __name__ == "__main__":
    main()
