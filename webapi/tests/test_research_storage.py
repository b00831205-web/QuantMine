from datetime import datetime

from sqlalchemy import create_engine, text

from app.api.v1.research.results import (
    build_backtest_summary_cards,
    fetch_backtest_summary_rows,
    fetch_research_runs,
)


def test_fetch_research_runs_returns_rows_newest_first() -> None:
    """Database rows are materialized and ordered by newest run id first."""
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE research_runs (
                    run_id INTEGER PRIMARY KEY,
                    run_timestamp TIMESTAMP NOT NULL
                )
                """
            )
        )
        connection.execute(
            text(
                "INSERT INTO research_runs (run_id, run_timestamp) "
                "VALUES (:run_id, :run_timestamp)"
            ),
            [
                {"run_id": 41, "run_timestamp": datetime(2026, 7, 29, 9, 0)},
                {"run_id": 42, "run_timestamp": datetime(2026, 7, 30, 9, 0)},
            ],
        )

    rows = fetch_research_runs(engine)

    assert [row["run_id"] for row in rows] == [42, 41]


def test_build_backtest_summary_cards_pivots_one_factor_period() -> None:
    """Long metric rows become one frontend-ready card per factor and period."""
    metric_rows = [
        {
            "variant_name": "raw", "backtest_id": "raw_test", "test_id": "newey_raw",
            "factor_name": "momentum_20d", "period": 5, "quantile_rank": 1,
            "metric_name": "yearly_return", "metric_value": -0.02,
        },
        {
            "variant_name": "raw", "backtest_id": "raw_test", "test_id": "newey_raw",
            "factor_name": "momentum_20d", "period": 5, "quantile_rank": 5,
            "metric_name": "yearly_return", "metric_value": 0.11,
        },
        {
            "variant_name": "raw", "backtest_id": "raw_test", "test_id": "newey_raw",
            "factor_name": "momentum_20d", "period": 5, "quantile_rank": 0,
            "metric_name": "yearly_return", "metric_value": 0.13,
        },
        {
            "variant_name": "raw", "backtest_id": "raw_test", "test_id": "newey_raw",
            "factor_name": "momentum_20d", "period": 5, "quantile_rank": 0,
            "metric_name": "sharp_ratio", "metric_value": 1.2,
        },
        {
            "variant_name": "raw", "backtest_id": "raw_test", "test_id": "newey_raw",
            "factor_name": "momentum_20d", "period": 5, "quantile_rank": 0,
            "metric_name": "max_drawdown", "metric_value": -0.08,
        },
        {
            "variant_name": "raw", "backtest_id": "raw_test", "test_id": "newey_raw",
            "factor_name": "momentum_20d", "period": 5, "quantile_rank": 0,
            "metric_name": "win_rate", "metric_value": 0.55,
        },
    ]

    cards = build_backtest_summary_cards(metric_rows)

    assert cards == [
        {
            "variant_name": "raw",
            "backtest_id": "raw_test",
            "test_id": "newey_raw",
            "factor_name": "momentum_20d",
            "period": 5,
            "quantile_yearly_returns": {
                "Q1": -0.02,
                "Q5": 0.11,
                "longShort": 0.13,
            },
            "sharpe": 1.2,
            "max_drawdown": -0.08,
            "win_rate": 0.55,
        }
    ]


def test_fetch_backtest_summary_rows_paginates_cards_not_metric_rows() -> None:
    """A page contains complete factor-period cards and counts groups, not rows."""
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE backtest_metrics (
                    run_id INTEGER NOT NULL,
                    variant_name TEXT NOT NULL,
                    backtest_id TEXT NOT NULL,
                    test_id TEXT NOT NULL,
                    factor_name TEXT NOT NULL,
                    period INTEGER NOT NULL,
                    quantile_rank INTEGER NOT NULL,
                    metric_name TEXT NOT NULL,
                    metric_value FLOAT
                )
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO backtest_metrics (
                    run_id, variant_name, backtest_id, test_id, factor_name,
                    period, quantile_rank, metric_name, metric_value
                ) VALUES (
                    :run_id, :variant_name, :backtest_id, :test_id, :factor_name,
                    :period, :quantile_rank, :metric_name, :metric_value
                )
                """
            ),
            [
                {
                    "run_id": 42, "variant_name": "raw", "backtest_id": "job",
                    "test_id": "newey", "factor_name": "alpha", "period": 5,
                    "quantile_rank": 0, "metric_name": "yearly_return", "metric_value": 0.10,
                },
                {
                    "run_id": 42, "variant_name": "raw", "backtest_id": "job",
                    "test_id": "newey", "factor_name": "alpha", "period": 5,
                    "quantile_rank": 0, "metric_name": "sharp_ratio", "metric_value": 1.5,
                },
                {
                    "run_id": 42, "variant_name": "raw", "backtest_id": "job",
                    "test_id": "newey", "factor_name": "zeta", "period": 5,
                    "quantile_rank": 0, "metric_name": "yearly_return", "metric_value": 0.20,
                },
            ],
        )

    cards, total = fetch_backtest_summary_rows(
        engine,
        run_id=42,
        variant="raw",
        page=1,
        page_size=1,
    )

    assert total == 2
    assert cards == [
        {
            "variant_name": "raw",
            "backtest_id": "job",
            "test_id": "newey",
            "factor_name": "alpha",
            "period": 5,
            "quantile_yearly_returns": {"longShort": 0.10},
            "sharpe": 1.5,
            "max_drawdown": None,
            "win_rate": None,
        }
    ]
