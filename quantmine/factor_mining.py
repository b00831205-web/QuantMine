"""Factor definitions.

Each function computes one factor as a wide date-by-ticker frame and registers
itself under a name via ``@factor_registry``, so configs can request factors by
name without importing them. Adding a factor means adding a decorated function
here; no call site needs to change.
"""
import pandas as pd
from .factor_register import factor_registry

@factor_registry('daily_return')
def daily_return(close:pd.DataFrame, tickers:list)->pd.DataFrame:
    """Compute daily percentage returns for a list of tickers.

    Args:
        df: Price dataframe indexed by date.
        tickers: Tickers to compute returns for.

    Returns:
        A dataframe of daily returns with one column per ticker.

    Notes:
        The first row for each ticker will be ``NaN`` because percentage change
        requires a previous observation.
    """
    cols = [t for t in tickers if t in close.columns]
    daily_return_df = close[cols].pct_change()
    return daily_return_df

@factor_registry("excess_return")
def excess_return(daily_return: pd.DataFrame) -> pd.DataFrame:
    """Compute excess returns over the market proxy SPY.

    Args:
        daily_return: Dataframe of daily returns that includes an ``SPY`` column.

    Returns:
        A dataframe of excess returns for all non-SPY columns.

    Notes:
        This function assumes ``SPY`` is the benchmark and removes it from the
        output.
    """
    market_return=daily_return['SPY']
    excess_return=daily_return.drop(columns=['SPY']).sub(market_return, axis=0)
    return excess_return

@factor_registry('momentum')
def momentum(close: pd.DataFrame, tickers: list, day:int =2) -> pd.DataFrame:
    """Compute a simple momentum factor for each ticker.

    Args:
        df: Price dataframe indexed by date.
        tickers: Tickers to process.
        day: Lookback window used to measure momentum.

    Returns:
        A dataframe with columns named like ``{day}DayMomentum_TICKER``.

    Notes:
        The factor is based on the relative price change between the current
        price and the price ``day - 1`` periods ago.
    """
    cols = [t for t in tickers if t in close.columns]
    mmt = close[cols].pct_change(day - 1)
    return mmt

@factor_registry('ShortTermReversal')
def ShortTermReversal(excess_return: pd.DataFrame,tickers: list, halflife: int, period: int)->pd.DataFrame:
    """Compute a short-term reversal factor from lagged excess returns.

    Args:
        excess_return: Dataframe of excess returns.
        tickers: Tickers to process.
        halflife: Halflife used to define the exponential decay weight.
        period: Rolling window length.

    Returns:
        A dataframe with one short-term reversal column per ticker.

    Notes:
        The signal is negated because high recent returns are assumed to mean
        lower near-term future returns.
    """
    cols = [t for t in tickers if t in excess_return.columns]
    data = excess_return[cols]
    wk = 0.5 ** (1 / halflife)
    # fixed-weight FIR filter: sum_i wk^i * x.shift(i), one whole-frame shift per lag.
    # Equivalent to rolling(period).apply(EWMA) but avoids the per-window Python loop
    # (O(dates*tickers*period) Python calls -> period vectorized operations).
    # NaN semantics match: any missing observation inside the window yields NaN.
    ewma = data * 1.0
    for i in range(1, period):
        ewma = ewma + (wk ** i) * data.shift(i)
    return -ewma #reversal signal is negated: high past returns imply lower expected near-term returns

@factor_registry('TwentyDayVolatility')
def TwentyDayVolatility(daily_return:pd.DataFrame, tickers:list)->pd.DataFrame:
    """Compute 20-day rolling volatility for each ticker.

    Args:
        daily_return: Dataframe of daily returns.
        tickers: Tickers to process.

    Returns:
        A dataframe of 20-day rolling standard deviations.
    """
    cols = [t for t in tickers if t in daily_return.columns]
    twenty_day_volatility = daily_return[cols].rolling(20).std()
    return twenty_day_volatility

@factor_registry('TwentyDayNegVotality')
def TwentyDayNegVotality(daily_return:pd.DataFrame, tickers:list)->pd.DataFrame:
    """Compute 20-day rolling volatility using only negative returns.

    Args:
        daily_return: Dataframe of daily returns.
        tickers: Tickers to process.

    Returns:
        A dataframe of rolling standard deviations calculated from negative
        returns only.

    Notes:
        Non-negative returns are converted to ``NaN`` before rolling.
    """
    cols = [t for t in tickers if t in daily_return.columns]
    neg_return = daily_return[cols].where(daily_return[cols] < 0) #where keeps values matching the condition, others become NaN
    return neg_return.rolling(window=20, min_periods=1).std()

@factor_registry('TwentyDayAvgVol')
def TwentyDayAvgVol(volume:pd.DataFrame, tickers:list)->pd.DataFrame:
    """Compute 20-day average trading volume for each ticker.

    Args:
        volume: Volume dataframe indexed by date.
        tickers: Tickers to process.

    Returns:
        A dataframe of 20-day rolling mean volume values.
    """
    cols = [t for t in tickers if t in volume.columns]
    volume_avg = volume[cols].rolling(20).mean()
    return volume_avg

@factor_registry('VolPriceCorr')
def VolPriceCorr(volume:pd.DataFrame, daily_return:pd.DataFrame, tickers:list)->pd.DataFrame:
    """Compute 20-day rolling correlation between returns and volume.

    Args:
        volume: Volume dataframe indexed by date.
        daily_return: Daily return dataframe indexed by date.
        tickers: Tickers to process.

    Returns:
        A dataframe of rolling correlation values for each ticker.

    Notes:
        This factor measures the relationship between trading activity and
        price movement over a 20-day window.
    """
    cols = [t for t in tickers if t in daily_return.columns and t in volume.columns]
    vol_price_corr = daily_return[cols].rolling(20).corr(volume[cols])
    return vol_price_corr
