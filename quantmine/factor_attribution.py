"""Carhart four-factor attribution of the long-short backtest returns.

Regresses the daily long-short return series on the Fama-French three factors
plus momentum (all taken from the Ken French Data Library) with Newey-West
(HAC) standard errors. This answers whether the strategy return is explained
by known risk premia or carries unexplained alpha.

Factor data (not included in the repo, download from the Ken French Data
Library and place under ``tmp/ff3/``):
    - F-F_Research_Data_Factors_daily.csv
    - F-F_Momentum_Factor_daily.csv
"""
import logging
from pathlib import Path

import pandas as pd
import statsmodels.api as sm

logger = logging.getLogger("quantmine.attribution")

_FACTOR_COLS = ["Mkt-RF", "SMB", "HML", "RF", "Mom"]


def fetch_french_factors_daily(
    start_date,
    end_date,
    *,
    cache_path: str | Path | None = None,
) -> pd.DataFrame | None:
    """Fetch daily Fama-French three-factor and momentum decimal returns.

    ``pandas_datareader`` loads clean frames from the Ken French Data Library,
    avoiding the header and footer noise in the raw CSV files. A successful
    download is cached as Parquet. If the live request fails, the cache is used;
    if neither source is available, return ``None`` so callers can skip
    attribution without failing the report.

    Args:
        start_date / end_date: Download range in any pandas-compatible format.
        cache_path: Parquet cache path; ``None`` disables caching.

    Returns:
        A date-indexed DataFrame with decimal-return columns
        ``Mkt-RF/SMB/HML/RF/Mom``, or ``None``.

    Notes:
        Ken French factors cover US equities. Supporting China A-shares requires
        replacing this data source while preserving ``carhart_attribution`` and
        the persistence contract.
    """
    cache = Path(cache_path) if cache_path else None
    try:
        import pandas_datareader.data as web

        start = pd.to_datetime(start_date)
        end = pd.to_datetime(end_date)
        ff = web.DataReader("F-F_Research_Data_Factors_daily", "famafrench", start, end)[0]
        mom = web.DataReader("F-F_Momentum_Factor_daily", "famafrench", start, end)[0]

        ff.columns = [str(column).strip() for column in ff.columns]
        mom.columns = [str(column).strip() for column in mom.columns]
        mom = mom.rename(columns={mom.columns[0]: "Mom"})

        merged = ff.join(mom[["Mom"]], how="inner") / 100  # percent -> decimal
        # The famafrench reader returns a PeriodIndex (period[D]), and since
        # pandas 3 `to_datetime` rejects period data outright instead of
        # coercing it. Reaching this with a PeriodIndex used to raise, get
        # caught by the blanket handler below, and surface as "factor data
        # unavailable" -- so the whole attribution feature looked like a
        # network problem and never produced a row.
        index = merged.index
        merged.index = (
            index.to_timestamp() if isinstance(index, pd.PeriodIndex)
            else pd.to_datetime(index)
        )
        merged = merged[_FACTOR_COLS].dropna(how="all")
        if merged.empty:
            raise ValueError("Ken French returned no rows for the requested range")

        if cache is not None:
            cache.parent.mkdir(parents=True, exist_ok=True)
            merged.to_parquet(cache)
        return merged
    except Exception as error:
        logger.warning("live FF factor download failed: %s", error)
        if cache is not None and cache.exists():
            logger.warning("falling back to cached FF factors at %s", cache)
            return pd.read_parquet(cache)
        return None


def load_french_factors(ff3_path: str, mom_path: str) -> pd.DataFrame:
    """Load and merge daily FF3 and momentum factors from Ken French CSVs.

    Args:
        ff3_path: Path to ``F-F_Research_Data_Factors_daily.csv``.
        mom_path: Path to ``F-F_Momentum_Factor_daily.csv``.

    Returns:
        A dataframe indexed by date with columns ``Mkt-RF``, ``SMB``, ``HML``,
        ``RF`` and ``Mom``, converted from percent to decimal returns.

    Notes:
        The raw CSVs carry header/footer junk rows; only rows whose date field
        matches ``YYYYMMDD`` are kept.
    """
    ff3 = pd.read_csv(ff3_path, skiprows=4)
    ff3.columns = ['Date'] + list(ff3.columns[1:])
    ff3 = ff3[ff3['Date'].astype(str).str.match(r'^\d{8}$')]

    mom = pd.read_csv(mom_path, skiprows=13)
    mom = mom.iloc[:, :2]
    mom.columns = ['Date', 'Mom']
    mom = mom[mom['Date'].astype(str).str.match(r'^\d{8}$')]

    merged = ff3.merge(mom, on='Date', how='inner')
    merged['date'] = pd.to_datetime(merged['Date'], format='%Y%m%d')
    cols = ['Mkt-RF', 'SMB', 'HML', 'RF', 'Mom']
    merged[cols] = merged[cols].astype(float) / 100  #percent -> decimal
    return merged.set_index('date')[cols]


def carhart_attribution(daily_returns: pd.DataFrame, factors: pd.DataFrame, maxlags: int = 20):
    """Regress the long-short series on Mkt-RF, SMB, HML and Mom.

    Args:
        daily_returns: Wide dataframe containing a ``long_short`` column of
            daily returns (output of ``expand_to_daily_returns``).
        factors: Daily factor dataframe from ``load_french_factors``.
        maxlags: Newey-West lag length for the HAC covariance. Default 20 to
            match the longest holding period.

    Returns:
        A fitted statsmodels OLS results object. ``params['const']`` is the
        daily alpha; multiply by 252 to annualize.

    Notes:
        The long-short portfolio is self-financing, so the raw spread (not the
        excess over RF) is regressed.
    """
    combined = (daily_returns[['long_short']]
                .join(factors[['Mkt-RF', 'SMB', 'HML', 'Mom']], how='inner')
                .dropna())
    x = sm.add_constant(combined[['Mkt-RF', 'SMB', 'HML', 'Mom']])
    return sm.OLS(combined['long_short'], x).fit(cov_type='HAC', cov_kwds={'maxlags': maxlags})
