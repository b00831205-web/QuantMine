"""单只股票端到端测试：data_acquisition 抓取 + 市值计算。

需要网络（yfinance）。运行：
    ./webapi/.venv/bin/python -m pytest test/test_market_cap_acquisition.py -v
"""

import pandas as pd
import pytest
import yfinance as yf

from quantmine.data_acquisition import data_acquisition

START = "2024-01-02"
END = "2024-03-01"


@pytest.mark.network
def test_single_ticker_market_cap_acquisition():
    close, volume, shares, market_cap = data_acquisition(
        tickers=["AAPL"],
        start_date=START,
        end_date=END,
        batch_size=1,
        max_retries=1,
        wait=1,
        checkpoint_dir="tmp/checkpoint_test",
        batch_wait=0,
    )

    # 1) 返回四个 date × ticker 表，列名正确
    for frame in (close, volume, shares, market_cap):
        assert isinstance(frame, pd.DataFrame)
    assert list(close.columns) == ["AAPL"]
    assert list(shares.columns) == ["AAPL"]
    assert list(market_cap.columns) == ["AAPL"]
    assert len(close) > 0
    assert len(market_cap) > 0

    # 2) 行情非空
    assert close["AAPL"].notna().sum() > 0
    assert volume["AAPL"].notna().sum() > 0

    # 3) 股本有值且量级合理（AAPL 流通股约 150 亿股）
    shares_valid = shares["AAPL"].dropna()
    assert len(shares_valid) > 0
    assert (shares_valid > 1e9).all()

    # 4) 市值 = 未复权收盘价 × 当日生效流通股（point-in-time 精确核对）
    raw = yf.download(
        ["AAPL"], start=START, end=END,
        auto_adjust=False, progress=False, threads=False, timeout=30,
    )
    if isinstance(raw.columns, pd.MultiIndex):
        unadjusted = raw["Close"].iloc[:, 0]
    else:
        unadjusted = raw["Close"]
    unadjusted = unadjusted.reindex(shares.index)
    expected = unadjusted * shares["AAPL"]

    merged = pd.concat(
        [market_cap["AAPL"].rename("cap"), expected.rename("expected")],
        axis=1,
    ).dropna()
    assert len(merged) > 0
    pd.testing.assert_series_equal(
        merged["cap"],
        merged["expected"],
        check_names=False,
        rtol=1e-6,
    )
