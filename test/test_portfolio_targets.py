"""Tests for quantile-history to portfolio-target conversion."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from quantmine.plugins.context import SourceContext
from quantmine.plugins.market_rules import create_unrestricted_market_rules
from quantmine.storage.connections import ConnectionRegistry
from quantmine.workflows.portfolio_targets import (
    build_quantile_target_weights,
)
from quantmine.workflows.position_backtest import run_position_backtest


def _tickers() -> pd.Index:
    return pd.Index(["AAA", "BBB", "CCC"], name="ticker")


def test_quantile_targets_preserve_and_normalize_current_weights() -> None:
    history = [
        {
            "date": pd.Timestamp("2026-09-17"),
            "Q5": {"AAA": 6.0, "BBB": 4.0},
        },
        {
            "date": pd.Timestamp("2026-09-21"),
            "Q5": {"BBB": 1.0, "CCC": 3.0},
        },
    ]

    actual = build_quantile_target_weights(
        history,
        tickers=_tickers(),
        group="Q5",
    )

    expected = pd.DataFrame(
        {
            "AAA": [0.6, 0.0],
            "BBB": [0.4, 0.25],
            "CCC": [0.0, 0.75],
        },
        index=pd.DatetimeIndex(
            ["2026-09-17", "2026-09-21"],
            name="date",
        ),
    )
    expected.columns.name = "ticker"
    pd.testing.assert_frame_equal(actual, expected)


@pytest.mark.parametrize(
    "members",
    [
        ["AAA", "BBB"],
        {"AAA", "BBB"},
        ("AAA", "BBB"),
    ],
)
def test_quantile_targets_support_legacy_membership_iterables(
    members: object,
) -> None:
    actual = build_quantile_target_weights(
        [{"date": pd.Timestamp("2026-09-17"), "Q5": members}],
        tickers=_tickers(),
        group="Q5",
    )

    assert actual.loc[pd.Timestamp("2026-09-17")].to_dict() == {
        "AAA": 0.5,
        "BBB": 0.5,
        "CCC": 0.0,
    }


def test_quantile_targets_apply_cash_buffer_after_normalization() -> None:
    actual = build_quantile_target_weights(
        [
            {
                "date": pd.Timestamp("2026-09-17"),
                "Q5": {"AAA": 3.0, "BBB": 1.0},
            }
        ],
        tickers=_tickers(),
        group="Q5",
        gross_exposure=0.8,
    )

    assert actual.iloc[0].to_dict() == {
        "AAA": pytest.approx(0.6),
        "BBB": pytest.approx(0.2),
        "CCC": 0.0,
    }
    assert actual.iloc[0].sum() == pytest.approx(0.8)


def test_quantile_targets_return_typed_empty_schedule() -> None:
    actual = build_quantile_target_weights(
        [],
        tickers=_tickers(),
        group="Q5",
    )

    assert actual.empty
    assert actual.columns.equals(_tickers())
    assert isinstance(actual.index, pd.DatetimeIndex)
    assert actual.index.name == "date"


def test_quantile_targets_feed_position_backtest_directly(
    tmp_path: Path,
) -> None:
    dates = pd.DatetimeIndex(["2026-09-17", "2026-09-18"])
    close = pd.DataFrame(
        {
            "AAA": [10.0, 11.0],
            "BBB": [20.0, 20.0],
            "CCC": [30.0, 30.0],
        },
        index=dates,
    )
    targets = build_quantile_target_weights(
        [
            {
                "date": dates[0],
                "Q5": {"AAA": 0.6, "BBB": 0.4},
            }
        ],
        tickers=close.columns,
        group="Q5",
    )

    result = run_position_backtest(
        close=close,
        target_weights=targets,
        initial_cash=1_000.0,
        component=create_unrestricted_market_rules(),
        context=SourceContext(
            connections=ConnectionRegistry({}),
            run_id=701,
            artifact_dir=tmp_path / "artifacts",
        ),
    )

    assert result.positions.loc[dates[0]].to_dict() == {
        "AAA": 60.0,
        "BBB": 20.0,
        "CCC": 0.0,
    }
    assert result.cash_curve.iloc[0] == 0.0
    assert result.equity_curve.tolist() == [1_000.0, 1_060.0]


def test_quantile_targets_reject_unknown_ticker() -> None:
    with pytest.raises(ValueError, match="unavailable.*ZZZ"):
        build_quantile_target_weights(
            [
                {
                    "date": pd.Timestamp("2026-09-17"),
                    "Q5": {"ZZZ": 1.0},
                }
            ],
            tickers=_tickers(),
            group="Q5",
        )


def test_quantile_targets_reject_non_increasing_dates() -> None:
    history = [
        {
            "date": pd.Timestamp("2026-09-18"),
            "Q5": {"AAA": 1.0},
        },
        {
            "date": pd.Timestamp("2026-09-17"),
            "Q5": {"BBB": 1.0},
        },
    ]

    with pytest.raises(ValueError, match="strictly increasing"):
        build_quantile_target_weights(
            history,
            tickers=_tickers(),
            group="Q5",
        )


@pytest.mark.parametrize(
    "members",
    [
        {},
        {"AAA": 0.0},
        {"AAA": -1.0},
        {"AAA": float("nan")},
        ["AAA", "AAA"],
    ],
)
def test_quantile_targets_reject_invalid_group_members(
    members: object,
) -> None:
    with pytest.raises((TypeError, ValueError), match="quantile group"):
        build_quantile_target_weights(
            [{"date": pd.Timestamp("2026-09-17"), "Q5": members}],
            tickers=_tickers(),
            group="Q5",
        )


@pytest.mark.parametrize(
    "gross_exposure",
    [True, -0.1, 1.1, float("nan")],
)
def test_quantile_targets_reject_invalid_exposure(
    gross_exposure: object,
) -> None:
    with pytest.raises((TypeError, ValueError), match="gross_exposure"):
        build_quantile_target_weights(
            [
                {
                    "date": pd.Timestamp("2026-09-17"),
                    "Q5": {"AAA": 1.0},
                }
            ],
            tickers=_tickers(),
            group="Q5",
            gross_exposure=gross_exposure,  # type: ignore[arg-type]
        )
