from __future__ import annotations
import logging

import pandas as pd
from sqlalchemy import MetaData, Table, select
from sqlalchemy.engine import Engine

from quantmine.report_metrics import (
    build_backtest_metrics_data,
    build_ic_decay_frame,
)
from quantmine.storage.ic import load_ic_variants
from .charts import (
    ic_decay_png,
    ic_heatmap_png,
    ic_hist_png,
    ic_multi_series_png,
    quantile_curve_png,
    rolling_sharpe_png,
)

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
    """Rows=year (falls back to month when there is only one year), columns=combos, values=mean IC."""
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
    """Fetch one combo's daily backtest returns and compound them into quantile net-value curves."""
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

def build_ic_pos_map(engine: Engine, run_id: int) -> dict[tuple[str,str,int], float]:
    result : dict[tuple[str,str,int], float] = {}
    try: 
        variants = load_ic_variants(engine, run_id)
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
                result[(variant_name, factor_name, int(period))] = round(
                    float((values > 0).mean()), 4

                )
    except Exception as error:
        logger.exception('build_ic_pos_map skipped: %s', error)
    return result

def _acf_rows(acf_df: pd.DataFrame |None) -> list[dict]:
    if acf_df is None or acf_df.empty:
        return []
    rows = []
    for _, record in acf_df.reset_index().iterrows():
        values = list(record)
        rows.append({
            'factor': values[0],
            'period': values[1],
            'lag': values[2],
            'acf': values[3] if len(values) >3 else None,
        })
    return rows

def _yearly_rows(yearly_df: pd.DataFrame | None) -> list[dict]:
    if yearly_df is None or yearly_df.empty:
        return []
    rows = []
    for _, record in yearly_df.reset_index().iterrows():
        values = list(record)
        rows.append({
            'year': values[0],
            'factor': values[1],
            'period': values[2],
            'ic_mean': values[3] if len(values) > 3 else None,
            'ic_std': values[4] if len(values) > 4 else None,
            'ir': values[5] if len(values) > 5 else None,
            'ic_pos': values[6] if len(values) > 6 else None,
            'n': values[7] if len(values) > 7 else None
        })
    return rows

def _build_ic_monthly_heatmap(combos: list[dict])->pd.DataFrame | None:
    if not combos:
        return None
    records: list[dict] = []
    for combo in combos:
        series = pd.Series(combo['ic'], index = pd.to_datetime(combo['dates']))
        for period, value in series.groupby(series.index.to_period('M')).mean().items():
            records.append({'period':str(period), 'combo': combo['label'], 'ic': float(value)})

    frame = pd.DataFrame(records).pivot(index = 'period', columns = 'combo', values  = 'ic')
    return frame.sort_index()

def build_ic_appendices(engine: Engine, run_id: int) -> dict:
    """Report appendix data: yearly IC, ACF, monthly heatmap (based on IC artifacts)."""
    appendices: dict = {
        "yearly": [],
        "acf": [],
        "monthly_heatmap": None,
    }
    try:
        variants = load_ic_variants(engine, run_id)
        combos = _collect_ic_combos(variants)
        appendices["monthly_heatmap"] = ic_heatmap_png(_build_ic_monthly_heatmap(combos))

        for variant in variants.values():
            scope = getattr(variant, "test", None)
            if scope is None:
                continue
            acf = scope.get("acf")
            yearly = scope.get("yearly")
            if not appendices["acf"] and acf is not None:
                appendices["acf"] = _acf_rows(acf)
            if not appendices["yearly"] and yearly is not None:
                appendices["yearly"] = _yearly_rows(yearly)
            if appendices["acf"] and appendices["yearly"]:
                break
    except Exception as error:  # 产物缺失时不能拖垮 PDF
        logger.exception("build_ic_appendices skipped: %s", error)
    return appendices

def build_ic_decay_png(engine: Engine, run_id: int) -> str | None:
    """A4 IC decay chart: computation lives in quantmine, only rendering happens here."""
    try:
        return ic_decay_png(build_ic_decay_frame(engine, run_id))
    except Exception as error:
        logger.warning("build_ic_decay_png skipped: %s", error)
        return None

def build_backtest_appendices(engine: Engine, run_id: int) -> dict:
    """A5 rolling Sharpe / Alpha·Beta + A6 factor autocorrelation: computation lives in quantmine, only rendering happens here."""
    result = {
        "rolling_sharpe": None,
        "alpha_beta": [],
        "factor_autocorr": [],
    }
    try:
        data = build_backtest_metrics_data(engine, run_id)
        result["rolling_sharpe"] = rolling_sharpe_png(
            data["rolling_sharpe_dates"],
            data["rolling_sharpe_values"],
        )
        result["alpha_beta"] = data["alpha_beta"]
        result["factor_autocorr"] = data["factor_autocorr"]
    except Exception as error:
        logger.warning("build_backtest_appendices skipped: %s", error)
    return result