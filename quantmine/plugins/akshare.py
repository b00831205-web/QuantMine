"""AkShare adapters for daily China A-share market data."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

import pandas as pd

from ..datareader import MarketData
from .context import SourceContext
from .contracts import (
    DataBinding,
    DataSourceComponent,
    MarketDataBundle,
    MarketDataCapability
)

HistoryLoader = Callable[..., pd.DataFrame]

_REQUIRED_COLUMNS = ("日期", "收盘","成交量")
_SUPPORTED_ADJUSTMENTS = frozenset({"", "qfq", "hfq"})

@dataclass(frozen = True)
class AkShareAStockDataSourcePlugin:
    """Load daily A-share close and volume frames from ``stock_zh_a_hist``"""
    history_loader : HistoryLoader | None = field(
        default = None,
        repr = False,
        compare = False
    )

    default_adjustment: str = "hfq"

    def __post_init__(self) -> None:
        if self.default_adjustment not in _SUPPORTED_ADJUSTMENTS:
            raise ValueError(
                "default_adjustment must be one of: '', qfq, hfq"
            )

    def load(
            self,
            binding: DataBinding,
            context: SourceContext
    ) -> MarketDataBundle:
        del context

        if not binding.tickers:
            raise ValueError(
                "AkshareAstockDataSourcePlugin requires DataBinding.tickers"
            )

        if binding.start is None or binding.end is None:
            raise ValueError(
                "AkshareAstockDataSourcePlugin requires "
                "DataBinding.start and DataBinding.end"
            )
        adjustment = (
            self.default_adjustment
            if binding.adjustment is None
            else binding.adjustment
        )
        if adjustment not in _SUPPORTED_ADJUSTMENTS:
            raise ValueError(
                "DataBinding.adjustment for Akshare must be one of:'', qfq, hfq "
            )
        start_date = pd.Timestamp(binding.start).strftime("%Y%m%d")
        end_date = pd.Timestamp(binding.end).strftime("%Y%m%d")
        loader = self.history_loader or _default_history_loader

        close_frames : dict[str, pd.Series] = {}
        volume_frames: dict[str, pd.Series] = {}

        for ticker in binding.tickers:
            frame = loader(
                symbol = ticker,
                period = 'daily',
                start_date = start_date,
                end_date = end_date,
                adjust = adjustment,
            )

            _validate_provider_frame(frame, ticker)

            normalized = frame.loc[:, _REQUIRED_COLUMNS].copy()
            normalized.index = pd.DatetimeIndex(
                pd.to_datetime(normalized['日期'], errors = "raise")
            )
            if normalized.index.has_duplicates:
                raise ValueError(
                    f"Akshare returned duplicate dates for ticker {ticker!r}"
                )

            close_frames[ticker] = pd.to_numeric(
                normalized['收盘'],
                errors = 'raise',
            ).rename(ticker)
            volume_frames[ticker] = pd.to_numeric(
                normalized['成交量'],
                errors = 'raise'
            ).rename(ticker)

        close = pd.concat(close_frames, axis = 1, sort = False).sort_index().sort_index(axis =1)
        volume = pd.concat(volume_frames,axis=1, sort = False).sort_index().sort_index(axis=1)

        return MarketDataBundle(
            market = MarketData(close = close, volume = volume),
            calendar = pd.DatetimeIndex(close.index),
            metadata = {
                "source_kind": "akshare_stock_zh_a_hist",
                "dataset": binding.dataset,
                "adjustment": adjustment,
                "period": "daily",
                "volume_unit": "lot"
            },
        )

def create_akshare_a_stock_data_source(
        **params: object,
) -> DataSourceComponent:
    """Create the standard connection-free Akshare A-share source component"""

    return DataSourceComponent(
        id = "akshare_a_stock_daily",
        capabilities=frozenset(
            {
                MarketDataCapability.CLOSE,
                MarketDataCapability.VOLUME
            }
        ),
        plugin = AkShareAStockDataSourcePlugin(**params),
        metadata={
            "market": "CN",
            "provider": "akshare",
            "frequency": "daily"
        }
    )

def _default_history_loader(**kwargs: str) -> pd.DataFrame:
    try:
        import akshare as ak
    except ImportError as error:
        raise RuntimeError(
            "AkShare support is not installed. "
            "Install quantmine with its 'data' extra."
        ) from error

    return ak.stock_zh_a_hist(**kwargs)

def _validate_provider_frame(frame: object, ticker: str) ->None:
    if not isinstance(frame, pd.DataFrame):
        raise TypeError(
            f"Akshare returned {type(frame).__name__} for ticker {ticker!r}; "
            "expected DataFrame"
        )
    if frame.empty:
        raise ValueError(f"Akshare returned no daily data for ticker {ticker!r}")

    missing = [column for column in _REQUIRED_COLUMNS if column not in frame.columns]
    if missing:
        raise ValueError(
            "AkShare frame for "
            f"{ticker!r} is missing required columns: {', '.join(missing) }"
        )