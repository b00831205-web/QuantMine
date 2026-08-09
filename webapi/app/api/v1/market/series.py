"""行情查询端点：多 ticker 时间序列、最新交易日与市场宽度。"""

from __future__ import annotations
from fastapi import Depends
from sqlalchemy.engine import Engine
import datetime as dt
import pandas as pd

from datetime import date

from fastapi import APIRouter, Query, HTTPException

from ....schemas import (
    MarketLatestDateResponse,
    MarketOverviewResponse,
    SeriesEntry,
    SeriesPoint,
    SeriesResponse,
)

from quantmine.storage.market import (
    fetch_latest_market_trade_date,
    fetch_market_bars,
    fetch_market_breadth,
    switch_to_month,
    switch_to_week,
)
from ....dependencies import get_request_engine

router = APIRouter()


@router.get("/market/series", response_model=SeriesResponse, summary="多 ticker 时间序列")
async def get_market_series(
    symbols: list[str] = Query(
        ...,
        min_length=1,
        max_length=20,
        description="ticker 列表，重复 key 传多个值",
    ),
    start_date: date = Query(..., alias="startDate", description="起日 YYYY-MM-DD"),
    end_date: date = Query(..., alias="endDate", description="止日 YYYY-MM-DD"),
    frequency: str = Query("D", pattern="^[DWM]$", description="D/W/M"),
    normalize: bool = Query(True, description="是否归一化到基期 100"),
    engine: Engine = Depends(get_request_engine)
) -> SeriesResponse:
    """查询多 ticker 时间序列，按区间与频率返回。

    ticker 去重并统一大写后查询；frequency 为 W/M 时按周/月重采样。
    normalize 为真时各序列归一化到基期 100，便于同图比较走势。

    Raises:
        HTTPException: start_date 晚于 end_date 或 ticker 超过 20 个时 422；
            区间内无数据时 404。
    """
    if start_date > end_date:
        raise HTTPException(status_code=422, detail='start_date cannot be later than end_date')
    tickers = list(dict.fromkeys(ticker.upper() for ticker in symbols))
    if len(tickers) > 20:
        raise HTTPException(status_code = 422, detail= 'numbers of ticker out of range, max_length = 20')

    result_dataframe = fetch_market_bars(engine, symbols=tickers, start_date=start_date, end_date=end_date)
    if result_dataframe.empty:
        raise HTTPException(status_code=404, detail="No market bars found")

    if frequency == 'W':
        result = switch_to_week(result_dataframe)

    elif frequency == 'D':
        result = result_dataframe

    else:
        result = switch_to_month(result_dataframe)

    series_result = []
    for ticker in tickers:
        ticker_result = result.loc[result['ticker'] == ticker].copy().sort_values('trade_date')
        if ticker_result.empty:
            raise HTTPException(status_code= 404, detail= f'cannot found info for ticker {ticker}')
        if normalize:
            ticker_result['value'] = ticker_result['close']/ticker_result['close'].iloc[0]*100
        else: 
            ticker_result['value'] = ticker_result['close']
        points = [
        SeriesPoint(
            date=row["trade_date"],
            value=float(row["value"]),
        )
        for row in ticker_result[["trade_date", "value"]].to_dict(orient="records")
        ]

        series_result.append(
            SeriesEntry(
                symbol=ticker,
                points=points,
            )
        )
    return SeriesResponse(base_date = start_date, series = series_result)

@router.get('/market/latest-date', response_model=MarketLatestDateResponse)
async def get_lastest_date(engine: Engine = Depends(get_request_engine)):
    result = fetch_latest_market_trade_date(engine)
    if result is None:
        raise HTTPException(status_code= 404, detail = 'latest date not found')
    else:
        return MarketLatestDateResponse(latest_trade_date=result)


@router.get("/market/overview", response_model=MarketOverviewResponse)
async def get_market_overview(engine: Engine = Depends(get_request_engine)):
    result = fetch_market_breadth(engine)
    if result is None:
        raise HTTPException(status_code=404, detail="market breadth not found")
    return MarketOverviewResponse(
        latest_trade_date=result["latest_date"],
        advancers=result["advancers"],
        decliners=result["decliners"],
        total=result["total"],
        breadth=result["breadth"],
    )
