"""Carhart four-factor attribution of each backtested long-short series.

Reads the stored ``long_short`` daily returns from ``backtest_results``, pulls
daily Fama-French + momentum factors from the Ken French library (with a local
parquet cache fallback), runs the HAC regression, and persists per-term results
into ``attribution_results`` for the PDF report's section 03.

If factor data cannot be obtained (offline and no cache), the task logs a
warning and exits cleanly — the report then keeps its "not stored" note rather
than failing the DAG.
"""
import argparse
import sys
from pathlib import Path

import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from quantmine.factor_attribution import carhart_attribution, fetch_french_factors_daily
from quantmine.storage.attribution import load_long_short_returns, save_attribution_results
from quantmine.storage.database import get_engine
from quantmine.storage.runs import find_run_id_by_airflow_batch

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# statsmodels 参数名 -> 报告展示的 term 名（const 特殊显示为 Alpha）
_TERM_LABELS = {"const": "Alpha", "Mkt-RF": "Mkt-RF", "SMB": "SMB", "HML": "HML", "Mom": "Mom"}


def _attribution_rows(
    key: tuple[str, str, int, str],
    long_short: pd.Series,
    factors: pd.DataFrame,
    *,
    run_id: int,
    maxlags: int,
) -> list[dict]:
    variant, factor, period, test_id = key
    daily_returns = long_short.to_frame("long_short")
    daily_returns.index = pd.to_datetime(daily_returns.index)

    result = carhart_attribution(daily_returns, factors, maxlags=maxlags)
    conf = result.conf_int()
    alpha_annual = float(result.params.get("const", 0.0)) * 252

    rows: list[dict] = []
    for name, label in _TERM_LABELS.items():
        if name not in result.params.index:
            continue
        rows.append({
            "run_id": run_id,
            "variant_name": variant,
            "test_id": test_id,
            "factor_name": factor,
            "period": period,
            "term": label,
            "coef": float(result.params[name]),
            "std_err": float(result.bse[name]),
            "t_stat": float(result.tvalues[name]),
            "p_value": float(result.pvalues[name]),
            "ci_lo": float(conf.loc[name, 0]),
            "ci_hi": float(conf.loc[name, 1]),
            "r2": float(result.rsquared),
            "adj_r2": float(result.rsquared_adj),
            "n": int(result.nobs),
            "alpha_annual": alpha_annual,
            "maxlags": maxlags,
        })
    return rows


def main():
    parser = argparse.ArgumentParser(description="Run and persist Carhart attribution")
    parser.add_argument("--date", required=True)
    parser.add_argument("--batch", required=True)
    parser.add_argument("--config", default="config.yaml")
    args = parser.parse_args()

    engine = get_engine()
    run_id = find_run_id_by_airflow_batch(engine, args.batch)

    with (PROJECT_ROOT / args.config).open(encoding="utf-8") as file:
        config = yaml.safe_load(file) or {}
    maxlags = int((config.get("carhart_attribution") or {}).get("maxlags", 20))

    groups = load_long_short_returns(engine, run_id)
    if not groups:
        print(f"Attribution skipped: no long_short rows for run_id={run_id}")
        return

    all_dates = pd.to_datetime(sorted({date for series in groups.values() for date in series.index}))
    cache_path = PROJECT_ROOT / "tmp" / "ff3" / "ff_daily.parquet"
    factors = fetch_french_factors_daily(all_dates.min(), all_dates.max(), cache_path=cache_path)
    if factors is None:
        print("Attribution skipped: Fama-French factor data unavailable (offline, no cache)")
        return

    rows: list[dict] = []
    for key, series in groups.items():
        try:
            rows.extend(
                _attribution_rows(
                    key, series, factors,
                    run_id=run_id, maxlags=maxlags,
                )
            )
        except Exception as error:  # 单个组合回归失败不拖垮整批
            print(f"Attribution failed for {key}: {error}")

    saved = save_attribution_results(engine, pd.DataFrame(rows))
    print(f"Attribution completed: run_id={run_id}, groups={len(groups)}, rows_saved={saved}")


if __name__ == "__main__":
    main()
