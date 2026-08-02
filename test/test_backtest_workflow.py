"""Contract tests for the in-memory backtest workflow."""

import numpy as np
import pandas as pd

from quantmine.ic_calculator import ICVariant, TestResult
from quantmine.workflows.backtest_workflow import (
    back_test_workflow,
    run_backtest_workflow,
    run_backtest_job,
)


def test_backtest_job_uses_train_selection_and_test_variant_data():
    """Only selector-approved factor-period pairs may reach the test backtest."""
    dates = pd.date_range("2024-01-01", periods=4, freq="B")
    tickers = [f"T{i}" for i in range(6)]
    factor_frame = pd.DataFrame(
        [np.arange(len(tickers), dtype=float)] * len(dates),
        index=dates,
        columns=tickers,
    )
    forward_return_frame = pd.DataFrame(
        {
            ticker: np.full(len(dates), index / 100)
            for index, ticker in enumerate(tickers)
        },
        index=dates,
    )
    close = pd.DataFrame(
        {
            ticker: 100 + index + np.arange(len(dates)) * (index + 1)
            for index, ticker in enumerate(tickers)
        },
        index=dates,
    )
    variant = ICVariant(
        train={},
        test={
            "factors": {"toy": factor_frame},
            "forward_returns": {1: forward_return_frame},
        },
        transforms=[],
    )
    selection_index = pd.MultiIndex.from_tuples(
        [("toy", 1), ("toy", 5)],
        names=["factor", "period"],
    )
    test_result = TestResult(
        summary=pd.DataFrame(index=selection_index),
        multiple_testing=pd.DataFrame(
            {"BH_significant": [True, False]},
            index=selection_index,
        ),
        test_method="newey_test",
        sample_scope="train",
    )
    job_config = {
        "part": 3,
        "cost_per_trade": 0.0,
        "selector": {"name": "bh", "params": {}},
    }

    job_result = run_backtest_job(
        close=close,
        variant=variant,
        test_result=test_result,
        job_config=job_config,
    )
    analysis = back_test_workflow(
        back_test_job=job_result,
        backtest_config={"part": 3},
    )

    assert job_result["status"] == "ok"
    assert job_result["selected_factor_periods"] == [("toy", 1)]
    assert set(job_result["quantile_returns"]) == {("toy", 1)}
    assert set(job_result["daily_returns"]) == {("toy", 1)}
    assert set(analysis) == {("toy", 1)}
    assert {"Q1", "Q2", "Q3", "long_short"}.issubset(
        job_result["daily_returns"][("toy", 1)].columns
    )
    assert "long_short" in analysis[("toy", 1)]["performance_summary"].index


def test_backtest_workflow_runs_configured_job_without_sensitivity():
    """The outer workflow must resolve job references and return results by id."""
    dates = pd.date_range("2024-01-01", periods=4, freq="B")
    tickers = [f"T{i}" for i in range(6)]
    factor_frame = pd.DataFrame(
        [np.arange(len(tickers), dtype=float)] * len(dates),
        index=dates,
        columns=tickers,
    )
    forward_return_frame = pd.DataFrame(
        {
            ticker: np.full(len(dates), index / 100)
            for index, ticker in enumerate(tickers)
        },
        index=dates,
    )
    close = pd.DataFrame(
        {
            ticker: 100 + index + np.arange(len(dates)) * (index + 1)
            for index, ticker in enumerate(tickers)
        },
        index=dates,
    )
    variant = ICVariant(
        train={},
        test={
            "factors": {"toy": factor_frame},
            "forward_returns": {1: forward_return_frame},
        },
        transforms=[],
    )
    selection_index = pd.MultiIndex.from_tuples(
        [("toy", 1)],
        names=["factor", "period"],
    )
    test_results = {
        "newey_raw": {
            "summary": pd.DataFrame(index=selection_index),
            "multiple_testing": pd.DataFrame(
                {"BH_significant": [True]},
                index=selection_index,
            ),
            "test_method": "newey_test",
            "sample_scope": "train",
        }
    }
    backtest_config = {
        "jobs": [
            {
                "id": "raw_test",
                "variant": "raw",
                "selection_test": "newey_raw",
                "part": 3,
                "cost_per_trade": 0.0,
                "selector": {"name": "bh", "params": {}},
                "sensitivity": {"enabled": False},
            }
        ]
    }

    results = run_backtest_workflow(
        close=close,
        variants={"raw": variant},
        test_results=test_results,
        backtest_config=backtest_config,
    )

    assert set(results) == {"raw_test"}
    assert results["raw_test"]["job"]["status"] == "ok"
    assert set(results["raw_test"]["analysis"]) == {("toy", 1)}
    assert results["raw_test"]["sanity"] is None


def test_backtest_workflow_runs_enabled_sensitivity_test():
    """An enabled sensitivity config must return the sanity-test payload."""
    dates = pd.date_range("2024-01-01", periods=4, freq="B")
    tickers = [f"T{i}" for i in range(6)]
    factor_frame = pd.DataFrame(
        [np.arange(len(tickers), dtype=float)] * len(dates),
        index=dates,
        columns=tickers,
    )
    forward_return_frame = pd.DataFrame(
        {
            ticker: np.full(len(dates), index / 100)
            for index, ticker in enumerate(tickers)
        },
        index=dates,
    )
    close = pd.DataFrame(
        {
            ticker: 100 + index + np.arange(len(dates)) * (index + 1)
            for index, ticker in enumerate(tickers)
        },
        index=dates,
    )
    variant = ICVariant(
        train={},
        test={
            "factors": {"toy": factor_frame},
            "forward_returns": {1: forward_return_frame},
        },
        transforms=[],
    )
    selection_index = pd.MultiIndex.from_tuples(
        [("toy", 1)],
        names=["factor", "period"],
    )
    test_results = {
        "newey_raw": {
            "summary": pd.DataFrame(index=selection_index),
            "multiple_testing": pd.DataFrame(
                {"BH_significant": [True]},
                index=selection_index,
            ),
            "test_method": "newey_test",
            "sample_scope": "train",
        }
    }
    backtest_config = {
        "jobs": [
            {
                "id": "raw_test",
                "variant": "raw",
                "selection_test": "newey_raw",
                "part": 3,
                "cost_per_trade": 0.0,
                "selector": {"name": "bh", "params": {}},
                "sensitivity": {"enabled": True, "random_seed": 42},
            }
        ]
    }

    results = run_backtest_workflow(
        close=close,
        variants={"raw": variant},
        test_results=test_results,
        backtest_config=backtest_config,
    )

    sanity_result = results["raw_test"]["sanity"]
    assert sanity_result is not None
    assert set(sanity_result) == {
        "forward_return_difference",
        "displaced_differences",
        "shuffled_differences",
        "summary",
    }
