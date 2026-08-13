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

    Two different absences, two different answers. An artifact with no ``weight``
    column at all predates weight persistence; those runs were equal-weighted, so
    ``1/n`` reproduces them faithfully. A null *within* a weighted set means
    something else: the weighting scheme found no market cap for that name on
    that date, and ``_weighted_group_return`` dropped it, so the backtest held no
    position in it. Reporting ``1/n`` there would invent a position the strategy
    never took and push the column past 100%.
    """
    df = pd.read_parquet(path)

    filtered = df[
        (df["trade_date"].astype(str) == trade_date)
        & (df["quantile_rank"] == quantile_rank)
    ].sort_values("ticker")
    if filtered.empty:
        return []

    quantile = "LS" if quantile_rank == 0 else f"Q{quantile_rank}"
    has_weights = "weight" in filtered.columns
    equal = round(1 / len(filtered), 6)
    weights = filtered["weight"].tolist() if has_weights else []
    return [
        {
            "symbol": ticker,
            "weight": (
                equal
                if not has_weights
                else 0.0
                if pd.isna(weights[position])
                else round(float(weights[position]), 6)
            ),
            "quantile": quantile,
        }
        for position, ticker in enumerate(filtered["ticker"].tolist())
    ]
