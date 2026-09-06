"""Immutable publication of A-share security-master and trading-calendar data."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import re
import shutil
from typing import Any
from uuid import uuid4

import pandas as pd

from ..plugins.a_share import AStockSecurityMaster

_SAFE_SEGMENT = re.compile(r"[A-Za-z0-9_.-]+\Z")

@dataclass(frozen = True)
class AStockReferencePublishSpec:
    """Non-secret identity and provenance for one reference-data version"""

    dataset_id: str
    market: str
    version: str
    source: str
    schema_version: str = "a_stock_reference_v1"

    def __post_init__(self) -> None:
        for label, value in (
            ("dataset_id", self.dataset_id),
            ("market", self.market),
            ("version", self.version)
        ):
            if(
                not isinstance(value, str)
                or not value
                or value.strip() != value
                or not _SAFE_SEGMENT.fullmatch(value)
            ):
                raise ValueError(
                    f"{label} must be a safe non-empty path segment"
                )
        if self.market != "CN":
            raise ValueError("A-share reference market must be 'CN'")

        for label, value in (
            ("source", self.source),
            ("schema_version", self.schema_version),
        ): 
            if( not isinstance(value, str)
               or not value 
               or value.strip() != value
        ):
                raise ValueError(
                    f"{label} must be a non-empty trimmed string"
                )

@dataclass(frozen=True)
class AStockReferencePublication:
    """Files and integrity metadata for one published reference version"""

    output_dir: Path
    security_master_path: Path
    trading_calendar_path: Path
    manifest_path: Path
    listing_count: int
    session_count: int
    min_session_date: pd.Timestamp
    max_session_date: pd.Timestamp
    content_sha256: str

def publish_a_stock_reference(
        security_master: AStockSecurityMaster,
        trading_calendar: pd.DatetimeIndex,
        *,
        root: Path,
        spec: AStockReferencePublishSpec
) -> AStockReferencePublication:
    """Publish one immutable and idempotent A-share reference-data version"""

    if not isinstance(security_master, AStockSecurityMaster):
        raise TypeError(
            "security_master must be an AStockSecurityMaster"
        )

    if not isinstance(spec, AStockReferencePublishSpec):
        raise TypeError(
            "spec must be an AStockReferencePublishSpec"
        )

    master_frame = security_master.to_frame()
    calendar = _normalize_calendar(trading_calendar)
    calendar_frame = pd.DataFrame({"date": calendar})

    content_sha256 = _content_sha256(
        master_frame,
        calendar,
        spec = spec
    )

    lake_root = Path(root).expanduser().resolve()
    lake_root.mkdir(parents = True, exist_ok = True)

    dataset_root = (lake_root / spec.dataset_id).resolve()
    _require_within(
        dataset_root,
        lake_root,
        label = "reference dataset"
    )

    output_dir = (
        dataset_root / "versions" / spec.version
    ).resolve()
    _require_within(
        output_dir,
        dataset_root,
        label = "reference version"
    )
    if output_dir.exists():
        return _load_existing_publication(
            output_dir,
            expected_content_sha256 = content_sha256,
            spec = spec
        )

    output_dir.parent.mkdir(parents = True, exist_ok=True)
    staging_dir = (
        output_dir.parent / f".{spec.version}.staging-{uuid4().hex}"
    )
    staging_dir.mkdir()

    security_master_path = staging_dir / "security_master.parquet"
    trading_calendar_path = (
        staging_dir / "trading_calendar.parquet"
    )
    manifest_path = staging_dir / "manifest.json"

    manifest = {
        "schema_version": spec.schema_version,
        "dataset_id": spec.dataset_id,
        "market": spec.market,
        "version": spec.version,
        "source": spec.source,
        "listing_count": len(master_frame),
        "ticker_count": int(master_frame["ticker"].nunique()),
        "session_count": len(calendar),
        "min_session_date": calendar.min().date().isoformat(),
        "max_session_date": calendar.max().date().isoformat(),
        "content_sha256": content_sha256,
    }
    try:
        master_frame.to_parquet(
            security_master_path,
            index = False,
        )
        calendar_frame.to_parquet(
            trading_calendar_path,
            index = False
        )
        manifest_path.write_text(
            json.dumps(
                manifest,
                ensure_ascii=False,
                indent = 2,
                sort_keys = True
            ),
            encoding="utf-8"
        )

        try:
            staging_dir.rename(output_dir)
        except OSError:
            if not output_dir.exists():
                raise

            shutil.rmtree(staging_dir)
            return _load_existing_publication(
                output_dir,
                expected_content_sha256 = content_sha256,
                spec = spec
            )
    except Exception:
        if staging_dir.exists():
            shutil.rmtree(staging_dir)

        raise
    return _publication_from_values(
        output_dir,
        listing_count = len(master_frame),
        calendar = calendar,
        content_sha256 = content_sha256,
    )

def _normalize_calendar(
        value: pd.DatetimeIndex,
) -> pd.DatetimeIndex:
    if not isinstance(value, pd.DatetimeIndex):
        raise TypeError(
            "trading_calendar must be a pandas DatetimeIndex"
        )
    calendar = pd.DatetimeIndex(
        pd.to_datetime(value, errors = "raise")
    ).normalize()

    if calendar.tz is not None:

        calendar = calendar.tz_localize(None)
    if calendar.empty:
        raise ValueError("trading calendar must not be empty")

    if calendar.has_duplicates:
        raise ValueError(
            "trading calendar contains duplicate dates"
        )

    if calendar.hasnans:
        raise ValueError(
            "trading calendar contains missing dates"
        )
    return calendar.sort_values()

def _content_sha256(
        master_frame: pd.DataFrame,
        calendar: pd.DatetimeIndex,
        *,
        spec: AStockReferencePublishSpec,
) -> str:
    payload: dict[str, Any] = {
        "schema_version": spec.schema_version,
        "dataset_id": spec.dataset_id,
        "market": spec.market,
        "version": spec.version,
        "source": spec.source,
        "security_master": json.loads(
            master_frame.to_json(
                orient = "records",
                date_format="iso",
                date_unit = "ns"
            )
        ),
        "trading_calendar": [
            value.date().isoformat() for value in calendar
        ],
    }
    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators = (",", ":"),
        allow_nan=False,
    ).encode("utf-8")

    return sha256(serialized).hexdigest()

def _load_existing_publication(
        output_dir: Path,
        *,
        expected_content_sha256: str,
        spec: AStockReferencePublishSpec,
) -> AStockReferencePublication:
    security_master_path = output_dir / "security_master.parquet"

    trading_calendar_path = (
        output_dir / "trading_calendar.parquet"
    )
    manifest_path = output_dir / "manifest.json"

    for path, label in (
        (security_master_path, "security master"),
        (trading_calendar_path, "trading calendar"),
        (manifest_path, "reference manifest")
    ):
        if not path.is_file():
            raise FileNotFoundError(
                f"existing {label} does not exist: {path}"
            )
    manifest = json.loads(
        manifest_path.read_text(encoding = "utf-8")
    )
    if not isinstance(manifest, dict):
        raise TypeError(
            "existing reference manifest must contain a JSON object"
        )
    master = AStockSecurityMaster.from_frame(
        pd.read_parquet(security_master_path)
    )
    calendar_frame = pd.read_parquet(trading_calendar_path)

    if "date" not in calendar_frame.columns:
        raise ValueError(
            "existing trading calendar is missing required column: date"
        )
    calendar = _normalize_calendar(
        pd.DatetimeIndex(calendar_frame["date"])
    )
    actual_content_sha256 = _content_sha256(
        master.to_frame(),
        calendar,
        spec = spec,
    )
    manifest_content_sha256 = manifest.get("content_sha256")
    if manifest_content_sha256 != actual_content_sha256:
        raise ValueError(
            "existing reference publication does not match its manifest"
        )

    if actual_content_sha256 != expected_content_sha256:
        raise FileExistsError(
            "reference version already exists with different content: "
            f"{output_dir}"
        )

    return _publication_from_values(
        output_dir,
        listing_count = len(master.to_frame()),
        calendar = calendar,
        content_sha256 = actual_content_sha256
    )

def _publication_from_values(
        output_dir: Path,
        *,
        listing_count: int,
        calendar: pd.DatetimeIndex,
        content_sha256: str,
) -> AStockReferencePublication:
    return AStockReferencePublication(
        output_dir = output_dir,
        security_master_path=(
            output_dir / "security_master.parquet"
        ),
        trading_calendar_path = (
            output_dir / "trading_calendar.parquet"
        ),
        manifest_path= output_dir / "manifest.json",
        listing_count = listing_count,
        session_count=len(calendar),
        min_session_date = calendar.min(),
        max_session_date = calendar.max(),
        content_sha256=content_sha256,
    )

def _require_within(
        path: Path,
        parent: Path,
        *,
        label: str,
)-> None:
    try:
        path.relative_to(parent)
    except ValueError as error:
        raise ValueError(
        f"{label} path escapes its configured root: {path}"
    ) from error
    