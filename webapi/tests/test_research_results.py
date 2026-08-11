"""Research-results API contract tests."""

from datetime import datetime

from app.api.v1.research import results


def test_research_options_route_exists(client, monkeypatch):
    """The filter endpoint exposes the newest database research run."""
    monkeypatch.setattr(
        results,
        "fetch_research_runs",
        lambda engine: [
            {
                "run_id": 42,
                "run_timestamp": datetime(2026, 7, 29, 10, 30),
            }
        ],
    )
    monkeypatch.setattr(
        results,
        "fetch_research_filter_values",
        lambda engine, run_id: {
            "variants": [],
            "test_ids": [],
            "sample_scopes": [],
        },
    )

    response = client.get("/api/v1/research/options")

    assert response.status_code == 200
    assert response.json()["defaultRunId"] == 42
    assert response.json()["runs"] == [
        {
            "runId": 42,
            "createdAt": "2026-07-29T10:30:00",
        }
    ]


def test_research_options_includes_filters_for_latest_run(client, monkeypatch):
    """Variant, test id, and scope options belong to the newest run only."""
    monkeypatch.setattr(
        results,
        "fetch_research_runs",
        lambda engine: [
            {
                "run_id": 42,
                "run_timestamp": datetime(2026, 7, 29, 10, 30),
            },
            {
                "run_id": 41,
                "run_timestamp": datetime(2026, 7, 28, 10, 30),
            },
        ],
    )
    monkeypatch.setattr(
        results,
        "fetch_research_filter_values",
        lambda engine, run_id: {
            "variants": ["raw", "orthogonalized"],
            "test_ids": ["newey_raw", "newey_orthogonalized"],
            "sample_scopes": ["train", "test"],
        },
    )

    response = client.get("/api/v1/research/options")

    assert response.status_code == 200
    assert response.json()["defaultRunId"] == 42
    assert response.json()["variants"] == ["raw", "orthogonalized"]
    assert response.json()["testIds"] == ["newey_raw", "newey_orthogonalized"]
    assert response.json()["sampleScopes"] == ["train", "test"]


def test_research_options_uses_requested_run_for_filter_values(client, monkeypatch):
    """An explicit runId must select that run's filter values, not latest's."""
    monkeypatch.setattr(
        results,
        "fetch_research_runs",
        lambda engine: [
            {"run_id": 42, "run_timestamp": datetime(2026, 7, 29, 10, 30)},
            {"run_id": 41, "run_timestamp": datetime(2026, 7, 28, 10, 30)},
        ],
    )
    monkeypatch.setattr(
        results,
        "research_run_exists",
        lambda engine, run_id: run_id == 41,
    )
    requested_run_ids: list[int] = []
    monkeypatch.setattr(
        results,
        "fetch_research_filter_values",
        lambda engine, run_id: requested_run_ids.append(run_id)
        or {
            "variants": ["orthogonalized"],
            "test_ids": ["newey_orthogonalized"],
            "sample_scopes": ["test"],
        },
    )

    response = client.get("/api/v1/research/options", params={"runId": 41})

    assert response.status_code == 200
    assert requested_run_ids == [41]
    assert response.json()["defaultRunId"] == 42
    assert response.json()["variants"] == ["orthogonalized"]
    assert response.json()["testIds"] == ["newey_orthogonalized"]
    assert response.json()["sampleScopes"] == ["test"]


def test_research_options_returns_not_found_for_unknown_requested_run(client, monkeypatch):
    """A requested run that does not exist must return the standard 404."""
    monkeypatch.setattr(
        results,
        "fetch_research_runs",
        lambda engine: [
            {"run_id": 42, "run_timestamp": datetime(2026, 7, 29, 10, 30)},
        ],
    )
    monkeypatch.setattr(results, "research_run_exists", lambda engine, run_id: False)

    response = client.get("/api/v1/research/options", params={"runId": 999})

    assert response.status_code == 404


def test_factor_results_respects_selected_filters(client, monkeypatch):
    """The factor table receives one paginated, filtered IC result set."""
    monkeypatch.setattr(results, "research_run_exists", lambda engine, run_id: True)
    monkeypatch.setattr(
        results,
        "fetch_factor_rows",
        lambda engine, **filters: (
            [
                {
                    "factor_name": "momentum_20d",
                    "period": 20,
                    "variant_name": "raw",
                    "test_id": "newey_raw",
                    "sample_scope": "train",
                    "ic_mean": 0.0412,
                    "ic_std": 0.0321,
                    "ir": 1.28,
                    "n": 252,
                    "t_stat": 3.45,
                    "p_value": 0.001,
                    "significant": True,
                    "bh_significant": True,
                }
            ],
            1,
        ),
    )

    response = client.get(
        "/api/v1/research/factors",
        params={
            "runId": 42,
            "variant": "raw",
            "testId": "newey_raw",
            "sampleScope": "train",
            "page": 1,
            "pageSize": 25,
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "items": [
            {
                "factorName": "momentum_20d",
                "period": 20,
                "variantName": "raw",
                "testId": "newey_raw",
                "sampleScope": "train",
                "icMean": 0.0412,
                "icStd": 0.0321,
                "ir": 1.28,
                "n": 252,
                "tStat": 3.45,
                "pValue": 0.001,
                "significant": True,
                "bhSignificant": True,
            }
        ],
        "total": 1,
        "page": 1,
        "pageSize": 25,
    }


def test_factor_results_returns_not_found_for_unknown_run(client, monkeypatch):
    """An unknown run is different from a known run with zero factor rows."""
    monkeypatch.setattr(results, "research_run_exists", lambda engine, run_id: False)

    response = client.get("/api/v1/research/factors", params={"runId": 999})

    assert response.status_code == 404


def test_backtest_summaries_returns_aggregated_cards(client, monkeypatch):
    """A run's long-form metrics are exposed as frontend-ready summary cards."""
    monkeypatch.setattr(results, "research_run_exists", lambda engine, run_id: True)
    monkeypatch.setattr(
        results,
        "fetch_backtest_summary_rows",
        lambda engine, **filters: (
            [
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
            ],
            1,
        ),
    )

    response = client.get(
        "/api/v1/research/backtest-summaries",
        params={"runId": 42, "variant": "raw", "testId": "newey_raw"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "items": [
            {
                "variantName": "raw",
                "backtestId": "raw_test",
                "testId": "newey_raw",
                "factorName": "momentum_20d",
                "period": 5,
                "quantileYearlyReturns": {
                    "Q1": -0.02,
                    "Q5": 0.11,
                    "longShort": 0.13,
                },
                "sharpe": 1.2,
                "maxDrawdown": -0.08,
                "winRate": 0.55,
            }
        ],
        "total": 1,
        "page": 1,
        "pageSize": 25,
    }


def test_backtest_summaries_returns_not_found_for_unknown_run(client, monkeypatch):
    """Backtest endpoint must reject an unknown run before querying metrics."""
    monkeypatch.setattr(results, "research_run_exists", lambda engine, run_id: False)

    response = client.get("/api/v1/research/backtest-summaries", params={"runId": 999})

    assert response.status_code == 404
