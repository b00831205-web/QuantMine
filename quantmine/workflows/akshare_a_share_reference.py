"""Collect and normalize A-share reference data from AkShare"""


from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from ..plugins.a_share import AStockSecurityMaster
from .a_share_reference import AStockReferenceData
from ..http_resilience import retry_http_call

ExchangeListLoader = Callable[[str], pd.DataFrame]
NoArgumentFrameLoader = Callable[[], pd.DataFrame]
_SSE_A_SHARE_DELIST_TYPES = {
    "全部": "1,8",
    "沪市": "1",
    "科创板": "8",
}

@dataclass(frozen = True)
class AkShareAStockReferenceCollector:
    """Collect current and historical A-share listing intervals.

    Shanghai's vendor field is named ``暂停上市日期``. It is treated here as
    the effective end of the tradable listing interval, rather than claiming
    it is always the legal deregistration date.
    """

    sh_loader: ExchangeListLoader | None = field(
        default = None,
        repr = False,
        compare = False,
    )

    sz_loader: ExchangeListLoader | None = field(
        default = None,
        repr = False,
        compare = False,
    )

    bj_loader: NoArgumentFrameLoader | None = field(
        default = None,
        repr = False,
        compare = False,
    )

    sh_delist_loader: ExchangeListLoader | None = field(
        default = None,
        repr = False,
        compare = False,
    )

    sz_delist_loader: ExchangeListLoader | None = field(
        default = None,
        repr = False,
        compare = False,
    )

    calendar_loader: NoArgumentFrameLoader | None = field(
        default = None,
        repr = False,
        compare = False,
    )

    def collect(self) -> AStockReferenceData:
        sh_loader = self.sh_loader or _default_sh_loader
        sz_loader = self.sz_loader or _default_sz_loader
        bj_loader = self.bj_loader or _default_bj_loader
        sh_delist_loader = (
            self.sh_delist_loader or _default_sh_delist_loader
        )
        sz_delist_loader = (
            self.sz_delist_loader or _default_sz_delist_loader
        )
        calendar_loader = (
            self.calendar_loader or _default_calendar_loader
        )

        current_frames = [
            _normalize_current_listings(
                sh_loader("主板A股"),
                code_column = "证券代码",
                list_date_column = "上市日期",
                exchange = "SSE",
                label ="上市所主板当前列表",
                allowed_prefixes = ("6",)
            ),
            _normalize_current_listings(
                sh_loader("科创板"),
                code_column = "证券代码",
                list_date_column = "上市日期",
                exchange = "SSE",
                label ="上交所科创板当前列表",
                allowed_prefixes = ("6",),
            ),
            _normalize_current_listings(
                sz_loader("A股列表"),
                code_column = "A股代码",
                list_date_column ="A股上市日期",
                exchange = "SZSE",
                label = "深交所当前列表",
                allowed_prefixes = ("0", "3"),
            ),
            _normalize_current_listings(
                bj_loader(),
                code_column = "证券代码",
                list_date_column = "上市日期",
                exchange = "BSE",
                label = "北交所当前列表",
                allowed_prefixes = None
            ),
        ]
        historical_frames = [
            _normalize_delisted_listings(
                sh_delist_loader("全部"),
                code_column ="公司代码",
                list_date_column = "上市日期",
                delist_date_column = "暂停上市日期",
                exchange = "SSE",
                label = "上交所历史退出列表",
                allowed_prefixes = ("6",),
            ),
            _normalize_delisted_listings(
                sz_delist_loader("终止上市公司"),
                code_column ="证券代码",
                list_date_column = "上市日期",
                delist_date_column = "终止上市日期",
                exchange = "SZSE",
                label = "深交所历史退市列表",
                allowed_prefixes = ("0","3"),
            )
        ]

        master_frame = pd.concat(
            [*current_frames, *historical_frames],
            ignore_index = True,
        )

        security_master = AStockSecurityMaster.from_frame(
            master_frame
        )
        trading_calendar = _normalize_trading_calendar(
            calendar_loader()
        )

        return AStockReferenceData(
            security_master = security_master,
            trading_calendar = trading_calendar
        )

def _normalize_current_listings(
        frame: pd.DataFrame,
        *,
        code_column: str,
        list_date_column: str,
        exchange: str,
        label: str,
        allowed_prefixes: tuple[str, ...] | None,
) -> pd.DataFrame:
    _require_frame_columns(
        frame,
        required = (code_column, list_date_column),
        label = label,
        allow_empty = False,
    )
    tickers = _normalize_tickers(
        frame[code_column],
        label = label,
    )

    if allowed_prefixes is not None:
        unexpected = ~tickers.str.startswith(allowed_prefixes)
        if unexpected.any():
            values = sorted(tickers.loc[unexpected].unique())
            raise ValueError(
                f"{label} contains non-A-share ticker prefixes: "
                +", ".join(values[:10])
            )
    list_dates = _normalize_dates(
        frame[list_date_column],
        label = f"{label} listing dates"
    )
    return _listing_frame(
        tickers = tickers,
        list_dates = list_dates,
        delist_dates = pd.Series(
            pd.NaT,
            index = frame.index,
            dtype = "datetime64[ns]",
        ),
        exchange = exchange,
    )

def _normalize_delisted_listings(
        frame: pd.DataFrame,
        *,
        code_column: str,
        list_date_column: str,
        delist_date_column: str,
        exchange: str,
        label: str,
        allowed_prefixes: tuple[str, ...],
) -> pd.DataFrame:
    _require_frame_columns(
        frame,
        required = (
            code_column,
            list_date_column,
            delist_date_column,
        ),
        label = label,
        allow_empty = True,
    )

    if frame.empty:
        return _empty_listing_frame()
    tickers = _normalize_tickers(
        frame[code_column],
        label = label,
    )
    a_share_mask = tickers.str.startswith(allowed_prefixes)

    filtered = frame.loc[a_share_mask].copy()
    tickers = tickers.loc[a_share_mask]
    if filtered.empty:
        return _empty_listing_frame()

    list_dates = _normalize_dates(
        filtered[list_date_column],
        label = f"{label} listing dates",
    )
    delist_dates = _normalize_dates(
        filtered[delist_date_column],
        label = f"{label} exist dates"
    )

    return _listing_frame(
        tickers = tickers,
        list_dates = list_dates,
        delist_dates = delist_dates,
        exchange = exchange
    )

def _listing_frame(
        *,
        tickers: pd.Series,
        list_dates: pd.Series,
        delist_dates: pd.Series,
        exchange: str,
) -> pd.DataFrame:
    normalized_tickers = tickers.reset_index(drop = True)
    normalized_list_dates = list_dates.reset_index(drop = True)
    normalized_delist_dates = delist_dates.reset_index(drop = True)

    listing_ids=[
        (
            f"{exchange}:{ticker}:"
            f"{list_date.strftime('%Y%m%d')}"
        )
        for ticker, list_date in zip(
            normalized_tickers,
            normalized_list_dates,
            strict = True,
        )
    ]
    return pd.DataFrame(
        {
            "listing_id": listing_ids,
            "ticker": normalized_tickers,
            "list_date": normalized_list_dates,
            "delist_date": normalized_delist_dates,
            "exchange": exchange,
            "security_type": "COMMON_STOCK"
        }
    )

def _empty_listing_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "listing_id": pd.Series(dtype="string"),
            "ticker": pd.Series(dtype = "string"),
            "list_date": pd.Series(dtype="datetime64[ns]"),
            "exchange": pd.Series(dtype="string"),
            "security_type": pd.Series(dtype = "string")
        }
    )

def _normalize_tickers(
        values: pd.Series,
        *,
        label: str,
) -> pd.Series:
    tickers = (
        values.astype(str).str.strip().str.replace(r"\.0\Z", "", regex = True).str.zfill(6)
    )

    invalid = ~tickers.str.fullmatch(r"\d{6}")
    if invalid.any():
        samples = sorted(tickers.loc[invalid].unique())
        raise ValueError(
            f"{label} contains invalid six-digit tickers: "
            +", ".join(samples[:10])
        )
    return tickers

def _normalize_dates(
        values: pd.Series,
        *,
        label: str,
) -> pd.Series:
    try:
        dates = pd.to_datetime(values, errors = "raise").dt.normalize()

    except (TypeError, ValueError) as error:
        raise ValueError(
            f"{label} contain invalid dates"
        ) from error

    if dates.isna().any():
        raise ValueError(
            f"{label} contain missing dates"
        )

    if dates.dt.tz is not None:
        dates = dates.dt.tz_localize(None)

    return dates

def _normalize_trading_calendar(
        frame: pd.DataFrame,
) -> pd.DatetimeIndex:
    _require_frame_columns(
        frame,
        required = ("trade_date",),
        label = "AkShare trading calendar",
        allow_empty = False,
    )

    try: 
        calendar = pd.DatetimeIndex(
            pd.to_datetime(
                frame["trade_date"],
                errors = "raise",
            )
        ).normalize()

    except (TypeError, ValueError) as error:
        raise ValueError(
            "AkShare trading calendar contains invalid dates"
        ) from error

    if calendar.tz is not None:
        calendar = calendar.tz_localize(None)

    if calendar.hasnans:
        raise ValueError(
            "AkShare trading calendar contains missing dates"
        )

    if calendar.has_duplicates:
        raise ValueError(
            "AkShare trading calendar contains duplicate dates"
        )
    return calendar.sort_values()

def _require_frame_columns(
        frame: pd.DataFrame,
        *,
        required: tuple[str, ...],
        label: str,
        allow_empty: bool,
) -> None:
    if not isinstance(frame, pd.DataFrame):
        raise TypeError(
            f"{label} loader must return a pandas DataFrame"
        )
    missing = [
        column for column in required if column not in frame.columns
    ]
    if missing:
        raise ValueError(
            f"{label} is missing required columns: "
            +", ".join(missing)
        )

    if frame.empty and not allow_empty:
        raise ValueError(f"{label} must not be empty")

def _akshare() -> Any:
    try:
        import akshare as ak

    except ImportError as error:
        raise RuntimeError(
            "AkShare reference collection requires the 'data' extra"
        ) from error

    return ak

def _default_sh_loader(symbol: str) -> pd.DataFrame:
    return retry_http_call(
        lambda: _akshare().stock_info_sh_name_code(
            symbol = symbol
        ),
        label = f"AkShare SSE current listings ({symbol})"
    )

def _default_sh_delist_loader(symbol:str) -> pd.DataFrame:
    """Load SSE delisted A shares without losing the upstream stock type."""

    try:
        stock_types = _SSE_A_SHARE_DELIST_TYPES[symbol]
    except KeyError as error:
        supported = ", ".join(_SSE_A_SHARE_DELIST_TYPES)
        raise ValueError(
            f"unsupported SSE delisted-list symbol {symbol!r}; "
            f"expected one of: {supported}"
        ) from error

    try: 
        import requests
    except ImportError as error:
        raise RuntimeError(
            "SSE reference collection requires the 'data' extra"
        ) from error

    def request_sse_delisted_list():
        response = requests.get(
            "https://query.sse.com.cn/commonQuery.do",
            params = {
                "sqlId": "COMMON_SSE_CP_GPJCTPZ_GPLB_GP_L",
                "isPagination": "true",
                "STOCK_CODE": "",
                "CSRC_CODE": "",
                "REG_PROVINCE": "",
                "STOCK_TYPE": stock_types,
                "COMPANY_STATUS": "3",
                "type": "inParams",
                "pageHelp.cacheSize": "1",
                "pageHelp.beginPage": "1",
                "pageHelp.pageSize": "500",
                "pageHelp.pageNo": "1",
                "pageHelp.endPage": "1",
            },
            headers = {
                "Accept": "*/*",
                "Referer": "https://www.sse.com.cn/",
                "User-Agent": "Mozilla/5.0",
            },
            timeout = 30,
        )
        response.raise_for_status()
        return response

    response = retry_http_call(
        request_sse_delisted_list,
        label = "SSE official delisted A-share listings"
    )
    payload = response.json()
    if not isinstance(payload, dict):
        raise TypeError(
            "SSE delisted-list response must be a JSON object"
        )

    rows = payload.get("result")
    if not isinstance(rows, list):
        raise TypeError(
            "SSE delisted-list response is missing the result list"
        )

    output_columns = [
        "公司代码",
        "公司简称",
        "上市日期",
        "暂停上市日期",
    ]
    if not rows:
        return pd.DataFrame(columns = output_columns)

    raw = pd.DataFrame(rows)
    required_columns = (
        "A_STOCK_CODE",
        "COMPANY_ABBR",
        "LIST_DATE",
        "DELIST_DATE",
        "STOCK_TYPE",
    )
    missing = [
        column for column in required_columns if column not in raw.columns
    ]
    if missing:
        raise ValueError(
            "SSE delisted-list response is missing required fields: " + ", ".join(missing)
        )
    allowed_types = set(stock_types.split(","))
    returned_types = set(
        raw["STOCK_TYPE"].astype(str).str.strip()
    )
    unexpected_types = sorted(returned_types - allowed_types)
    if unexpected_types:
        raise ValueError(
            "SSE delisted-list response contains unexpected stock types: "
            +", ".join(unexpected_types)
        )

    return (
        raw.loc[:, ["A_STOCK_CODE", "COMPANY_ABBR", "LIST_DATE", "DELIST_DATE"],]
        .rename(
            columns = {
                "A_STOCK_CODE": "公司代码",
                "COMPANY_ABBR": "公司简称",
                "LIST_DATE": "上市日期",
                "DELIST_DATE": "暂停上市日期",
            }
        )
        .reset_index(drop=True)
    )

def _default_sz_loader(symbol: str) -> pd.DataFrame:
    return retry_http_call(
        lambda: _akshare().stock_info_sz_name_code(
            symbol = symbol
        ),
        label = f"AkShare SZSE current listings ({symbol})"
    )

def _default_bj_loader() -> pd.DataFrame:
    return retry_http_call(
        lambda: _akshare().stock_info_bj_name_code(),
        label= "AkShare BSE current listings"
    )

def _default_sz_delist_loader(symbol: str) -> pd.DataFrame:
    return retry_http_call(
        lambda: _akshare().stock_info_sz_delist(
            symbol = symbol
        ),
        label = f"AkShare SZSE delisted listings ({symbol})"
    )

def _default_calendar_loader() -> pd.DataFrame:
    return retry_http_call(
        lambda: _akshare().tool_trade_date_hist_sina(),
        label = "AkShare trading calendar"
    )
