"""Assemble the report context from the database.

Tables provide the exhaustive result tables (test_results, backtest_metrics);
chart series come from artifacts when available and degrade to ``None`` when
not. Attribution is not persisted yet, so that section is left empty and the
template shows a "not stored" note. Number formatting lives here so the
template stays logic-free.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import MetaData, Table, select
from sqlalchemy.engine import Engine

from .labels import get_labels
from .tables import (
    acf_tables, alpha_beta_table, attribution_tables, backtest_table,
    factor_autocorr_table, gross_table, ic_table, monotonicity_table,
    sanity_table, summary_table, turnover_table, yearly_ic_tables,
)


def _f(value, digits: int = 4) -> str:
    if value is None:
        return "—"
    return f"{value:.{digits}f}"


def _pct(value, digits: int = 1) -> str:
    if value is None:
        return "—"
    return f"{value * 100:.{digits}f}%"


def _yn(value, lang: str) -> str:
    if value is None:
        return "—"
    yes, no = ("是", "否") if lang == "zh" else ("Y", "N")
    return yes if value else no


def _table(engine: Engine, name: str) -> Table:
    return Table(name, MetaData(), autoload_with=engine)


def _fetch_run(engine: Engine, run_id: int) -> dict | None:
    table = _table(engine, "research_runs")
    stmt = select(table.c.run_id, table.c.run_timestamp, table.c.git_commit).where(
        table.c.run_id == run_id
    )
    with engine.connect() as conn:
        row = conn.execute(stmt).mappings().first()
    return dict(row) if row else None


def _fetch_ic_rows(engine: Engine, run_id: int, test_id: str | None, lang: str, ic_pos_map: dict | None = None) -> list[dict]:
    table = _table(engine, "test_results")
    conditions = [table.c.run_id == run_id]
    if test_id:
        conditions.append(table.c.test_id == test_id)
    stmt = (
        select(table)
        .where(*conditions)
        .order_by(table.c.variant_name, table.c.factor_name, table.c.period)
    )
    with engine.connect() as conn:
        rows = conn.execute(stmt).mappings().all()
    return [
        {
            "variant": r["variant_name"], "factor": r["factor_name"], "period": r["period"],
            "method": r["test_method"], "ic_mean": _f(r["ic_mean"]), "ic_std": _f(r["ic_std"], 3),
            "ir": _f(r["ir"], 3), "ic_pos": _pct(ic_pos_map.get((r['variant_name'], r['factor_name'], r['period']))) if ic_pos_map and ic_pos_map.get((r['variant_name'], r['factor_name'], r['period'])) is not None else '-', "n": r["n"], "t": _f(r["t_stat"], 2),
            "p": _f(r["p_value"], 4), "bonf": _yn(r["significant"], lang), "bh": _yn(r["bh_significant"], lang),
        }
        for r in rows
    ]


def _fetch_backtest_groups(engine: Engine, run_id: int, test_id: str | None) -> list[dict]:
    """Pivot backtest_metrics into per (variant,factor,period) group blocks."""
    table = _table(engine, "backtest_metrics")
    conditions = [table.c.run_id == run_id]
    if test_id:
        conditions.append(table.c.test_id == test_id)
    stmt = select(table).where(*conditions)
    with engine.connect() as conn:
        rows = conn.execute(stmt).mappings().all()

    # group key -> {quantile_rank -> {metric_name -> value}} and monotonicity metrics
    blocks: dict[tuple, dict] = {}
    for r in rows:
        key = (r["variant_name"], r["factor_name"], r["period"])
        block = blocks.setdefault(key, {"metrics": {}, "mono": {}})
        name = r["metric_name"]
        if name.startswith("monotonicity_"):
            block["mono"][name.removeprefix("monotonicity_")] = r["metric_value"]
        else:
            block["metrics"].setdefault(r["quantile_rank"], {})[name] = r["metric_value"]

    result = []
    for (variant, factor, period), block in sorted(blocks.items()):
        rows_out = []
        for rank in sorted(block["metrics"]):
            m = block["metrics"][rank]
            group = "long_short" if rank == 0 else f"Q{rank}"
            rows_out.append({
                "group": group,
                "ann": _pct(m.get("yearly_return")), "vol": _pct(m.get("volatility")),
                "sharpe": _f(m.get("sharp_ratio"), 2), "mdd": _pct(m.get("max_drawdown")),
                "win": _pct(m.get("win_rate")), "turnover": _pct(m.get('turnover')) if m.get('turnover') is not None else '-',
            })
        mono = block["mono"]
        result.append({
            "label": f"{variant} · {factor} · {period}d",
            "rows": rows_out,
            "mono": {
                "corr": _f(mono.get("mean_based_corr"), 2), "p": _f(mono.get("mean_based_pvalue"), 3),
                "daily": _f(mono.get("daily_avg_corr"), 2), "pos": _pct(mono.get("daily_corr_positive_pct")),
            },
        })
    return result

def _fetch_sanity_rows(engine: Engine, run_id: int, test_id: str | None) -> list[dict]:
    table = _table(engine, "backtest_metrics")
    conditions = [table.c.run_id == run_id, table.c.metric_name.like("sanity_%")]
    if test_id:
        conditions.append(table.c.test_id == test_id)
    stmt = (
        select(table.c.factor_name, table.c.period, table.c.metric_name, table.c.metric_value)
        .where(*conditions)
        .order_by(table.c.factor_name, table.c.period)
    )
    with engine.connect() as conn:
        rows = conn.execute(stmt).mappings().all()

    groups: dict[tuple, dict] = {}
    for r in rows:
        parts = (r["metric_name"] or "").split("_", 2)
        if len(parts) != 3 or parts[0] != "sanity":
            continue
        key = (r["factor_name"], r["period"])
        scenario = parts[1]
        metric = parts[2]
        group = groups.setdefault(key, {
            "factor": r["factor_name"], "period": r["period"], "scenarios": {},
        })
        group["scenarios"].setdefault(scenario, {})[metric] = r["metric_value"]

    result = []
    for group in groups.values():
        for scenario, metrics in group["scenarios"].items():
            result.append({
                "factor": group["factor"],
                "period": group["period"],
                "scenario": scenario,
                "mean_diff": metrics.get("mean_difference"),
                "std_diff": metrics.get("std_difference"),
                "mean_to_std": metrics.get("mean_to_std"),
            })
    return result

def _fetch_turnover_rows(engine: Engine, run_id: int, test_id: str | None) -> list[dict]:
    """A6 turnover: read turnover from backtest_metrics."""
    table = _table(engine, "backtest_metrics")
    conditions = [table.c.run_id == run_id, table.c.metric_name == "turnover"]
    if test_id:
        conditions.append(table.c.test_id == test_id)
    stmt = (
        select(
            table.c.factor_name, table.c.period, table.c.quantile_rank,
            table.c.metric_value,
        )
        .where(*conditions)
        .order_by(table.c.factor_name, table.c.period, table.c.quantile_rank)
    )
    with engine.connect() as conn:
        rows = conn.execute(stmt).mappings().all()
    return [
        {
            "factor": r["factor_name"],
            "period": r["period"],
            "rank": r["quantile_rank"],
            "turnover": r["metric_value"],
        }
        for r in rows
    ]


def _fetch_gross_rows(engine: Engine, run_id: int, test_id: str | None) -> list[dict]:
    """A8 gross-return performance: read gross_ prefixed metrics (requires pipeline persistence first)."""
    table = _table(engine, "backtest_metrics")
    conditions = [table.c.run_id == run_id, table.c.metric_name.like("gross_%")]
    if test_id:
        conditions.append(table.c.test_id == test_id)
    stmt = (
        select(
            table.c.factor_name, table.c.period, table.c.quantile_rank,
            table.c.metric_name, table.c.metric_value,
        )
        .where(*conditions)
    )
    with engine.connect() as conn:
        rows = conn.execute(stmt).mappings().all()

    groups: dict[tuple, dict] = {}
    for r in rows:
        key = (r["factor_name"], r["period"], r["quantile_rank"])
        metric = r["metric_name"].removeprefix("gross_")
        groups.setdefault(key, {
            "factor": r["factor_name"],
            "period": r["period"],
            "rank": r["quantile_rank"],
            "metrics": {},
        })["metrics"][metric] = r["metric_value"]
    result = []
    for group in groups.values():
        metrics = group["metrics"]
        result.append({
            "factor": group["factor"],
            "period": group["period"],
            "rank": group["rank"],
            "total_return": metrics.get("total_return"),
            "yearly_return": metrics.get("yearly_return"),
            "volatility": metrics.get("volatility"),
            "sharpe": metrics.get("sharp_ratio"),
            "mdd": metrics.get("max_drawdown"),
            "win": metrics.get("win_rate"),
        })
    return result


_ATTR_TERM_ORDER = {"Alpha": 0, "Mkt-RF": 1, "SMB": 2, "HML": 3, "Mom": 4}


def _fetch_attribution(engine: Engine, run_id: int, test_id: str | None) -> list[dict]:
    """Read attribution_results into the per-group structure the template wants.

    Returns a list of ``{variant, terms[], r2, adj_r2, n, alpha_annual}`` blocks,
    one per (variant, factor, period). Empty list when nothing is stored — the
    caller then leaves the section's "not stored" note in place.
    """
    try:
        table = _table(engine, "attribution_results")
    except Exception:
        return []  # 表还没建（未跑迁移）时优雅降级
    conditions = [table.c.run_id == run_id]
    if test_id:
        conditions.append(table.c.test_id == test_id)
    stmt = select(table).where(*conditions)
    with engine.connect() as conn:
        rows = conn.execute(stmt).mappings().all()

    blocks: dict[tuple, dict] = {}
    for r in rows:
        key = (r["variant_name"], r["factor_name"], r["period"])
        block = blocks.setdefault(key, {"terms": [], "model": r})
        block["terms"].append({
            "term": r["term"], "coef": _f(r["coef"]), "stderr": _f(r["std_err"]),
            "t": _f(r["t_stat"], 2), "p": _f(r["p_value"], 4),
            "ci_lo": _f(r["ci_lo"]), "ci_hi": _f(r["ci_hi"]),
        })

    result = []
    for (variant, factor, period), block in sorted(blocks.items()):
        model = block["model"]
        result.append({
            "variant": f"{variant} · {factor} · {period}d",
            "terms": sorted(block["terms"], key=lambda t: _ATTR_TERM_ORDER.get(t["term"], 99)),
            "r2": _f(model["r2"], 3), "adj_r2": _f(model["adj_r2"], 3),
            "n": model["n"], "alpha_annual": _pct(model["alpha_annual"]),
        })
    return result


def _disclaimer_lines(lang: str, meta: dict) -> list[str]:
    if lang == "zh":
        return [
            f"幸存者偏差：{meta['universe_recovered']}/{meta['universe_total']} 可恢复。",
            f"样本外 {meta['test_start']}→ 检验力有限，覆盖单一市场状态。",
            "成本按换手率单边计价，未含冲击/融券成本。",
            "全部为回测结果，非实盘、不构成投资建议。",
        ]
    return [
        f"Survivorship: {meta['universe_recovered']}/{meta['universe_total']} recoverable.",
        f"Out-of-sample {meta['test_start']}→ has limited power, single market regime.",
        "Costs charged one-way on turnover; no market-impact or borrow cost.",
        "All backtest results — not live, not investment advice.",
    ]


def _appendix_items(lang: str) -> list[dict]:
    zh = lang == "zh"
    spec = [
        ("A1", "分年度 IC 表" if zh else "Yearly IC table", "逐年 IC/IR/n" if zh else "IC/IR/n by year"),
        ("A2", "IC 自相关(ACF)表" if zh else "IC autocorrelation (ACF)", "各滞后阶" if zh else "by lag"),
        ("A3", "分年/分月 IC 热力图" if zh else "Yearly/monthly IC heatmap", "跨时间稳定性" if zh else "stability over time"),
        ("A4", "IC 衰减图" if zh else "IC decay", "信号半衰期" if zh else "signal half-life"),
        ("A5", "滚动 Sharpe / alpha·beta" if zh else "Rolling Sharpe / alpha·beta", "稳定性" if zh else "stability"),
        ("A6", "换手率 + 因子自相关" if zh else "Turnover + factor autocorrelation", "可实现性" if zh else "implementability"),
        ("A7", "稳健性检验" if zh else "Robustness checks", "位移/打乱" if zh else "displacement/shuffle"),
        ("A8", "毛收益绩效表" if zh else "Gross-return performance", "与表 2 对照" if zh else "vs Table 2"),
    ]
    return [{"code": c, "title": t, "note": n} for c, t, n in spec]


def assemble_context(
    engine: Engine,
    run_id: int,
    test_id: str | None,
    lang: str,
    include_ai: bool,
    *,
    charts: dict | None = None,
    meta_overrides: dict | None = None,
    ic_pos_map : dict | None = None,
    appendices: dict | None = None,
) -> dict:
    """Build the full template context. ``charts``/``meta_overrides`` let the
    caller inject artifact-derived figures or environment-specific metadata."""
    labels = get_labels(lang)
    run = _fetch_run(engine, run_id) or {}
    ic_rows = _fetch_ic_rows(engine, run_id, test_id, lang, ic_pos_map)
    sanity_rows = _fetch_sanity_rows(engine, run_id, test_id)
    turnover_rows = _fetch_turnover_rows(engine, run_id, test_id)
    gross_rows = _fetch_gross_rows(engine, run_id, test_id)
    backtest_groups = _fetch_backtest_groups(engine, run_id, test_id)
    attribution = _fetch_attribution(engine, run_id, test_id)

    factors = sorted({r["factor"] for r in ic_rows}) or ["—"]
    variants = sorted({r["variant"] for r in ic_rows}) or ["—"]
    meta = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "test_id": test_id or "—", "run_id": run_id,
        "git_commit": (run.get("git_commit") or "—")[:10],
        "factors": ", ".join(factors), "variants": ", ".join(variants),
        "start_date": "—", "end_date": "—", "train_end": "—", "test_start": "—",
        "periods": "—", "universe_recovered": "—", "universe_total": "—",
    }
    meta.update(meta_overrides or {})

    summary_rows = [
        {"dim": "IC", "metric": "rows", "value": str(len(ic_rows)), "sample": "train/test"},
        {"dim": "Backtest", "metric": "groups", "value": str(len(backtest_groups)), "sample": "test"},
    ]

    tables = {
        "ic": ic_table(ic_rows, labels),
        "backtest": backtest_table(backtest_groups, labels),
        "monotonicity": monotonicity_table(backtest_groups, labels),
        "attribution": attribution_tables(attribution or None, labels),
        "summary": summary_table(summary_rows, labels),
        "yearly": yearly_ic_tables((appendices or {}).get("yearly", []), labels),
        "acf": acf_tables((appendices or {}).get("acf", []), labels),
        "sanity": sanity_table(sanity_rows, labels),
        "alpha_beta": alpha_beta_table((appendices or {}).get("alpha_beta", []), labels),
        "turnover": turnover_table(turnover_rows, labels),
        "factor_autocorr": factor_autocorr_table((appendices or {}).get("factor_autocorr", []), labels),
        "gross": gross_table(gross_rows, labels),
    }

    merged_charts = dict(charts or {})
    if (appendices or {}).get("monthly_heatmap"):
        merged_charts["monthly_heatmap"] = appendices["monthly_heatmap"]

    if (appendices or {}).get("ic_decay"):
        merged_charts["ic_decay"] = appendices["ic_decay"]
    if (appendices or {}).get("rolling_sharpe"):
        merged_charts["rolling_sharpe"] = appendices["rolling_sharpe"]

    appendix_data = {
        "yearly": (appendices or {}).get("yearly", []),
        "acf": (appendices or {}).get("acf", []),
        "ic_decay": bool((appendices or {}).get("ic_decay")),
        "rolling_sharpe": bool((appendices or {}).get("rolling_sharpe")),
        "alpha_beta": (appendices or {}).get("alpha_beta", []),
        "factor_autocorr": (appendices or {}).get("factor_autocorr", []),
        "turnover": turnover_rows,
        "gross": gross_rows,
        "sanity": sanity_rows,
    }
    return {
        "lang": lang, "L": labels, "include_ai": include_ai,
        "meta": meta, "ic_rows": ic_rows, "backtest_groups": backtest_groups,
        "attribution": attribution or None,  # None → template shows the "not stored" note
        "summary_rows": summary_rows,
        "tables": tables,
        "charts": merged_charts or {"ic_series": None, "ic_hist": None, "quantile_curve": None, "drawdown": None, "loadings": None},
        "ai": {"ic": None, "backtest": None, "overall": None},
        "disclaimer_lines": _disclaimer_lines(lang, meta),
        "appendix_items": _appendix_items(lang),
        "appendix_data": appendix_data
    }
