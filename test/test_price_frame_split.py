"""Tests for splitting one download into adjusted and unadjusted closes.

The market-cap leg used to issue its own ``auto_adjust=False`` price download,
doubling every run's price requests. It never needed to: requesting
``auto_adjust=False`` once returns ``Adj Close`` (identical to what
``auto_adjust=True`` puts in ``Close``) alongside the raw ``Close``, with the
same ``Volume`` either way.

The hazard this creates is silent: checkpoints written before the change have no
``Adj Close``, and their ``Close`` is already adjusted. Reading both layouts the
same way would blend adjusted and unadjusted prices into one series, and nothing
downstream could notice -- both are plausible prices.
"""
import pandas as pd
import pytest

from quantmine.data_acquisition import split_price_frames


def frame(fields, tickers=("AAA", "BBB")):
    index = pd.to_datetime(["2026-08-03", "2026-08-04"])
    columns = pd.MultiIndex.from_product([list(fields), list(tickers)])
    data = {}
    for i, (field, ticker) in enumerate(columns):
        data[(field, ticker)] = [float(i), float(i) + 1]
    return pd.DataFrame(data, index=index, columns=columns)


def test_new_layout_yields_both_price_series():
    data = frame(["Adj Close", "Close", "Volume"])

    adjusted, raw, volume = split_price_frames(data)

    assert adjusted.equals(data["Adj Close"])
    assert raw.equals(data["Close"])
    assert volume.equals(data["Volume"])
    # the two price series must be distinguishable, not the same object
    assert not adjusted.equals(raw)


def test_legacy_layout_treats_close_as_already_adjusted():
    """Pre-change checkpoints were fetched with auto_adjust=True."""
    data = frame(["Close", "Volume"])

    adjusted, raw, volume = split_price_frames(data)

    assert adjusted.equals(data["Close"])
    assert raw is None            # the unadjusted series was never stored
    assert volume.equals(data["Volume"])


def test_legacy_close_is_never_mistaken_for_an_unadjusted_price():
    """The regression guard: returning legacy Close as `raw` would feed adjusted
    prices into market cap, distorting the cross-sectional size ordering that
    market-cap weighting depends on."""
    _, raw, _ = split_price_frames(frame(["Close", "Volume"]))

    assert raw is None


def test_adjusted_series_is_the_same_in_both_layouts():
    """Whichever layout a checkpoint has, the return series must not shift."""
    new = frame(["Adj Close", "Close", "Volume"])
    legacy = new[["Close", "Volume"]].rename(
        columns={"Close": "Close"}, level=0
    )
    # emulate the legacy file: its Close holds what the new file calls Adj Close
    legacy = pd.concat({"Close": new["Adj Close"], "Volume": new["Volume"]}, axis=1)

    assert split_price_frames(new)[0].equals(split_price_frames(legacy)[0])


def test_volume_is_returned_unchanged_by_either_layout():
    """Volume is identical between auto_adjust modes, so switching the flag must
    not alter any volume-based factor."""
    new = frame(["Adj Close", "Close", "Volume"])

    assert split_price_frames(new)[2].equals(new["Volume"])
