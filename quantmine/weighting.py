"""Portfolio weighting strategies for the quantile backtest.

Mirrors the factor-selector pattern in ``ic_models``: schemes register with
``@register_weighting("name")`` and job configs select one by name, as
``weighting: {name: mcap}``. Equal weighting is itself a registered method
rather than a special case, so the default path shares the same dispatch as
every other scheme.

A weighting function receives one quantile group's tickers, the rebalance
date, and an optional wide date-by-ticker ``market_cap`` frame, and returns
the target weights as a Series indexed by those tickers. Renormalizing over
the members that actually have data on a given day is the backtest's job, so
these functions only express relative target weights.
"""
from .registry import make_registry
import pandas as pd

REGISTER_WEIGHTING, register_weighting = make_registry()

@register_weighting('equal')
def equal_weight(tickers, date, market_cap =None, **params):
    """Weight every group member equally, ignoring market cap."""
    return pd.Series(1.0/len(tickers), index=list(tickers))

@register_weighting('mcap')
def mcap_weight(tickers, date, market_cap, **params):
    """Weight group members by their market cap on the rebalance date.

    Falls back to equal weighting when no member has a positive market cap
    (e.g. the window predates the available share history), so a missing
    column degrades into the default rather than silently producing NaN.
    """
    if market_cap is None:
        raise ValueError('mcap weighting requires a market_cap frame')
    tickers = list(tickers)
    # reindex(不是 .loc): 某票被清洗丢出 market_cap 列时当 NaN, 归一时自然忽略, 不 KeyError
    w = market_cap.reindex(index=[date], columns=tickers).iloc[0].astype(float)
    total = w.sum()
    if not (total > 0):
        return equal_weight(tickers, date)
    return w / total