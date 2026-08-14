from sqlalchemy import create_engine, text

from app.reports.data import _fetch_backtest_groups


def _engine_with_metrics(rows: list[dict]):
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE backtest_metrics (
                    run_id INTEGER NOT NULL,
                    test_id TEXT,
                    variant_name TEXT NOT NULL,
                    backtest_id TEXT NOT NULL,
                    factor_name TEXT NOT NULL,
                    period INTEGER NOT NULL,
                    quantile_rank INTEGER,
                    metric_name TEXT NOT NULL,
                    metric_value FLOAT
                )
                """
            )
        )
        connection.execute(
            text(
                "INSERT INTO backtest_metrics (run_id, test_id, variant_name, "
                "backtest_id, factor_name, period, quantile_rank, metric_name, "
                "metric_value) VALUES (:run_id, :test_id, :variant_name, "
                ":backtest_id, :factor_name, :period, :quantile_rank, "
                ":metric_name, :metric_value)"
            ),
            rows,
        )
    return engine


def _row(backtest_id: str, metric_name: str, metric_value: float, **overrides):
    row = {
        "run_id": 1, "test_id": "newey_orthogonalized",
        "variant_name": "orthogonalized", "backtest_id": backtest_id,
        "factor_name": "TwentyDayAvgVol", "period": 5, "quantile_rank": 1,
        "metric_name": metric_name, "metric_value": metric_value,
    }
    row.update(overrides)
    return row


def test_two_jobs_sharing_a_variant_stay_separate() -> None:
    """Equal- and market-cap-weighted jobs both run the ``orthogonalized``
    variant over the same factor and period. Keying the groups without the
    backtest id collapsed them into one block whose metrics came from whichever
    row was read last, so a third of the table vanished while still looking
    complete."""
    engine = _engine_with_metrics([
        _row("orthogonalized_quintile", "yearly_return", 0.11),
        _row("mcap_quintile", "yearly_return", 0.07),
    ])

    groups = _fetch_backtest_groups(engine, 1, None)

    assert len(groups) == 2
    by_label = {g["label"]: g for g in groups}
    assert set(by_label) == {
        "mcap_quintile · orthogonalized · TwentyDayAvgVol · 5d",
        "orthogonalized_quintile · orthogonalized · TwentyDayAvgVol · 5d",
    }
    annuals = {
        label: group["rows"][0]["ann"] for label, group in by_label.items()
    }
    assert annuals[
        "orthogonalized_quintile · orthogonalized · TwentyDayAvgVol · 5d"
    ] == "11.0%"
    assert annuals["mcap_quintile · orthogonalized · TwentyDayAvgVol · 5d"] == "7.0%"


def test_monotonicity_is_attributed_to_its_own_job() -> None:
    """Monotonicity is stored per job with no quantile rank; it has to follow
    the same key or one job's correlation is reported under the other's name."""
    engine = _engine_with_metrics([
        _row("orthogonalized_quintile", "monotonicity_mean_based_corr", 0.9,
             quantile_rank=None),
        _row("mcap_quintile", "monotonicity_mean_based_corr", -0.4,
             quantile_rank=None),
    ])

    groups = _fetch_backtest_groups(engine, 1, None)

    mono = {g["label"]: g["mono"]["corr"] for g in groups}
    assert mono[
        "orthogonalized_quintile · orthogonalized · TwentyDayAvgVol · 5d"
    ] == "0.90"
    assert mono["mcap_quintile · orthogonalized · TwentyDayAvgVol · 5d"] == "-0.40"
