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
from .tables import attribution_tables, backtest_table, ic_table, monotonicity_table, summary_table


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


def _fetch_ic_rows(engine: Engine, run_id: int, test_id: str | None, lang: str) -> list[dict]:
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
            "ir": _f(r["ir"], 3), "ic_pos": "—", "n": r["n"], "t": _f(r["t_stat"], 2),
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
                "win": _pct(m.get("win_rate")), "turnover": "—",
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
) -> dict:
    """Build the full template context. ``charts``/``meta_overrides`` let the
    caller inject artifact-derived figures or environment-specific metadata."""
    labels = get_labels(lang)
    run = _fetch_run(engine, run_id) or {}
    ic_rows = _fetch_ic_rows(engine, run_id, test_id, lang)
    backtest_groups = _fetch_backtest_groups(engine, run_id, test_id)

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
        "attribution": attribution_tables(None, labels),
        "summary": summary_table(summary_rows, labels),
    }

    return {
        "lang": lang, "L": labels, "include_ai": include_ai,
        "meta": meta, "ic_rows": ic_rows, "backtest_groups": backtest_groups,
        "attribution": None,  # not persisted yet — template shows the "not stored" note
        "summary_rows": summary_rows,
        "tables": tables,
        "charts": charts or {"ic_series": None, "ic_hist": None, "quantile_curve": None, "drawdown": None, "loadings": None},
        "ai": {"ic": None, "backtest": None, "attribution": None, "overall": None},
        "disclaimer_lines": _disclaimer_lines(lang, meta),
        "appendix_items": _appendix_items(lang),
    }
