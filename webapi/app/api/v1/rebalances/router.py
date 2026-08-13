"""Rebalance endpoints: list / return curves (detail pending)."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.engine import Engine

from datetime import date

from ....dependencies import get_request_engine
from .db import (
    count_rebalance_rows,
    fetch_holdings_count_map,
    fetch_rebalance_return_rows,
    fetch_rebalance_rows,
    fetch_rebalance_detail_row,
    fetch_next_rebalance_date,
    fetch_market_closes,
    fetch_next_dates_map,
    fetch_spy_closes,
    fetch_turnover_excess_map,
)
from .holdings import fetch_holdings, resolve_ticker_history_path
from .series import build_return_series, parse_rebalance_id, build_contributions

router = APIRouter()


def rank_suffix(rank: int) -> str:
    """0 -> LS (long-short), otherwise -> Q1..Q5"""
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
    run_ids = {r["run_id"] for r in rows}
    metrics_map = fetch_turnover_excess_map(engine, run_ids)
    next_dates_map = fetch_next_dates_map(engine)
    holdings_count_map = fetch_holdings_count_map(engine, run_ids)

    all_dates = {r["trade_date"] for r in rows}
    all_dates |= {d for d in next_dates_map.values() if d is not None}
    spy_closes = fetch_spy_closes(engine, all_dates)

    items = []
    for r in rows:
        metric_key = (
            r["run_id"], r["backtest_id"], r["variant_name"],
            r["factor_name"], r["period"], r["quantile_rank"],
        )
        next_key = (*metric_key, str(r["trade_date"]))
        metrics = metrics_map.get(metric_key, {})
        next_date = next_dates_map.get(next_key)
        spy_cur = spy_closes.get(r["trade_date"])
        spy_next = spy_closes.get(next_date) if next_date else None
        spy_return = (spy_next / spy_cur - 1) if (spy_cur and spy_next) else None
        net_return = r["return_value"]
        excess_return = (
            net_return - spy_return
            if (net_return is not None and spy_return is not None)
            else None
        )
        trading_days = (next_date - r["trade_date"]).days if next_date else None

        items.append({
            "rebalanceId": (
                f"{r['run_id']}__{r['backtest_id']}__{r['variant_name']}__{r['factor_name']}"
                f"__{r['period']}d__{r['trade_date']}__"
                f"{rank_suffix(r['quantile_rank'])}"
            ),
            "backtestJob": r["backtest_id"],
            "variant": r["variant_name"],
            # Two jobs can share a variant, so without this a market-cap and an
            # equal-weight row are indistinguishable in the table.
            "weighting": r["weighting"],
            "factor": r["factor_name"],
            "holdingPeriod": r["period"],
            "type": "long_short" if r["quantile_rank"] == 0 else "quantile",
            "quantile": rank_suffix(r["quantile_rank"]),
            "rebalanceDate": str(r["trade_date"]),
            "netReturn": net_return,
            "spyReturn": spy_return,
            "excessReturn": excess_return,
            "turnover": metrics.get("turnover"),
            "holdingsCount": holdings_count_map.get(next_key),
            "tradingDaysToNext": trading_days,
            "unit": "decimal",
        })
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
    # 空持仓有三种截然不同的原因，前端必须能区分：LS 组合本就没有独立持仓（正常），
    # 产物文件找不到（部署/挂载故障），文件在但这一期没有记录（数据问题）。
    # 以前一律显示"本期没有独立持仓"，把故障说成了正常，排查时极具误导性。
    if ident['quantile_rank'] == 0:
        holdings_status = 'long_short'
    elif path is None:
        holdings_status = 'artifact_missing'
    elif not holdings:
        holdings_status = 'empty'
    else:
        holdings_status = 'ok'
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

    metrics_map = fetch_turnover_excess_map(engine, {ident["run_id"]})
    metric_key = (
        ident["run_id"], ident["backtest_id"], ident["variant_name"],
        ident["factor_name"], ident["period"], ident["quantile_rank"],
    )
    metrics = metrics_map.get(metric_key, {})
    trade_date_obj = date.fromisoformat(ident["trade_date"])
    spy_closes = fetch_spy_closes(
        engine,
        {trade_date_obj} | ({next_date} if next_date else set()),
    )
    spy_cur = spy_closes.get(trade_date_obj)
    spy_next = spy_closes.get(next_date) if next_date else None
    spy_return = (spy_next / spy_cur - 1) if (spy_cur and spy_next) else None
    net_return = row["return_value"]
    excess_return = (
        net_return - spy_return
        if (net_return is not None and spy_return is not None)
        else None
    )
    trading_days = (next_date - trade_date_obj).days if next_date else None

    summary = {
        'rebalanceId': rebalance_id,
        'backtestJob': row['backtest_id'],
        'variant': row['variant_name'],
        'weighting': row['weighting'],
        'factor': row['factor_name'],
        'holdingPeriod': row['period'],
        'type': 'long_short' if row['quantile_rank'] == 0 else 'quantile',
        'rebalanceDate': str(row['trade_date']),
        'netReturn': row['return_value'],
        'spyReturn': spy_return,
        'excessReturn': excess_return,
        'turnover': metrics.get('turnover'),
        'holdingsCount': len(holdings),
        'holdingsStatus': holdings_status,
        'tradingDaysToNext': trading_days,
        'unit': 'decimal',
    }
    return {
        **summary,
        'asOfDate': str(row['trade_date']),
        'holdings': holdings,
        'contributions': contributions,
    }
