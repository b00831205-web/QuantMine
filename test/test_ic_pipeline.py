"""Contract tests for the split -> IC preparation -> IC calculation pipeline."""

import numpy as np
import pandas as pd

from quantmine.ic_calculator import (
    ICVariant,
    TEST_METHOD,
    calculate_ic,
    forward_return,
    orthogonalize_analysis,
    prepare_ic_inputs,
    prepare_raw_variant,
    run_test,
    test_time_stationary as run_time_stationarity,
)
from quantmine.workflows.ic import run_ic_workflow


def test_prepared_inputs_produce_separate_train_and_test_ic(tmp_path):
    """The pipeline must prepare returns once, split by date, and calculate both IC sets."""
    dates = pd.date_range("2024-01-01", periods=12, freq="B")
    columns = ["A", "B", "C"]
    close = pd.DataFrame(
        {
            ticker: 100 + offset + np.arange(len(dates)) * (offset + 1)
            for offset, ticker in enumerate(columns)
        },
        index=dates,
    )
    factors = {
        "factor_1": pd.DataFrame(
            [np.roll(np.arange(len(columns)), shift) for shift in range(len(dates))],
            index=dates,
            columns=columns,
        )
    }
    train_end = str(dates[5].date())
    test_start = str(dates[6].date())

    prepared = prepare_ic_inputs(
        close=close,
        factors=factors,
        train_end=train_end,
        test_start=test_start,
        periods=[1],
    )

    expected_forward_returns = forward_return(close, periods=[1])[1]
    pd.testing.assert_frame_equal(
        prepared["forward_returns"]["train"][1],
        expected_forward_returns.loc[:train_end],
    )
    pd.testing.assert_frame_equal(
        prepared["forward_returns"]["test"][1],
        expected_forward_returns.loc[test_start:],
    )

    results = calculate_ic(
        prepared,
        str(tmp_path / "cs_ic.parquet"),
    )

    assert set(results) == {"train", "test"}
    for scope in ("train", "test"):
        assert isinstance(results[scope], pd.DataFrame)
        assert list(results[scope].columns) == [("factor_1", 1)]


def test_registered_test_and_stationarity_consume_raw_variant(tmp_path):
    """Downstream analyses must consume a variant, not raw close/factor inputs."""
    dates = pd.date_range("2024-01-01", periods=20, freq="B")
    columns = ["A", "B", "C"]
    close = pd.DataFrame(
        {
            ticker: 100 + offset + (np.arange(len(dates)) + 1) ** (offset + 1)
            for offset, ticker in enumerate(columns)
        },
        index=dates,
    )
    factors = {
        "factor_1": pd.DataFrame(
            [np.roll(np.arange(len(columns)), shift) for shift in range(len(dates))],
            index=dates,
            columns=columns,
        )
    }

    raw_variant = prepare_raw_variant(
        close=close,
        factors=factors,
        train_end=str(dates[9].date()),
        test_start=str(dates[10].date()),
        periods=[1],
        output_path=str(tmp_path / "raw_cs_ic.parquet"),
    )

    test_result, multiple_testing_result = run_test(
        variant=raw_variant,
        test_method="newey_test",
        TEST_METHOD=TEST_METHOD,
    )
    stationary_result = run_time_stationarity(
        raw_variant,
        rolling_period=2,
    )

    assert test_result[1] == "newey_test"
    # Registered test methods retain the existing (summary_df, orthogonalized)
    # return contract so multiple_testing can consume them.
    assert isinstance(test_result[0][0], pd.DataFrame)
    assert multiple_testing_result[1] == "newey_test"
    assert isinstance(multiple_testing_result[0], pd.DataFrame)
    assert isinstance(stationary_result["rolling_ic_train"], pd.DataFrame)
    assert not bool(stationary_result["orthogonalized"])


def test_orthogonalized_variant_can_run_registered_test(tmp_path):
    """Orthogonalization must return a complete variant usable by later tests."""
    dates = pd.date_range("2024-01-01", periods=20, freq="B")
    columns = ["A", "B", "C"]
    close = pd.DataFrame(
        {
            ticker: 100 + offset + (np.arange(len(dates)) + 1) ** (offset + 1)
            for offset, ticker in enumerate(columns)
        },
        index=dates,
    )
    factors = {
        "factor_1": pd.DataFrame(
            [np.roll(np.arange(len(columns)), shift) for shift in range(len(dates))],
            index=dates,
            columns=columns,
        )
    }
    raw_variant = prepare_raw_variant(
        close=close,
        factors=factors,
        train_end=str(dates[9].date()),
        test_start=str(dates[10].date()),
        periods=[1],
        output_path=str(tmp_path / "raw_cs_ic.parquet"),
    )

    orth_variant = orthogonalize_analysis(raw_variant, periods=[1])
    test_result, _ = run_test(
        variant=orth_variant,
        test_method="newey_test",
        TEST_METHOD=TEST_METHOD,
    )

    assert isinstance(orth_variant, ICVariant)
    assert orth_variant.train["orthogonalized"] is True
    assert orth_variant.test["orthogonalized"] is True
    assert isinstance(orth_variant.train["cs_ic"], pd.DataFrame)
    assert isinstance(orth_variant.test["cs_ic"], pd.DataFrame)
    assert orth_variant.transforms[-1]["name"] == "orthogonalize"
    assert isinstance(test_result[0][0], pd.DataFrame)


def test_configuration_driven_ic_workflow_returns_normalized_results():
    dates = pd.date_range("2024-01-01", periods=20, freq="B")
    columns = ["A", "B", "C"]
    close = pd.DataFrame(
        {
            ticker: 100 + offset + (np.arange(len(dates)) + 1) ** (offset + 1)
            for offset, ticker in enumerate(columns)
        },
        index=dates,
    )
    factors = {
        "factor_1": pd.DataFrame(
            [np.roll(np.arange(len(columns)), shift) for shift in range(len(dates))],
            index=dates,
            columns=columns,
        )
    }
    config = {
        "train_end": str(dates[9].date()),
        "test_start": str(dates[10].date()),
        "periods": [1],
        "processors": [],
        "tests": [
            {
                "id": "newey_raw",
                "name": "newey_test",
                "input": "raw",
                "params": {"lag_multiplier": 2},
            }
        ],
    }

    variants, results = run_ic_workflow(close, factors, config)

    assert set(variants) == {"raw"}
    assert set(results) == {"newey_raw"}
    assert results["newey_raw"]["variant_name"] == "raw"
    assert results["newey_raw"]["test_method"] == "newey_test"
    assert isinstance(results["newey_raw"]["summary"], pd.DataFrame)
    assert isinstance(results["newey_raw"]["multiple_testing"], pd.DataFrame)
