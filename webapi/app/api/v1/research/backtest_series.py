from datetime import date
from sqlalchemy import MetaData, Table, select
from sqlalchemy.engine import Engine
from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.v1.research.results import research_run_exists
from app.dependencies import get_request_engine
from app.schemas import BacktestSeriesResponse

router = APIRouter()

def build_backtest_series(
        rows: list[dict],
) -> tuple[date| None, list[dict]]:
    grouped: dict[int, list[dict]] = {}
    for row in rows:
        if row['return_value'] is None:
            continue

        rank = row['quantile_rank']
        grouped.setdefault(rank, []).append(row)

    if not grouped:
        return None, []

    series = []
    base_date: date| None = None

    for rank in sorted(grouped, key = lambda value: (value!=0, value)):
        level = 100.0
        points = []

        for row in sorted(grouped[rank], key = lambda value: value['trade_date']):
            level *= 1+ float(row['return_value'])
            trade_date = row['trade_date']
            if base_date is None or trade_date < base_date:
                base_date = trade_date

            points.append({
                'date': trade_date,
                'value': level,
            }
            )
        symbol = 'Long-Short' if rank == 0 else f'Q{rank}'
        series.append({'symbol': symbol, 'points': points})
    return base_date, series

def fetch_backtest_return_rows(
        engine: Engine,
        *,
        run_id: int,
        variant: str,
        backtest_id: str,
        test_id: str,
        factor_name:str,
        period: int,
)-> list[dict]:
    metadata = MetaData()
    table = Table('backtest_results', metadata, autoload_with= engine)

    statement = (
        select(table.c.trade_date,
               table.c.quantile_rank,
               table.c.return_value,
               ).where(table.c.run_id == run_id,
                       table.c.variant_name == variant,
                       table.c.backtest_id == backtest_id,
                       table.c.test_id == test_id,
                       table.c.factor_name == factor_name,
                       table.c.period == period
                ).order_by(table.c.trade_date.asc(), table.c.quantile_rank.asc())
    )
    with engine.connect() as connection:
        rows = connection.execute(statement).mappings().all()
    return [dict(row) for row in rows]

@router.get('/research/backtest-series', response_model = BacktestSeriesResponse,)
async def get_backtest_series(
    run_id: int = Query(...,alias = 'runId'),
    variant: str = Query(...),
    backtest_id: str = Query(...,alias='backtestId'),
    test_id: str = Query(..., alias = 'testId'),
    factor_name: str=Query(...,alias = 'factorName'),
    period: int = Query(...,ge=1),
    engine: Engine = Depends(get_request_engine)
) -> BacktestSeriesResponse:
    if not research_run_exists(engine, run_id):
        raise HTTPException(status_code= 404, detail = 'research run not found')

    rows = fetch_backtest_return_rows(engine,
                                      run_id=run_id,
                                      variant=variant,
                                      backtest_id=backtest_id,
                                      test_id=test_id,
                                      factor_name=factor_name,
                                      period = period)
    base_date, series = build_backtest_series(rows)

    return BacktestSeriesResponse(
        baseDate = base_date,
        series = series,
    )