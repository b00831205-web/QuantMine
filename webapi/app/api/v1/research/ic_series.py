from datetime import date
from fastapi import APIRouter, Depends,  HTTPException, Query
from sqlalchemy.engine import Engine

from app.api.v1.research.results import research_run_exists
from app.dependencies import get_request_engine
from app.schemas import IcSeriesResponse
from quantmine.storage.ic import load_ic_variants

import pandas as pd

router = APIRouter()
def build_ic_series(
        frame: pd.DataFrame,
        *,
        factor_name: str,
        period: int,
) -> tuple[date|None, list[dict]]:
    if (factor_name, period) not in frame.columns:
        return None, []

    values = frame[(factor_name, period)].dropna()

    if values.empty:
        return None, []
    points = [{
        'date': pd.Timestamp(trade_date).date(),
        'value': float(ic_value),
    
    }for trade_date, ic_value in values.items()]
    base_date = points[0]['date']
    return base_date , [{'symbol':'IC', 'points': points}]

@router.get('/research/ic-series', response_model =  IcSeriesResponse)
async def get_ic_series(
    run_id: int = Query(..., alias = 'runId'),
    variant: str = Query(...),
    sample_scope: str = Query(..., alias = 'sampleScope'),
    factor_name: str = Query(..., alias = 'factorName'),
    period: int = Query(...,ge =1),
    engine: Engine = Depends(get_request_engine)
)-> IcSeriesResponse:
    if not research_run_exists(engine, run_id):
        raise HTTPException(status = 404, detail='Research run not found')

    variants = load_ic_variants(engine, run_id)
    selected_variant = variants.get(variant)

    if selected_variant is None or sample_scope not in {'train', 'test'}:
        return IcSeriesResponse(baseDate=None, series=[])

    scope = getattr(selected_variant, sample_scope)
    frame = scope.get('cs_ic')

    if not isinstance(frame, pd.DataFrame):
        return IcSeriesResponse(baseDate=None, series=[])

    base_date, series= build_ic_series(frame,
                                       factor_name = factor_name,
                                       period = period,
                                       )
    return IcSeriesResponse(baseDate=base_date, series = series)