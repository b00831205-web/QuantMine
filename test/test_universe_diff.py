"""Unit tests for the point-in-time index-membership diff.

Every case here is a way the daily wiki scrape can quietly corrupt the universe:

1. a one-off scrape miss must not delete a live member (grace period)
2. the exit date must be the last confirmed member day, not the day the grace
   period expired -- otherwise every removal overstates membership by N days
3. a spell with no last_seen must raise rather than fall back to start_date,
   which would end a decades-long membership on its first day
4. an implausible scrape (too few members, too many changes) must abort before
   any write, since a parse failure looks exactly like a mass delisting
5. punctuation must be canonicalized on both sides, or BRK.B vs BRK-B reads as
   a delisting plus an addition
"""
from datetime import date

import pandas as pd
import pytest

from quantmine.datareader import MembershipTableSource
from quantmine.universe import (
    UniverseSanityError,
    canonical_ticker,
    diff_universe,
)

AS_OF = date(2026, 8, 10)


def spell(ticker, start="2010-01-01", last_seen="2026-08-07", missing=0):
    return {
        "ticker": ticker,
        "start_date": date.fromisoformat(start),
        "last_seen": None if last_seen is None else date.fromisoformat(last_seen),
        "missing_scrapes": missing,
    }


def test_present_ticker_is_confirmed_not_reopened():
    diff = diff_universe([spell("AAPL")], {"AAPL"}, AS_OF)

    assert diff.confirmed == ["AAPL"]
    assert diff.opened == []
    assert diff.closed == []


def test_unseen_ticker_opens_a_spell_dated_today():
    diff = diff_universe([spell("AAPL")], {"AAPL", "NEW1"}, AS_OF)

    assert diff.opened == ["NEW1"]
    assert diff.change_count == 1


def test_single_absence_is_pending_not_closed():
    """A ticker missing from one scrape stays investable: it is almost always a
    scrape problem, and closing the spell would hide it from every backtest."""
    diff = diff_universe([spell("AAPL", missing=0)], set(), AS_OF)

    assert diff.pending == ["AAPL"]
    assert diff.closed == []


def test_absence_closes_the_spell_once_grace_is_exhausted():
    diff = diff_universe(
        [spell("AAPL", missing=2)], set(), AS_OF, grace_scrapes=3
    )

    assert diff.pending == []
    assert [t for t, _, _ in diff.closed] == ["AAPL"]


def test_exit_date_is_last_confirmed_day_not_the_expiry_day():
    """end_date must be last_seen. Using AS_OF would credit the ticker with the
    whole grace period as membership it never had."""
    diff = diff_universe(
        [spell("AAPL", last_seen="2026-08-05", missing=2)],
        set(),
        AS_OF,
        grace_scrapes=3,
    )

    _, _, end_date = diff.closed[0]
    assert end_date == date(2026, 8, 5)
    assert end_date < AS_OF


def test_grace_of_one_closes_immediately():
    """The reconciliation path uses grace_scrapes=1: the snapshot's staleness is
    known, so waiting buys nothing."""
    diff = diff_universe(
        [spell("AAPL", missing=0)], set(), AS_OF, grace_scrapes=1
    )

    assert [t for t, _, _ in diff.closed] == ["AAPL"]


def test_missing_last_seen_raises_instead_of_guessing():
    with pytest.raises(UniverseSanityError, match="last_seen"):
        diff_universe(
            [spell("AAPL", start="1999-01-04", last_seen=None, missing=5)],
            set(),
            AS_OF,
            grace_scrapes=3,
        )


def test_mass_change_aborts_before_writing():
    """A wholesale scrape failure looks like every member being delisted."""
    open_spells = [spell(f"T{i}") for i in range(30)]

    with pytest.raises(UniverseSanityError, match="membership changes"):
        diff_universe(open_spells, set(), AS_OF, grace_scrapes=1, max_change=15)


def test_max_change_can_be_disabled_for_the_gap_backfill():
    open_spells = [spell(f"T{i}") for i in range(30)]

    diff = diff_universe(
        open_spells, set(), AS_OF, grace_scrapes=1, max_change=None
    )

    assert len(diff.closed) == 30


def test_confirmations_do_not_count_toward_the_change_threshold():
    """500 unchanged members must not trip a 15-change guard."""
    open_spells = [spell(f"T{i}") for i in range(500)]
    observed = {f"T{i}" for i in range(500)}

    diff = diff_universe(open_spells, observed, AS_OF, max_change=15)

    assert diff.change_count == 0
    assert len(diff.confirmed) == 500


def test_punctuation_is_canonicalized_on_both_sides():
    """BRK.B in the table and BRK-B from the scrape are the same membership."""
    diff = diff_universe([spell("BRK.B")], {canonical_ticker("BRK.B")}, AS_OF)

    assert diff.confirmed == ["BRK-B"]
    assert diff.opened == []
    assert diff.closed == []


def test_canonical_ticker_is_idempotent():
    assert canonical_ticker("BRK-B") == "BRK-B"
    assert canonical_ticker(" brk.b ") == "BRK-B"


def test_reopened_spell_leaves_the_gap_out_of_the_universe():
    """A name that left and rejoined gets a second spell, not a resurrected
    first one, so the months it was out stay out of the backtest's universe."""
    diff = diff_universe([], {"AAPL"}, AS_OF)
    assert diff.opened == ["AAPL"]

    # Both spells as they would sit in index_membership, fed to the source the
    # backtest actually queries.
    source = MembershipTableSource(
        pd.DataFrame(
            {
                "ticker": ["AAPL", "AAPL"],
                "start_date": [date(2010, 1, 1), AS_OF],
                "end_date": [date(2026, 3, 31), None],
            }
        )
    )

    assert "AAPL" in source.get_constituents("2026-03-31")
    assert "AAPL" not in source.get_constituents("2026-06-15")  # inside the gap
    assert "AAPL" in source.get_constituents(AS_OF)
