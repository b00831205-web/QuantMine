"""Contracts for immutable IC-workflow artifact publication."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pandas.testing as pdt
import pytest

from quantmine.ic_calculator import ICVariant
from quantmine.workflows.ic_research_artifacts import (
    ICResearchArtifacts,
    ICResearchPublication,
    load_ic_research_artifacts,
    publish_ic_research_artifacts,
)


def _workflow_output() -> tuple[dict[str, ICVariant], dict[str, dict]]:
    dates = pd.date_range("2026-01-02", periods=3, freq="B", name="date")
    factor = pd.DataFrame(
        {"000001": [0.1, 0.2, 0.3], "000002": [0.3, 0.1, -0.1]},
        index=dates,
    )
    forward_return = pd.DataFrame(
        {"000001": [0.01, -0.02, 0.03], "000002": [0.02, 0.01, -0.01]},
        index=dates,
    )
    cs_ic = pd.DataFrame(
        {("momentum", 5): [1.0, -1.0, 1.0]},
        index=dates,
    )
    cs_ic.columns = pd.MultiIndex.from_tuples(
        cs_ic.columns,
        names=["factor", "period"],
    )
    variants = {
        "raw": ICVariant(
            train={
                "factors": {"momentum": factor},
                "forward_returns": {5: forward_return},
                "cs_ic": cs_ic,
                "orthogonalized": False,
            },
            test={
                "factors": {"momentum": factor * 2},
                "forward_returns": {5: forward_return * 2},
                "cs_ic": cs_ic * 0.5,
                "orthogonalized": False,
            },
            transforms=[{"name": "raw"}],
        )
    }
    index = pd.MultiIndex.from_tuples(
        [("momentum", 5)],
        names=["factor", "period"],
    )
    test_results = {
        "newey_raw": {
            "variant_name": "raw",
            "test_method": "newey_west",
            "sample_scope": "train",
            "summary": pd.DataFrame(
                {"IC_mean": [0.03], "t_stat": [2.2], "p_value": [0.03]},
                index=index,
            ),
            "multiple_testing": pd.DataFrame(
                {"BH_significant": [True]},
                index=index,
            ),
        }
    }
    return variants, test_results


def test_ic_research_publication_validates_summary_counts(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="variant_count"):
        ICResearchPublication(
            run_id=903,
            output_dir=tmp_path / "903",
            manifest_path=tmp_path / "903" / "manifest.json",
            variant_count=1,
            test_count=0,
            variant_names=(),
            test_ids=(),
        )


def test_publish_ic_research_artifacts_writes_complete_immutable_output(
    tmp_path: Path,
) -> None:
    variants, test_results = _workflow_output()

    publication = publish_ic_research_artifacts(
        variants,
        test_results,
        run_id=903,
        root=tmp_path / "ic-research",
    )

    assert publication.run_id == 903
    assert publication.variant_names == ("raw",)
    assert publication.test_ids == ("newey_raw",)
    assert publication.variant_count == 1
    assert publication.test_count == 1
    assert publication.output_dir == tmp_path / "ic-research" / "903"

    expected_paths = {
        "manifest.json",
        "variants/raw/train/factors/momentum.parquet",
        "variants/raw/train/forward_returns/5.parquet",
        "variants/raw/train/cs_ic.parquet",
        "variants/raw/test/factors/momentum.parquet",
        "variants/raw/test/forward_returns/5.parquet",
        "variants/raw/test/cs_ic.parquet",
        "tests/newey_raw/train/summary.parquet",
        "tests/newey_raw/train/multiple_testing.parquet",
    }
    actual_paths = {
        path.relative_to(publication.output_dir).as_posix()
        for path in publication.output_dir.rglob("*")
        if path.is_file()
    }
    assert actual_paths == expected_paths

    manifest = json.loads(publication.manifest_path.read_text(encoding="utf-8"))
    assert manifest["schema_version"] == 1
    assert manifest["run_id"] == 903
    assert manifest["variant_count"] == 1
    assert manifest["test_count"] == 1
    assert manifest["variants"]["raw"]["transforms"] == [{"name": "raw"}]
    assert manifest["tests"]["newey_raw"]["variant_name"] == "raw"
    assert manifest["tests"]["newey_raw"]["test_method"] == "newey_west"


def test_publish_ic_research_artifacts_is_idempotent_for_same_content(
    tmp_path: Path,
) -> None:
    variants, test_results = _workflow_output()
    root = tmp_path / "ic-research"

    first = publish_ic_research_artifacts(
        variants,
        test_results,
        run_id=903,
        root=root,
    )
    second = publish_ic_research_artifacts(
        variants,
        test_results,
        run_id=903,
        root=root,
    )

    assert second == first


def test_publish_ic_research_artifacts_rejects_changed_existing_run(
    tmp_path: Path,
) -> None:
    variants, test_results = _workflow_output()
    root = tmp_path / "ic-research"
    publish_ic_research_artifacts(
        variants,
        test_results,
        run_id=903,
        root=root,
    )
    variants["raw"].train["cs_ic"].iloc[0, 0] = 0.25

    with pytest.raises(FileExistsError, match="different content"):
        publish_ic_research_artifacts(
            variants,
            test_results,
            run_id=903,
            root=root,
        )


def test_load_ic_research_artifacts_verifies_and_restores_workflow(
    tmp_path: Path,
) -> None:
    variants, test_results = _workflow_output()
    root = tmp_path / "ic-research"
    publication = publish_ic_research_artifacts(
        variants,
        test_results,
        run_id=903,
        root=root,
    )

    loaded = load_ic_research_artifacts(root=root, run_id=903)

    assert isinstance(loaded, ICResearchArtifacts)
    assert loaded.publication == publication
    assert set(loaded.variants) == {"raw"}
    assert loaded.variants["raw"].transforms == [{"name": "raw"}]
    assert loaded.variants["raw"].train["orthogonalized"] is False
    assert set(loaded.variants["raw"].train["forward_returns"]) == {5}
    pdt.assert_frame_equal(
        loaded.variants["raw"].train["factors"]["momentum"],
        variants["raw"].train["factors"]["momentum"],
        check_freq=False,
    )
    pdt.assert_frame_equal(
        loaded.variants["raw"].test["cs_ic"],
        variants["raw"].test["cs_ic"],
        check_freq=False,
    )

    assert set(loaded.test_results) == {"newey_raw"}
    restored_test = loaded.test_results["newey_raw"]
    assert restored_test["variant_name"] == "raw"
    assert restored_test["test_method"] == "newey_west"
    assert restored_test["sample_scope"] == "train"
    pdt.assert_frame_equal(
        restored_test["summary"],
        test_results["newey_raw"]["summary"],
    )
    pdt.assert_frame_equal(
        restored_test["multiple_testing"],
        test_results["newey_raw"]["multiple_testing"],
    )


def test_load_ic_research_artifacts_rejects_tampered_content(
    tmp_path: Path,
) -> None:
    variants, test_results = _workflow_output()
    root = tmp_path / "ic-research"
    publication = publish_ic_research_artifacts(
        variants,
        test_results,
        run_id=903,
        root=root,
    )
    path = publication.output_dir / "variants/raw/train/cs_ic.parquet"
    tampered = pd.read_parquet(path)
    tampered.iloc[0, 0] = 0.12345
    tampered.to_parquet(path)

    with pytest.raises(ValueError, match="content hash"):
        load_ic_research_artifacts(root=root, run_id=903)


def test_load_ic_research_artifacts_rejects_unsafe_manifest_path(
    tmp_path: Path,
) -> None:
    variants, test_results = _workflow_output()
    root = tmp_path / "ic-research"
    publication = publish_ic_research_artifacts(
        variants,
        test_results,
        run_id=903,
        root=root,
    )
    manifest = json.loads(
        publication.manifest_path.read_text(encoding="utf-8")
    )
    manifest["tests"]["newey_raw"]["artifacts"]["summary"]["path"] = (
        "../summary.parquet"
    )
    publication.manifest_path.write_text(
        json.dumps(manifest),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="safe|path"):
        load_ic_research_artifacts(root=root, run_id=903)
