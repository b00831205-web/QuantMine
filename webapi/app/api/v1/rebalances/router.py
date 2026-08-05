"""Rebalance endpoints：列表 / 收益曲线（详情待续）。"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.engine import Engine

from datetime import date

from ....dependencies import get_request_engine
from .db import (
    count_rebalance_rows,
    fetch_rebalance_return_rows,
    fetch_rebalance_rows,
    fetch_rebalance_detail_row,
    fetch_next_rebalance_date,
    fetch_market_closes,
)
from .holdings import fetch_holdings, resolve_ticker_history_path
from .series import build_return_series, parse_rebalance_id, build_contributions

router = APIRouter()


def rank_suffix(rank: int) -> str:
    """0 → LS（多空），其余 → Q1..Q5"""
    return "LS" if rank == 0 else f"Q{rank}"


@router.get("/rebalances")
def get_rebalances(
    backtest_job: str | None = Query(None, alias="backtestJob"),
    variant: str | None = Query(None),
    factor: str | None = Query(None),
    trade_date: date | None = Query(None, alias="tradeDate"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    engine: Engine = Depends(get_request_engine),
):
    rows = fetch_rebalance_rows(
        engine,
        backtest_job=backtest_job,
        variant=variant,
        factor=factor,
        trade_date=trade_date,
        page=page,
        page_size=page_size,
    )
    items = [
        {
            "rebalanceId": (
                f"{r['run_id']}__{r['backtest_id']}__{r['variant_name']}__{r['factor_name']}"
                f"__{r['period']}d__{r['trade_date']}__"
                f"{rank_suffix(r['quantile_rank'])}"
            ),
            "backtestJob": r["backtest_id"],
            "variant": r["variant_name"],
            "factor": r["factor_name"],
            "holdingPeriod": r["period"],
            "type": "long_short" if r["quantile_rank"] == 0 else "quantile",
            "quantile": rank_suffix(r["quantile_rank"]),
            "rebalanceDate": str(r["trade_date"]),
            "netReturn": r["return_value"],
            "spyReturn": None,
            "excessReturn": None,
            "turnover": None,
            "holdingsCount": None,
            "tradingDaysToNext": None,
            "unit": "decimal",
        }
        for r in rows
    ]
    total = count_rebalance_rows(
        engine,
        backtest_job=backtest_job,
        variant=variant,
        factor=factor,
        trade_date=trade_date,
    )
    return {"items": items, "total": total, "page": page, "pageSize": page_size}


@router.get("/rebalances/{rebalance_id}/returns")
def get_rebalance_returns(
    rebalance_id: str,
    engine: Engine = Depends(get_request_engine),
):
    try:
        ident = parse_rebalance_id(rebalance_id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail="Rebalance not found") from error

    rows = fetch_rebalance_return_rows(
        engine,
        backtest_id=ident["backtest_id"],
        variant_name=ident["variant_name"],
        factor_name=ident["factor_name"],
        period=ident["period"],
        quantile_rank=ident["quantile_rank"],
    )
    return {"series": build_return_series(rows)}

@router.get('/rebalances/{rebalance_id}')
def get_rebalance_detail(
    rebalance_id: str,
    engine: Engine = Depends(get_request_engine),
): 
    try:
        ident = parse_rebalance_id(rebalance_id)
    except ValueError as error:
        raise HTTPException(status_code= 404, detail = 'Rebalance not found') from error

    row = fetch_rebalance_detail_row(engine, **ident)
    if row is None:
        raise HTTPException(status_code= 404, detail = 'Rebalance not found')

    path = resolve_ticker_history_path(
        run_id=ident['run_id'],
        backtest_id=ident['backtest_id'],
        factor_name=ident['factor_name'],
        period=ident['period'],
    )
    holdings = (
        fetch_holdings(path, ident['trade_date'], ident['quantile_rank'])
        if path else []
    )
    next_date = fetch_next_rebalance_date(engine, **ident)

    closes=[]
    if holdings and next_date is not None:
        closes = fetch_market_closes(
            engine,
            [h['symbol'] for h in holdings],
            [date.fromisoformat(ident['trade_date']),next_date]
        )
    contributions = build_contributions(
        holdings,
        closes,
        ident['trade_date'],
        str(next_date) if next_date else None,
    )

    summary = {
        'rebalanceId': rebalance_id,
        'backtestJob': row['backtest_id'],
        'variant': row['variant_name'],
        'factor': row['factor_name'],
        'holdingPeriod': row['period'],
        'type': 'long_short' if row['quantile_rank'] == 0 else 'quantile',
        'rebalanceDate': str(row['trade_date']),
        'netReturn': row['return_value'],
        'spyReturn': None,
        'excessReturn': None,
        'turnover': None,
        'holdingsCount': len(holdings),
        'tradingDaysToNext': None,
        'unit': 'decimal',
    }
    return {
        **summary,
        'asOfDate': str(row['trade_date']),
        'holdings': holdings,
        'contributions': contributions,
    }
