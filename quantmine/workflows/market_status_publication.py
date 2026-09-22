"""Immutable, market-neutral publication of daily market status"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
from uuid import uuid4

import pandas as pd

from .market_status import DailyMarketStatus

_BASE_COLUMNS = (
    "date",
    "ticker",
    "is_listed",
    "is_tradable","listing_days"
)

@dataclass(frozen = True)
class MarketStatusPublishSpec:
    dataset_id: str
    market: str
    version: str
    source: str
    source_observed_at : str | None = None
    schema_version: str = "daily_market_status_v1"

    def __post_init__(self) -> None:
        for label, value in (
            ("dataset_id", self.dataset_id),
            ("market", self.market),
            ("version", self.version)
        ):
            if not value or value.strip() != value:
                raise ValueError(f"{label} must be a non-empty trimmed string")

            if (
                "/" in value or "\\" in value or value in {".", ".."}
            ):
                raise ValueError(f"{label} must be a safe path segment")

        for label, value in (
            ("source", self.source),
            ("schema_version", self.schema_version),
        ):
            if not value or value.strip() != value:
                raise ValueError(f"{label} must be a non-empty trimmed string")

        if self.source_observed_at is not None:
            observed_at = pd.Timestamp(self.source_observed_at)
            if observed_at.tzinfo is None:
                raise ValueError(
                    "source_observed_at must include a timezone"
                )
            object.__setattr__(
                self,
                "source_observed_at",
                observed_at.isoformat()
            )

@dataclass(frozen = True)
class MarketStatusPublication:
    output_dir: Path
    status_path: Path
    manifest_path: Path
    row_count: int
    as_of_date: pd.Timestamp
    content_sha256: str

def publish_daily_market_status(
        status: DailyMarketStatus,
        *,
        root: Path,
        spec: MarketStatusPublishSpec
) -> MarketStatusPublication:
    """Publish one immutable market-status version for one market date"""

    if not isinstance(status, DailyMarketStatus):
        raise TypeError("status must be a DailyMarketStatus")

    normalized = _normalize(status)
    as_of_date = status.as_of_date
    content_sha256 = _content_sha256(normalized)

    output_dir = (
        root / spec.dataset_id/ f"market={spec.market}" / f"date={as_of_date.date().isoformat()}" / "versions" / spec.version
    )
    status_path = output_dir / "status.parquet"
    manifest_path = output_dir / "manifest.json"

    manifest = {
        "as_of_date" : as_of_date.date().isoformat(),
        "content_sha256": content_sha256,
        "dataset_id": spec.dataset_id,
        "market": spec.market,
        "row_count": len(normalized),
        "schema_version": spec.schema_version,
        "source": spec.source,
        "source_observed_at": spec.source_observed_at,
        "version": spec.version,
    }

    if output_dir.exists():
        if not status_path.is_file() or not manifest_path.is_file():
            raise FileExistsError(
                f"market-status version directory is incomplete: {output_dir}"
            )
        existing = json.loads(manifest_path.read_text(encoding = "utf-8"))
        _assert_existing_manifest_matches(
            existing,
            manifest = manifest,
            version = spec.version
        )
        return _publication_from_manifest(output_dir, existing)

    version_dir = output_dir.parent
    version_dir.mkdir(parents = True, exist_ok = True)

    staging_dir = version_dir /f".{spec.version}.staging-{uuid4().hex}"
    staging_dir.mkdir()

    normalized.to_parquet(staging_dir / "status.parquet", index= False)
    (staging_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii = False, sort_keys = True, indent = 2),
        encoding = "utf-8",
    )
    try:
        staging_dir.replace(output_dir)

    except FileExistsError:
        if not status_path.is_file() or not manifest_path.is_file():
            raise

        existing = json.loads(manifest_path.read_text(encoding = "utf-8"))
        _assert_existing_manifest_matches(
            existing,
            manifest = manifest,
            version = spec.version,
        )
        return _publication_from_manifest(output_dir, existing)

    return _publication_from_manifest(output_dir, manifest)

def _normalize(status: DailyMarketStatus) -> pd.DataFrame:
    frame = status.frame
    extensions = sorted(
        column for column in frame.columns
        if column not in _BASE_COLUMNS
    )

    return (
        frame.loc[:, [*_BASE_COLUMNS, *extensions]]
        .sort_values(["date","ticker"])
        .reset_index(drop = True)
    )

def _content_sha256(frame: pd.DataFrame) -> str:
    payload = frame.to_json(
        orient = "split",
        index = False,
        date_format = "iso",
        date_unit = "ns"
    )
    return sha256(payload.encode("utf-8")).hexdigest()

def _publication_from_manifest(
        output_dir: Path,
        manifest: dict[str, object],
) -> MarketStatusPublication:
    return MarketStatusPublication(
        output_dir= output_dir,
        status_path=output_dir / "status.parquet",
        manifest_path= output_dir / "manifest.json",
        row_count = int(manifest["row_count"]),
        as_of_date=pd.Timestamp(str(manifest["as_of_date"])),
        content_sha256=str(manifest["content_sha256"])
    )

def _assert_existing_manifest_matches(
        existing: dict[str, object],
        *,
        manifest: dict[str, object],
        version: str,
) -> None:
    if existing.get("content_sha256") != manifest["content_sha256"]:
        raise FileExistsError(
            f"market-status version {version!r} already exists "
            "with different content"
        )

    provenance_keys = (
        "dataset_id",
        "market",
        "as_of_date",
        "schema_version",
        "source",
        "source_observed_at",
        "version"
    )
    if any(existing.get(key) != manifest[key] for key in provenance_keys):
        raise FileExistsError(
            f"market-status version {version!r} already exists "
            "with different provenance"
        )