"""Resolve persistent dataset-version selectors into immutable versions"""

from __future__ import annotations

from dataclasses import replace

import pandas as pd

from .plugins.contracts import VersionedDatasetBinding


AS_OF_DATE_VERSION = "{as_of_date}"


def resolve_versioned_dataset_binding(
        binding: VersionedDatasetBinding,
        *,
        as_of_date: pd.Timestamp | str,
) -> VersionedDatasetBinding:
    """Resolve a configured version selector for one deterministic run date."""

    if not isinstance(binding, VersionedDatasetBinding):
        raise TypeError(
            "binding must be a VersionedDatasetBinding"
        )

    if binding.version != AS_OF_DATE_VERSION:
        return binding

    date = pd.Timestamp(as_of_date)
    if pd.isna(date):
        raise ValueError("as_of_date must not be NaT")

    return replace(
        binding,
        version = date.strftime("%Y%m%d")
    )