"""Immutable publication of wide-frame historical market data"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import re
import shutil
from uuid import uuid4

import pandas as pd

from ..plugins.contracts import MarketDataBundle


_SAFE_SEGMENT = re.compile(r"[A-Za-z0-9_.-]+\Z")

@dataclass(frozen = True)
class MarketDataPublishSpec:
    dataset_id: str
    market: str
    version: str
    source: str
    frequency: str
    adjustment: str | None = None
    schema_version: str = "market_data_bundle_v1"

    def __post_init__(self) -> None:
        for label, value in (
            ("dataset_id", self.dataset_id),
            ("market", self.market),
            ("version", self.version)
        ):
            if (
                not isinstance(value, str)
                or not value
                or value.strip() != value
                or not _SAFE_SEGMENT.fullmatch(value)
            ):
                raise ValueError(
                    f"{label} must be a safe non-empty path segment"
                )

        for label, value in (
            ("source", self.source),
            ("frequency", self.frequency),
            ("schema_version", self.schema_version)
        ):
            if(
                not isinstance(value, str)
                or not value
                or value.strip() != value
            ):
                raise ValueError(
                    f"{label} must be a non-empty trimmed string"
                )

        if (
            self.adjustment is not None
            and (
                not isinstance(self.adjustment, str)
                or self.adjustment.strip() != self.adjustment
            )
        ):
            raise ValueError(
                "adjustment must be None or a trimmed string"
            )

@dataclass(frozen = True)
class MarketDataPublication:
    output_dir: Path
    close_path: Path
    volume_path: Path
    manifest_path: Path
    date_count: int
    ticker_count: int
    content_sha256: str

def publish_market_data_bundle(
        bundle: MarketDataBundle,
        *,
        root: Path,
        spec: MarketDataPublishSpec
) -> MarketDataPublication:
    """Publish one immutable close-and-volume market-data version"""

    if not isinstance(bundle, MarketDataBundle):
        raise TypeError("bundle must be a MarketDataBundle")

    if not isinstance(spec, MarketDataPublishSpec):
        raise TypeError("spec must be a MarketDataPublishSpec")

    close = _normalize_frame(
        bundle.market.close,
        label = "close"
    )

    volume = _normalize_frame(
        bundle.market.volume,
        label = "volume"
    )

    if (
        not close.index.equals(volume.index)
        or not close.columns.equals(volume.columns)
    ):
        raise ValueError(
            "close and volume must have identical dates and tickers"
        )

    content_sha256 = _content_sha256(
        close = close,
        volume = volume,
    )

    lake_root = Path(root).expanduser().resolve()
    lake_root.mkdir(parents = True, exist_ok=True)

    dataset_root = (lake_root / spec.dataset_id).resolve()
    output_dir = (
        dataset_root / "versions" / spec.version
    ).resolve()

    _require_within(
        dataset_root,
        lake_root,
        label = "market-data dataset"
    )
    _require_within(
        output_dir,
        dataset_root,
        label = "market-data version"
    )

    manifest = {
        "adjustment": spec.adjustment,
        "content_sha256": content_sha256,
        "dataset_id": spec.dataset_id,
        "date_count": len(close.index),
        "end_date": close.index.max().date().isoformat(),
        "fields": ["close", "volume"],
        "frequency": spec.frequency,
        "market": spec.market,
        "schema_version": spec.schema_version,
        "source": spec.source,
        "start_date": close.index.min().date().isoformat(),
        "ticker_count": len(close.columns),
        "version": spec.version,
    }

    if output_dir.exists():
        return _load_existing_publication(
            output_dir,
            expected_manifest = manifest
        )

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging_dir = (
        output_dir.parent / f".{spec.version}.staging-{uuid4().hex}"
    )

    staging_dir.mkdir()

    try:
        close.to_parquet(
            staging_dir / "close.parquet",
            index = True
        )
        volume.to_parquet(
            staging_dir / "volume.parquet",
            index = True,
        )
        (staging_dir / "manifest.json").write_text(
            json.dumps(
                manifest,
                ensure_ascii=False,
                indent = 2,
                sort_keys= True
            ),
            encoding = "utf-8",
        )

        try:
            staging_dir.rename(output_dir)
        except OSError:
            if not output_dir.exists():
                raise

            shutil.rmtree(staging_dir)
            return _load_existing_publication(
                output_dir,
                expected_manifest = manifest,
            )

    except Exception:
        if staging_dir.exists():
            shutil.rmtree(staging_dir)
        raise

    return _publication_from_manifest(
        output_dir,
        manifest
    )

def _normalize_frame(
        frame: pd.DataFrame | None,
        *,
        label: str,
) -> pd.DataFrame:
    if not isinstance(frame, pd.DataFrame):
        raise TypeError(
            f"{label} must be a pandas DataFrame"
        )

    if frame.empty:
        raise ValueError(f"{label} must not be empty")

    normalized = frame.copy()
    normalized.index = pd.DatetimeIndex(
        pd.to_datetime(normalized.index, errors="raise")
    )

    if normalized.index.tz is not None:
        normalized.index = normalized.index.tz_localize(None)

    if normalized.index.hasnans:
        raise ValueError(f"{label} contains missing dates")

    if normalized.index.has_duplicates:
        raise ValueError(f"{label} contains duplicate dates")

    normalized.columns = pd.Index(
        str(column).strip() for column in normalized.columns
    )

    if any(not column for column in normalized.columns):
        raise ValueError(f"{label} contains an empty ticker")

    if normalized.columns.has_duplicates:
        raise ValueError(
            f"{label} contains duplicate tickers"
        )

    try:
        normalized = normalized.apply(
            pd.to_numeric,
            errors = "raise"
        )
    except (TypeError, ValueError) as error:
        raise ValueError(
            f"{label} contains non-numeric values"
        ) from error

    normalized.index.name = "date"

    return (
        normalized.sort_index().sort_index(axis =1)
    )

def _content_sha256(
        *,
        close: pd.DataFrame,
        volume: pd.DataFrame,
) -> str:
    digest = sha256()

    for field_name, frame in (
        ("close", close),
        ("volume", volume),
    ):
        digest.update(field_name.encode("utf-8"))
        digest.update(
            json.dumps(
                frame.columns.tolist(),
                ensure_ascii= False,
            ).encode("utf-8")
        )
        digest.update(
            pd.util.hash_pandas_object(
                frame,
                index = True
            ).to_numpy().tobytes()
        )
    return digest.hexdigest()

def _load_existing_publication(
        output_dir: Path,
        *,
        expected_manifest: dict[str, object],
) -> MarketDataPublication:
    close_path = output_dir / "close.parquet"
    volume_path = output_dir / "volume.parquet"
    manifest_path = output_dir / "manifest.json"

    if (
        not close_path.is_file()
        or not volume_path.is_file()
        or not manifest_path.is_file()
    ):
        raise FileExistsError(
            f"market-data version directory is incomplete: {output_dir}"
        )
    existing = json.loads(
        manifest_path.read_text(encoding = "utf-8")
    )

    if (
        existing.get("content_sha256") != expected_manifest["content_sha256"]
    ):
        raise FileExistsError(
            f"market-data version "
            f"{expected_manifest['version']!r} "
            "already exists with different content"
        )

    provenance_keys = (
        "dataset_id",
        "market",
        "version",
        "source",
        "frequency",
        "adjustment",
        "schema_version",
    )

    if any(
        existing.get(key) != expected_manifest[key] for key in provenance_keys
    ):
        raise FileExistsError(
            f"market-data version "
            f"{expected_manifest['version']!r} "
            "already exists with different provenance"
        )

    return _publication_from_manifest(
        output_dir,
        existing,
    )

def _publication_from_manifest(
        output_dir: Path,
        manifest: dict[str, object]
) -> MarketDataPublication:
    return MarketDataPublication(
        output_dir = output_dir,
        close_path = output_dir / "close.parquet",
        volume_path= output_dir / "volume.parquet",
        manifest_path = output_dir /"manifest.json",
        date_count= int(manifest["date_count"]),
        ticker_count = int(manifest["ticker_count"]),
        content_sha256=str(manifest["content_sha256"])
    )

def _require_within(
        path: Path,
        parent: Path,
        *,
        label: str,
) -> None:
    try:
        path.relative_to(parent)
    except ValueError as error:
        raise ValueError(
            f"{label} escapes its configured root"
        ) from error
