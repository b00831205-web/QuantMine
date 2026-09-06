"""Tests for the scheduler-neutral daily eligibility refresh task."""

from __future__ import annotations

import pandas as pd

from quantmine.workflows.eligibility import (
    EligibilityDataTier,
    EligibilityPublishSpec,
    refresh_daily_eligibility,
)


class RecordingBuilder:
    def __init__(self) -> None:
        self.received_dates: list[pd.Timestamp] = []

    def build(self, as_of_date: pd.Timestamp) -> pd.DataFrame:
        self.received_dates.append(as_of_date)
        return pd.DataFrame(
            {
                "date": [as_of_date, as_of_date],
                "ticker": ["000001", "000002"],
                "is_listed": [True, True],
                "is_tradable": [True, False],
                "listing_days": [100, 100],
                "is_st": [False, True],
            }
        )


def test_refresh_builds_and_publishes_one_normalized_business_date(tmp_path) -> None:
    builder = RecordingBuilder()
    publication = refresh_daily_eligibility(
        builder,
        as_of_date="2024-01-02 14:35:00",
        root=tmp_path,
        spec=EligibilityPublishSpec(
            dataset_id="cn_daily_eligibility",
            version="2024-01-02T180000Z",
            market="CN",
            data_tier=EligibilityDataTier.RECONSTRUCTED,
            source="test_fixture",
            rule_version="test_v1",
        ),
    )

    assert builder.received_dates == [pd.Timestamp("2024-01-02")]
    assert publication.row_count == 2
    assert publication.eligibility_path.is_file()
