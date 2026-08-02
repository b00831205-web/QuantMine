"""Tests for registered factor-period selection rules."""

import pandas as pd
import pytest

from quantmine.ic_calculator import (
    TestResult,
    get_significant_factor,
    select_significant_factor_periods,
)


def test_bh_selector_returns_only_significant_factor_period_pairs():
    """BH selection must retain both factor name and holding period."""
    index = pd.MultiIndex.from_tuples(
        [
            ("momentum", 1),
            ("momentum", 5),
            ("daily_return", 20),
        ],
        names=["factor", "period"],
    )
    test_result = TestResult(
        summary=pd.DataFrame(index=index),
        multiple_testing=pd.DataFrame(
            {"BH_significant": [False, True, True]},
            index=index,
        ),
        test_method="newey_test",
        sample_scope="train",
    )

    selected_pairs = select_significant_factor_periods(
        test_result=test_result,
        selector_name="bh",
    )

    assert selected_pairs == [
        ("momentum", 5),
        ("daily_return", 20),
    ]


def test_get_significant_factor_forwards_direct_selector_parameters():
    index = pd.MultiIndex.from_tuples(
        [("momentum", 5)],
        names=["factor", "period"],
    )
    test_result = TestResult(
        summary=pd.DataFrame({"p_value": [0.02]}, index=index),
        multiple_testing=None,
        test_method="newey_test",
        sample_scope="train",
    )

    assert get_significant_factor(
        test_result,
        "p_value",
        alpha=0.01,
    ) == []


def test_unknown_selector_has_a_clear_error():
    test_result = TestResult(
        summary=pd.DataFrame(),
        multiple_testing=None,
        test_method="newey_test",
        sample_scope="train",
    )

    with pytest.raises(ValueError, match="Unknown factor selector"):
        select_significant_factor_periods(
            test_result,
            "missing",
        )
