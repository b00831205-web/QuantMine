"""DAG step 0: refresh the point-in-time index membership table.

Runs ahead of the download step so ``task_1`` picks up additions the same day.
A failed or implausible scrape aborts this step; the membership table keeps its
previous state and the download proceeds on yesterday's universe, which is the
safe direction to be wrong in.
"""

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from quantmine.storage.database import get_pipeline_engine
from quantmine.universe import (
    DEFAULT_GRACE_SCRAPES,
    MAX_PLAUSIBLE_DAILY_CHANGE,
)
from quantmine.workflows.universe import refresh_universe


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Refresh point-in-time index membership from Wikipedia",
    )
    parser.add_argument("--date", required=True)
    parser.add_argument("--batch", required=True)
    parser.add_argument("--index", default="SP500")
    parser.add_argument(
        "--grace-scrapes",
        type=int,
        default=DEFAULT_GRACE_SCRAPES,
        help="Consecutive absences tolerated before a ticker's spell is closed",
    )
    parser.add_argument(
        "--max-change",
        type=int,
        default=MAX_PLAUSIBLE_DAILY_CHANGE,
        help="Abort above this many membership changes in one run",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report the diff without writing it",
    )
    args = parser.parse_args()

    as_of = pd.Timestamp(args.date).date()
    diff, counts = refresh_universe(
        get_pipeline_engine(),
        as_of,
        index_name=args.index,
        grace_scrapes=args.grace_scrapes,
        max_change=args.max_change,
        dry_run=args.dry_run,
    )

    if diff.opened:
        print(f"[{args.batch}] added: {', '.join(diff.opened)}")
    if diff.closed:
        print(
            f"[{args.batch}] removed: "
            + ", ".join(f"{t} (through {end})" for t, _, end in diff.closed)
        )
    if diff.pending:
        print(
            f"[{args.batch}] absent but within grace, still investable: "
            f"{', '.join(diff.pending)}"
        )
    mode = "dry run, nothing written" if args.dry_run else "written"
    print(
        f"[{args.batch}] {args.index} membership {mode}: "
        f"{counts['opened']} opened, {counts['closed']} closed, "
        f"{counts['confirmed']} confirmed, {counts['pending']} pending"
    )


if __name__ == "__main__":
    main()
