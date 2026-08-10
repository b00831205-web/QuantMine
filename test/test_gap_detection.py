"""Unit tests for interior-gap detection (P2).

A hole in the middle of one ticker's history is invisible to every bound the
planner uses: first_date and last_date both still look correct. It shows up only
in the row count, which is why detection is two-phase -- count first (cheap, no
dates), then query dates for the few tickers that come up short.

Each test is a way that could go wrong: missing the hole, inventing holes out of
market closures, re-queuing work the head/tail planner already owns, or chasing
an unfillable hole forever.
"""
import pandas as pd
import pytest

from quantmine.download_plan import (
    build_gap_jobs,
    contiguous_gaps,
    find_gap_candidates,
    gap_key,
)

CALENDAR = list(pd.bdate_range("2026-01-01", "2026-01-30"))
AS_OF = pd.Timestamp("2026-08-10")


def coverage(rows):
    return pd.DataFrame(
        rows, columns=["ticker", "first_date", "last_date", "observations"]
    )


def test_complete_ticker_is_not_a_candidate():
    full = coverage([("T", CALENDAR[0], CALENDAR[-1], len(CALENDAR))])

    assert find_gap_candidates(full, CALENDAR) == []


def test_short_row_count_flags_a_ticker_whose_bounds_look_perfect():
    """The whole point: bounds are right, the middle is not."""
    short = coverage([("T", CALENDAR[0], CALENDAR[-1], len(CALENDAR) - 5)])

    assert find_gap_candidates(short, CALENDAR) == ["T"]


def test_candidates_are_ordered_worst_first():
    c = coverage([
        ("SMALL", CALENDAR[0], CALENDAR[-1], len(CALENDAR) - 2),
        ("BIG", CALENDAR[0], CALENDAR[-1], len(CALENDAR) - 10),
    ])

    assert find_gap_candidates(c, CALENDAR) == ["BIG", "SMALL"]


def test_tiny_shortfall_is_ignored():
    """One missing day is usually a halt, not a failed download; chasing it
    re-requests an empty window on every run."""
    c = coverage([("T", CALENDAR[0], CALENDAR[-1], len(CALENDAR) - 1)])

    assert find_gap_candidates(c, CALENDAR, min_missing=2) == []


def test_short_span_is_measured_against_its_own_window_not_the_whole_calendar():
    """A ticker listed halfway through must not look like it is missing the
    first half of the year."""
    c = coverage([("NEW", CALENDAR[10], CALENDAR[-1], len(CALENDAR) - 10)])

    assert find_gap_candidates(c, CALENDAR) == []


def test_gap_windows_are_contiguous_runs():
    missing = set(CALENDAR[5:9])
    observed = set(CALENDAR) - missing

    windows = contiguous_gaps(observed, CALENDAR, CALENDAR[0], CALENDAR[-1])

    assert windows == [(CALENDAR[5], CALENDAR[8])]


def test_two_separate_holes_produce_two_windows():
    observed = set(CALENDAR) - set(CALENDAR[3:5]) - set(CALENDAR[15:18])

    windows = contiguous_gaps(observed, CALENDAR, CALENDAR[0], CALENDAR[-1])

    assert windows == [(CALENDAR[3], CALENDAR[4]), (CALENDAR[15], CALENDAR[17])]


def test_head_and_tail_are_not_reported_as_gaps():
    """They belong to the main planner; reporting them here queues the same
    window twice."""
    observed = set(CALENDAR[5:-5])

    windows = contiguous_gaps(observed, CALENDAR, CALENDAR[5], CALENDAR[-6])

    assert windows == []


def test_weekends_are_never_gaps():
    """The calendar is the benchmark's own trade dates, so non-trading days
    cannot appear as missing in the first place."""
    observed = set(CALENDAR)

    assert contiguous_gaps(observed, CALENDAR, CALENDAR[0], CALENDAR[-1]) == []


def test_single_day_hole_is_below_the_threshold():
    observed = set(CALENDAR) - {CALENDAR[7]}

    assert contiguous_gaps(observed, CALENDAR, CALENDAR[0], CALENDAR[-1],
                           min_gap=2) == []


def test_tickers_sharing_a_window_merge_into_one_job():
    window = (CALENDAR[5], CALENDAR[8])
    jobs = build_gap_jobs({"A": [window], "B": [window]}, as_of=AS_OF)

    assert len(jobs) == 1
    assert jobs[0].tickers == ("A", "B")
    assert jobs[0].reason == "fill gap"


def test_unfillable_gap_stops_being_requested():
    window = (CALENDAR[5], CALENDAR[8])
    attempts = {gap_key("A", *window): {"attempts": 3,
                                        "last_attempt": "2026-08-09"}}

    assert build_gap_jobs({"A": [window]}, as_of=AS_OF, attempts=attempts) == []


def test_gap_ledger_key_is_distinct_from_the_whole_ticker_key():
    """Otherwise one unfillable 2019 hole would rest a live ticker and silence
    its daily increment."""
    window = (CALENDAR[5], CALENDAR[8])

    assert gap_key("A", *window) != "A"
    assert gap_key("A", *window).startswith("A|")


def test_gap_jobs_are_backfill_priority_never_ahead_of_the_increment():
    jobs = build_gap_jobs({"A": [(CALENDAR[5], CALENDAR[8])]}, as_of=AS_OF)

    from quantmine.download_plan import PRIORITY_INCREMENT

    assert jobs[0].priority > PRIORITY_INCREMENT


def test_no_calendar_yields_no_candidates():
    """A database with no benchmark rows yet must not claim everything is a gap."""
    c = coverage([("T", CALENDAR[0], CALENDAR[-1], 1)])

    assert find_gap_candidates(c, []) == []
