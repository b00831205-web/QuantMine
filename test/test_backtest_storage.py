"""Contract tests for backtest persistence helpers."""

import pandas as pd
import pandas.testing as pdt

from quantmine.storage import backtest as backtest_storage
from quantmine.storage.backtest import (
    build_backtest_metric_rows,
    build_backtest_rows,
    write_dataframe_artifact,
)


def test_build_backtest_rows_adds_variant_and_quantile_identity():
    dates = pd.to_datetime(["2026-07-20", "2026-07-21"])
    result = pd.DataFrame(
        {
            "Q1": [0.01, 0.02],
            "Q5": [0.03, 0.04],
            "long_short": [0.02, 0.02],
        },
        index=dates,
    )

    rows = build_backtest_rows(
        {("momentum", 5): result},
        run_id=7,
        variant_name="orthogonalized",
        backtest_id="orth_quintile",
        test_id="newey_orthogonalized",
    )

    assert len(rows) == 6
    assert set(rows["quantile_rank"]) == {0, 1, 5}
    assert rows["run_id"].eq(7).all()
    assert rows["variant_name"].eq("orthogonalized").all()
    assert rows["factor_name"].eq("momentum").all()
    assert rows["period"].eq(5).all()


def test_build_backtest_metric_rows_flattens_summary_and_monotonicity():
    summary = pd.DataFrame(
        {
            "yearly_return": [0.10, 0.25],
            "sharp_ratio": [0.80, 1.50],
        },
        index=pd.Index(["Q1", "long_short"], name="quantile"),
    )
    analysis = {
        ("momentum", 5): {
            "performance_summary": summary,
            "monotonicity_test_result": {
                "mean_based_corr": 0.9,
                "daily_avg_corr": 0.7,
                "part": 5,
            },
        }
    }

    rows = build_backtest_metric_rows(
        analysis,
        run_id=7,
        variant_name="raw",
        backtest_id="raw_test",
        test_id="newey_raw",
    )

    assert len(rows) == 6
    assert rows["run_id"].eq(7).all()
    assert rows["variant_name"].eq("raw").all()
    assert rows["backtest_id"].eq("raw_test").all()
    assert rows["test_id"].eq("newey_raw").all()
    assert rows["factor_name"].eq("momentum").all()
    assert rows["period"].eq(5).all()

    summary_rows = rows[~rows["metric_name"].str.startswith("monotonicity_")]
    assert set(summary_rows[summary_rows["quantile_rank"] == 1]["metric_name"]) == {
        "yearly_return",
        "sharp_ratio",
    }
    assert set(summary_rows[summary_rows["quantile_rank"] == 0]["metric_name"]) == {
        "yearly_return",
        "sharp_ratio",
    }

    monotonicity_rows = rows[rows["metric_name"].str.startswith("monotonicity_")]
    assert set(monotonicity_rows["metric_name"]) == {
        "monotonicity_mean_based_corr",
        "monotonicity_daily_avg_corr",
    }
    assert monotonicity_rows["quantile_rank"].eq(0).all()


def test_write_dataframe_artifact_round_trips_parquet_and_sanitizes_name(tmp_path):
    dataframe = pd.DataFrame(
        {"Q1": [0.01, 0.02], "long_short": [0.03, 0.04]},
        index=pd.to_datetime(["2026-07-20", "2026-07-21"]),
    )

    path, row_count = write_dataframe_artifact(
        dataframe=dataframe,
        artifact_dir=tmp_path,
        run_id=7,
        backtest_id="raw_test",
        artifact_type="net/return_curve",
        artifact_key="momentum/5",
    )

    assert row_count == 2
    assert path.endswith("net_return_curve__momentum_5.parquet")
    restored = pd.read_parquet(path)
    pdt.assert_frame_equal(restored, dataframe)


def test_save_backtest_workflow_results_routes_one_successful_job(monkeypatch, tmp_path):
    calls = {"result_rows": None, "metric_rows": None, "artifacts": []}

    def fake_save_backtest_results(engine, rows):
        calls["result_rows"] = rows
        return len(rows)

    def fake_save_backtest_metrics(engine, rows):
        calls["metric_rows"] = rows
        return len(rows)

    def fake_write_dataframe_artifact(**kwargs):
        calls["artifacts"].append(kwargs)
        return str(tmp_path / "curve.parquet"), len(kwargs["dataframe"])

    def fake_save_backtest_artifact_record(**kwargs):
        return 1

    monkeypatch.setattr(backtest_storage, "save_backtest_results", fake_save_backtest_results)
    monkeypatch.setattr(backtest_storage, "save_backtest_metrics", fake_save_backtest_metrics)
    monkeypatch.setattr(backtest_storage, "write_dataframe_artifact", fake_write_dataframe_artifact)
    monkeypatch.setattr(
        backtest_storage,
        "save_backtest_artifact_record",
        fake_save_backtest_artifact_record,
    )

    dates = pd.to_datetime(["2026-07-20", "2026-07-21"])
    daily_returns = {
        ("momentum", 5): pd.DataFrame(
            {"Q1": [0.01, 0.02], "long_short": [0.02, 0.03]}, index=dates
        )
    }
    workflow_results = {
        "raw_test": {
            "job": {"status": "ok", "daily_returns": daily_returns},
            "analysis": {
                ("momentum", 5): {
                    "performance_summary": pd.DataFrame(
                        {"sharp_ratio": [1.2]}, index=["long_short"]
                    ),
                    "monotonicity_test_result": {"mean_based_corr": 0.8, "part": 5},
                    "net_return_df": pd.DataFrame(
                        {"long_short": [1.02, 1.05]}, index=dates
                    ),
                }
            },
            "sanity": None,
        }
    }
    config = {
        "jobs": [
            {
                "id": "raw_test",
                "variant": "raw",
                "selection_test": "newey_raw",
            }
        ]
    }

    saved = backtest_storage.save_backtest_workflow_results(
        engine=object(),
        workflow_results=workflow_results,
        run_id=7,
        backtest_config=config,
        artifact_dir=tmp_path,
    )

    assert saved["raw_test"] == {
        "status": "ok",
        "result_rows": 4,
        "metric_rows": 2,
        "artifact_rows": 1,
    }
    assert calls["result_rows"] is not None
    assert calls["metric_rows"] is not None
    assert len(calls["artifacts"]) == 1
    assert calls["artifacts"][0]["artifact_type"] == "net_return_curve"


def test_save_backtest_workflow_results_reports_job_with_empty_analysis(
    monkeypatch,
    tmp_path,
):
    """A successful job must be reported even when it produced no artifacts."""
    monkeypatch.setattr(
        backtest_storage,
        "save_backtest_results",
        lambda engine, rows: len(rows),
    )
    monkeypatch.setattr(
        backtest_storage,
        "save_backtest_metrics",
        lambda engine, rows: len(rows),
    )

    workflow_results = {
        "empty_job": {
            "job": {
                "status": "ok",
                "daily_returns": {},
            },
            "analysis": {},
            "sanity": None,
        }
    }
    config = {
        "jobs": [
            {
                "id": "empty_job",
                "variant": "raw",
                "selection_test": "newey_raw",
            }
        ]
    }

    saved = backtest_storage.save_backtest_workflow_results(
        engine=object(),
        workflow_results=workflow_results,
        run_id=7,
        backtest_config=config,
        artifact_dir=tmp_path,
    )

    assert saved["empty_job"] == {
        "status": "ok",
        "result_rows": 0,
        "metric_rows": 0,
        "artifact_rows": 0,
    }
