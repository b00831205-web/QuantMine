"""单股票完整链路测试：抓取 → 落库 → 市值列验证。

只用 AAPL 一只股票 + 短窗口，避免触发 Yahoo 限流。
会写入一个测试 research run 并 upsert AAPL 的 market_bars（含市值列）。

运行（先加载 .env 的数据库连接）：
    cd /mnt/e/Handout/project/project_quant/quant-factor-mining
    export $(grep -v '^#' .env | xargs)
    ./.venv/bin/python -m pytest test/test_market_cap_pipeline.py -v
"""

import pandas as pd
import pytest
from sqlalchemy import MetaData, Table, select

from quantmine.data_acquisition import data_acquisition
from quantmine.storage.database import get_engine
from quantmine.storage.runs import create_run
from quantmine.storage.market import build_latest_snapshot, build_market_bars
from quantmine.workflows.market import save_daily_market_data

START = "2024-01-02"
END = "2024-01-10"


@pytest.mark.network
def test_single_ticker_market_cap_pipeline():
    engine = get_engine()

    # 1) 抓取：一只股票，短窗口；shares 从 2015 起拉全量披露
    close, volume, shares, market_cap = data_acquisition(
        tickers=["AAPL"],
        start_date=START,
        end_date=END,
        batch_size=1,
        max_retries=1,
        wait=1,
        checkpoint_dir="tmp/checkpoint_test_pipeline",
        batch_wait=0,
        shares_start_date="2015-01-01",
    )

    assert list(close.columns) == ["AAPL"]
    assert len(close) > 0
    assert shares["AAPL"].notna().sum() > 0, "AAPL 流通股应抓到历史披露"
    assert market_cap["AAPL"].notna().sum() > 0, "市值应为正数且非空"

    # 2) 落库：测试 run + market_bars（含 shares_outstanding / market_cap）
    run_id = create_run(engine, {"test": "market_cap_pipeline"})
    result = save_daily_market_data(
        engine, close, volume, run_id,
        shares=shares, market_cap=market_cap,
    )
    assert result["bars_written"] > 0

    # 3) 验证：最新 AAPL 行的两列有值，市值为正
    table = Table("market_bars", MetaData(), autoload_with=engine)
    statement = (
        select(
            table.c.trade_date,
            table.c.shares_outstanding,
            table.c.market_cap,
        )
        .where(table.c.ticker == "AAPL", table.c.source_run_id == run_id)
        .order_by(table.c.trade_date.desc())
        .limit(1)
    )
    with engine.connect() as conn:
        row = conn.execute(statement).mappings().first()

    assert row is not None, "market_bars 应有 AAPL 数据"
    assert row["shares_outstanding"] is not None, "shares_outstanding 不应为空"
    assert row["market_cap"] is not None, "market_cap 不应为空"
    assert float(row["market_cap"]) > 0

    # 4) 快照层：build_latest_snapshot 必须把两列带上（共享库 market_latest
    #    有 trade_date>= 门槛，读回不稳，故直接断言纯函数输出）
    bars = build_market_bars(close, volume, run_id, shares=shares, market_cap=market_cap)
    snapshot = build_latest_snapshot(bars)
    assert "shares_outstanding" in snapshot.columns
    assert "market_cap" in snapshot.columns
    assert snapshot["shares_outstanding"].notna().all(), "快照 shares 不应为空"
    assert (snapshot["market_cap"] > 0).all(), "快照市值应为正"
