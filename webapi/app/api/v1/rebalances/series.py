"""Rebalance business logic: id parsing, net-value series building (no routes, no database access)."""


def parse_rebalance_id(rebalance_id: str) -> dict:
    """Split a composite id back into query conditions:
    {backtest_id}__{variant}__{factor}__{period}d__{trade_date}__{Qn|LS}
    """
    parts = rebalance_id.split("__")
    if len(parts) != 7:
        raise ValueError(f"invalid rebalance id: {rebalance_id}")
    run_id, backtest_id, variant, factor, period_part, trade_date, rank_part = parts
    if not period_part.endswith("d") or (
        rank_part != "LS" and not rank_part.startswith("Q")
    ):
        raise ValueError(f"invalid rebalance id: {rebalance_id}")
    return {
        "run_id": int(run_id),
        "backtest_id": backtest_id,
        "variant_name": variant,
        "factor_name": factor,
        "period": int(period_part[:-1]),
        "trade_date": trade_date,
        "quantile_rank": 0 if rank_part == "LS" else int(rank_part[1:]),
    }


def build_return_series(rows: list[dict]) -> list[dict]:
    """Compound ascending return_value into net-value points (starting at 100).
    返回 [{date, value}]，与前端 SeriesPoint 形状一致。
    """
    level = 100.0
    points = []
    for row in rows:
        if row["return_value"] is None:
            continue
        level *= 1 + float(row["return_value"])
        points.append({"date": str(row["trade_date"]), "value": round(level, 4)})
    return points

def build_contributions(
        holdings: list[dict],
        closes: list[dict],
        trade_date: str,
        next_trade_date: str|None,
) -> list[dict]:
    by_symbol: dict[str, dict[str, float]] = {}
    for row in closes:
        by_symbol.setdefault(row['ticker'], {})[str(row['trade_date'])] = row['close']

    contributions = []
    for h in holdings:
        prev = by_symbol.get(h['symbol'],{}).get(trade_date)
        nxt = (
            by_symbol.get(h['symbol'], {}).get(next_trade_date)
            if next_trade_date
            else None
        )
        if prev is None or nxt is None or prev == 0:
            continue
        contributions.append(
            {'symbol': h['symbol'], 'contribution': round(nxt / prev-1, 6)}
        )
    return contributions
