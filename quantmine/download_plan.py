"""Decide what market data still needs downloading, per ticker.

The daily job used to work off one global watermark -- ``max(trade_date)`` over
the whole table -- and download that single window for everyone. That is only
correct while every ticker shares the same history. It stops being correct the
moment the universe changes:

* A name added to the index today has no rows at all, but the global watermark
  says the database is current through yesterday, so nothing reaches back for
  its past. Momentum and volatility need a lookback window, so that name's
  factors stay NaN -- and "recently added to the index" is a systematic
  category, not a random one, which quietly biases any factor computed over it.
* A batch that failed leaves a hole in the middle of one ticker's history that
  no watermark can see.

So the planner asks, per ticker, what range it *should* have (its membership
spells, widened by a lookback buffer, clipped to the analysis window) and
subtracts what it already has. Tickers needing the same window are grouped into
one download job, which keeps the common case -- everyone at the same watermark
-- to a single request batch.

Everything here is pure: dates in, jobs out. No network, no database.
"""

from dataclasses import dataclass, field
from datetime import date

import pandas as pd

# ~280 trading days, comfortably covering a 252-day (12-month) momentum
# lookback plus slack for holidays. A ticker joining the index today needs this
# much prior history before its lookback factors produce anything.
DEFAULT_LOOKBACK_DAYS = 420

# Membership dates are calendar dates; bar dates are trading dates. A spell
# starting 2015-01-01 can only ever have its first bar on 2015-01-02, and the
# longest run of consecutive market closures is a holiday pressed against a
# weekend. Without this slack every ticker looks permanently short at the head
# and gets a backfill request on every single run.
CALENDAR_SLACK_DAYS = 7


# Priorities, low number first. The daily increment must outrank catch-up work:
# jobs get truncated when a run has more than it can do, and sorting by date
# alone puts the increment (latest start date) last, so a backlog of historical
# backfills would silently starve the pipeline of today's prices.
PRIORITY_INCREMENT = 0
PRIORITY_BACKFILL = 1

# A ticker that has never returned data after this many attempts is very likely
# gone from Yahoo for good -- most of the index's historical members were
# acquired or delisted and have no downloadable history. Without a ceiling they
# are re-requested on every run forever, burning the rate limit that the live
# universe needs.
DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_COOLDOWN_DAYS = 30


@dataclass(frozen=True)
class DownloadJob:
    """One contiguous window to request for a set of tickers."""

    start: pd.Timestamp
    end: pd.Timestamp
    tickers: tuple[str, ...]
    reason: str = ""
    priority: int = PRIORITY_BACKFILL

    def __str__(self) -> str:
        return (
            f"{self.start.date()}..{self.end.date()}  "
            f"{len(self.tickers):4d} tickers  ({self.reason})"
        )


@dataclass
class TickerTarget:
    """The window a ticker ought to have covered."""

    ticker: str
    required_start: pd.Timestamp  # ideal, includes the lookback buffer
    mandatory_start: pd.Timestamp  # days it was actually in the index
    end: pd.Timestamp


def _as_timestamp(value) -> pd.Timestamp | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    stamp = pd.Timestamp(value)
    return None if pd.isna(stamp) else stamp.normalize()


def build_targets(
    membership: pd.DataFrame,
    *,
    as_of: pd.Timestamp,
    analysis_start: pd.Timestamp,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    extra_tickers: tuple[str, ...] = ("SPY",),
) -> dict[str, TickerTarget]:
    """Collapse membership spells into one target window per ticker.

    Args:
        membership: Rows of ``ticker`` / ``start_date`` / ``end_date``.
        as_of: Latest date worth having.
        analysis_start: Earliest date the project cares about.
        lookback_days: Calendar days of pre-membership history to also fetch.
        extra_tickers: Always-wanted names outside the index, such as the
            benchmark, which doubles as the trading calendar.

    Returns:
        One target per ticker, keyed by ticker.

    Notes:
        Two starts, deliberately. ``mandatory_start`` is the first day the
        ticker was actually in the index; missing data before that is usually
        just history Yahoo does not have (the company had not listed), so
        chasing it would re-request the same unavailable range every single day.
        ``required_start`` reaches further back for the factor lookback and is
        used as the download start when a fetch is triggered -- best effort,
        never a trigger on its own.
    """
    membership = membership.copy()
    membership["ticker"] = membership["ticker"].astype(str).str.replace(
        ".", "-", regex=False
    )

    spans: dict[str, tuple[pd.Timestamp, pd.Timestamp]] = {}
    for record in membership.to_dict(orient="records"):
        ticker = record["ticker"]
        start = _as_timestamp(record.get("start_date")) or analysis_start
        end = _as_timestamp(record.get("end_date")) or as_of
        if ticker in spans:
            previous_start, previous_end = spans[ticker]
            spans[ticker] = (min(previous_start, start), max(previous_end, end))
        else:
            spans[ticker] = (start, end)

    for ticker in extra_tickers:
        spans[ticker] = (analysis_start, as_of)

    targets: dict[str, TickerTarget] = {}
    for ticker, (start, end) in spans.items():
        mandatory_start = max(analysis_start, start)
        required_start = max(
            analysis_start, start - pd.Timedelta(days=lookback_days)
        )
        capped_end = min(as_of, end)
        if mandatory_start > capped_end:
            # Spell ended before the analysis window opened; nothing to fetch,
            # and it must stay that way or delisted names get re-requested
            # forever.
            continue
        targets[ticker] = TickerTarget(
            ticker=ticker,
            required_start=required_start,
            mandatory_start=mandatory_start,
            end=capped_end,
        )
    return targets


def build_download_plan(
    membership: pd.DataFrame,
    coverage: pd.DataFrame,
    *,
    as_of: pd.Timestamp,
    analysis_start: pd.Timestamp,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    extra_tickers: tuple[str, ...] = ("SPY",),
    attempts: dict | None = None,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    cooldown_days: int = DEFAULT_COOLDOWN_DAYS,
) -> list[DownloadJob]:
    """Work out the download jobs that would bring every ticker up to date.

    Args:
        membership: Point-in-time index membership spells.
        coverage: Per-ticker ``first_date`` / ``last_date`` already stored,
            as returned by ``fetch_ticker_coverage``.
        as_of: The date being processed.
        analysis_start: Earliest date the project cares about.
        lookback_days: Pre-membership history to fetch alongside a backfill.
        extra_tickers: Always-wanted names outside the index.
        attempts: Ledger of ``{ticker: {"attempts": n, "last_attempt": date}}``
            for names that returned nothing, used to rest hopeless ones.
        max_attempts: Failures before a ticker is rested.
        cooldown_days: How long a rested ticker stays out of the plan.

    Returns:
        Jobs ordered by priority then date -- the daily increment first,
        catch-up work behind it -- with tickers needing identical windows merged
        into one job. Empty when everything is already covered.

    Notes:
        Head and tail are separate decisions. The tail (new days at the end) is
        the ordinary daily increment. The head only triggers when data is
        missing for days the ticker was genuinely in the index -- see
        ``build_targets`` for why the lookback buffer must not be a trigger.
    """
    targets = build_targets(
        membership,
        as_of=as_of,
        analysis_start=analysis_start,
        lookback_days=lookback_days,
        extra_tickers=extra_tickers,
    )

    have: dict[str, tuple[pd.Timestamp, pd.Timestamp]] = {}
    for record in coverage.to_dict(orient="records"):
        first = _as_timestamp(record.get("first_date"))
        last = _as_timestamp(record.get("last_date"))
        if first is not None and last is not None:
            have[str(record["ticker"])] = (first, last)

    exhausted = _exhausted_keys(
        attempts or {}, as_of, max_attempts, cooldown_days
    )

    grouped: dict[tuple[pd.Timestamp, pd.Timestamp, str, int], list[str]] = {}

    def add(start, end, ticker, reason, priority=PRIORITY_BACKFILL):
        if start > end:
            return
        grouped.setdefault((start, end, reason, priority), []).append(ticker)

    slack = pd.Timedelta(days=CALENDAR_SLACK_DAYS)
    for ticker, target in targets.items():
        if ticker not in have:
            if ticker in exhausted:
                # Tried repeatedly, never got a row. Almost certainly delisted
                # with no history on Yahoo; retried again only after cooldown.
                continue
            add(target.required_start, target.end, ticker, "new ticker")
            continue
        first, last = have[ticker]
        if first > target.mandatory_start + slack:
            # Reach back to required_start, not just mandatory_start: if we are
            # paying for a request anyway, take the lookback with it.
            add(target.required_start, first - pd.Timedelta(days=1),
                ticker, "backfill history")
        if last < target.end:
            # Closed spells get the same slack as the head. Their end_date is a
            # calendar date that may land on a weekend, and without slack the
            # planner would re-request that empty tail on every run, forever.
            # Open spells must not get it: end is today, and the one-or-two-day
            # difference *is* the daily increment.
            is_open = target.end >= as_of
            if is_open or last < target.end - slack:
                add(last + pd.Timedelta(days=1), target.end, ticker,
                    "increment", PRIORITY_INCREMENT)

    jobs = [
        DownloadJob(start=start, end=end, tickers=tuple(sorted(tickers)),
                    reason=reason, priority=priority)
        for (start, end, reason, priority), tickers in grouped.items()
    ]
    # Priority first, then date. Callers truncate this list, so the daily
    # increment has to sit at the front regardless of how much catch-up work
    # is queued behind it.
    jobs.sort(key=lambda job: (job.priority, job.start, job.end))
    return jobs


def find_gap_candidates(
    coverage: pd.DataFrame,
    calendar: list,
    *,
    min_missing: int = 2,
) -> list[str]:
    """Name the tickers whose history has holes, cheaply.

    Neither ``first_date`` nor ``last_date`` can reveal a hole in the middle --
    a batch that failed in 2019 leaves one ticker short while its bounds still
    look perfect. Counting fixes that: a ticker present on every trading day
    between its own bounds has exactly as many rows as the benchmark does over
    the same span, so any shortfall localizes to a ticker without reading a
    single date.

    Args:
        coverage: ``fetch_ticker_coverage`` output.
        calendar: Sorted trading dates, from ``fetch_trading_calendar``.
        min_missing: Ignore shortfalls smaller than this. One- or two-day holes
            are usually real -- a halt, or a day the name genuinely did not
            trade -- and chasing them re-requests an empty window forever.

    Returns:
        Tickers worth the follow-up per-date query, worst shortfall first.
    """
    if not calendar or coverage.empty:
        return []
    trading_days = pd.DatetimeIndex(pd.to_datetime(pd.Series(calendar)))

    shortfalls: list[tuple[int, str]] = []
    for record in coverage.to_dict(orient="records"):
        first = _as_timestamp(record.get("first_date"))
        last = _as_timestamp(record.get("last_date"))
        if first is None or last is None:
            continue
        expected = int(
            ((trading_days >= first) & (trading_days <= last)).sum()
        )
        missing = expected - int(record.get("observations", 0))
        if missing >= min_missing:
            shortfalls.append((missing, str(record["ticker"])))
    shortfalls.sort(reverse=True)
    return [ticker for _, ticker in shortfalls]


def contiguous_gaps(
    observed: set,
    calendar: list,
    first: pd.Timestamp,
    last: pd.Timestamp,
    *,
    min_gap: int = 2,
) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    """Collapse a ticker's missing trading days into contiguous windows.

    Args:
        observed: Trade dates the ticker already has.
        calendar: Sorted trading dates.
        first: Ticker's first observation; nothing before it is a gap.
        last: Ticker's last observation; nothing after it is a gap.
        min_gap: Minimum consecutive missing trading days to report.

    Returns:
        ``(start, end)`` windows, one per run of missing trading days.

    Notes:
        Bounded by the ticker's own first/last on purpose. Missing days outside
        that span are the head and tail, which the main planner already owns;
        reporting them here would queue the same window twice.
    """
    observed_norm = {pd.Timestamp(d).normalize() for d in observed}
    runs: list[tuple[pd.Timestamp, pd.Timestamp]] = []
    current: list[pd.Timestamp] = []

    for raw in calendar:
        day = pd.Timestamp(raw).normalize()
        if day < first or day > last:
            continue
        if day in observed_norm:
            if len(current) >= min_gap:
                runs.append((current[0], current[-1]))
            current = []
        else:
            current.append(day)
    if len(current) >= min_gap:
        runs.append((current[0], current[-1]))
    return runs


def build_gap_jobs(
    gaps: dict[str, list[tuple[pd.Timestamp, pd.Timestamp]]],
    *,
    as_of: pd.Timestamp,
    attempts: dict | None = None,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    cooldown_days: int = DEFAULT_COOLDOWN_DAYS,
) -> list[DownloadJob]:
    """Turn per-ticker gap windows into download jobs.

    Args:
        gaps: ``{ticker: [(start, end), ...]}`` from ``contiguous_gaps``.
        as_of: Date being processed, for the attempt ledger.
        attempts: Ledger keyed by ``gap_key`` as well as by ticker, so a hole
            Yahoo simply has no data for stops being re-requested.
        max_attempts: Failures before a gap is rested.
        cooldown_days: How long a rested gap stays out of the plan.

    Returns:
        Backfill-priority jobs, tickers sharing a window merged.
    """
    exhausted = _exhausted_keys(
        attempts or {}, as_of, max_attempts, cooldown_days
    )
    grouped: dict[tuple[pd.Timestamp, pd.Timestamp], list[str]] = {}
    for ticker, windows in gaps.items():
        for start, end in windows:
            if gap_key(ticker, start, end) in exhausted:
                continue
            grouped.setdefault((start, end), []).append(ticker)

    jobs = [
        DownloadJob(start=start, end=end, tickers=tuple(sorted(tickers)),
                    reason="fill gap", priority=PRIORITY_BACKFILL)
        for (start, end), tickers in grouped.items()
    ]
    jobs.sort(key=lambda job: (job.start, job.end))
    return jobs


def gap_key(ticker: str, start: pd.Timestamp, end: pd.Timestamp) -> str:
    """Ledger key for one gap window, distinct from the whole-ticker key."""
    return f"{ticker}|{pd.Timestamp(start).date()}|{pd.Timestamp(end).date()}"


def _exhausted_keys(
    attempts: dict,
    as_of: pd.Timestamp,
    max_attempts: int,
    cooldown_days: int,
) -> set[str]:
    """Tickers that have failed enough times to be worth resting.

    Not a permanent blacklist: after ``cooldown_days`` they are tried once more.
    Yahoo occasionally starts serving a name it previously refused, and a
    one-way blacklist would keep shrinking the recoverable universe -- the same
    trap ``data_acquisition`` avoids by never auto-blacklisting empty columns.
    """
    exhausted = set()
    for ticker, record in attempts.items():
        if int(record.get("attempts", 0)) < max_attempts:
            continue
        last = _as_timestamp(record.get("last_attempt"))
        if last is None or (as_of - last).days < cooldown_days:
            exhausted.add(ticker)
    return exhausted


def summarize(jobs: list[DownloadJob]) -> str:
    """One human-readable line per job, for the pipeline log."""
    if not jobs:
        return "  (nothing to download)"
    return "\n".join(f"  {job}" for job in jobs)
