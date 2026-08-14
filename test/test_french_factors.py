"""Contract tests for the Ken French daily factor loader."""

import sys
import types

import pandas as pd

from quantmine.factor_attribution import fetch_french_factors_daily


def _reader_stub(index):
    """Stand in for pandas_datareader.data, returning Ken French shaped frames.

    The real reader hands back percent returns keyed by a period index and wraps
    each frame in a dict-like keyed by table number, which is why the caller
    subscripts ``[0]``.
    """
    ff = pd.DataFrame(
        {"Mkt-RF": [1.0, -2.0], "SMB": [0.5, 0.25], "HML": [-0.5, 1.0], "RF": [0.01, 0.01]},
        index=index,
    )
    mom = pd.DataFrame({"Mom   ": [0.75, -0.25]}, index=index)

    def data_reader(name, source, start, end):
        return {0: ff if name.startswith("F-F_Research") else mom}

    return types.SimpleNamespace(DataReader=data_reader)


def _install(monkeypatch, index):
    package = types.ModuleType("pandas_datareader")
    package.data = _reader_stub(index)
    monkeypatch.setitem(sys.modules, "pandas_datareader", package)
    monkeypatch.setitem(sys.modules, "pandas_datareader.data", package.data)


def test_period_index_is_converted_rather_than_rejected(monkeypatch):
    """The famafrench reader returns period[D]. pandas 3 refuses to coerce that
    through to_datetime, and the blanket except in the loader turned the
    resulting TypeError into "factor data unavailable" -- so attribution looked
    like an offline failure and never stored a row."""
    _install(monkeypatch, pd.period_range("2026-01-02", periods=2, freq="D"))

    factors = fetch_french_factors_daily("2026-01-01", "2026-01-31", cache_path=None)

    assert factors is not None
    assert isinstance(factors.index, pd.DatetimeIndex)
    assert factors.index.tolist() == [pd.Timestamp("2026-01-02"), pd.Timestamp("2026-01-03")]


def test_percent_returns_become_decimals(monkeypatch):
    _install(monkeypatch, pd.period_range("2026-01-02", periods=2, freq="D"))

    factors = fetch_french_factors_daily("2026-01-01", "2026-01-31", cache_path=None)

    assert factors["Mkt-RF"].tolist() == [0.01, -0.02]
    # the momentum column arrives padded with trailing spaces
    assert factors["Mom"].tolist() == [0.0075, -0.0025]


def test_datetime_index_still_works(monkeypatch):
    """Guards the non-period branch, so a future reader change does not regress."""
    _install(monkeypatch, pd.to_datetime(["2026-01-02", "2026-01-03"]))

    factors = fetch_french_factors_daily("2026-01-01", "2026-01-31", cache_path=None)

    assert isinstance(factors.index, pd.DatetimeIndex)


def test_download_failure_without_cache_returns_none(monkeypatch):
    """Callers rely on None to skip attribution instead of failing the DAG."""
    package = types.ModuleType("pandas_datareader")

    def boom(*args, **kwargs):
        raise RuntimeError("network down")

    package.data = types.SimpleNamespace(DataReader=boom)
    monkeypatch.setitem(sys.modules, "pandas_datareader", package)
    monkeypatch.setitem(sys.modules, "pandas_datareader.data", package.data)

    assert fetch_french_factors_daily("2026-01-01", "2026-01-31", cache_path=None) is None


def test_cache_is_written_then_used_when_the_download_fails(monkeypatch, tmp_path):
    cache = tmp_path / "ff3" / "ff_daily.parquet"
    _install(monkeypatch, pd.period_range("2026-01-02", periods=2, freq="D"))
    first = fetch_french_factors_daily("2026-01-01", "2026-01-31", cache_path=cache)
    assert cache.exists()

    def boom(*args, **kwargs):
        raise RuntimeError("network down")

    monkeypatch.setattr(sys.modules["pandas_datareader.data"], "DataReader", boom)
    fallback = fetch_french_factors_daily("2026-01-01", "2026-01-31", cache_path=cache)

    pd.testing.assert_frame_equal(fallback, first)
