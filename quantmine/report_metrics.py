"""Report appendix metrics shared with the Web API reporting layer.

This module computes data only; charts are rendered in
``webapi/app/reports/charts.py``.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import MetaData, Table, select
from sqlalchemy.engine import Engine

from .storage.ic import load_ic_variants
from .storage.paths import resolve_artifact_path

# Development-time A6 factor directory. Read from storage once factor artifacts
# are persisted in the database.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
FACTOR_DIR = PROJECT_ROOT / "tmp" / "factors"


def build_ic_decay_frame(engine: Engine, run_id: int) -> pd.DataFrame | None:
    """Aggregate mean IC by holding period for each variant-factor pair.

    Returns a DataFrame indexed by holding period with pair names as columns.
    """
    variants = load_ic_variants(engine, run_id)
    records = []
    for variant_name, variant in variants.items():
        scope = getattr(variant, "test", None)
        if scope is None:
            continue
        frame = scope.get("cs_ic")
        if frame is None:
            continue
        for (factor_name, period) in frame.columns:
            values = frame[(factor_name, period)].dropna()
            if values.empty:
                continue
            records.append({
                "combo": f"{variant_name} · {factor_name}",
                "period": int(period),
                "ic": float(values.mean()),
            })
    if not records:
        return None
    out = pd.DataFrame(records).pivot(index="period", columns="combo", values="ic")
    return out.sort_index()


def load_net_return_curve(engine: Engine, run_id: int) -> pd.DataFrame | None:
    """Load the run's first net-return-curve artifact as a wide DataFrame."""
    metadata = MetaData()
    table = Table("backtest_artifacts", metadata, autoload_with=engine)
    statement = (
        select(table.c.path)
        .where(table.c.run_id == run_id, table.c.artifact_type == "net_return_curve")
        .limit(1)
    )
    with engine.connect() as connection:
        path = connection.execute(statement).scalar_one_or_none()
    if not path:
        return None
    resolved = resolve_artifact_path(path)
    if not resolved.exists():
        return None
    return pd.read_parquet(resolved)


def fetch_spy_series(engine: Engine, start, end) -> pd.Series:
    """Return SPY closes within the requested interval."""
    metadata = MetaData()
    table = Table("market_bars", metadata, autoload_with=engine)
    statement = (
        select(table.c.trade_date, table.c.close)
        .where(
            table.c.ticker == "SPY",
            table.c.trade_date >= start,
            table.c.trade_date <= end,
        )
        .order_by(table.c.trade_date)
    )
    with engine.connect() as connection:
        rows = connection.execute(statement).mappings().all()
    return pd.Series(
        {r["trade_date"]: float(r["close"]) for r in rows if r["close"] is not None}
    ).sort_index()


def factor_autocorr_rows(factor_dir: Path | None = None) -> list[dict]:
    """Return mean cross-sectional lag-1 autocorrelation for each factor."""
    directory = factor_dir or FACTOR_DIR
    rows = []
    if not directory.exists():
        return rows
    for path in sorted(directory.glob("*.parquet")):
        try:
            df = pd.read_parquet(path)
            corrs = []
            for col in df.columns:
                series = df[col].dropna()
                if len(series) > 5:
                    value = series.autocorr(1)
                    if value is not None and not pd.isna(value):
                        corrs.append(float(value))
            rows.append({
                "factor": path.stem,
                "autocorr": float(pd.Series(corrs).mean()) if corrs else None,
            })
        except Exception:
            continue
    return rows


def build_backtest_metrics_data(engine: Engine, run_id: int) -> dict:
    """Compute rolling Sharpe, alpha/beta, and factor autocorrelation data."""
    result = {
        "rolling_sharpe_dates": [],
        "rolling_sharpe_values": [],
        "alpha_beta": [],
        "factor_autocorr": factor_autocorr_rows(),
    }
    curve = load_net_return_curve(engine, run_id)
    if curve is None or curve.empty:
        return result

    returns = curve.pct_change().dropna()
    col = "long_short" if "long_short" in returns.columns else returns.columns[0]
    series = returns[col]

    rolling_mean = series.rolling(63).mean()
    rolling_std = series.rolling(63).std()
    rolling = (rolling_mean / rolling_std * (252 ** 0.5)).dropna()
    result["rolling_sharpe_dates"] = [
        d.date() if hasattr(d, "date") else d for d in rolling.index
    ]
    result["rolling_sharpe_values"] = rolling.tolist()

    spy = fetch_spy_series(
        engine, series.index.min(), series.index.max()
    ).pct_change()
    df = pd.concat([series.rename("port"), spy.rename("spy")], axis=1).dropna()
    if len(df) > 30:
        x = df["spy"].to_numpy()
        y = df["port"].to_numpy()
        beta = float(np.cov(x, y)[0, 1] / np.var(x))
        alpha_daily = float(np.mean(y) - beta * np.mean(x))
        alpha_annual = (1 + alpha_daily) ** 252 - 1
        result["alpha_beta"] = [{
            "alpha": alpha_annual,
            "beta": beta,
            "n": len(df),
        }]
    return result
