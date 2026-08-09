from dataclasses import dataclass
import pandas as pd
from typing import TypeAlias, Protocol
from abc import ABC, abstractmethod

@dataclass
class MarketData:
    close: pd.DataFrame = None
    volume: pd.DataFrame = None
    market_cap : pd.DataFrame = None
    def require(self, *fields: str)->None:
        for field in fields:
            if getattr(self, field) is None:
                raise ValueError(f'You have not provided the data for "{field}"')

class DataSource(Protocol):
    def load(self, tickers: list[str], start: str, end: str )-> MarketData:
        ... #ellipsis: conventional placeholder body for Protocol methods

class LocalFileSource(ABC):
    def __init__(self, paths: dict[str, str]):
        self.paths = paths
    @abstractmethod
    def _read_file(self, path:str)->pd.DataFrame:
        ...
    def load(self, tickers: list[str] =None, start: str=None, end:str= None)-> MarketData:
        loaded = {}
        for field_name, path in self.paths.items():
            df = self._read_file(path)
            if tickers:
                loaded[field_name] = df.loc[start:end, tickers]
            else:
                loaded[field_name] = df.loc[start:end]
        return MarketData(**loaded)

class YFinanceSource:
    def __init__(self, batch_size: int =50, max_retries: int=3, wait: int=60, checkpoint_dir:str="tmp/checkpoint"):
        self.batch_size = batch_size
        self.max_retries = max_retries
        self.wait = wait
        self.checkpoint_dir = checkpoint_dir
    def load(self, tickers: list[str], start: str, end: str) ->MarketData:
        #lazy import: users who only read local files don't need the yfinance dependency chain
        from .data_acquisition import data_acquisition
        # 只需价格: with_market_cap=False 跳过逐票 get_shares_full 网络开销
        close, volume, _, _ = data_acquisition(tickers=tickers, start_date = start, end_date = end, batch_size= self.batch_size,
                                    max_retries= self.max_retries, wait= self.wait, checkpoint_dir=self.checkpoint_dir,
                                    with_market_cap=False)
        return MarketData(close = close, volume = volume)

class ParquetSource(LocalFileSource):
    def _read_file(self, path:str) -> pd.DataFrame:
        return pd.read_parquet(path)

class CSVSource(LocalFileSource):
    def _read_file(self, path):
        return pd.read_csv(path, index_col = 0, parse_dates= True)

class ExcelSource(LocalFileSource):
    def _read_file(self, path):
        return pd.read_excel(path, index_col=0, parse_dates= True)

class ConstituentsSource(Protocol):
    """Protocol for point-in-time universe sources.

    The backtest calls ``get_constituents(date)`` on every rebalance day to get
    that day's valid universe. Any object implementing the method can plug in:
    a static list, an interval membership table, or a live API.
    """
    def get_constituents(self, date: pd.Timestamp) -> set[str]:
        ...

class StaticUniverse:
    """Fixed universe: the simplest option when no point-in-time data is available.

    Note: a fixed universe makes the backtest survivorship-biased; disclose this
    when interpreting results.
    """
    def __init__(self, tickers: list[str] | set[str]):
        self._tickers = set(tickers)
    def get_constituents(self, date: pd.Timestamp) -> set[str]:
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
        date = pd.Timestamp(date)
        if date not in self._cache:
            #the end-date condition must be parenthesized as a whole, otherwise rows
            #with end>=date would bypass the start<=date check
            mask = (self._start <= date) & (self._end.isnull() | (self._end >= date))
            self._cache[date] = set(self._tickers[mask])
        return self._cache[date]

FactorDict: TypeAlias = dict[str, pd.DataFrame]
ForwardReturn: TypeAlias = dict[int, pd.DataFrame]
