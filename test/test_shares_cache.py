"""Tests for the per-ticker share-count cache.

The bug: the cache lived under a directory keyed by
``md5(tickers, start_date, end_date)``. Share counts belong to a ticker, not to
a download window, so every run whose window differed by a day missed the whole
cache and re-issued one request per ticker -- ~500 serial calls to the endpoint
Yahoo throttles first. On disk the evidence was five signature directories
holding 0, 1 and 1 cached files between them.
"""
import time

import pandas as pd
import pytest

from quantmine.data_acquisition import (
    load_shares_cache,
    save_shares_cache,
    shares_cache_dir,
)


@pytest.fixture
def series():
    return pd.Series(
        [100.0, 110.0],
        index=pd.to_datetime(["2015-01-02", "2020-06-01"]),
        name="shares",
    )


def test_cache_survives_a_different_date_window(tmp_path, series):
    """The whole point: the key must not encode the download window."""
    save_shares_cache(str(tmp_path), "AAPL", series)

    # A later run with a completely different window must still hit.
    assert load_shares_cache(str(tmp_path), "AAPL", max_age_days=30) is not None


def test_cache_lives_outside_any_task_signature_directory(tmp_path, series):
    save_shares_cache(str(tmp_path), "AAPL", series)

    cached = shares_cache_dir(str(tmp_path))

    assert cached.endswith("shares")
    assert (tmp_path / "shares" / "AAPL.parquet").exists()


def test_cached_series_is_raw_not_aligned_to_a_price_index(tmp_path, series):
    """Storing it pre-aligned is what forced the cache under the task dir.

    Raw means one cache entry serves every window, and the caller reindexes.
    """
    save_shares_cache(str(tmp_path), "AAPL", series)

    loaded = load_shares_cache(str(tmp_path), "AAPL", max_age_days=30)

    assert list(loaded.index) == list(series.index)
    assert len(loaded) == 2      # not padded out to a trading calendar


def test_stale_cache_is_refetched(tmp_path, series):
    """Share counts move on buybacks and issuance, roughly quarterly. An
    unbounded cache would freeze market caps at whatever they were first run."""
    save_shares_cache(str(tmp_path), "AAPL", series)
    path = tmp_path / "shares" / "AAPL.parquet"
    old = time.time() - 60 * 86400
    import os

    os.utime(path, (old, old))

    assert load_shares_cache(str(tmp_path), "AAPL", max_age_days=30) is None
    assert load_shares_cache(str(tmp_path), "AAPL", max_age_days=90) is not None


def test_missing_entry_returns_none(tmp_path):
    assert load_shares_cache(str(tmp_path), "NOPE", max_age_days=30) is None


def test_corrupt_entry_does_not_stop_the_run(tmp_path):
    directory = tmp_path / "shares"
    directory.mkdir()
    (directory / "BAD.parquet").write_text("not parquet", encoding="utf-8")

    assert load_shares_cache(str(tmp_path), "BAD", max_age_days=30) is None


def test_reindexing_on_read_reproduces_the_old_aligned_behaviour(tmp_path, series):
    """Alignment moved from write-time to read-time; the result must match."""
    save_shares_cache(str(tmp_path), "AAPL", series)
    price_index = pd.to_datetime(
        ["2015-01-02", "2016-01-04", "2020-06-01", "2021-01-04"]
    )

    aligned = load_shares_cache(
        str(tmp_path), "AAPL", max_age_days=30
    ).reindex(price_index, method="ffill")

    assert aligned.tolist() == [100.0, 100.0, 110.0, 110.0]
