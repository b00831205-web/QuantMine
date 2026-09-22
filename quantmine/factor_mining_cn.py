"""China A-share price-volume factor definitions."""

from __future__ import annotations
import pandas as pd

from .factor_register import factor_registry

def _available_columns(
        frame : pd.DataFrame,
        tickers : list[str],
) -> list[str]:
    return [ticker for ticker in tickers if ticker in frame.columns ]

@factor_registry("CNMomentum20D")
def cn_momentum_20d(
    close: pd.DataFrame,
    tickers : list[str],
    window: int = 20
) -> pd.DataFrame:
    """20-trading-day price momentum"""
    columns = _available_columns(close, tickers)
    return close[columns].pct_change(window)

@factor_registry("CNReversal5D")
def cn_reversal_5d(
    close: pd.DataFrame,
    tickers: list[str],
    window: int = 5
) -> pd.DataFrame:
    """Negative five_traing_day return as a short-term reversal signal"""
    columns = _available_columns(close, tickers)
    return -close[columns].pct_change(window)

@factor_registry("CNVolatility20D")
def cn_volatility_20d(
    close: pd.DataFrame,
    tickers: list[str],
    window: int =20
) -> pd.DataFrame:
    """Rolling volatility of daily returns"""
    columns = _available_columns(close, tickers)
    returns = close[columns].pct_change()
    return returns.rolling(window=window, min_periods = window).std()

@factor_registry("CNVolumeRatio20D")
def cn_volume_ratio_20d(
    volume: pd.DataFrame,
    tickers: list[str],
    window: int =20
) -> pd.DataFrame:
    """Current volume divided by its trailing avaerage volume"""
    columns = _available_columns(volume, tickers)
    selected = volume[columns]
    average = selected.rolling(window = window, min_periods=window).mean()
    return selected / average