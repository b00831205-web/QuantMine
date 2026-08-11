"""Market data input: where price data and the trading universe come from.

Two independent abstractions live here. ``DataSource`` loads price data into a
``MarketData`` bundle, whether from local files or from yfinance.
``ConstituentsSource`` answers which tickers were investable on a given date,
which is what keeps a backtest free of survivorship bias.

Both are protocols, so a caller can supply any object with the right method
without subclassing anything here.
"""
from dataclasses import dataclass
import pandas as pd
from typing import TypeAlias, Protocol
from abc import ABC, abstractmethod

@dataclass
class MarketData:
    """A bundle of wide date-by-ticker frames.

    Fields default to None because sources supply different subsets: a local
    file source may load only closes, while a full download also carries
    volume and market cap. Consumers state their needs with ``require``.
    """
    close: pd.DataFrame = None
    volume: pd.DataFrame = None
    market_cap : pd.DataFrame = None
    def require(self, *fields: str)->None:
        """Raise ValueError if any named field was not supplied.

        Fails loudly at the start of a computation instead of surfacing an
        obscure ``NoneType`` error somewhere in the middle of it.
        """
        for field in fields:
            if getattr(self, field) is None:
                raise ValueError(f'You have not provided the data for "{field}"')

class DataSource(Protocol):
    """Protocol for anything that can load market data for a date range."""
    def load(self, tickers: list[str], start: str, end: str )-> MarketData:
        ... #ellipsis: conventional placeholder body for Protocol methods

class LocalFileSource(ABC):
    """Base for sources reading wide frames from local files.

    Subclasses only implement ``_read_file`` for their format; slicing by date
    and ticker is shared here.

    Args:
        paths: Maps ``MarketData`` field names to file paths, e.g.
            ``{"close": "close.parquet", "volume": "volume.parquet"}``.
    """
    def __init__(self, paths: dict[str, str]):
        self.paths = paths
    @abstractmethod
    def _read_file(self, path:str)->pd.DataFrame:
        ...
    def load(self, tickers: list[str] =None, start: str=None, end:str= None)-> MarketData:
        """Read each configured file, sliced to the given window and tickers.

        All arguments are optional: omitting them loads the files whole.
        """
        loaded = {}
        for field_name, path in self.paths.items():
            df = self._read_file(path)
            if tickers:
                loaded[field_name] = df.loc[start:end, tickers]
            else:
                loaded[field_name] = df.loc[start:end]
        return MarketData(**loaded)

class YFinanceSource:
    """Download prices from Yahoo Finance, with batching and checkpoints.

    Loads closes and volumes only; market cap is skipped because it costs one
    extra request per ticker. Use ``data_acquisition`` directly when market cap
    is needed.
    """
    def __init__(self, batch_size: int =50, max_retries: int=3, wait: int=60, checkpoint_dir:str="tmp/checkpoint"):
        self.batch_size = batch_size
        self.max_retries = max_retries
        self.wait = wait
        self.checkpoint_dir = checkpoint_dir
    def load(self, tickers: list[str], start: str, end: str) ->MarketData:
        """Download closes and volumes for the tickers over the date range."""
        #lazy import: users who only read local files don't need the yfinance dependency chain
        from .data_acquisition import data_acquisition
        # Prices only: skip per-ticker get_shares_full network requests.
        close, volume, _, _ = data_acquisition(tickers=tickers, start_date = start, end_date = end, batch_size= self.batch_size,
                                    max_retries= self.max_retries, wait= self.wait, checkpoint_dir=self.checkpoint_dir,
                                    with_market_cap=False)
        return MarketData(close = close, volume = volume)

class ParquetSource(LocalFileSource):
    """Local file source reading parquet."""
    def _read_file(self, path:str) -> pd.DataFrame:
        return pd.read_parquet(path)

class CSVSource(LocalFileSource):
    """Local file source reading CSV with a parsed date index."""
    def _read_file(self, path):
        return pd.read_csv(path, index_col = 0, parse_dates= True)

class ExcelSource(LocalFileSource):
    """Local file source reading Excel with a parsed date index."""
    def _read_file(self, path):
        return pd.read_excel(path, index_col=0, parse_dates= True)

class ConstituentsSource(Protocol):
    """Protocol for point-in-time universe sources.

    The backtest calls ``get_constituents(date)`` on every rebalance day to get
    that day's valid universe. Any object implementing the method can plug in:
    a static list, an interval membership table, or a live API.
    """
    def get_constituents(self, date: pd.Timestamp) -> set[str]:
        """Return the tickers investable on ``date``."""
        ...

class StaticUniverse:
    """Fixed universe: the simplest option when no point-in-time data is available.

    Note: a fixed universe makes the backtest survivorship-biased; disclose this
    when interpreting results.
    """
    def __init__(self, tickers: list[str] | set[str]):
        self._tickers = set(tickers)
    def get_constituents(self, date: pd.Timestamp) -> set[str]:
        """Return the fixed universe, ignoring ``date``."""
        return self._tickers

class MembershipTableSource:
    """Interval-table source: point-in-time universe from (ticker, start_date, end_date) rows.

    A missing ``end_date`` means the ticker is still a member. Dates are parsed
    once at construction (re-parsing the whole table on every query would cost a
    full scan per rebalance day) and query results are cached per date.

    Args:
        table: DataFrame with ticker/start_date/end_date columns.
        normalize: If True, replace '.' with '-' in tickers (e.g. BRK.B -> BRK-B)
            to match yfinance column names; pass False if your price data uses
            the '.' convention.
    """
    def __init__(self, table: pd.DataFrame, ticker_col: str = 'ticker',
                 start_col: str = 'start_date', end_col: str = 'end_date',
                 normalize: bool = True):
        self._start = pd.to_datetime(table[start_col])
        self._end = pd.to_datetime(table[end_col])
        tickers = table[ticker_col].astype(str)
        if normalize:
            tickers = tickers.str.replace('.', '-', regex=False)
        self._tickers = tickers
        self._cache: dict[pd.Timestamp, set[str]] = {}

    def get_constituents(self, date: pd.Timestamp) -> set[str]:
        """Return members whose interval covers ``date``, cached per date."""
        date = pd.Timestamp(date)
        if date not in self._cache:
            #the end-date condition must be parenthesized as a whole, otherwise rows
            #with end>=date would bypass the start<=date check
            mask = (self._start <= date) & (self._end.isnull() | (self._end >= date))
            self._cache[date] = set(self._tickers[mask])
        return self._cache[date]

FactorDict: TypeAlias = dict[str, pd.DataFrame]
ForwardReturn: TypeAlias = dict[int, pd.DataFrame]
