"""Tests for publishing immutable, versioned daily eligibility datasets."""

from __future__ import annotations

from dataclasses import replace
import json

import pandas as pd
import pytest

from quantmine.workflows.eligibility import (
    EligibilityDataTier,
    EligibilityPublishSpec,
    load_latest_eligibility_before,
    publish_daily_eligibility,
    refresh_cumulative_daily_eligibility,
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


def _frame_for_date(date: str) -> pd.DataFrame:
    frame = _eligibility_frame()
    frame["date"] = date
    return frame


def test_load_latest_eligibility_before_selects_latest_compatible_version(
    tmp_path,
) -> None:
    spec = _spec()
    first_spec = replace(spec, version="20240102")
    second_spec = replace(spec, version="20240103")
    publish_daily_eligibility(
        _frame_for_date("2024-01-02"),
        root=tmp_path,
        spec=first_spec,
    )
    publish_daily_eligibility(
        _frame_for_date("2024-01-03"),
        root=tmp_path,
        spec=second_spec,
    )

    version, frame = load_latest_eligibility_before(
        tmp_path,
        spec=replace(spec, version="20240104"),
        as_of_date="2024-01-04",
    )

    assert version == "20240103"
    assert pd.to_datetime(frame["date"]).dt.normalize().unique().tolist() == [
        pd.Timestamp("2024-01-03")
    ]


def test_load_latest_eligibility_before_excludes_same_day_version(
    tmp_path,
) -> None:
    spec = _spec()
    publish_daily_eligibility(
        _frame_for_date("2024-01-02"),
        root=tmp_path,
        spec=replace(spec, version="20240102"),
    )
    publish_daily_eligibility(
        _frame_for_date("2024-01-03"),
        root=tmp_path,
        spec=replace(spec, version="20240103"),
    )

    result = load_latest_eligibility_before(
        tmp_path,
        spec=replace(spec, version="new-run"),
        as_of_date="2024-01-03",
    )

    assert result is not None
    assert result[0] == "20240102"


def test_load_latest_eligibility_before_ignores_incompatible_provenance(
    tmp_path,
) -> None:
    expected_spec = replace(_spec(), version="compatible")
    incompatible_spec = replace(
        _spec(),
        version="incompatible",
        rule_version="other_rules",
    )
    publish_daily_eligibility(
        _frame_for_date("2024-01-02"),
        root=tmp_path,
        spec=expected_spec,
    )
    publish_daily_eligibility(
        _frame_for_date("2024-01-03"),
        root=tmp_path,
        spec=incompatible_spec,
    )

    result = load_latest_eligibility_before(
        tmp_path,
        spec=replace(expected_spec, version="20240104"),
        as_of_date="2024-01-04",
    )

    assert result is not None
    assert result[0] == "compatible"


def test_load_latest_eligibility_before_returns_none_without_history(
    tmp_path,
) -> None:
    assert load_latest_eligibility_before(
        tmp_path,
        spec=_spec(),
        as_of_date="2024-01-04",
    ) is None


def test_load_latest_eligibility_before_rejects_incomplete_version(
    tmp_path,
) -> None:
    incomplete = (
        tmp_path
        / _spec().dataset_id
        / "versions"
        / "incomplete"
    )
    incomplete.mkdir(parents=True)

    with pytest.raises(ValueError, match="directory is incomplete"):
        load_latest_eligibility_before(
            tmp_path,
            spec=_spec(),
            as_of_date="2024-01-04",
        )


class _DailyBuilder:
    def __init__(self, *, returned_date: str | None = None) -> None:
        self.returned_date = returned_date
        self.requested_dates: list[pd.Timestamp] = []

    def build(self, as_of_date: pd.Timestamp) -> pd.DataFrame:
        self.requested_dates.append(as_of_date)
        date = self.returned_date or as_of_date.date().isoformat()
        return _frame_for_date(date)


def test_refresh_cumulative_daily_eligibility_appends_prior_version(
    tmp_path,
) -> None:
    first_builder = _DailyBuilder()
    first = refresh_cumulative_daily_eligibility(
        first_builder,
        as_of_date="2024-01-02",
        root=tmp_path,
        spec=replace(_spec(), version="20240102"),
    )

    second_builder = _DailyBuilder()
    second = refresh_cumulative_daily_eligibility(
        second_builder,
        as_of_date="2024-01-03",
        root=tmp_path,
        spec=replace(_spec(), version="20240103"),
    )

    assert first_builder.requested_dates == [pd.Timestamp("2024-01-02")]
    assert second_builder.requested_dates == [pd.Timestamp("2024-01-03")]
    assert first.row_count == 2
    assert second.row_count == 4
    assert second.min_date == pd.Timestamp("2024-01-02")
    assert second.max_date == pd.Timestamp("2024-01-03")

    saved = pd.read_parquet(second.eligibility_path)
    assert saved.groupby("date").size().to_dict() == {
        pd.Timestamp("2024-01-02"): 2,
        pd.Timestamp("2024-01-03"): 2,
    }


def test_refresh_cumulative_daily_eligibility_can_roll_from_legacy_version(
    tmp_path,
) -> None:
    legacy_spec = replace(_spec(), version="history_v1")
    legacy = publish_daily_eligibility(
        _frame_for_date("2024-01-02"),
        root=tmp_path,
        spec=legacy_spec,
    )

    rolled = refresh_cumulative_daily_eligibility(
        _DailyBuilder(),
        as_of_date="2024-01-03",
        root=tmp_path,
        spec=replace(_spec(), version="20240103"),
    )

    assert rolled.output_dir.name == "20240103"
    assert rolled.row_count == 4
    assert rolled.min_date == pd.Timestamp("2024-01-02")
    assert rolled.max_date == pd.Timestamp("2024-01-03")
    assert legacy.output_dir.is_dir()
    assert pd.read_parquet(legacy.eligibility_path).shape[0] == 2


def test_refresh_cumulative_daily_eligibility_is_idempotent(
    tmp_path,
) -> None:
    spec = replace(_spec(), version="20240102")
    first = refresh_cumulative_daily_eligibility(
        _DailyBuilder(),
        as_of_date="2024-01-02",
        root=tmp_path,
        spec=spec,
    )
    second = refresh_cumulative_daily_eligibility(
        _DailyBuilder(),
        as_of_date="2024-01-02",
        root=tmp_path,
        spec=spec,
    )

    assert second == first
    assert pd.read_parquet(second.eligibility_path).shape[0] == 2


def test_refresh_cumulative_daily_eligibility_rejects_wrong_snapshot_date(
    tmp_path,
) -> None:
    with pytest.raises(
        ValueError,
        match="must return exactly the requested as_of_date",
    ):
        refresh_cumulative_daily_eligibility(
            _DailyBuilder(returned_date="2024-01-01"),
            as_of_date="2024-01-02",
            root=tmp_path,
            spec=replace(_spec(), version="20240102"),
        )
