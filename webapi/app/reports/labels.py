"""Report i18n labels and language resolution.

The report is rendered in the reader's language: an explicit ``lang`` query
param wins; otherwise the request's ``Accept-Language`` header is consulted;
otherwise English. Only ``en`` and ``zh`` are supported today — add a dict here
plus the language code to ``SUPPORTED`` to add another.
"""
from __future__ import annotations

SUPPORTED = ("en", "zh")
DEFAULT_LANG = "en"

_LABELS: dict[str, dict[str, str]] = {
    "en": {
        "report_title": "Factor Efficacy · Backtest · Attribution — Full Results",
        "brand": "QUANTMINE · Factor Research Report",
        "generated_at": "Generated at",
        "test_id": "Test ID",
        "run_id": "Run ID",
        "factors_variants": "Factors / Variants",
        "backtest_window": "Backtest window",
        "sample_split": "Sample split",
        "holding_periods": "Holding periods (trading days)",
        "ai_analysis": "AI analysis",
        "ai_on": "on (per-section AI commentary)",
        "ai_off": "off (data-only)",
        "cover_note": "Full listing of backtest research results — not live performance, not investment advice. Secondary and stability tests are in the appendix.",
        "sec_ic": "IC Significance · full fields",
        "sec_backtest": "Backtest · full fields",
        "sec_attribution": "Attribution · Carhart 4-factor (daily · HAC)",
        "sec_overall": "Overall · Disclaimer",
        "sec_appendix": "Appendix · secondary & stability tests (full fields)",
        "tbl_ic_caption": "Table 1 · all variant × factor × period × method (unfiltered)",
        "col_variant": "Variant", "col_factor": "Factor", "col_period": "Period",
        "col_method": "Method", "col_ic_mean": "IC mean", "col_ic_std": "IC std",
        "col_ir": "IR", "col_ic_pos": "IC>0%", "col_n": "n", "col_t": "NW-t",
        "col_p": "p", "col_bonf": "Bonf.", "col_bh": "BH",
        "fig_ic_series": "Fig 1 · IC rolling mean by variant × factor × period",
        "fig_ic_hist": "Fig 2 · IC distribution (histogram)",
        "fig_ic_heatmap": "Fig 2b · mean IC heatmap by year × combination",
        "tbl_bt_caption": "Table 2 · quantile & long-short performance (net of cost; gross in appendix)",
        "col_group": "Group", "col_ann": "Annualized", "col_vol": "Volatility",
        "col_sharpe": "Sharpe", "col_mdd": "Max DD", "col_win": "Win rate",
        "col_turnover": "Turnover", "long_short": "Long-Short",
        "col_year": "Year", "col_lag": "Lag", "col_acf": "ACF",
        "col_scenario": "Scenario", "col_mean_diff": "Mean diff",
        "col_std_diff": "Std diff", "col_mean_to_std": "Mean/Std",
        "tbl_mono_caption": "Table 2b · monotonicity test",
        "col_mono_corr": "Mean Spearman", "col_mono_daily": "Daily avg corr",
        "col_mono_pos": "Daily positive %",
        "fig_quantile_curve": "Fig 3 · cumulative NAV Q1–Q5 / long-short",
        "fig_drawdown": "Fig 4 · long-short drawdown (underwater)",
        "tbl_attr_caption": "Table 3 · long-short daily return on FF3+MOM · one per variant",
        "col_term": "Term", "col_coef": "coef", "col_stderr": "std err",
        "col_hac_t": "t (HAC)", "col_ci_lo": "[0.025", "col_ci_hi": "0.975]",
        "attr_alpha": "Alpha", "attr_missing": "Attribution results are not stored for this run.",
        "fig_loadings": "Fig 5 · factor loadings + 95% CI",
        "tbl_summary_caption": "Table 4 · key results (numbers only, no judgment)",
        "col_dim": "Dimension", "col_metric": "Metric", "col_value": "Value", "col_sample": "Sample",
        "disclaimer_title": "Limitations & bias disclosure (fixed text)",
        "ai_slot": "AI analysis", "ai_toggle": "toggle-controlled",
        "ai_slot_note": "On: AI interprets the numbers above · Off: this block is not rendered.",
        "col_total_return": "Total", "col_alpha": "Alpha (ann.)", "col_beta": "Beta",
        "col_autocorr": "Autocorr",
        "ai_summary_slot": "AI overall analysis (report-level)",
        "no_data": "No data.",
        "page": "Page",
    },
    "zh": {
        "report_title": "因子有效性 · 回测 · 归因 — 完整结果",
        "brand": "QUANTMINE · 因子研究报告",
        "generated_at": "生成时间戳",
        "test_id": "Test ID",
        "run_id": "Run ID",
        "factors_variants": "因子 / 变体",
        "backtest_window": "回测区间",
        "sample_split": "样本切分",
        "holding_periods": "持有期（交易日）",
        "ai_analysis": "AI 分析",
        "ai_on": "开（各节含 AI 解读）",
        "ai_off": "关（纯数据版）",
        "cover_note": "回测研究结果的完整列示，非实盘、不构成投资建议。次要与稳定性检验见附录。",
        "sec_ic": "IC 检验 · 全字段",
        "sec_backtest": "回测检验 · 全字段",
        "sec_attribution": "归因分析 · Carhart 四因子（日频 · HAC）",
        "sec_overall": "整体表现 · 声明",
        "sec_appendix": "附录 · 次要与稳定性检验（全字段）",
        "tbl_ic_caption": "表 1 · 全部 变体 × 因子 × 持有期 × 方法（不筛选）",
        "col_variant": "变体", "col_factor": "因子", "col_period": "持有期",
        "col_method": "方法", "col_ic_mean": "IC均值", "col_ic_std": "IC std",
        "col_ir": "IR", "col_ic_pos": "IC>0%", "col_n": "n", "col_t": "NW-t",
        "col_p": "p", "col_bonf": "Bonf.", "col_bh": "BH",
        "fig_ic_series": "图 1 · IC 滚动均值（按变体 × 因子 × 持有期）",
        "fig_ic_hist": "图 2 · IC 分布（直方图）",
        "fig_ic_heatmap": "图 2b · 分年均值 IC 热力图（组合 × 年份）",
        "tbl_bt_caption": "表 2 · 分位与多空绩效（扣费口径；毛收益见附录）",
        "col_group": "组合", "col_ann": "年化", "col_vol": "波动",
        "col_sharpe": "Sharpe", "col_mdd": "最大回撤", "col_win": "胜率",
        "col_turnover": "换手", "long_short": "Long-Short",
        "col_year": "年份", "col_lag": "滞后", "col_acf": "ACF",
        "col_scenario": "场景", "col_mean_diff": "均值差",
        "col_std_diff": "标准差", "col_mean_to_std": "均值/标准差",
        "tbl_mono_caption": "表 2b · 单调性检验",
        "col_mono_corr": "均值 Spearman", "col_mono_daily": "日度平均 corr",
        "col_mono_pos": "日度为正占比",
        "fig_quantile_curve": "图 3 · 分位累计净值 Q1–Q5 / 多空",
        "fig_drawdown": "图 4 · 多空回撤（水下图）",
        "tbl_attr_caption": "表 3 · 多空日收益对 FF3+动量回归 · 每变体一张",
        "col_term": "项", "col_coef": "coef", "col_stderr": "std err",
        "col_hac_t": "t (HAC)", "col_ci_lo": "[0.025", "col_ci_hi": "0.975]",
        "attr_alpha": "Alpha", "attr_missing": "该 run 未入库归因结果。",
        "fig_loadings": "图 5 · 因子载荷 + 95% 置信区间",
        "tbl_summary_caption": "表 4 · 关键结论汇总（纯数字，不加判断）",
        "col_dim": "维度", "col_metric": "指标", "col_value": "值", "col_sample": "样本",
        "disclaimer_title": "局限与偏差声明（固定文本）",
        "ai_slot": "AI 分析", "ai_toggle": "开关控制",
        "ai_slot_note": "开：AI 基于上表数字解读 · 关：本块不渲染。",
        "ai_summary_slot": "AI 综合分析（整报告级）",
        "no_data": "暂无数据。",
        "page": "第",
        "col_total_return": "总收益", "col_alpha": "Alpha（年化）", "col_beta": "Beta",
        "col_autocorr": "自相关",
    },
}


def get_labels(lang: str) -> dict[str, str]:
    return _LABELS.get(lang, _LABELS[DEFAULT_LANG])


def resolve_lang(param: str | None, accept_language: str | None) -> str:
    """Pick the report language: explicit param > Accept-Language > default."""
    if param:
        code = param.strip().lower().split("-")[0]
        if code in SUPPORTED:
            return code
    if accept_language:
        # Accept-Language: "zh-CN,zh;q=0.9,en;q=0.8" — take the first supported.
        for part in accept_language.split(","):
            code = part.split(";")[0].strip().lower().split("-")[0]
            if code in SUPPORTED:
                return code
    return DEFAULT_LANG
