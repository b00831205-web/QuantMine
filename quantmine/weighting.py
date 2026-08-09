from .registry import make_registry
import pandas as pd

REGISTER_WEIGHTING, register_weighting = make_registry()

@register_weighting('equal')
def equal_weight(tickers, date, market_cap =None, **params):
    return pd.Series(1.0/len(tickers), index=list(tickers))

@register_weighting('mcap')
def mcap_weight(tickers, date, market_cap, **params):
    if market_cap is None:
        raise ValueError('mcap weighting requires a market_cap frame')
    tickers = list(tickers)
    # reindex(不是 .loc): 某票被清洗丢出 market_cap 列时当 NaN, 归一时自然忽略, 不 KeyError
    w = market_cap.reindex(index=[date], columns=tickers).iloc[0].astype(float)
    total = w.sum()
    if not (total > 0):
        return equal_weight(tickers, date)
    return w / total