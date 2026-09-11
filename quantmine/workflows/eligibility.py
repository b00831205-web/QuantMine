"""Immutable publication of normalized daily eligibility dataset"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
from uuid import uuid4
import pandas as pd
from typing import Protocol
from enum import StrEnum
from collections.abc import Mapping

from ..plugins.eligibility import DailyEligibilityUniverse

_BASE_COLUMNS = (
    "date",
    "ticker",
    "is_listed",
    "is_tradable",
    "listing_days"
)

class EligibilityDataTier(StrEnum):
    RECONSTRUCTED = "reconstructed"
    OBSERVED = "observed"
    VENDOR_PIT = "vendor_pit"

@dataclass(frozen = True)
class EligibilityPublishSpec:
    dataset_id: str
    version: str
    market: str
    data_tier: EligibilityDataTier
    source: str
    rule_version: str | None = None
    source_observed_at: str | None = None
    schema_version: str = "daily_eligibility_v1"

    def __post_init__(self) -> None:
        try:
            data_tier = EligibilityDataTier(self.data_tier)
        except ValueError as error:
            raise ValueError(
                "date_tier must be one of: reconstructed, observed, vendor_pit"
            ) from error

        object.__setattr__(self, "data_tier", data_tier)

        for label, value in (
            ("dataset_id", self.dataset_id),
            ("version", self.version),
            ("market", self.market),
            ("source", self.source),
            ("schema_version", self.schema_version)
        ):
            if not value or value.strip() != value:
                raise ValueError(f"{label} must be a non-empty trimmed string")

            if "/" in value or "\\" in value or value in (".",".."):
                raise ValueError(f"{label} must be a safe path segment")

        if data_tier is EligibilityDataTier.RECONSTRUCTED:
            if not self.rule_version:
                raise ValueError(
                    "rule_version is required for reconstructed eligibility data"
                )

        if data_tier is EligibilityDataTier.OBSERVED:
            if not self.source_observed_at:
                raise ValueError(
                    "source_observed_at is required for observed eligibility data"
                )
        if self.source_observed_at is not None:
            observed_at = pd.Timestamp(self.source_observed_at)
            if observed_at.tzinfo is None:
                raise ValueError("source_observed_at must include a timezone")

            object.__setattr__(
                self,
                "source_observed_at",
                observed_at.isoformat()
            )

@dataclass(frozen = True)
class EligibilityPublication:
    output_dir: Path
    eligibility_path: Path
    manifest_path: Path
    row_count: int
    min_date: pd.Timestamp
    max_date: pd.Timestamp
    content_sha256: str

def _normalize(frame: pd.DataFrame) -> pd.DataFrame:
    DailyEligibilityUniverse.from_frame(frame)

    normalized = frame.copy()
    normalized["date"] = pd.to_datetime(
        normalized["date"],
        errors = "raise"
    ).dt.normalize()
    normalized["ticker"] = normalized["ticker"].astype(str).str.strip()
    normalized["listing_days"] = pd.to_numeric(
        normalized["listing_days"],
        errors = "raise"
    )

    extension_columns = sorted(
        column for column in normalized.columns if column not in _BASE_COLUMNS
    )
    normalized = normalized.loc[:, [*_BASE_COLUMNS, *extension_columns]]
    return normalized.sort_values(["date", "ticker"]).reset_index(drop=True)

def _content_sha256(frame: pd.DataFrame)->str:
    payload = frame.to_json(
        orient = "split",
        index = 'False',
        date_format= "iso",
        date_unit = "ns"
    )
    return sha256(payload.encode("utf-8")).hexdigest()

def _publication_from_manifest(
        output_dir: Path,
        manifest: dict[str, object],
) -> EligibilityPublication:
    return EligibilityPublication(
        output_dir = output_dir,
        eligibility_path= output_dir / "eligibility.parquet",
        manifest_path = output_dir / "manifest.json",
        row_count = int(manifest["row_count"]),
        min_date = pd.Timestamp(str(manifest["min_date"])),
        max_date = pd.Timestamp(str(manifest["max_date"])),
        content_sha256= str(manifest["content_sha256"])
    )

def publish_daily_eligibility(
        frame: pd.DataFrame,
        *,
        root: Path,
        spec: EligibilityPublishSpec,
) -> EligibilityPublication:

    """Validate and immutably publish one version of a daily eligibility table."""

    normalized = _normalize(frame)
    content_sha256 = _content_sha256(normalized)
    provenance = _provenance_manifest(spec)

    output_dir = root / spec.dataset_id /"versions" / spec.version
    eligibility_path = output_dir / "eligibility.parquet"
    manifest_path = output_dir / "manifest.json"

    if output_dir.exists():
        if not manifest_path.is_file() or not eligibility_path.is_file():
            raise FileExistsError(
                f"eligibility version directory is incomplete: {output_dir}"
            )

        manifest = json.loads(manifest_path.read_text(encoding = "utf-8"))
        _assert_existing_manifest_matches(
            manifest,
            content_sha256 = content_sha256,
            provenance=provenance,
            version = spec.version
        )
        return _publication_from_manifest(output_dir, manifest)

    manifest = {
        "dataset_id": spec.dataset_id,
        "market": spec.market,
        "max_date": normalized["date"].max().date().isoformat(),
        "min_date": normalized["date"].min().date().isoformat(),
        "row_count": len(normalized),
        "schema_version": spec.schema_version,
        "version": spec.version,
        "content_sha256": content_sha256,
        **provenance
    }
    _assert_existing_manifest_matches(
        manifest,
        content_sha256=content_sha256,
        provenance=provenance,
        version = spec.version
    )

    versions_dir = output_dir.parent
    versions_dir.mkdir(parents=True, exist_ok=True)

    staging_dir = versions_dir / f".{spec.version}.staging-{uuid4().hex}"
    staging_dir.mkdir()
    staging_eligibility_path = staging_dir / "eligibility.parquet"
    staging_manifest_path = staging_dir / "manifest.json"

    normalized.to_parquet(staging_eligibility_path, index = False)
    staging_manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent = 2),
        encoding = "utf-8",
    )

    try:
        staging_dir.replace(output_dir)
    except FileExistsError:
        if not manifest_path.is_file() or not eligibility_path.is_file():
            raise

        existing_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        _assert_existing_manifest_matches(
            existing_manifest,
            content_sha256=content_sha256,
            provenance=provenance,
            version = spec.version
        )
        return _publication_from_manifest(output_dir, existing_manifest)

    return _publication_from_manifest(output_dir, manifest)

class DailyEligibilityFrameBuilder(Protocol):
    """Market-specific builder used by schedulers without coupling to Airflow"""

    def build(self, as_of_date: pd.Timestamp) -> pd.DataFrame:
        """Return one normalized-or-normalizable daily eligibility table."""

def refresh_daily_eligibility(
        builder: DailyEligibilityFrameBuilder,
        *,
        as_of_date: pd.Timestamp | str,
        root: Path,
        spec: EligibilityPublishSpec
) -> EligibilityPublication:
    """Build and publish one daily eligibility version.

    This is intentionally scheduler-neutral. An Airflow task will later call
    this function and pass its own market-specific builder.
    """

    normalized_date = pd.Timestamp(as_of_date).normalize()
    frame = builder.build(normalized_date)

    return publish_daily_eligibility(
        frame,
        root = root,
        spec = spec
    )

def _provenance_manifest(spec: EligibilityPublishSpec) -> dict[str, object]:
    return {
        "data_tier": spec.data_tier.value,
        "source": spec.source,
        "source_observed_at": spec.source_observed_at,
        "rule_version": spec.rule_version
    }

def _assert_existing_manifest_matches(
        manifest: dict[str, object],
        *,
        content_sha256: str,
        provenance: dict[str, object],
        version: str,
) -> None:
    if manifest.get("content_sha256") != content_sha256:
        raise FileExistsError(
            f"eligibility version {version!r} already exists "
            "with different content"
        )

    if any(manifest.get(key) != value for key, value in provenance.items()):
        raise FileExistsError(
            f"eligibility version {version!r} already exists "
            "with different provenance" 
        )
def load_latest_eligibility_before(
    root: Path,
    *,
    spec: EligibilityPublishSpec,
    as_of_date: pd.Timestamp | str,
) -> tuple[str, pd.DataFrame] | None:
    """Load the latest compatible immutable version before one date."""

    date = pd.Timestamp(as_of_date).normalize()
    versions_dir = Path(root) / spec.dataset_id / "versions"

    if not versions_dir.exists():
        return None

    expected_provenance = _provenance_manifest(spec)
    candidates: list[tuple[pd.Timestamp, str, Path]] = []

    for version_dir in versions_dir.iterdir():
        if not version_dir.is_dir() or version_dir.name.startswith("."):
            continue

        manifest_path = version_dir / "manifest.json"
        eligibility_path = version_dir / "eligibility.parquet"

        if not manifest_path.is_file() or not eligibility_path.is_file():
            raise ValueError(
                f"eligibility version directory is incomplete: "
                f"{version_dir}"
            )

        try:
            manifest = json.loads(
                manifest_path.read_text(encoding="utf-8")
            )
        except (
            OSError,
            UnicodeError,
            json.JSONDecodeError,
        ) as error:
            raise ValueError(
                f"eligibility manifest is invalid: {manifest_path}"
            ) from error

        if not isinstance(manifest, Mapping):
            raise ValueError(
                f"eligibility manifest must be a JSON object: "
                f"{manifest_path}"
            )

        compatible = (
            manifest.get("dataset_id") == spec.dataset_id
            and manifest.get("market") == spec.market
            and manifest.get("schema_version") == spec.schema_version
            and all(
                manifest.get(key) == value
                for key, value in expected_provenance.items()
            )
        )
        if not compatible:
            continue

        max_date = pd.Timestamp(
            manifest.get("max_date")
        ).normalize()

        if max_date < date:
            candidates.append(
                (
                    max_date,
                    str(manifest.get("version")),
                    eligibility_path,
                )
            )

    if not candidates:
        return None

    _, version, eligibility_path = max(candidates)
    return version, pd.read_parquet(eligibility_path)

def refresh_cumulative_daily_eligibility(
        builder: DailyEligibilityFrameBuilder,
        *,
        as_of_date: pd.Timestamp | str,
        root: Path,
        spec: EligibilityPublishSpec,
) -> EligibilityPublication:
    """Append one daily snapshot into a new immutable cumulative version."""

    date = pd.Timestamp(as_of_date).normalize()
    daily_frame = _normalize(builder.build(date))

    daily_dates = pd.DatetimeIndex(
        daily_frame["date"].drop_duplicates()
    )
    if (
        len(daily_dates) != 1
        or daily_dates[0] != date
    ):
        raise ValueError(
            "daily eligibility builder must return exactly "
            "the requested as_of_date"
        )

    previous = load_latest_eligibility_before(
        root,
        spec = spec,
        as_of_date= date
    )

    if previous is None:
        cumulative = daily_frame

    else:
        _, previous_frame = previous
        previous_frame = _normalize(previous_frame)

        cumulative = pd.concat(
            [previous_frame, daily_frame],
            ignore_index = True,
            sort = False,
        )

        if cumulative.duplicated(
            subset= ["date", "ticker"]
        ).any():
            raise ValueError(
                "cumulative eligibility contains duplicate date/ticker rows"
            )

    return publish_daily_eligibility(
        cumulative,
        root = root,
        spec = spec
    )