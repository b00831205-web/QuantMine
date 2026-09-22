"""Tests for resolving configured dataset-version selectors."""

from __future__ import annotations

import pandas as pd
import pytest

from quantmine.dataset_versions import (
    AS_OF_DATE_VERSION,
    resolve_versioned_dataset_binding,
)
from quantmine.plugins.contracts import VersionedDatasetBinding


def _binding(version: str) -> VersionedDatasetBinding:
    return VersionedDatasetBinding(
        connection_ref="cn_reference",
        dataset="cn_a_share_reference",
        market="CN",
        version=version,
    )


def test_resolves_as_of_date_selector_to_an_immutable_daily_version() -> None:
    resolved = resolve_versioned_dataset_binding(
        _binding(AS_OF_DATE_VERSION),
        as_of_date=pd.Timestamp("2026-09-09 18:00:00"),
    )

    assert resolved == _binding("20260909")


def test_preserves_an_explicit_immutable_version() -> None:
    binding = _binding("20260906")

    resolved = resolve_versioned_dataset_binding(
        binding,
        as_of_date="2026-09-09",
    )

    assert resolved is binding


def test_as_of_date_selector_rejects_a_missing_run_date() -> None:
    with pytest.raises(ValueError, match="as_of_date"):
        resolve_versioned_dataset_binding(
            _binding(AS_OF_DATE_VERSION),
            as_of_date=None,
        )
