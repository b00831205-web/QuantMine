"""Tests for turning stored backtest returns into chart-ready net-value series."""

from datetime import date

from app.api.v1.research import backtest_series
from app.api.v1.research.backtest_series import build_backtest_series


def test_build_backtest_series_compounds_each_quantile_in_date_order() -> None:
    """Each portfolio starts at 100 and compounds its own daily return stream."""
    rows = [
        {"trade_date": date(2024, 1, 2), "quantile_rank": 1, "return_value": 0.01},
        {"trade_date": date(2024, 1, 3), "quantile_rank": 1, "return_value": 0.02},
        {"trade_date": date(2024, 1, 2), "quantile_rank": 5, "return_value": -0.02},
        {"trade_date": date(2024, 1, 3), "quantile_rank": 5, "return_value": 0.03},
        {"trade_date": date(2024, 1, 2), "quantile_rank": 0, "return_value": 0.02},
        {"trade_date": date(2024, 1, 3), "quantile_rank": 0, "return_value": -0.01},
    ]

    base_date, series = build_backtest_series(rows)

    assert base_date == date(2024, 1, 2)
    assert series == [
        {
            "symbol": "Long-Short",
            "points": [
                {"date": date(2024, 1, 2), "value": 102.0},
                {"date": date(2024, 1, 3), "value": 100.98},
            ],
        },
        {
            "symbol": "Q1",
            "points": [
                {"date": date(2024, 1, 2), "value": 101.0},
                {"date": date(2024, 1, 3), "value": 103.02},
            ],
        },
        {
            "symbol": "Q5",
            "points": [
                {"date": date(2024, 1, 2), "value": 98.0},
                {"date": date(2024, 1, 3), "value": 100.94},
            ],
        },
    ]


def test_backtest_series_route_returns_chart_payload(client, monkeypatch) -> None:
    """A card identity returns only its compounded, chart-ready portfolios."""
    monkeypatch.setattr(backtest_series, "research_run_exists", lambda engine, run_id: True)
    monkeypatch.setattr(
        backtest_series,
        "fetch_backtest_return_rows",
        lambda engine, **filters: [
            {
                "trade_date": date(2024, 1, 2),
                "quantile_rank": 1,
                "return_value": 0.01,
            },
            {
                "trade_date": date(2024, 1, 3),
                "quantile_rank": 1,
                "return_value": 0.02,
            },
        ],
    )

    response = client.get(
        "/api/v1/research/backtest-series",
        params={
            "runId": 10,
            "variant": "legacy_tmp_raw",
            "backtestId": "legacy_tmp_after_cost",
            "testId": "legacy_tmp_bh",
            "factorName": "Momentum",
            "period": 5,
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "baseDate": "2024-01-02",
        "series": [
            {
                "symbol": "Q1",
                "points": [
                    {"date": "2024-01-02", "value": 101.0},
                    {"date": "2024-01-03", "value": 103.02},
                ],
            }
        ],
    }


def test_backtest_series_route_returns_empty_payload_when_returns_are_absent(
    client,
    monkeypatch,
) -> None:
    """A valid legacy card without daily rows is an empty chart, not a missing run."""
    monkeypatch.setattr(backtest_series, "research_run_exists", lambda engine, run_id: True)
    monkeypatch.setattr(backtest_series, "fetch_backtest_return_rows", lambda engine, **_: [])

    response = client.get(
        "/api/v1/research/backtest-series",
        params={
            "runId": 10,
            "variant": "legacy_tmp_raw",
            "backtestId": "legacy_tmp_after_cost",
            "testId": "legacy_tmp_bh",
            "factorName": "Momentum",
            "period": 5,
        },
    )

    assert response.status_code == 200
    assert response.json() == {"baseDate": None, "series": []}
