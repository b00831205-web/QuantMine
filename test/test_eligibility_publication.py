"""Tests for publishing immutable, versioned daily eligibility datasets."""

from __future__ import annotations

import json

import pandas as pd
import pytest

from quantmine.workflows.eligibility import (
    EligibilityDataTier,
    EligibilityPublishSpec,
    publish_daily_eligibility,
)


def _eligibility_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": ["2024-01-02", "2024-01-02"],
            "ticker": ["000001", "000002"],
            "is_listed": [True, True],
            "is_tradable": [True, False],
            "listing_days": [100, 100],
            "is_st": [False, True],
        }
    )


def _spec() -> EligibilityPublishSpec:
    return EligibilityPublishSpec(
        dataset_id="cn_daily_eligibility",
        version="2024-01-02T180000Z",
        market="CN",
        data_tier=EligibilityDataTier.RECONSTRUCTED,
        source="akshare_reconstruction",
        rule_version="cn_eligibility_rules_v1",
    )


def test_publish_writes_an_immutable_version_with_manifest(tmp_path) -> None:
    publication = publish_daily_eligibility(
        _eligibility_frame(),
        root=tmp_path,
        spec=_spec(),
    )

    expected_directory = (
        tmp_path
        / "cn_daily_eligibility"
        / "versions"
        / "2024-01-02T180000Z"
    )
    assert publication.output_dir == expected_directory
    assert publication.eligibility_path == expected_directory / "eligibility.parquet"
    assert publication.manifest_path == expected_directory / "manifest.json"
    assert publication.row_count == 2
    assert publication.min_date == pd.Timestamp("2024-01-02")
    assert publication.max_date == pd.Timestamp("2024-01-02")

    saved = pd.read_parquet(publication.eligibility_path)
    assert saved["ticker"].tolist() == ["000001", "000002"]
    assert saved["is_st"].tolist() == [False, True]

    manifest = json.loads(publication.manifest_path.read_text(encoding="utf-8"))
    assert manifest == {
        "content_sha256": publication.content_sha256,
        "data_tier": "reconstructed",
        "dataset_id": "cn_daily_eligibility",
        "market": "CN",
        "max_date": "2024-01-02",
        "min_date": "2024-01-02",
        "row_count": 2,
        "rule_version": "cn_eligibility_rules_v1",
        "schema_version": "daily_eligibility_v1",
        "source": "akshare_reconstruction",
        "source_observed_at": None,
        "version": "2024-01-02T180000Z",
    }


def test_publish_is_idempotent_for_identical_version_content(tmp_path) -> None:
    first = publish_daily_eligibility(_eligibility_frame(), root=tmp_path, spec=_spec())
    second = publish_daily_eligibility(_eligibility_frame(), root=tmp_path, spec=_spec())

    assert second == first


def test_publish_rejects_reusing_a_version_for_different_content(tmp_path) -> None:
    publish_daily_eligibility(_eligibility_frame(), root=tmp_path, spec=_spec())

    changed = _eligibility_frame()
    changed.loc[1, "is_tradable"] = True

    with pytest.raises(FileExistsError, match="already exists with different content"):
        publish_daily_eligibility(changed, root=tmp_path, spec=_spec())


def test_publish_rejects_reusing_a_version_with_different_provenance(tmp_path) -> None:
    publish_daily_eligibility(_eligibility_frame(), root=tmp_path, spec=_spec())

    observed_spec = EligibilityPublishSpec(
        dataset_id="cn_daily_eligibility",
        version="2024-01-02T180000Z",
        market="CN",
        data_tier=EligibilityDataTier.OBSERVED,
        source="akshare_daily_snapshot",
        source_observed_at="2024-01-02T16:00:00+08:00",
    )

    with pytest.raises(FileExistsError, match="already exists with different provenance"):
        publish_daily_eligibility(
            _eligibility_frame(),
            root=tmp_path,
            spec=observed_spec,
        )


def test_observed_tier_requires_an_observation_timestamp() -> None:
    with pytest.raises(ValueError, match="source_observed_at"):
        EligibilityPublishSpec(
            dataset_id="cn_daily_eligibility",
            version="2024-01-03T180000Z",
            market="CN",
            data_tier=EligibilityDataTier.OBSERVED,
            source="akshare_daily_snapshot",
        )
