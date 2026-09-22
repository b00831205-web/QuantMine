"""Tests for immutable position-backtest artifact publication."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

from quantmine.plugins.context import SourceContext
from quantmine.plugins.market_rules import create_unrestricted_market_rules
from quantmine.storage.connections import ConnectionRegistry
from quantmine.workflows import position_backtest_artifacts as artifacts_module
from quantmine.workflows.position_backtest import run_position_backtest
from quantmine.workflows.position_backtest_artifacts import (
    load_position_backtest_artifact,
    publish_position_backtest_artifact,
    publish_position_backtest_run_manifest,
)


def _result(tmp_path: Path, *, weight: float = 0.5):
    close = pd.DataFrame(
        {
            "AAA": [10.0, 11.0],
            "BBB": [20.0, 20.0],
        },
        index=pd.DatetimeIndex(["2026-09-17", "2026-09-18"]),
    )
    targets = pd.DataFrame(
        {"AAA": [weight], "BBB": [0.0]},
        index=close.index[:1],
    )
    return run_position_backtest(
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


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_position_backtest_artifact_publishes_all_audit_tables(
    tmp_path: Path,
) -> None:
    publication = publish_position_backtest_artifact(
        _result(tmp_path),
        run_id=701,
        job_id="top_quantile",
        factor_name="momentum",
        period=5,
        root=tmp_path / "published",
    )

    assert publication.run_id == 701
    assert publication.job_id == "top_quantile"
    assert publication.factor_name == "momentum"
    assert publication.period == 5
    assert publication.date_count == 2
    assert publication.ticker_count == 2
    assert publication.output_dir == (
        tmp_path / "published" / "701" / "top_quantile" / "momentum-5"
    )
    assert publication.manifest_path.is_file()

    manifest = json.loads(
        publication.manifest_path.read_text(encoding="utf-8")
    )
    assert manifest["schema_version"] == 1
    assert set(manifest["files"]) == {
        "equity_curve.parquet",
        "daily_returns.parquet",
        "cash_curve.parquet",
        "positions.parquet",
        "sellable_positions.parquet",
        "requested_shares.parquet",
        "executed_shares.parquet",
        "fees.parquet",
        "reasons.parquet",
        "valuation_prices.parquet",
        "tradable.parquet",
        "price_sources.parquet",
    }

    for relative_path, digest in manifest["files"].items():
        path = publication.output_dir / relative_path
        assert path.is_file()
        assert digest == _sha256(path)

    assert manifest["final_state"] == {
        "cash": 500.0,
        "positions": {"AAA": 50.0, "BBB": 0.0},
        "sellable_positions": {"AAA": 50.0, "BBB": 0.0},
    }


def test_position_backtest_artifact_is_idempotent_for_same_content(
    tmp_path: Path,
) -> None:
    root = tmp_path / "published"
    first = publish_position_backtest_artifact(
        _result(tmp_path),
        run_id=701,
        job_id="top_quantile",
        factor_name="momentum",
        period=5,
        root=root,
    )
    second = publish_position_backtest_artifact(
        _result(tmp_path),
        run_id=701,
        job_id="top_quantile",
        factor_name="momentum",
        period=5,
        root=root,
    )

    assert second == first


def test_position_backtest_artifact_loads_verified_result(
    tmp_path: Path,
) -> None:
    root = tmp_path / "published"
    expected = _result(tmp_path)
    publication = publish_position_backtest_artifact(
        expected,
        run_id=701,
        job_id="top_quantile",
        factor_name="momentum",
        period=5,
        root=root,
    )

    loaded = load_position_backtest_artifact(
        root=root,
        run_id=701,
        job_id="top_quantile",
        factor_name="momentum",
        period=5,
    )

    assert loaded.publication == publication
    pd.testing.assert_series_equal(
        loaded.result.equity_curve,
        expected.equity_curve,
        check_freq=False,
    )
    pd.testing.assert_series_equal(
        loaded.result.daily_returns,
        expected.daily_returns,
        check_freq=False,
    )
    pd.testing.assert_series_equal(
        loaded.result.cash_curve,
        expected.cash_curve,
        check_freq=False,
    )

    for name in (
        "positions",
        "sellable_positions",
        "requested_shares",
        "executed_shares",
        "fees",
        "reasons",
        "valuation_prices",
        "tradable",
        "price_sources",
    ):
        pd.testing.assert_frame_equal(
            getattr(loaded.result, name),
            getattr(expected, name),
            check_freq=False,
            check_dtype=name not in {"reasons", "price_sources"},
        )

    pd.testing.assert_series_equal(
        loaded.result.final_state.positions,
        expected.final_state.positions,
    )
    pd.testing.assert_series_equal(
        loaded.result.final_state.sellable_positions,
        expected.final_state.sellable_positions,
    )
    assert loaded.result.final_state.cash == expected.final_state.cash


def test_position_backtest_artifact_rejects_tampered_file(
    tmp_path: Path,
) -> None:
    root = tmp_path / "published"
    publication = publish_position_backtest_artifact(
        _result(tmp_path),
        run_id=701,
        job_id="top_quantile",
        factor_name="momentum",
        period=5,
        root=root,
    )
    path = publication.output_dir / "positions.parquet"
    path.write_bytes(path.read_bytes() + b"tampered")

    with pytest.raises(ValueError, match="checksum mismatch"):
        load_position_backtest_artifact(
            root=root,
            run_id=701,
            job_id="top_quantile",
            factor_name="momentum",
            period=5,
        )


def test_position_backtest_artifact_rejects_identity_mismatch(
    tmp_path: Path,
) -> None:
    root = tmp_path / "published"
    publication = publish_position_backtest_artifact(
        _result(tmp_path),
        run_id=701,
        job_id="top_quantile",
        factor_name="momentum",
        period=5,
        root=root,
    )
    manifest = json.loads(publication.manifest_path.read_text(encoding="utf-8"))
    manifest["factor_name"] = "different_factor"
    publication.manifest_path.write_text(
        json.dumps(manifest),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="identity"):
        load_position_backtest_artifact(
            root=root,
            run_id=701,
            job_id="top_quantile",
            factor_name="momentum",
            period=5,
        )


def test_position_backtest_artifact_rejects_final_state_conflict(
    tmp_path: Path,
) -> None:
    root = tmp_path / "published"
    publication = publish_position_backtest_artifact(
        _result(tmp_path),
        run_id=701,
        job_id="top_quantile",
        factor_name="momentum",
        period=5,
        root=root,
    )
    manifest = json.loads(publication.manifest_path.read_text(encoding="utf-8"))
    manifest["final_state"]["cash"] = 999.0
    publication.manifest_path.write_text(
        json.dumps(manifest),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="cash disagrees"):
        load_position_backtest_artifact(
            root=root,
            run_id=701,
            job_id="top_quantile",
            factor_name="momentum",
            period=5,
        )


def test_position_backtest_run_manifest_aggregates_sorted_artifacts(
    tmp_path: Path,
) -> None:
    root = tmp_path / "published"
    publish_position_backtest_artifact(
        _result(tmp_path),
        run_id=701,
        job_id="z_score",
        factor_name="value",
        period=20,
        root=root,
    )
    publish_position_backtest_artifact(
        _result(tmp_path),
        run_id=701,
        job_id="top_quantile",
        factor_name="momentum",
        period=5,
        root=root,
    )

    publication = publish_position_backtest_run_manifest(
        root=root,
        run_id=701,
    )

    assert publication.run_id == 701
    assert publication.output_dir == root / "701"
    assert publication.manifest_path == root / "701" / "run_manifest.json"
    assert publication.artifact_count == 2

    manifest = json.loads(publication.manifest_path.read_text(encoding="utf-8"))
    assert manifest["schema_version"] == 1
    assert manifest["artifact_type"] == "position_backtest_run"
    assert manifest["run_id"] == 701
    assert manifest["artifact_count"] == 2
    assert manifest["artifacts"] == [
        {
            "job_id": "top_quantile",
            "factor_name": "momentum",
            "period": 5,
            "artifact_dir": "top_quantile/momentum-5",
            "manifest_sha256": _sha256(
                root / "701" / "top_quantile" / "momentum-5" / "manifest.json"
            ),
            "date_count": 2,
            "ticker_count": 2,
        },
        {
            "job_id": "z_score",
            "factor_name": "value",
            "period": 20,
            "artifact_dir": "z_score/value-20",
            "manifest_sha256": _sha256(
                root / "701" / "z_score" / "value-20" / "manifest.json"
            ),
            "date_count": 2,
            "ticker_count": 2,
        },
    ]


def test_position_backtest_run_manifest_is_rebuildable(
    tmp_path: Path,
) -> None:
    root = tmp_path / "published"
    publish_position_backtest_artifact(
        _result(tmp_path),
        run_id=701,
        job_id="top_quantile",
        factor_name="momentum",
        period=5,
        root=root,
    )

    first = publish_position_backtest_run_manifest(root=root, run_id=701)
    first_content = first.manifest_path.read_bytes()
    second = publish_position_backtest_run_manifest(root=root, run_id=701)

    assert second == first
    assert second.manifest_path.read_bytes() == first_content


def test_position_backtest_run_manifest_rejects_tampered_child_artifact(
    tmp_path: Path,
) -> None:
    root = tmp_path / "published"
    publication = publish_position_backtest_artifact(
        _result(tmp_path),
        run_id=701,
        job_id="top_quantile",
        factor_name="momentum",
        period=5,
        root=root,
    )
    path = publication.output_dir / "fees.parquet"
    path.write_bytes(path.read_bytes() + b"tampered")

    with pytest.raises(ValueError, match="checksum mismatch"):
        publish_position_backtest_run_manifest(root=root, run_id=701)


def test_position_backtest_artifact_refuses_content_conflict(
    tmp_path: Path,
) -> None:
    root = tmp_path / "published"
    publish_position_backtest_artifact(
        _result(tmp_path, weight=0.5),
        run_id=701,
        job_id="top_quantile",
        factor_name="momentum",
        period=5,
        root=root,
    )

    with pytest.raises(FileExistsError, match="different content"):
        publish_position_backtest_artifact(
            _result(tmp_path, weight=0.25),
            run_id=701,
            job_id="top_quantile",
            factor_name="momentum",
            period=5,
            root=root,
        )


def test_position_backtest_artifact_cleans_staging_after_write_failure(
    monkeypatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "published"

    monkeypatch.setattr(
        artifacts_module,
        "_write_frame",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            RuntimeError("disk failed")
        ),
    )

    with pytest.raises(RuntimeError, match="disk failed"):
        publish_position_backtest_artifact(
            _result(tmp_path),
            run_id=701,
            job_id="top_quantile",
            factor_name="momentum",
            period=5,
            root=root,
        )

    assert not list(root.glob(".*.staging-*"))
    assert not (root / "701").exists()


@pytest.mark.parametrize(
    ("job_id", "factor_name", "period"),
    [
        ("bad/name", "momentum", 5),
        ("top_quantile", "bad/name", 5),
        ("top_quantile", "momentum", 0),
    ],
)
def test_position_backtest_artifact_rejects_unsafe_identity(
    tmp_path: Path,
    job_id: str,
    factor_name: str,
    period: int,
) -> None:
    with pytest.raises(ValueError):
        publish_position_backtest_artifact(
            _result(tmp_path),
            run_id=701,
            job_id=job_id,
            factor_name=factor_name,
            period=period,
            root=tmp_path / "published",
        )
