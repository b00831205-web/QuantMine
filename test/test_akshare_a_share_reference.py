"""AkShare normalization for A-share reference data."""

import sys
from types import ModuleType

import pandas as pd
import pytest

from quantmine.workflows.akshare_a_share_reference import (
    AkShareAStockReferenceCollector,
    _default_sh_delist_loader,
)


def _collector(**overrides) -> AkShareAStockReferenceCollector:
    loaders = {
        "sh_loader": lambda symbol: pd.DataFrame(
            {
                "证券代码": ["600001"] if symbol == "主板A股" else ["688001"],
                "证券简称": ["上证主板"] if symbol == "主板A股" else ["科创公司"],
                "上市日期": ["1998-01-01"] if symbol == "主板A股" else ["2020-01-01"],
            }
        ),
        "sz_loader": lambda symbol: pd.DataFrame(
            {
                "A股代码": ["000001"],
                "A股简称": ["深证公司"],
                "A股上市日期": ["1991-04-03"],
            }
        ),
        "bj_loader": lambda: pd.DataFrame(
            {
                "证券代码": ["430001"],
                "证券简称": ["北证公司"],
                "上市日期": ["2022-01-01"],
            }
        ),
        "sh_delist_loader": lambda symbol: pd.DataFrame(
            {
                "公司代码": ["600002", "900901"],
                "公司简称": ["上证退市", "上证B股"],
                "上市日期": ["1998-04-08", "1995-01-01"],
                "暂停上市日期": ["2006-04-24", "2010-01-01"],
            }
        ),
        "sz_delist_loader": lambda symbol: pd.DataFrame(
            {
                "证券代码": ["000003", "200003"],
                "证券简称": ["深证退市", "深证B股"],
                "上市日期": ["1991-01-14", "1992-01-01"],
                "终止上市日期": ["2002-06-14", "2003-01-01"],
            }
        ),
        "calendar_loader": lambda: pd.DataFrame(
            {"trade_date": ["2026-09-02", "2026-09-01"]}
        ),
    }
    loaders.update(overrides)
    return AkShareAStockReferenceCollector(**loaders)


def test_collector_normalizes_current_and_delisted_a_share_intervals() -> None:
    reference = _collector().collect()

    master = reference.security_master.to_frame()
    assert master[["ticker", "exchange", "delist_date"]].to_dict(
        "records"
    ) == [
        {
            "ticker": "000001",
            "exchange": "SZSE",
            "delist_date": pd.NaT,
        },
        {
            "ticker": "000003",
            "exchange": "SZSE",
            "delist_date": pd.Timestamp("2002-06-14"),
        },
        {
            "ticker": "430001",
            "exchange": "BSE",
            "delist_date": pd.NaT,
        },
        {
            "ticker": "600001",
            "exchange": "SSE",
            "delist_date": pd.NaT,
        },
        {
            "ticker": "600002",
            "exchange": "SSE",
            "delist_date": pd.Timestamp("2006-04-24"),
        },
        {
            "ticker": "688001",
            "exchange": "SSE",
            "delist_date": pd.NaT,
        },
    ]
    assert master["listing_id"].tolist() == [
        "SZSE:000001:19910403",
        "SZSE:000003:19910114",
        "BSE:430001:20220101",
        "SSE:600001:19980101",
        "SSE:600002:19980408",
        "SSE:688001:20200101",
    ]
    assert master["security_type"].eq("COMMON_STOCK").all()
    assert reference.trading_calendar.tolist() == [
        pd.Timestamp("2026-09-01"),
        pd.Timestamp("2026-09-02"),
    ]


def test_collector_uses_explicit_exchange_categories() -> None:
    calls: list[tuple[str, str]] = []

    def sh_loader(symbol: str) -> pd.DataFrame:
        calls.append(("sh", symbol))
        return pd.DataFrame(
            {
                "证券代码": ["600001" if symbol == "主板A股" else "688001"],
                "证券简称": ["主板公司" if symbol == "主板A股" else "科创公司"],
                "上市日期": ["1998-01-01" if symbol == "主板A股" else "2020-01-01"],
            }
        )

    collector = _collector(sh_loader=sh_loader)
    collector.collect()

    assert calls == [("sh", "主板A股"), ("sh", "科创板")]


def test_collector_rejects_incomplete_vendor_frames() -> None:
    collector = _collector(
        sz_loader=lambda symbol: pd.DataFrame(
            {"A股代码": ["000001"]}
        )
    )

    with pytest.raises(ValueError, match="深交所当前列表.*A股上市日期"):
        collector.collect()


def _install_fake_requests(
    monkeypatch: pytest.MonkeyPatch,
    payload: object,
) -> dict[str, object]:
    observed: dict[str, object] = {}

    class _Response:
        def raise_for_status(self) -> None:
            observed["status_checked"] = True

        def json(self) -> object:
            return payload

    requests = ModuleType("requests")

    def get(url, *, params, headers, timeout):
        observed.update(
            {
                "url": url,
                "params": params,
                "headers": headers,
                "timeout": timeout,
            }
        )
        return _Response()

    requests.get = get
    monkeypatch.setitem(sys.modules, "requests", requests)
    return observed


def test_sse_delist_loader_requests_only_a_share_stock_types(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed = _install_fake_requests(
        monkeypatch,
        {
            "result": [
                {
                    "A_STOCK_CODE": "600190",
                    "COMPANY_ABBR": "退市锦港",
                    "LIST_DATE": "19990609",
                    "DELIST_DATE": "20250728",
                    "STOCK_TYPE": "1",
                },
                {
                    "A_STOCK_CODE": "688555",
                    "COMPANY_ABBR": "退市科创",
                    "LIST_DATE": "20200101",
                    "DELIST_DATE": "20250101",
                    "STOCK_TYPE": "8",
                },
            ]
        },
    )

    frame = _default_sh_delist_loader("全部")

    assert observed["status_checked"] is True
    assert observed["params"]["STOCK_TYPE"] == "1,8"
    assert observed["timeout"] == 30
    assert frame.to_dict("records") == [
        {
            "公司代码": "600190",
            "公司简称": "退市锦港",
            "上市日期": "19990609",
            "暂停上市日期": "20250728",
        },
        {
            "公司代码": "688555",
            "公司简称": "退市科创",
            "上市日期": "20200101",
            "暂停上市日期": "20250101",
        },
    ]


def test_sse_delist_loader_rejects_b_share_rows_returned_by_upstream(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_requests(
        monkeypatch,
        {
            "result": [
                {
                    "A_STOCK_CODE": "600190",
                    "COMPANY_ABBR": "退市锦港",
                    "LIST_DATE": "19980519",
                    "DELIST_DATE": "20250728",
                    "STOCK_TYPE": "2",
                }
            ]
        },
    )

    with pytest.raises(ValueError, match="unexpected stock types: 2"):
        _default_sh_delist_loader("全部")


def test_sse_delist_loader_rejects_incomplete_response_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_requests(
        monkeypatch,
        {
            "result": [
                {
                    "A_STOCK_CODE": "600190",
                    "COMPANY_ABBR": "退市锦港",
                    "LIST_DATE": "19990609",
                    "STOCK_TYPE": "1",
                }
            ]
        },
    )

    with pytest.raises(ValueError, match="DELIST_DATE"):
        _default_sh_delist_loader("全部")
