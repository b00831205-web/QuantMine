"""Routed AkShare source for resilient China A-share history loading."""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

import pandas as pd

from ..datareader import MarketData
from ..http_resilience import (
    DEFAULT_HTTP_RETRY_POLICY,
    is_transient_http_error,
    retry_http_call,
)
from ..resilience import RetryPolicy, Sleeper
from .context import SourceContext
from .contracts import (
    DataBinding,
    DataSourceComponent,
    MarketDataBundle,
    MarketDataCapability,
)

HistoryLoader = Callable[..., pd.DataFrame]

_SUPPORTED_ADJUSTMENTS = frozenset({"", "qfq", "hfq"})
_PROVIDER_COLUMNS = {
    "tencent": ("date", "close", "volume"),
    "sina": ("date", "close", "volume"),
    "eastmoney": ("日期", "收盘", "成交量"),
}


@dataclass(frozen=True)
class AkShareRoutedAStockDataSourcePlugin:
    """Load SH, SZ, and Beijing history through Tencent market symbols."""

    tencent_history_loader: HistoryLoader | None = field(
        default=None,
        repr=False,
        compare=False,
    )
    sina_history_loader: HistoryLoader | None = field(
        default=None,
        repr=False,
        compare=False,
    )
    eastmoney_history_loader: HistoryLoader | None = field(
        default=None,
        repr=False,
        compare=False,
    )
    request_interval_seconds: float = 0.0
    sleeper: Sleeper = field(default=time.sleep, repr=False, compare=False)
    retry_policy: RetryPolicy = DEFAULT_HTTP_RETRY_POLICY
    default_adjustment: str = "hfq"

    def __post_init__(self) -> None:
        if self.default_adjustment not in _SUPPORTED_ADJUSTMENTS:
            raise ValueError("default_adjustment must be one of: '', qfq, hfq")
        if (
            not isinstance(self.request_interval_seconds, (int, float))
            or isinstance(self.request_interval_seconds, bool)
        ):
            raise TypeError("request_interval_seconds must be a number")
        if self.request_interval_seconds < 0:
            raise ValueError("request_interval_seconds must be non-negative")
        if not callable(self.sleeper):
            raise TypeError("sleeper must be callable")
        if not isinstance(self.retry_policy, RetryPolicy):
            raise TypeError("retry_policy must be a RetryPolicy")

    def load(
        self,
        binding: DataBinding,
        context: SourceContext,
    ) -> MarketDataBundle:
        del context

        if not binding.tickers:
            raise ValueError("routed AkShare source requires DataBinding.tickers")
        if binding.start is None or binding.end is None:
            raise ValueError(
                "routed AkShare source requires DataBinding.start and DataBinding.end"
            )

        adjustment = (
            self.default_adjustment
            if binding.adjustment is None
            else binding.adjustment
        )
        if adjustment not in _SUPPORTED_ADJUSTMENTS:
            raise ValueError(
                "DataBinding.adjustment must be one of: '', qfq, hfq"
            )

        start_date = pd.Timestamp(binding.start).strftime("%Y%m%d")
        end_date = pd.Timestamp(binding.end).strftime("%Y%m%d")
        close_frames: dict[str, pd.Series] = {}
        volume_frames: dict[str, pd.Series] = {}
        providers: set[str] = set()

        for position, ticker in enumerate(binding.tickers):
            if position > 0 and self.request_interval_seconds > 0:
                self.sleeper(float(self.request_interval_seconds))

            provider = "tencent"
            def load_ticker(current_ticker: str = ticker) -> pd.DataFrame:
                loader = self.tencent_history_loader or _tencent_loader
                return loader(
                    symbol=_tencent_symbol(current_ticker),
                    start_date=start_date,
                    end_date=end_date,
                    adjust=adjustment,
                )

            frame = retry_http_call(
                load_ticker,
                label=f"AkShare {provider} history request for {ticker}",
                policy=self.retry_policy,
                sleeper=self.sleeper,
            )
            if isinstance(frame, pd.DataFrame) and frame.empty:
                provider = "sina"

                def load_sina(current_ticker: str = ticker) -> pd.DataFrame:
                    loader = self.sina_history_loader or _sina_loader
                    return loader(
                        symbol=_tencent_symbol(current_ticker),
                        start_date=start_date,
                        end_date=end_date,
                        adjust=adjustment,
                    )

                try:
                    frame = retry_http_call(
                        load_sina,
                        label=f"AkShare {provider} history request for {ticker}",
                        policy=self.retry_policy,
                        sleeper=self.sleeper,
                    )
                except Exception as error:
                    if not _is_provider_unavailable(error):
                        raise
                    frame = pd.DataFrame()

            if isinstance(frame, pd.DataFrame) and frame.empty:
                provider = "eastmoney"

                def load_eastmoney(
                    current_ticker: str = ticker,
                ) -> pd.DataFrame:
                    loader = (
                        self.eastmoney_history_loader
                        or _eastmoney_loader
                    )
                    return loader(
                        symbol=current_ticker,
                        start_date=start_date,
                        end_date=end_date,
                        adjust=adjustment,
                    )

                frame = retry_http_call(
                    load_eastmoney,
                    label=f"AkShare {provider} history request for {ticker}",
                    policy=self.retry_policy,
                    sleeper=self.sleeper,
                )
            providers.add(provider)
            date_column, close_column, volume_column = _provider_columns(
                frame,
                ticker=ticker,
                provider=provider,
            )
            index = pd.DatetimeIndex(
                pd.to_datetime(frame[date_column], errors="raise")
            )
            if index.has_duplicates:
                raise ValueError(
                    f"AkShare {provider} returned duplicate dates for {ticker!r}"
                )

            close_frames[ticker] = pd.Series(
                pd.to_numeric(frame[close_column], errors="raise").to_numpy(),
                index=index,
                name=ticker,
            )
            volume = pd.to_numeric(frame[volume_column], errors="raise")
            if provider == "eastmoney":
                volume = volume * 100
            volume_frames[ticker] = pd.Series(
                volume.to_numpy(),
                index=index,
                name=ticker,
            )

        close = pd.concat(close_frames, axis=1, sort=False).sort_index()
        close = close.sort_index(axis=1)
        volume = pd.concat(volume_frames, axis=1, sort=False).sort_index()
        volume = volume.sort_index(axis=1)

        return MarketDataBundle(
            market=MarketData(close=close, volume=volume),
            calendar=pd.DatetimeIndex(close.index),
            metadata={
                "source_kind": "akshare_routed_a_stock_history",
                "providers": sorted(providers),
                "dataset": binding.dataset,
                "adjustment": adjustment,
                "period": "daily",
                "volume_unit": "share",
                "routing": {
                    "SSE": "tencent",
                    "SZSE": "tencent",
                    "BSE": "tencent",
                },
                "empty_response_fallbacks": ["sina", "eastmoney"],
            },
        )


def create_akshare_routed_a_stock_data_source(
    **params: object,
) -> DataSourceComponent:
    """Create the routed, connection-free A-share history component."""

    retry_policy = params.get("retry_policy")
    if isinstance(retry_policy, Mapping):
        params["retry_policy"] = RetryPolicy(**dict(retry_policy))

    return DataSourceComponent(
        id="akshare_routed_a_stock_daily",
        capabilities=frozenset(
            {MarketDataCapability.CLOSE, MarketDataCapability.VOLUME}
        ),
        plugin=AkShareRoutedAStockDataSourcePlugin(**params),
        metadata={
            "market": "CN",
            "provider": "akshare_routed",
            "frequency": "daily",
        },
        retry_classifier=is_transient_http_error,
    )


def _tencent_symbol(ticker: str) -> str:
    if ticker.startswith("920"):
        return f"bj{ticker}"
    if ticker.startswith(("6", "689")):
        return f"sh{ticker}"
    return f"sz{ticker}"


def _provider_columns(
    frame: object,
    *,
    ticker: str,
    provider: str,
) -> tuple[str, str, str]:
    if not isinstance(frame, pd.DataFrame):
        raise TypeError(
            f"AkShare {provider} returned {type(frame).__name__} for "
            f"ticker {ticker!r}; expected DataFrame"
        )
    if frame.empty:
        raise ValueError(
            f"AkShare {provider} returned no daily data for ticker {ticker!r}"
        )
    required = _PROVIDER_COLUMNS[provider]
    missing = [column for column in required if column not in frame.columns]
    if missing:
        raise ValueError(
            f"AkShare {provider} frame for {ticker!r} is missing required "
            f"columns: {', '.join(missing)}"
        )
    return required


def _akshare():
    try:
        import akshare as ak
    except ImportError as error:
        raise RuntimeError(
            "AkShare support is not installed. Install quantmine with its "
            "'data' extra."
        ) from error
    return ak


def _sina_loader(**kwargs: str) -> pd.DataFrame:
    return _akshare().stock_zh_a_daily(
        symbol=kwargs["symbol"],
        start_date=kwargs["start_date"],
        end_date=kwargs["end_date"],
        adjust=kwargs.get("adjust", ""),
    )


def _eastmoney_loader(**kwargs: str) -> pd.DataFrame:
    return _akshare().stock_zh_a_hist(
        symbol=kwargs["symbol"],
        period="daily",
        start_date=kwargs["start_date"],
        end_date=kwargs["end_date"],
        adjust=kwargs.get("adjust", ""),
    )


def _is_provider_unavailable(error: Exception) -> bool:
    return (
        is_transient_http_error(error)
        or type(error).__name__ == "JSONDecodeError"
    )


def _tencent_loader(**kwargs: str) -> pd.DataFrame:
    try:
        import requests
    except ImportError as error:
        raise RuntimeError(
            "The routed AkShare source requires requests. Install quantmine "
            "with its 'data' extra."
        ) from error

    symbol = kwargs["symbol"]
    adjustment = kwargs.get("adjust", "")
    start = pd.Timestamp(kwargs["start_date"])
    end = pd.Timestamp(kwargs["end_date"])
    rows: list[list[object]] = []

    for first_year in range(start.year, end.year + 1, 2):
        last_year = min(first_year + 1, end.year)
        response = requests.get(
            "https://proxy.finance.qq.com/ifzqgtimg/appstock/app/newfqkline/get",
            params={
                "_var": f"kline_day{adjustment}{first_year}",
                "param": (
                    f"{symbol},day,{first_year}-01-01,"
                    f"{last_year}-12-31,640,{adjustment}"
                ),
                "r": "0.8205512681390605",
            },
            timeout=30,
        )
        response.raise_for_status()
        text = response.text
        if "=" not in text:
            raise ValueError("Tencent history response is not wrapped JSON")
        payload = json.loads(text.split("=", 1)[1])
        symbol_data = payload.get("data", {}).get(symbol, {})
        key = "day" if not adjustment else f"{adjustment}day"
        chunk = symbol_data.get(key, [])
        if not isinstance(chunk, list):
            raise TypeError(
                f"Tencent history response has invalid {key} for {symbol!r}"
            )
        rows.extend(chunk)

    if not rows:
        return pd.DataFrame(columns=list(_PROVIDER_COLUMNS["tencent"]))
    if any(not isinstance(row, list) or len(row) < 6 for row in rows):
        raise ValueError(f"Tencent returned malformed kline data for {symbol!r}")

    frame = pd.DataFrame(
        {
            "date": [row[0] for row in rows],
            "close": pd.to_numeric([row[2] for row in rows], errors="raise"),
            "volume": pd.to_numeric([row[5] for row in rows], errors="raise"),
        }
    )
    if not symbol.startswith(("sh688", "sz399", "sh000", "sz000")):
        frame["volume"] = frame["volume"] * 100
    dates = pd.to_datetime(frame["date"], errors="raise")
    frame = frame.loc[(dates >= start) & (dates <= end)].copy()
    frame["date"] = dates.loc[frame.index]
    return frame.drop_duplicates(subset=["date"], keep="last").reset_index(drop=True)
