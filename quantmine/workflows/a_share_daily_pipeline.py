"""Configuration contract for the A-share daily production pipeline"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Mapping

from ..plugins.contracts import VersionedDatasetBinding
import json
from pathlib import Path

import pandas as pd
from .a_share_eligibility_refresh import (
    refresh_a_share_eligibility_from_market_status,
)

from .a_share_reference import ParquetAStockReferenceLoader
from .a_share_status import AStockDailyStatusNormalizer, SpotCoveragePolicy
from .a_share_status_refresh import refresh_a_share_market_status
from .akshare_a_share_snapshot import (
    AStockRawSnapshot,
    AkShareAStockRawSnapshotCollector,
)

from .eligibility import (
    EligibilityDataTier,
    EligibilityPublication,
    EligibilityPublishSpec,
)

from .market_status_publication import (
    MarketStatusPublication,
    MarketStatusPublishSpec
)

from ..plugins.context import SourceContext

from .trading_sessions import StaticCalendarSessionGate
from .akshare_a_share_snapshot import (
    A_SHARE_RAW_SNAPSHOT_SCHEMA_VERSION,
    AStockRawSnapshot,
    AkShareAStockRawSnapshotCollector
)

from ..dataset_versions import resolve_versioned_dataset_binding

A_SHARE_DAILY_PIPELINE_CONFIG_VERSION = 1

@dataclass(frozen = True)
class AStockDailyPipelineConfig:
    """Non-secret reference required to produce daily A-share dataset"""

    raw_connection_ref: str
    reference_binding: VersionedDatasetBinding
    status_binding: VersionedDatasetBinding
    eligibility_binding: VersionedDatasetBinding
    eligibility_rule_version: str
    spot_coverage_policy: SpotCoveragePolicy = field(
        default_factory= SpotCoveragePolicy
    )

    def __post_init__(self) -> None:
        if (
            not self.raw_connection_ref
            or self.raw_connection_ref.strip() != self.raw_connection_ref
        ):
            raise ValueError(
                "raw_connection_ref must be a non-empty trimmed string"
            )

        for label, binding in (
            ("reference_binding", self.reference_binding),
            ("status_binding", self.status_binding),
            ("eligibility_binding", self.eligibility_binding),
        ):
            if binding.market != "CN":
                raise ValueError(f"{label}.market must be 'CN'")

        if (
            not self.eligibility_rule_version
            or self.eligibility_rule_version.strip() != self.eligibility_rule_version
        ):
            raise ValueError(
                "eligibility_rule_version must be a non-emtpy trimmed string"
            )

    @classmethod
    def from_mapping(
        cls,
        value: Mapping[str, Any],
    ) -> "AStockDailyPipelineConfig":
        payload = _mapping(value, label = "A-share daily pipeline config")

        if payload.get("schema_version") != A_SHARE_DAILY_PIPELINE_CONFIG_VERSION:
            raise ValueError(
                "Unsupported A-share daily pipeline config schema version "
                f"{payload.get('schema_version')!r}; expected "
                f"{A_SHARE_DAILY_PIPELINE_CONFIG_VERSION}"
            )

        return cls(
            raw_connection_ref = _string(
                payload.get("raw_connection_ref"),
                label = "raw_connection_ref"
            ),
            reference_binding = _binding(
                payload.get("reference_binding"),
                label = "reference_binding",
            ),
            status_binding = _binding(
                payload.get("status_binding"),
                label = "status_binding",
            ),
            eligibility_binding = _binding(
                payload.get("eligibility_binding"),
                label = "eligibility_binding"
            ),
            eligibility_rule_version = _string(
                payload.get("eligibility_rule_version"),
                label = "eligibility_rule_version",
            ),
            spot_coverage_policy = _spot_coverage_policy(
                payload.get("spot_coverage")
            )
        )
    def to_mapping(self) -> dict[str, object]:
        return {
            "schema_version": A_SHARE_DAILY_PIPELINE_CONFIG_VERSION,
            "raw_connection_ref": self.raw_connection_ref,
            "reference_binding": _binding_mapping(self.reference_binding),
            "status_binding": _binding_mapping(self.status_binding),
            "eligibility_binding": _binding_mapping(self.eligibility_binding),
            "eligibility_rule_version": self.eligibility_rule_version,
            "spot_coverage": {
                "max_missing_count": (
                    self.spot_coverage_policy.max_missing_count
                ),
                "max_missing_ratio": (
                    self.spot_coverage_policy.max_missing_ratio
                )
            }
        }

def _binding_mapping(
        binding: VersionedDatasetBinding,
) -> dict[str, str]:
    return {
        "connection_ref": binding.connection_ref,
        "dataset": binding.dataset,
        "market": binding.market,
        "version": binding.version
    }

def _binding(
        value: object,
        *,
        label: str
) -> VersionedDatasetBinding:
    payload = _mapping(value, label = label)
    return VersionedDatasetBinding(
        connection_ref = _string(
            payload.get("connection_ref"),
            label = f"{label}.connection_ref"
        ),
        dataset = _string(
            payload.get("dataset"),
            label = f"{label}.dataset"
        ),
        market = _string(
            payload.get("market"),
            label = f"{label}.market"
        ),
        version = _string(
            payload.get("version"),
            label = f"{label}.version",
        ),
    )

def _mapping(value: object, *, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{label} must be a JSON object")

    return dict(value)

def _string(value: object, *, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise TypeError(f"{label} must be a non-empty string")
    return value

@dataclass(frozen = True)
class AStockDailyPipelineResult:
    raw_snapshot: AStockRawSnapshot
    status_publication: MarketStatusPublication
    eligibility_publication: EligibilityPublication

def run_a_share_daily_pipeline(
        context: SourceContext,
        *,
        config: AStockDailyPipelineConfig,
        as_of_date: pd.Timestamp | str,
        collector: AkShareAStockRawSnapshotCollector | None = None
) -> AStockDailyPipelineResult:
    """Run one idempotent, scheduler-neutral A-share production day."""

    date = pd.Timestamp(as_of_date).normalize()
    reference_binding = resolve_versioned_dataset_binding(
        config.reference_binding,
        as_of_date = date,
    )

    eligibility_binding = resolve_versioned_dataset_binding(
        config.eligibility_binding,
        as_of_date = date
    )

    raw_root = context.connections.parquet_root(
        config.raw_connection_ref
    )
    snapshot = _load_existing_raw_snapshot(raw_root, date)

    if snapshot is None:
        snapshot = (
            collector or AkShareAStockRawSnapshotCollector()
        ).collect(
            as_of_date = date,
            root = raw_root,
        )

    reference = ParquetAStockReferenceLoader(
        context = context,
        connection_ref = reference_binding.connection_ref,
        dataset = reference_binding.dataset,
        version = reference_binding.version,
    ).load()

    status_publication = refresh_a_share_market_status(
        snapshot,
        AStockDailyStatusNormalizer(
            security_master = reference.security_master,
            trading_calendar = reference.trading_calendar,
            spot_coverage_policy=config.spot_coverage_policy
        ),
        as_of_date = date,
        root = context.connections.parquet_root(
            config.status_binding.connection_ref
        ),
        spec = MarketStatusPublishSpec(
            dataset_id = config.status_binding.dataset,
            market = config.status_binding.market,
            version = config.status_binding.version,
            source = "akshare_a_share_raw_snapshot",
        ),
    )

    eligibility_publication = (
        refresh_a_share_eligibility_from_market_status(
            context,
            as_of_date = date,
            status_connection_ref = config.status_binding.connection_ref,
            status_dataset = config.status_binding.dataset,
            status_version = config.status_binding.version,
            eligibility_root = context.connections.parquet_root(
                eligibility_binding.connection_ref
            ),
            eligibility_spec = EligibilityPublishSpec(
                dataset_id = eligibility_binding.dataset,
                version = eligibility_binding.version,
                market = eligibility_binding.market,
                data_tier = EligibilityDataTier.RECONSTRUCTED,
                source = "a_share_market_status",
                rule_version = config.eligibility_rule_version,
            ),
        )
    )

    return AStockDailyPipelineResult(
        raw_snapshot = snapshot,
        status_publication = status_publication,
        eligibility_publication = eligibility_publication,
    )

def is_a_share_trading_session(
        context: SourceContext,
        *,
        config: AStockDailyPipelineConfig,
        as_of_date: pd.Timestamp | str,
) -> bool:
    """Return whether a date is present in the configured A-share calendar"""

    date = pd.Timestamp(as_of_date).normalize()

    reference_binding = resolve_versioned_dataset_binding(
        config.reference_binding,
        as_of_date = date,
    )

    reference = ParquetAStockReferenceLoader(
        context = context,
        connection_ref= reference_binding.connection_ref,
        dataset = reference_binding.dataset,
        version = reference_binding.version,
    ).load()

    return StaticCalendarSessionGate(
        reference.trading_calendar,
    ).is_session(as_of_date)

def _load_existing_raw_snapshot(
        root: Path,
        date: pd.Timestamp,
) -> AStockRawSnapshot | None:
    output_dir = (
        root / "akshare_a_share_raw" / date.date().isoformat()
    )
    if not output_dir.exists():
        return None

    spot_path = output_dir / "spot.parquet"
    suspension_path = output_dir / "suspension.parquet"
    manifest_path = output_dir / "manifest.json"

    for path, label in (
        (spot_path, "spot snapshot"),
        (suspension_path, "suspension snapshot"),
        (manifest_path, "raw snapshot manifest"),
    ):
        if not path.is_file():
            raise FileNotFoundError(
                f"existing {label} does not exist: {path}"
            )

    manifest = json.loads(manifest_path.read_text(encoding = "utf-8"))
    schema_version = manifest.get("schema_version")
    if schema_version != A_SHARE_RAW_SNAPSHOT_SCHEMA_VERSION:
        raise ValueError(
            "unsupported raw snapshot schema version "
            f"{schema_version!r} expected "
            f"{A_SHARE_RAW_SNAPSHOT_SCHEMA_VERSION!r}"
        )
    if manifest.get("as_of_date") != date.date().isoformat():
        raise ValueError(
            "existing raw snapshot date does not match required date"
        )

    return AStockRawSnapshot(
        output_dir = output_dir,
        spot_path = spot_path,
        suspension_path = suspension_path,
        manifest_path = manifest_path,
        spot_row_count = int(manifest["spot_row_count"]),
        suspension_row_count = int(manifest["suspension_row_count"])
    )

def _spot_coverage_policy(value: object) -> SpotCoveragePolicy:
    if value is None:
        return SpotCoveragePolicy()

    payload = _mapping(value, label="spot_coverage")

    return SpotCoveragePolicy(
        max_missing_count=payload.get("max_missing_count", 0),
        max_missing_ratio=payload.get("max_missing_ratio", 0.0)
    )
