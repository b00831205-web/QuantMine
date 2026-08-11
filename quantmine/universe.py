"""Index-membership maintenance: what the index held, and when it changed.

Two halves that deliberately do not know about each other. ``fetch_wiki_members``
goes to the network and returns today's constituent list, guarded by sanity
checks. ``diff_universe`` is pure: it takes the open membership spells, today's
observed list, and returns the writes to apply. Keeping the diff free of both
network and database makes the interesting logic -- grace periods, reopened
spells, exit dates -- testable without either.

Why a grace period at all: a ticker missing from one scrape is far more often a
scrape problem (Wikipedia edit in flight, table reshuffled, request throttled)
than a real index deletion. Closing a spell on first absence would silently
shrink the investable universe, and MembershipTableSource would then hide those
names from every backtest that runs afterwards.
"""
import os
from dataclasses import dataclass, field
from datetime import date
from io import StringIO
from urllib.request import Request, urlopen

import pandas as pd

WIKI_SP500_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"

# stdlib urllib rather than requests: this is one GET with one header, and
# requests is absent from webapi/.venv -- the only Linux venv with a Postgres
# driver, hence the only one that can run the membership import at all.
#
# Wikipedia answers 403 to urllib's default agent, which is also what pandas
# would send if handed the URL directly. Their policy asks for a descriptive
# string with a contact, so deployments should set QUANT_HTTP_USER_AGENT to one
# naming their own project.
DEFAULT_USER_AGENT = (
    "quantmine/0.1 (index-membership sync; "
    "https://github.com/fja05680/sp500 for the underlying data)"
)

# The index holds 500 companies (503 share classes as of 2026). A scrape that
# comes back far short of that parsed the wrong table or hit a partial page --
# it is never a real index event, so the daily job aborts instead of writing.
MIN_PLAUSIBLE_MEMBERS = 450
MAX_PLAUSIBLE_MEMBERS = 520

# S&P reshuffles a handful of names at a time; quarterly rebalances move well
# under ten. A larger single-day delta means the source changed shape, not that
# the index did.
MAX_PLAUSIBLE_DAILY_CHANGE = 15

DEFAULT_GRACE_SCRAPES = 3


class UniverseSanityError(RuntimeError):
    """A scraped constituent list failed its plausibility checks.

    Raised instead of returning a suspect list, so a bad scrape aborts the DAG
    step rather than propagating into the membership table.
    """


def canonical_ticker(ticker: str) -> str:
    """Normalize a ticker to the yfinance convention (``BRK.B`` -> ``BRK-B``).

    Every writer must funnel through this. Class-share names are the only ones
    affected, but they are exactly the ones that would otherwise read as a
    deletion plus an addition when a source changes punctuation.
    """
    return str(ticker).strip().upper().replace(".", "-")


def fetch_wiki_members(url: str = WIKI_SP500_URL, timeout: int = 30) -> set[str]:
    """Scrape the current index constituents from Wikipedia.

    Returns:
        Canonicalized tickers from the constituents table.

    Raises:
        urllib.error.URLError: If the page cannot be fetched.
        UniverseSanityError: If no table carries a recognizable symbol column,
            or the member count falls outside the plausible range.

    Notes:
        The symbol column is found by name rather than by table position:
        Wikipedia's page has several tables and their order is not stable
        across edits. The page is fetched explicitly rather than handed to
        ``read_html`` as a URL, because Wikipedia 403s the default agent that
        pandas would send.
    """
    request = Request(
        url,
        headers={
            "User-Agent": os.environ.get(
                "QUANT_HTTP_USER_AGENT", DEFAULT_USER_AGENT
            )
        },
    )
    with urlopen(request, timeout=timeout) as response:
        html = response.read().decode("utf-8")
    tables = pd.read_html(StringIO(html))
    for table in tables:
        columns = {str(c).strip().lower(): c for c in table.columns}
        symbol_col = columns.get("symbol") or columns.get("ticker")
        if symbol_col is None:
            continue
        members = {
            canonical_ticker(value)
            for value in table[symbol_col].dropna()
            if str(value).strip()
        }
        if len(members) >= MIN_PLAUSIBLE_MEMBERS:
            return _validated(members)
    raise UniverseSanityError(
        f"No constituents table found at {url}; the page layout likely changed"
    )


def _validated(members: set[str]) -> set[str]:
    if not MIN_PLAUSIBLE_MEMBERS <= len(members) <= MAX_PLAUSIBLE_MEMBERS:
        raise UniverseSanityError(
            f"Scraped {len(members)} members, outside the plausible range "
            f"[{MIN_PLAUSIBLE_MEMBERS}, {MAX_PLAUSIBLE_MEMBERS}]"
        )
    return members


@dataclass
class UniverseDiff:
    """The writes one scrape implies, split by kind so callers can log them.

    Args:
        opened: Tickers starting a new membership spell today.
        confirmed: Tickers still present; only their ``last_seen`` advances.
        pending: Tickers absent but still inside the grace period. No write
            beyond the counter; they stay investable meanwhile.
        closed: Spells whose absence outlived the grace period, as
            ``(ticker, start_date, end_date)``.
    """

    opened: list[str] = field(default_factory=list)
    confirmed: list[str] = field(default_factory=list)
    pending: list[str] = field(default_factory=list)
    closed: list[tuple[str, date, date]] = field(default_factory=list)

    @property
    def change_count(self) -> int:
        """Real membership changes, excluding routine confirmations."""
        return len(self.opened) + len(self.closed)


def diff_universe(
    open_spells: list[dict],
    observed: set[str],
    as_of: date,
    *,
    grace_scrapes: int = DEFAULT_GRACE_SCRAPES,
    max_change: int | None = MAX_PLAUSIBLE_DAILY_CHANGE,
) -> UniverseDiff:
    """Compare today's constituent list against the open membership spells.

    Args:
        open_spells: Rows with ``end_date IS NULL``, each carrying ``ticker``,
            ``start_date``, ``last_seen``, and ``missing_scrapes``.
        observed: Canonicalized tickers scraped for ``as_of``.
        as_of: The date this scrape describes.
        grace_scrapes: Consecutive absences tolerated before a spell is closed.
        max_change: Abort above this many real changes in one scrape; pass None
            to disable, which the one-off gap backfill does because catching up
            on months of drift legitimately moves far more than a day's worth.

    Returns:
        The writes to apply, grouped by kind.

    Raises:
        UniverseSanityError: If the implied change count exceeds ``max_change``.

    Notes:
        A closed spell's ``end_date`` is its ``last_seen``, so the exit date is
        the last day membership was actually confirmed rather than the day the
        grace period happened to expire. Understating membership this way is the
        safe direction: the backtest skips a few days it could have traded,
        rather than holding a name the index no longer contained.
    """
    diff = UniverseDiff()
    open_tickers = set()

    for spell in open_spells:
        ticker = canonical_ticker(spell["ticker"])
        open_tickers.add(ticker)
        if ticker in observed:
            diff.confirmed.append(ticker)
            continue
        # +1 counts this scrape, which has not been persisted yet.
        absences = int(spell.get("missing_scrapes") or 0) + 1
        if absences >= grace_scrapes:
            last_seen = spell.get("last_seen")
            if last_seen is None:
                # Refusing to guess: falling back to start_date would end a
                # decades-long membership on its first day, and nothing
                # downstream would flag the result as wrong. Every writer sets
                # last_seen, so a NULL means a hand-edited row.
                raise UniverseSanityError(
                    f"{ticker} (spell from {spell['start_date']}) has no "
                    "last_seen, so its exit date cannot be determined. Set "
                    "last_seen to the last date it was confirmed in the index."
                )
            diff.closed.append((ticker, spell["start_date"], last_seen))
        else:
            diff.pending.append(ticker)

    diff.opened = sorted(observed - open_tickers)
    diff.confirmed.sort()
    diff.pending.sort()
    diff.closed.sort()

    # An empty table is initial seeding, not a one-day rebalance. Applying the
    # daily-change guard there makes every fresh deployment impossible to
    # bootstrap because all ~503 constituents necessarily look newly added.
    # Once any open baseline exists, keep the guard fully enforced.
    if open_spells and max_change is not None and diff.change_count > max_change:
        raise UniverseSanityError(
            f"{as_of} implies {diff.change_count} membership changes "
            f"({len(diff.opened)} added, {len(diff.closed)} removed), above the "
            f"{max_change} threshold; refusing to write. Re-run with "
            "--max-change to override once the diff has been reviewed."
        )
    return diff
