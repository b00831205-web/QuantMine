"""GET /api/v1/market/series — 多 ticker 时间序列查询。

阶段 0 仅固化契约，handler 函数体留 TODO(USER_LEARNING)。
"""

from __future__ import annotations
from fastapi import Depends
from sqlalchemy.engine import Engine
import datetime as dt
import pandas as pd

from datetime import date

from fastapi import APIRouter, Query, HTTPException

from ....schemas import SeriesResponse, SeriesEntry, SeriesPoint, MarketLatestDateResponse

from quantmine.storage.market import fetch_market_bars, switch_to_week, switch_to_month, fetch_latest_market_trade_date
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

    TODO(USER_LEARNING):
        目标：实现参数校验后的查询逻辑，返回 SeriesResponse；
        输入：symbols / start_date / end_date / frequency / normalize；
        输出：SeriesResponse（baseDate + series[]）；
        约束：
          ① start_date ≤ end_date；区间过长应考虑降采样或 422；
          ② symbols 必须为大写；建议在调用服务前归一化；
          ③ 不要直接连数据库；调用占位 service 或返回明确 TODO 错误；
          ④ 必须使用统一错误格式（raise HTTPException 或 api_error_response）。
        提示：① 当前服务层尚未实现，可先 raise 501；
              ② 后续接 storage.market.get_series(...)；
              ③ 频率 frequency 与 quantmine/storage/market.py 对齐。
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