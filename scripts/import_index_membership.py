"""One-off: seed ``index_membership`` from the fja05680/sp500 snapshot, then reconcile.

The daily wiki diff can only track changes from the day it starts running. This
script establishes the baseline it diffs against, in two steps:

  1. Import ``sp500_ticker_start_end.csv`` -- history back to the 1990s, already
     cross-checked by that repo's maintainer, which is more trustworthy than
     anything we could reconstruct from Wikipedia's changes table.
  2. Reconcile the imported "today" slice against a live wiki scrape and report
     the difference, because that snapshot lags: it is refreshed by hand every
     few weeks, so the tail is always stale.

Reconciliation reports by default and only writes under ``--apply``. The gap is
the one place where a bad decision is unrecoverable-by-inspection: everything
after it inherits the baseline, and a wrong exit date there quietly biases every
backtest without ever looking like an error.

Refresh the snapshot before running::

    git -C ../sp500 pull

Then::

    python scripts/import_index_membership.py                 # import + report
    python scripts/import_index_membership.py --apply         # also write the gap
"""

import argparse
import os
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from quantmine.storage.database import get_pipeline_engine
from quantmine.storage.membership import (
    DEFAULT_INDEX,
    fetch_members_on,
    upsert_spells,
)
from quantmine.universe import canonical_ticker, fetch_wiki_members
from quantmine.workflows.universe import refresh_universe

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CSV = PROJECT_ROOT.parent / "sp500" / "sp500_ticker_start_end.csv"


def load_csv(path: Path) -> pd.DataFrame:
    """Read the membership snapshot, validating its columns."""
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


def snapshot_date_of(path: Path) -> date:
    """Date the snapshot last asserted its open spells were still members.

    Uses the file's last git commit date, which is the only honest answer: the
    newest ``start_date`` in the CSV lags it (nothing joined that week) and
    today's date overstates it. This date becomes ``last_seen``, and therefore
    the ``end_date`` of any spell the reconciliation later closes.

    Returns:
        The commit date, falling back to the file's mtime outside a git repo.
    """
    try:
        stamp = subprocess.run(
            ["git", "-C", str(path.parent), "log", "-1", "--format=%cs", "--", path.name],
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        ).stdout.strip()
        if stamp:
            return date.fromisoformat(stamp)
    except (subprocess.SubprocessError, OSError, ValueError):
        pass
    return datetime.fromtimestamp(path.stat().st_mtime).date()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seed index_membership and reconcile it against Wikipedia",
    )
    parser.add_argument(
        "--csv",
        type=Path,
        default=Path(os.environ.get("SP500_MEMBERSHIP_CSV", DEFAULT_CSV)),
    )
    parser.add_argument("--index", default=DEFAULT_INDEX)
    parser.add_argument(
        "--as-of",
        default=pd.Timestamp.today().strftime("%Y-%m-%d"),
        help="Date the reconciliation describes; defaults to today",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write the reconciliation gap; without it, only report",
    )
    parser.add_argument(
        "--skip-import",
        action="store_true",
        help="Reconcile only, leaving the existing rows untouched",
    )
    parser.add_argument(
        "--snapshot-date",
        help="Override the date the snapshot's open spells were last confirmed; "
             "defaults to the CSV's last git commit date",
    )
    args = parser.parse_args()

    engine = get_pipeline_engine()
    as_of = pd.Timestamp(args.as_of).date()

    if not args.skip_import:
        csv_path = args.csv.expanduser()
        table = load_csv(csv_path)
        snapshot_date = (
            date.fromisoformat(args.snapshot_date)
            if args.snapshot_date
            else snapshot_date_of(csv_path)
        )
        written = upsert_spells(
            engine,
            table,
            index_name=args.index,
            source=f"fja05680/sp500:{csv_path.name}",
            snapshot_date=snapshot_date,
        )
        print(
            f"Imported {written} spells from {csv_path} "
            f"(snapshot last confirmed {snapshot_date})"
        )

    in_db = fetch_members_on(engine, as_of, args.index)
    on_wiki = {canonical_ticker(t) for t in fetch_wiki_members()}
    print(f"\nAs of {as_of}: {len(in_db)} members in the database, "
          f"{len(on_wiki)} on Wikipedia")

    only_wiki = sorted(on_wiki - in_db)
    only_db = sorted(in_db - on_wiki)
    if only_wiki:
        print(f"\nOn Wikipedia, missing from the database ({len(only_wiki)}) "
              "-- additions the snapshot has not caught up to:")
        print("  " + ", ".join(only_wiki))
    if only_db:
        print(f"\nIn the database, gone from Wikipedia ({len(only_db)}) "
              "-- removals the snapshot has not caught up to:")
        print("  " + ", ".join(only_db))
    if not only_wiki and not only_db:
        print("\nBaseline already matches Wikipedia; nothing to reconcile.")
        return

    if not args.apply:
        print(
            "\nReview the lists above, then re-run with --apply to write them. "
            "Additions get start_date = --as-of and removals get end_date = "
            "their last confirmed day, so pick an --as-of you can defend."
        )
        return

    # grace_scrapes=1 closes absences immediately: the snapshot's staleness is
    # known, not a suspected scrape failure, so the usual wait buys nothing.
    # max_change=None because catching up on months of drift legitimately
    # exceeds any single-day threshold -- the review above is the gate instead.
    diff, counts = refresh_universe(
        engine,
        as_of,
        index_name=args.index,
        grace_scrapes=1,
        max_change=None,
        source="wikipedia:reconcile",
        members=on_wiki,
    )
    print(
        f"\nReconciled: {counts['opened']} opened, {counts['closed']} closed, "
        f"{counts['confirmed']} confirmed"
    )
    if diff.closed:
        print(
            "Exit dates written: "
            + ", ".join(f"{t}={end}" for t, _, end in diff.closed)
        )


if __name__ == "__main__":
    main()
