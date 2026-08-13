"""Read holdings of a rebalance from the ticker_history parquet (pure data access)."""

import os
from pathlib import Path

import pandas as pd

# webapi/app/api/v1/rebalances/holdings.py → parents[5] = 项目根
_PROJECT_ROOT = Path(__file__).resolve().parents[5]


def resolve_ticker_history_path(
    *, run_id: int, backtest_id: str, factor_name: str, period: int
) -> str | None:
    """Resolve the real ticker_history parquet location via project-root relative path + glob.

    **不信任数据库 `backtest_artifacts.path` 列**：该列存的是写入时机器的绝对路径
    （回测在 Windows 跑 → `E:\\...`），在 WSL 后端上不存在。改用 OS 无关的键 glob：
        <artifacts>/backtest/*/<run_id>/<backtest_id>/ticker_history__<factor>__<period>.parquet
    （`*` 覆盖 batch 段，如 ``manual``）。可用 ``QUANTMINE_ARTIFACT_DIR`` 覆盖 artifacts 根。
    """
    base = Path(os.environ.get("QUANTMINE_ARTIFACT_DIR") or (_PROJECT_ROOT / "data" / "artifacts"))
    pattern = f"backtest/*/{run_id}/{backtest_id}/ticker_history__{factor_name}__{period}.parquet"
    matches = sorted(base.glob(pattern))
    return str(matches[0]) if matches else None


def fetch_holdings(path: str, trade_date: str, quantile_rank: int) -> list[dict]:
    """Read one rebalance's holdings, with the weights the backtest actually used.

    The ``weight`` column is what the portfolio held; deriving ``1/n`` from the
    ticker list instead would silently report an equal-weight portfolio for a
    market-cap-weighted run, and the reported returns would not match the
    holdings shown next to them.

    Artifacts written before weights were persisted have no such column (or
    null values). Those runs were equal-weighted, so falling back to ``1/n``
    reproduces them faithfully rather than guessing.
    """
    df = pd.read_parquet(path)

    filtered = df[
        (df["trade_date"].astype(str) == trade_date)
        & (df["quantile_rank"] == quantile_rank)
    ].sort_values("ticker")
    if filtered.empty:
        return []

    quantile = "LS" if quantile_rank == 0 else f"Q{quantile_rank}"
    equal = round(1 / len(filtered), 6)
    stored = (
        filtered["weight"] if "weight" in filtered.columns else pd.Series(dtype=float)
    )
    holdings = []
    for position, ticker in enumerate(filtered["ticker"].tolist()):
        weight = stored.iloc[position] if position < len(stored) else None
        holdings.append(
            {
                "symbol": ticker,
                "weight": equal if pd.isna(weight) else round(float(weight), 6),
                "quantile": quantile,
            }
        )
    return holdings
