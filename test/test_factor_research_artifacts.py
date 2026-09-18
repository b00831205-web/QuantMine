"""Tests for immutable factor-research artifact contracts."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from quantmine.research import FactorResearchResult
from quantmine.workflows.factor_research_artifacts import (
    FactorResearchArtifacts,
    FactorResearchPublication,
    _build_factor_manifest,
    _factor_content_sha256,
    _normalize_factor_frame,
    load_factor_research_artifacts,
    publish_factor_research_artifacts,
)


def _publication(tmp_path: Path, **overrides) -> FactorResearchPublication:
    values = {
        "run_id": 701,
        "output_dir": tmp_path / "701" / "factors",
        "manifest_path": tmp_path / "701" / "factors" / "manifest.json",
        "factor_paths": {
            "momentum": tmp_path / "701" / "factors" / "momentum.parquet",
        },
        "factor_count": 1,
        "pending_count": 0,
    }
    values.update(overrides)
    return FactorResearchPublication(**values)


def test_factor_research_publication_accepts_consistent_summary(
    tmp_path: Path,
) -> None:
    publication = _publication(tmp_path)

    assert publication.run_id == 701
    assert publication.factor_count == 1
    assert tuple(publication.factor_paths) == ("momentum",)


@pytest.mark.parametrize("run_id", (0, -1, True, "701"))
def test_factor_research_publication_requires_positive_integer_run_id(
    tmp_path: Path,
    run_id: object,
) -> None:
    with pytest.raises(ValueError, match="run_id must be a positive integer"):
        _publication(tmp_path, run_id=run_id)


def test_factor_research_publication_requires_matching_factor_count(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="factor_count must match factor_paths"):
        _publication(tmp_path, factor_count=2)


def test_factor_research_publication_rejects_negative_pending_count(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="pending_count must be non-negative"):
        _publication(tmp_path, pending_count=-1)


def test_normalize_factor_frame_returns_deterministic_wide_frame() -> None:
    frame = pd.DataFrame(
        {
            "600000": ["2.0", "1.0"],
            "000001": ["4.0", "3.0"],
        },
        index=pd.DatetimeIndex(
            ["2024-01-03 00:00:00+08:00", "2024-01-02 00:00:00+08:00"]
        ),
    )

    normalized = _normalize_factor_frame("CNMomentum20D", frame)

    assert normalized.index.equals(
        pd.DatetimeIndex(["2024-01-02", "2024-01-03"], name="date")
    )
    assert normalized.columns.tolist() == ["000001", "600000"]
    assert normalized.dtypes.apply(lambda dtype: dtype.kind).tolist() == ["f", "f"]


@pytest.mark.parametrize(
    "signal",
    ("", "../momentum", "factor/name", " factor", "因子"),
)
def test_normalize_factor_frame_requires_safe_signal_name(signal: str) -> None:
    with pytest.raises(ValueError, match="safe non-empty path segment"):
        _normalize_factor_frame(
            signal,
            pd.DataFrame({"AAA": [1.0]}, index=["2024-01-02"]),
        )


def test_normalize_factor_frame_requires_non_empty_dataframe() -> None:
    with pytest.raises(TypeError, match="pandas DataFrame"):
        _normalize_factor_frame("momentum", object())

    with pytest.raises(ValueError, match="must not be empty"):
        _normalize_factor_frame("momentum", pd.DataFrame())


def test_normalize_factor_frame_rejects_invalid_date_axis() -> None:
    duplicate_dates = pd.DataFrame(
        {"AAA": [1.0, 2.0]},
        index=["2024-01-02", "2024-01-02"],
    )
    missing_date = pd.DataFrame(
        {"AAA": [1.0]},
        index=pd.DatetimeIndex([pd.NaT]),
    )

    with pytest.raises(ValueError, match="duplicate dates"):
        _normalize_factor_frame("momentum", duplicate_dates)
    with pytest.raises(ValueError, match="missing dates"):
        _normalize_factor_frame("momentum", missing_date)


def test_normalize_factor_frame_rejects_invalid_ticker_axis() -> None:
    duplicate_tickers = pd.DataFrame(
        [[1.0, 2.0]],
        columns=["AAA", " AAA"],
        index=["2024-01-02"],
    )
    empty_ticker = pd.DataFrame(
        [[1.0]],
        columns=[" "],
        index=["2024-01-02"],
    )

    with pytest.raises(ValueError, match="duplicate tickers"):
        _normalize_factor_frame("momentum", duplicate_tickers)
    with pytest.raises(ValueError, match="empty ticker"):
        _normalize_factor_frame("momentum", empty_ticker)


def test_normalize_factor_frame_rejects_non_numeric_values() -> None:
    with pytest.raises(ValueError, match="non-numeric values"):
        _normalize_factor_frame(
            "momentum",
            pd.DataFrame({"AAA": ["bad"]}, index=["2024-01-02"]),
        )


def test_factor_content_hash_is_stable_across_input_order() -> None:
    frame = pd.DataFrame(
        {
            "AAA": [1.0, 2.0],
            "BBB": [3.0, 4.0],
        },
        index=pd.to_datetime(["2024-01-02", "2024-01-03"]),
    )
    reordered = frame.loc[
        [pd.Timestamp("2024-01-03"), pd.Timestamp("2024-01-02")],
        ["BBB", "AAA"],
    ]

    assert _factor_content_sha256(
        "momentum",
        reordered,
    ) == _factor_content_sha256("momentum", frame)


def test_factor_content_hash_changes_with_content_identity() -> None:
    frame = pd.DataFrame(
        {
            "AAA": [1.0, 2.0],
            "BBB": [3.0, 4.0],
        },
        index=pd.to_datetime(["2024-01-02", "2024-01-03"]),
    )
    changed_value = frame.copy()
    changed_value.loc[pd.Timestamp("2024-01-03"), "BBB"] = 5.0
    changed_date = frame.copy()
    changed_date.index = pd.to_datetime(["2024-01-02", "2024-01-04"])
    changed_ticker = frame.rename(columns={"BBB": "CCC"})

    hashes = {
        _factor_content_sha256("momentum", frame),
        _factor_content_sha256("reversal", frame),
        _factor_content_sha256("momentum", changed_value),
        _factor_content_sha256("momentum", changed_date),
        _factor_content_sha256("momentum", changed_ticker),
    }

    assert len(hashes) == 5


def _research_result(
    *,
    requested_signals: tuple[str, ...] = ("momentum", "reversal"),
    pending: dict[str, str] | None = None,
    factors: dict[str, object] | None = None,
) -> FactorResearchResult:
    frame = pd.DataFrame(
        {"000001": [1.0, 2.0], "600000": [3.0, 4.0]},
        index=pd.to_datetime(["2024-01-02", "2024-01-03"]),
    )
    return FactorResearchResult(
        market_data=None,  # The artifact contract only consumes result metadata.
        requested_signals=requested_signals,
        pending=pending if pending is not None else {"reversal": "not ready"},
        factors=factors if factors is not None else {"momentum": frame},
    )


def test_build_factor_manifest_describes_completed_and_pending_signals() -> None:
    result = _research_result()

    manifest = _build_factor_manifest(result, run_id=702)

    assert manifest["schema_version"] == 1
    assert manifest["run_id"] == 702
    assert manifest["requested_signals"] == ["momentum", "reversal"]
    assert manifest["factor_count"] == 1
    assert manifest["pending"] == {"reversal": "not ready"}
    assert manifest["pending_count"] == 1
    assert manifest["factors"] == {
        "momentum": {
            "path": "momentum.parquet",
            "content_sha256": _factor_content_sha256(
                "momentum", result.factors["momentum"]
            ),
            "date_count": 2,
            "ticker_count": 2,
            "min_date": "2024-01-02",
            "max_date": "2024-01-03",
        }
    }


@pytest.mark.parametrize(
    ("requested_signals", "pending", "factors", "match"),
    (
        (("momentum", "momentum"), {}, {}, "duplicate signals"),
        (("momentum",), {"unknown": "not ready"}, {}, "unknown signals"),
        (("momentum",), {}, {"unknown": pd.DataFrame()}, "unknown signals"),
        (("momentum",), {}, {}, "not accounted for"),
        (("momentum",), {"momentum": "not ready"}, {"momentum": pd.DataFrame()}, "both completed and pending"),
    ),
)
def test_build_factor_manifest_requires_complete_signal_accounting(
    requested_signals: tuple[str, ...],
    pending: dict[str, str],
    factors: dict[str, object],
    match: str,
) -> None:
    with pytest.raises(ValueError, match=match):
        _build_factor_manifest(
            _research_result(
                requested_signals=requested_signals,
                pending=pending,
                factors=factors,
            ),
            run_id=702,
        )


def test_publish_factor_research_artifacts_writes_immutable_run_output(
    tmp_path: Path,
) -> None:
    result = _research_result()

    publication = publish_factor_research_artifacts(
        result,
        run_id=702,
        root=tmp_path / "factor-research",
    )

    assert publication.output_dir == tmp_path / "factor-research" / "702"
    assert publication.factor_count == 1
    assert publication.pending_count == 1
    assert publication.manifest_path.is_file()
    assert publication.factor_paths == {
        "momentum": publication.output_dir / "momentum.parquet",
    }

    manifest = json.loads(publication.manifest_path.read_text(encoding="utf-8"))
    assert manifest == _build_factor_manifest(result, run_id=702)
    pd.testing.assert_frame_equal(
        pd.read_parquet(publication.factor_paths["momentum"]),
        _normalize_factor_frame("momentum", result.factors["momentum"]),
    )


def test_publish_factor_research_artifacts_is_idempotent_for_same_run_content(
    tmp_path: Path,
) -> None:
    result = _research_result()
    root = tmp_path / "factor-research"

    first = publish_factor_research_artifacts(result, run_id=702, root=root)
    second = publish_factor_research_artifacts(result, run_id=702, root=root)

    assert second == first


def test_publish_factor_research_artifacts_rejects_different_existing_run(
    tmp_path: Path,
) -> None:
    root = tmp_path / "factor-research"
    publish_factor_research_artifacts(
        _research_result(),
        run_id=702,
        root=root,
    )
    changed = _research_result(
        factors={
            "momentum": pd.DataFrame(
                {"000001": [9.0]},
                index=pd.to_datetime(["2024-01-02"]),
            )
        },
    )

    with pytest.raises(FileExistsError, match="different content"):
        publish_factor_research_artifacts(changed, run_id=702, root=root)


def test_publish_factor_research_artifacts_cleans_staging_output_on_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "factor-research"
    result = _research_result()

    def fail_to_parquet(self: pd.DataFrame, *args: object, **kwargs: object) -> None:
        raise OSError("simulated parquet write failure")

    monkeypatch.setattr(pd.DataFrame, "to_parquet", fail_to_parquet)

    with pytest.raises(OSError, match="simulated parquet write failure"):
        publish_factor_research_artifacts(result, run_id=702, root=root)

    assert not (root / "702").exists()
    assert not list(root.glob(".702.staging-*"))


def test_load_factor_research_artifacts_verifies_and_returns_frames(
    tmp_path: Path,
) -> None:
    result = _research_result()
    root = tmp_path / "factor-research"
    publication = publish_factor_research_artifacts(
        result,
        run_id=702,
        root=root,
    )

    loaded = load_factor_research_artifacts(root=root, run_id=702)

    assert isinstance(loaded, FactorResearchArtifacts)
    assert loaded.publication == publication
    assert loaded.requested_signals == ("momentum", "reversal")
    assert loaded.pending == {"reversal": "not ready"}
    assert set(loaded.factors) == {"momentum"}
    pd.testing.assert_frame_equal(
        loaded.factors["momentum"],
        _normalize_factor_frame("momentum", result.factors["momentum"]),
    )


def test_load_factor_research_artifacts_rejects_tampered_factor_content(
    tmp_path: Path,
) -> None:
    root = tmp_path / "factor-research"
    publication = publish_factor_research_artifacts(
        _research_result(),
        run_id=702,
        root=root,
    )
    tampered = pd.read_parquet(publication.factor_paths["momentum"])
    tampered.iloc[0, 0] = 999.0
    tampered.to_parquet(publication.factor_paths["momentum"])

    with pytest.raises(ValueError, match="content hash"):
        load_factor_research_artifacts(root=root, run_id=702)


def test_load_factor_research_artifacts_rejects_unsafe_manifest_path(
    tmp_path: Path,
) -> None:
    root = tmp_path / "factor-research"
    publication = publish_factor_research_artifacts(
        _research_result(),
        run_id=702,
        root=root,
    )
    manifest = json.loads(
        publication.manifest_path.read_text(encoding="utf-8")
    )
    manifest["factors"]["momentum"]["path"] = "../momentum.parquet"
    publication.manifest_path.write_text(
        json.dumps(manifest),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="safe|path"):
        load_factor_research_artifacts(root=root, run_id=702)
