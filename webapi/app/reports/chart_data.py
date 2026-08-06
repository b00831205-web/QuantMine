from __future__ import annotations
import logging
import pandas as pd
from sqlalchemy import MetaData, Table, select
from sqlalchemy.engine import Engine

from quantmine.storage.ic import load_ic_variants
from .charts import ic_heatmap_png, ic_hist_png, ic_multi_series_png, quantile_curve_png

logger = logging.getLogger("quantmine.webapi")

def _collect_ic_combos(variants: dict, *, limit: int = 8) -> list[dict]:
    combos: list[dict] = []
    for variant_name, variant in variants.items():
        scope = getattr(variant, 'test', None)
        if scope is None:
            continue
        frame = scope.get('cs_ic')
        if frame is None:
            continue
        for (factor_name, period) in frame.columns:
            values = frame[(factor_name, period)].dropna()
            if values.empty:
                continue
            combos.append({
                'label': f'{variant_name} · {factor_name} · {period}d',
                'variant': variant_name,
                'factor': factor_name,
                'period': int(period),
                'dates': [pd.Timestamp(value).date() for value in values.index],
                'ic': [float(value) for value in values],
            }
            )
            if len(combos) >= limit:
                return combos
    return combos


def _build_ic_heatmap(combos: list[dict]) -> pd.DataFrame | None:
    """行=年份（只有一年时降级为月份），列=组合，值=均值 IC。"""
    if not combos:
        return None

    records: list[dict] = []
    for combo in combos:
        series = pd.Series(combo["ic"], index=pd.to_datetime(combo["dates"]))
        for year, value in series.groupby(series.index.year).mean().items():
            records.append({"period": int(year), "combo": combo["label"], "ic": float(value)})

    frame = pd.DataFrame(records).pivot(index="period", columns="combo", values="ic")
    if frame.shape[0] <= 1:
        month_records: list[dict] = []
        for combo in combos:
            series = pd.Series(combo["ic"], index=pd.to_datetime(combo["dates"]))
            for period, value in series.groupby(series.index.to_period("M")).mean().items():
                month_records.append({"period": str(period), "combo": combo["label"], "ic": float(value)})
        frame = pd.DataFrame(month_records).pivot(index="period", columns="combo", values="ic")
    return frame.sort_index()


def _fetch_quantile_curve(
    engine: Engine,
    *,
    run_id: int,
    variant: str,
    factor: str,
    period: int,
    test_id: str | None,
) -> tuple[list, dict[str, list[float]]] | None:
    """取一个组合的回测每日收益，累计成各分位净值曲线。"""
    metadata = MetaData()
    table = Table("backtest_results", metadata, autoload_with=engine)
    conditions = [
        table.c.run_id == run_id,
        table.c.variant_name == variant,
        table.c.factor_name == factor,
        table.c.period == period,
    ]
    if test_id:
        conditions.append(table.c.test_id == test_id)

    statement = (
        select(table.c.trade_date, table.c.quantile_rank, table.c.return_value)
        .where(*conditions)
        .order_by(table.c.trade_date)
    )
    with engine.connect() as connection:
        rows = connection.execute(statement).mappings().all()

    grouped: dict[int, dict] = {}
    for row in rows:
        if row["return_value"] is None:
            continue
        grouped.setdefault(row["quantile_rank"], {})[row["trade_date"]] = float(row["return_value"])
    if not grouped:
        return None

    all_dates = sorted({date for values in grouped.values() for date in values})
    quantiles: dict[str, list[float]] = {}
    for rank in sorted(grouped, key=lambda value: (value != 0, value)):
        level = 100.0
        series: list[float] = []
        for trade_date in all_dates:
            ret = grouped[rank].get(trade_date)
            if ret is not None:
                level *= 1.0 + ret
            series.append(level)
        quantiles["Long-Short" if rank == 0 else f"Q{rank}"] = series
    return all_dates, quantiles


def build_report_charts(engine, run_id: int, test_id: str | None)-> dict:
    charts = {
        "ic_series": None,
        "ic_hist": None,
        "ic_heatmap": None,
        "quantile_curve": None,
        "drawdown": None,
        "loadings": None,
    }
    try:
        variants = load_ic_variants(engine, run_id)
        combos = _collect_ic_combos(variants)

        charts["ic_series"] = ic_multi_series_png(combos)
        charts["ic_hist"] = ic_hist_png(combos[0]["ic"]) if combos else None
        charts["ic_heatmap"] = ic_heatmap_png(_build_ic_heatmap(combos))

        if combos:
            curve = None
            for combo in combos:
                curve = _fetch_quantile_curve(
                    engine,
                    run_id=run_id,
                    variant=combo["variant"],
                    factor=combo["factor"],
                    period=combo["period"],
                    test_id=test_id,
                )
                if curve is not None:
                    break
            if curve is not None:
                dates, quantiles = curve
                charts["quantile_curve"] = quantile_curve_png(dates, quantiles, None)
            else:
                logger.warning("quantile curve skipped: no backtest rows for run %s", run_id)
    except Exception as error:  # 产物缺失/损坏时不能拖垮 PDF，图表降级为无图
        logger.warning("build_report_charts skipped: %s", error)
    return charts
