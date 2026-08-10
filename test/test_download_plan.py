"""Unit tests for the per-ticker download planner.

The bug this replaces: one global watermark for the whole table. Each test below
is a case that watermark got wrong, or a way the per-ticker fix could overcorrect
into re-downloading the same range every day.
"""
import pandas as pd
import pytest

from quantmine.download_plan import (
    DEFAULT_LOOKBACK_DAYS,
    build_download_plan,
    build_targets,
)

AS_OF = pd.Timestamp("2026-08-10")
ANALYSIS_START = pd.Timestamp("2015-01-01")


def membership(rows):
    return pd.DataFrame(rows, columns=["ticker", "start_date", "end_date"])


def coverage(rows):
    return pd.DataFrame(
        rows, columns=["ticker", "first_date", "last_date", "observations"]
    )


def plan(m, c, **kw):
    return build_download_plan(
        m, c, as_of=AS_OF, analysis_start=ANALYSIS_START, **kw
    )


def jobs_for(jobs, ticker):
    return [j for j in jobs if ticker in j.tickers]


def test_everyone_at_the_same_watermark_is_one_job():
    """The common case must stay a single batch, not 500 of them."""
    m = membership([(f"T{i}", "2015-01-01", None) for i in range(500)])
    c = coverage([(f"T{i}", "2015-01-02", "2026-08-07", 2900) for i in range(500)]
                 + [("SPY", "2015-01-02", "2026-08-07", 2900)])

    jobs = plan(m, c)

    assert len(jobs) == 1
    assert len(jobs[0].tickers) == 501
    assert jobs[0].start == pd.Timestamp("2026-08-08")
    assert jobs[0].end == AS_OF


def test_new_constituent_gets_history_not_just_today():
    """The headline bug: a name added today must not start with one day of data."""
    m = membership([("OLD", "2015-01-01", None), ("NEW", "2026-08-10", None)])
    c = coverage([("OLD", "2015-01-02", "2026-08-07", 2900),
                  ("SPY", "2015-01-02", "2026-08-07", 2900)])

    new_jobs = jobs_for(plan(m, c), "NEW")

    assert len(new_jobs) == 1
    job = new_jobs[0]
    assert job.end == AS_OF
    # reaches back a lookback window, not to the join date
    assert job.start < pd.Timestamp("2026-08-10") - pd.Timedelta(days=300)
    assert job.start == AS_OF - pd.Timedelta(days=DEFAULT_LOOKBACK_DAYS)


def test_new_constituent_history_is_capped_at_analysis_start():
    m = membership([("NEW", "2015-01-05", None)])

    jobs = jobs_for(plan(m, coverage([])), "NEW")

    assert jobs[0].start == ANALYSIS_START


def test_partial_history_triggers_a_backfill_job():
    """Data starts after the ticker joined -> the head is genuinely missing."""
    m = membership([("T", "2015-01-01", None)])
    c = coverage([("T", "2020-06-01", "2026-08-10", 1500)])

    backfills = [j for j in jobs_for(plan(m, c), "T") if j.reason == "backfill history"]

    assert len(backfills) == 1
    assert backfills[0].start == ANALYSIS_START
    assert backfills[0].end == pd.Timestamp("2020-05-31")


def test_missing_lookback_alone_does_not_retrigger_forever():
    """A ticker whose data starts exactly at its join date is complete.

    Its pre-join lookback simply does not exist (the company had not listed).
    Treating that as a gap would re-request the same empty range every day.
    """
    m = membership([("IPO", "2024-03-01", None)])
    c = coverage([("IPO", "2024-03-01", "2026-08-10", 600)])

    assert jobs_for(plan(m, c), "IPO") == []


def test_delisted_ticker_is_never_requested_again_once_complete():
    m = membership([("GONE", "2015-01-01", "2023-05-15")])
    c = coverage([("GONE", "2015-01-02", "2023-05-15", 2100)])

    assert jobs_for(plan(m, c), "GONE") == []


def test_delisted_ticker_still_gets_its_own_tail_not_todays():
    """A spell that ended in 2023 must not be extended to today."""
    m = membership([("GONE", "2015-01-01", "2023-05-15")])
    c = coverage([("GONE", "2015-01-02", "2023-01-31", 2000)])

    jobs = jobs_for(plan(m, c), "GONE")

    assert len(jobs) == 1
    assert jobs[0].end == pd.Timestamp("2023-05-15")
    assert jobs[0].end < AS_OF


def test_spell_entirely_before_the_analysis_window_is_dropped():
    m = membership([("ANCIENT", "1998-01-01", "2004-12-31")])

    assert plan(m, coverage([]))[0].tickers == ("SPY",)


def test_benchmark_is_always_included_even_though_it_is_not_a_constituent():
    jobs = plan(membership([]), coverage([]))

    assert any("SPY" in job.tickers for job in jobs)


def test_rejoined_ticker_spans_both_spells():
    """Two spells collapse into one target covering the whole outer range."""
    m = membership([("BACK", "2015-01-01", "2019-06-30"),
                    ("BACK", "2024-01-15", None)])

    targets = build_targets(
        m, as_of=AS_OF, analysis_start=ANALYSIS_START,
        lookback_days=DEFAULT_LOOKBACK_DAYS, extra_tickers=(),
    )

    assert targets["BACK"].mandatory_start == ANALYSIS_START
    assert targets["BACK"].end == AS_OF


def test_ticker_punctuation_is_canonicalized_to_match_market_bars():
    m = membership([("BRK.B", "2015-01-01", None)])
    c = coverage([("BRK-B", "2015-01-02", "2026-08-10", 2900)])

    # Without normalization BRK.B looks like a brand-new ticker needing 11 years.
    assert jobs_for(plan(m, c), "BRK-B") == []
    assert jobs_for(plan(m, c), "BRK.B") == []


def test_market_closure_at_the_head_is_not_a_gap():
    """Membership dates are calendar dates, bar dates are trading dates.

    A spell opening on a holiday can only ever have its first bar days later;
    treating that as missing history means a backfill request on every run.
    """
    m = membership([("T", "2015-01-01", None)])          # New Year's Day
    c = coverage([("T", "2015-01-05", "2026-08-10", 2900)])  # first Monday

    assert jobs_for(plan(m, c), "T") == []


def test_closed_spell_ending_on_a_weekend_is_not_re_requested():
    """end_date is a calendar date; the last bar is the Friday before."""
    m = membership([("GONE", "2015-01-01", "2023-05-13")])   # a Saturday
    c = coverage([("GONE", "2015-01-02", "2023-05-12", 2100)])  # Friday

    assert jobs_for(plan(m, c), "GONE") == []


def test_open_spell_still_gets_its_daily_increment_despite_the_slack():
    """The slack must not swallow the ordinary one-day increment."""
    m = membership([("T", "2015-01-01", None)])
    c = coverage([("T", "2015-01-02", "2026-08-09", 2900)])

    jobs = jobs_for(plan(m, c), "T")

    assert len(jobs) == 1
    assert jobs[0].start == pd.Timestamp("2026-08-10")


def test_up_to_date_universe_produces_no_jobs():
    m = membership([("T", "2015-01-01", None)])
    c = coverage([("T", "2015-01-02", "2026-08-10", 2900),
                  ("SPY", "2015-01-02", "2026-08-10", 2900)])

    assert plan(m, c) == []


def test_head_and_tail_are_separate_jobs_with_distinct_windows():
    """A ticker missing both ends must not be re-downloaded as one huge span."""
    m = membership([("T", "2015-01-01", None)])
    c = coverage([("T", "2018-01-02", "2024-01-02", 1500)])

    reasons = {j.reason: j for j in jobs_for(plan(m, c), "T")}

    assert set(reasons) == {"backfill history", "increment"}
    assert reasons["backfill history"].end == pd.Timestamp("2018-01-01")
    assert reasons["increment"].start == pd.Timestamp("2024-01-03")


def test_daily_increment_is_first_even_behind_a_huge_backlog():
    """Callers truncate the plan. If the increment were not first, a backlog of
    historical backfills would starve the pipeline of today's prices."""
    # Distinct exit dates, so they cannot merge into one job -- this is what the
    # real membership table looks like: ~130 delisted names, each its own window.
    m = membership(
        [("LIVE", "2015-01-01", None)]
        + [(f"OLD{i}", "2015-01-01",
            (pd.Timestamp("2019-01-01") + pd.Timedelta(days=i)).date().isoformat())
           for i in range(200)]
    )
    c = coverage([("LIVE", "2015-01-02", "2026-08-09", 2900),
                  ("SPY", "2015-01-02", "2026-08-09", 2900)])

    jobs = plan(m, c)

    assert len(jobs) > 100                       # backlog really is there
    assert jobs[0].reason == "increment"
    assert set(jobs[0].tickers) == {"LIVE", "SPY"}
    # and truncating to a handful still keeps it
    assert jobs[:3][0].reason == "increment"


def test_hopeless_tickers_stop_being_requested():
    """~195 historical members have no recoverable Yahoo history. Without a
    ceiling they are re-requested every run, burning the shared rate limit."""
    m = membership([("DEAD", "2015-01-01", "2018-01-01")])
    attempts = {"DEAD": {"attempts": 3, "last_attempt": "2026-08-05"}}

    assert jobs_for(plan(m, coverage([]), attempts=attempts), "DEAD") == []


def test_hopeless_tickers_are_retried_after_the_cooldown():
    """Not a permanent blacklist: Yahoo sometimes starts serving a name later,
    and a one-way blacklist would keep shrinking the recoverable universe."""
    m = membership([("DEAD", "2015-01-01", "2018-01-01")])
    attempts = {"DEAD": {"attempts": 9, "last_attempt": "2026-01-01"}}

    assert jobs_for(plan(m, coverage([]), attempts=attempts), "DEAD") != []


def test_attempts_below_the_ceiling_still_get_requested():
    m = membership([("MAYBE", "2015-01-01", "2018-01-01")])
    attempts = {"MAYBE": {"attempts": 2, "last_attempt": "2026-08-09"}}

    assert jobs_for(plan(m, coverage([]), attempts=attempts), "MAYBE") != []


def test_ledger_never_suppresses_the_live_increment():
    """A rested ticker must still receive its daily increment if it has data."""
    m = membership([("T", "2015-01-01", None)])
    c = coverage([("T", "2015-01-02", "2026-08-09", 2900)])
    attempts = {"T": {"attempts": 99, "last_attempt": "2026-08-09"}}

    jobs = jobs_for(plan(m, c, attempts=attempts), "T")

    assert len(jobs) == 1 and jobs[0].reason == "increment"


@pytest.mark.parametrize("empty", [pd.DataFrame(columns=["ticker", "first_date", "last_date", "observations"])])
def test_empty_database_downloads_the_whole_window(empty):
    m = membership([("T", "2015-01-01", None)])

    jobs = jobs_for(plan(m, empty), "T")

    assert jobs[0].start == ANALYSIS_START
    assert jobs[0].end == AS_OF
