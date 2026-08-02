"""Tests for importing legacy parquet backtest summaries into metric rows."""

import importlib
import sys
from pathlib import Path

import pandas as pd


def test_build_legacy_backtest_metric_rows_preserves_quantile_and_monotonicity_metrics():
    """A legacy summary becomes long-form rows compatible with backtest_metrics."""
    summary = pd.DataFrame(
        {
            "yearly_return": [-0.02, 0.11, 0.13],
            "volatility": [0.15, 0.17, 0.09],
            "sharp_ratio": [-0.1, 0.65, 1.2],
            "max_drawdown": [-0.20, -0.18, -0.08],
            "win_rate": [0.51, 0.57, 0.55],
        },
        index=pd.Index(["Q1", "Q5", "long_short"], name="quantile"),
    )
    monotonicity = pd.DataFrame(
        {
            "mean_based_corr": [0.9],
            "mean_based_pvalue": [0.01],
            "daily_avg_corr": [0.4],
            "daily_corr_positive_pct": [0.53],
        },
    )

    importer = importlib.import_module("scripts.import_legacy_tmp_backtest_metrics")
    rows = importer.build_legacy_backtest_metric_rows(
        summary=summary,
        monotonicity=monotonicity,
        run_id=10,
        variant_name="legacy_tmp_raw",
        backtest_id="legacy_tmp_after_cost",
        test_id="legacy_tmp_bh",
        factor_name="TwentyDayAvgVol",
        period=1,
    )

    q1_yearly_return = rows.loc[
        (rows["quantile_rank"] == 1)
        & (rows["metric_name"] == "yearly_return")
    ].iloc[0]
    long_short_sharpe = rows.loc[
        (rows["quantile_rank"] == 0)
        & (rows["metric_name"] == "sharp_ratio")
    ].iloc[0]
    monotonicity_row = rows.loc[
        rows["metric_name"] == "monotonicity_mean_based_corr"
    ].iloc[0]

    assert len(rows) == 19
    assert q1_yearly_return["metric_value"] == -0.02
    assert long_short_sharpe["metric_value"] == 1.2
    assert monotonicity_row["quantile_rank"] == 0
    assert monotonicity_row["metric_value"] == 0.9
    assert set(rows["run_id"]) == {10}
    assert set(rows["factor_name"]) == {"TwentyDayAvgVol"}


def test_discover_legacy_backtest_cases_pairs_after_cost_summary_with_monotonicity(
    tmp_path: Path,
):
    """Each legacy after-cost summary must be paired with its mono parquet."""
    summary_path = (
        tmp_path / "5DaysHoldingPeriod_TwentyDayAvgVol_summary_after_cost.parquet"
    )
    mono_path = tmp_path / "5DaysHoldingPeriod_TwentyDayAvgVol_mono.parquet"
    summary_path.touch()
    mono_path.touch()

    importer = importlib.import_module("scripts.import_legacy_tmp_backtest_metrics")
    cases = importer.discover_legacy_backtest_cases(tmp_path)

    assert cases == [
        {
            "period": 5,
            "factor_name": "TwentyDayAvgVol",
            "summary_path": summary_path,
            "monotonicity_path": mono_path,
        }
    ]


def test_discover_legacy_backtest_cases_allows_missing_monotonicity(
    tmp_path: Path,
):
    """A valid after-cost summary remains importable when mono analysis was skipped."""
    summary_path = tmp_path / "1DaysHoldingPeriod_DailyReturn_summary_after_cost.parquet"
    summary_path.touch()

    importer = importlib.import_module("scripts.import_legacy_tmp_backtest_metrics")
    cases = importer.discover_legacy_backtest_cases(tmp_path)

    assert cases == [
        {
            "period": 1,
            "factor_name": "DailyReturn",
            "summary_path": summary_path,
            "monotonicity_path": None,
        }
    ]


def test_discover_legacy_backtest_return_cases_reads_factor_and_period(
    tmp_path: Path,
):
    """Legacy daily-return filenames retain their factor and holding period."""
    raw_path = tmp_path / "backtest_Momentum_5daysholdingperiod.parquet"
    raw_path.touch()

    importer = importlib.import_module("scripts.import_legacy_tmp_backtest_metrics")

    assert importer.discover_legacy_backtest_return_cases(tmp_path) == [
        {
            "factor_name": "Momentum",
            "period": 5,
            "path": raw_path,
        }
    ]


def test_build_legacy_backtest_metric_rows_allows_missing_monotonicity():
    """Skipping mono analysis must not prevent importing core backtest metrics."""
    summary = pd.DataFrame(
        {"yearly_return": [0.02, 0.08]},
        index=pd.Index(["Q1", "long_short"], name="quantile"),
    )

    importer = importlib.import_module("scripts.import_legacy_tmp_backtest_metrics")
    rows = importer.build_legacy_backtest_metric_rows(
        summary=summary,
        monotonicity=None,
        run_id=10,
        variant_name="legacy_tmp_raw",
        backtest_id="legacy_tmp_after_cost",
        test_id="legacy_tmp_bh",
        factor_name="DailyReturn",
        period=1,
    )

    assert len(rows) == 2
    assert set(rows["metric_name"]) == {"yearly_return"}
    assert set(rows["quantile_rank"]) == {0, 1}


def test_build_all_legacy_backtest_metric_rows_reads_and_combines_cases(
    monkeypatch,
    tmp_path: Path,
):
    """Every discovered parquet pair contributes rows to one write-ready frame."""
    importer = importlib.import_module("scripts.import_legacy_tmp_backtest_metrics")
    summary_path = tmp_path / "1DaysHoldingPeriod_DailyReturn_summary_after_cost.parquet"
    mono_path = tmp_path / "1DaysHoldingPeriod_DailyReturn_mono.parquet"
    cases = [
        {
            "period": 1,
            "factor_name": "DailyReturn",
            "summary_path": summary_path,
            "monotonicity_path": mono_path,
        }
    ]
    summary = pd.DataFrame(
        {"yearly_return": [0.02, 0.08]},
        index=pd.Index(["Q1", "long_short"], name="quantile"),
    )
    monotonicity = pd.DataFrame({"mean_based_corr": [0.9]})

    monkeypatch.setattr(importer, "discover_legacy_backtest_cases", lambda _: cases)
    monkeypatch.setattr(
        importer.pd,
        "read_parquet",
        lambda path: summary if path == summary_path else monotonicity,
    )

    rows = importer.build_all_legacy_backtest_metric_rows(
        backtest_dir=tmp_path,
        run_id=10,
        variant_name="legacy_tmp_raw",
        backtest_id="legacy_tmp_after_cost",
        test_id="legacy_tmp_bh",
    )

    assert len(rows) == 3
    assert set(rows["factor_name"]) == {"DailyReturn"}
    assert set(rows["metric_name"]) == {
        "yearly_return",
        "monotonicity_mean_based_corr",
    }


def test_build_all_legacy_backtest_return_rows_reuses_shared_row_builder(
    monkeypatch,
    tmp_path: Path,
):
    """Legacy daily-return frames become write-ready backtest_results rows."""
    importer = importlib.import_module("scripts.import_legacy_tmp_backtest_metrics")
    return_path = tmp_path / "backtest_Momentum_5daysholdingperiod.parquet"
    daily_returns = pd.DataFrame(
        {
            "Q1": [0.01, -0.02],
            "Q5": [0.03, 0.04],
            "long_short": [0.02, 0.06],
        },
        index=pd.to_datetime(["2024-01-02", "2024-01-03"]),
    )

    monkeypatch.setattr(
        importer,
        "discover_legacy_backtest_return_cases",
        lambda _: [
            {
                "factor_name": "Momentum",
                "period": 5,
                "path": return_path,
            }
        ],
    )
    monkeypatch.setattr(importer.pd, "read_parquet", lambda _: daily_returns)

    rows = importer.build_all_legacy_backtest_return_rows(
        backtest_dir=tmp_path,
        run_id=10,
        variant_name="legacy_tmp_raw",
        backtest_id="legacy_tmp_after_cost",
        test_id="legacy_tmp_bh",
    )

    assert len(rows) == 6
    assert set(rows["factor_name"]) == {"Momentum"}
    assert set(rows["period"]) == {5}
    assert set(rows["quantile_rank"]) == {0, 1, 5}
    assert set(rows["return_value"]) == {0.01, -0.02, 0.03, 0.04, 0.02, 0.06}


def test_main_builds_and_saves_legacy_backtest_metrics(monkeypatch, tmp_path: Path):
    """The command-line entry point routes its arguments into the shared storage layer."""
    importer = importlib.import_module("scripts.import_legacy_tmp_backtest_metrics")
    metric_rows = pd.DataFrame({"metric_name": ["yearly_return"]})
    engine = object()
    captured: dict = {}

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "import_legacy_tmp_backtest_metrics.py",
            "--run-id",
            "10",
            "--backtest-dir",
            str(tmp_path),
        ],
    )
    monkeypatch.setattr(importer, "get_engine", lambda: engine)
    def fake_build_all(**kwargs):
        captured["build_kwargs"] = kwargs
        return metric_rows

    monkeypatch.setattr(importer, "build_all_legacy_backtest_metric_rows", fake_build_all)
    monkeypatch.setattr(
        importer,
        "build_all_legacy_backtest_return_rows",
        lambda **_: pd.DataFrame(),
    )
    monkeypatch.setattr(
        importer,
        "save_backtest_metrics",
        lambda received_engine, received_rows: captured.update(
            engine=received_engine,
            rows=received_rows,
        )
        or len(received_rows),
    )
    monkeypatch.setattr(importer, "save_backtest_results", lambda *_: 0)

    importer.main()

    assert captured["build_kwargs"] == {
        "backtest_dir": tmp_path,
        "run_id": 10,
        "variant_name": "legacy_tmp_raw",
        "backtest_id": "legacy_tmp_after_cost",
        "test_id": "legacy_tmp_bh",
    }
    assert captured["engine"] is engine
    assert captured["rows"] is metric_rows


def test_main_also_saves_legacy_daily_return_rows(monkeypatch, tmp_path: Path):
    """The legacy command imports both summary metrics and daily backtest returns."""
    importer = importlib.import_module("scripts.import_legacy_tmp_backtest_metrics")
    metric_rows = pd.DataFrame({"metric_name": ["yearly_return"]})
    return_rows = pd.DataFrame({"return_value": [0.02]})
    engine = object()
    captured: dict = {}

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "import_legacy_tmp_backtest_metrics.py",
            "--run-id",
            "10",
            "--backtest-dir",
            str(tmp_path),
        ],
    )
    monkeypatch.setattr(importer, "get_engine", lambda: engine)
    monkeypatch.setattr(
        importer,
        "build_all_legacy_backtest_metric_rows",
        lambda **_: metric_rows,
    )
    monkeypatch.setattr(
        importer,
        "build_all_legacy_backtest_return_rows",
        lambda **_: return_rows,
    )
    monkeypatch.setattr(importer, "save_backtest_metrics", lambda *_: 1)
    monkeypatch.setattr(
        importer,
        "save_backtest_results",
        lambda received_engine, received_rows: captured.update(
            engine=received_engine,
            rows=received_rows,
        )
        or len(received_rows),
    )

    importer.main()

    assert captured["engine"] is engine
    assert captured["rows"] is return_rows
