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
from ..datareader import MarketData


_SAFE_SEGMENT = re.compile(r"[A-Za-z0-9_.-]+\Z")
_DATE_VERSION = re.compile(
    r"(?P<date>\d{8})(?:-r(?P<revision>[1-9]\d*))?\Z"
)

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
    coverage_complete: bool | None = None

def load_latest_market_data_before(
        root: Path,
        *,
        dataset_id: str,
        as_of_date: pd.Timestamp | str,
) -> tuple[MarketDataPublication, MarketDataBundle] | None:
    """Load the newest complete date-versioned market-data publication before a date."""

    if (
        not isinstance(dataset_id, str)
        or not dataset_id
        or not _SAFE_SEGMENT.fullmatch(dataset_id)
    ):
        raise ValueError("dataset_id must be a safe non-empty path segment")

    date = pd.Timestamp(as_of_date).normalize()
    if pd.isna(date):
        raise ValueError("as_of_date must not be NaT")

    versions_dir = Path(root) / dataset_id /"versions"
    if not versions_dir.is_dir():
        return None

    candidates: list[tuple[pd.Timestamp, int,Path, dict[str, object]]] = []

    for output_dir in versions_dir.iterdir():
        if not output_dir.is_dir() or output_dir.name.startswith("."):
            continue

        match = _DATE_VERSION.fullmatch(output_dir.name)
        if match is None:
            continue

        try:
            version_date = pd.to_datetime(
                match.group("date"),
                format="%Y%m%d",
                errors="raise",
            ).normalize()
        except (TypeError, ValueError):
            continue

        revision = int(match.group("revision") or 0)

        if version_date >= date:
            continue

        close_path = output_dir / "close.parquet"
        volume_path = output_dir / "volume.parquet"
        manifest_path = output_dir / "manifest.json"
        if not (
            close_path.is_file()
            and volume_path.is_file()
            and manifest_path.is_file()
        ):
            raise ValueError(
                f"market-data version directory is incomplete: {output_dir}"
            )

        try:
            manifest = json.loads(
                manifest_path.read_text(encoding = "utf-8")
            )

        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise ValueError(
                f"market-data manifest is invalid: {manifest_path}"
            ) from error

        if not isinstance(manifest, dict):
            raise ValueError(
                f"market-data manifest must be a JSON object: {manifest_path}"
            )

        if (
            manifest.get("dataset_id") != dataset_id
            or manifest.get("version") != output_dir.name
        ):
            raise ValueError(
                f"market-data manifest does not match its version directory: "
                f"{output_dir}"
            )

        candidates.append((version_date, revision, output_dir, manifest))

    if not candidates:
        return None

    _, _, output_dir, manifest = max(candidates, key = lambda item: (item[0], item[1]))
    close = pd.read_parquet(output_dir / "close.parquet")
    volume = pd.read_parquet(output_dir / "volume.parquet")

    return (
        _publication_from_manifest(output_dir, manifest),
        MarketDataBundle(
            market= MarketData(close= close, volume = volume),
            calendar = pd.DatetimeIndex(close.index),
            metadata = {
                "version": manifest["version"],
                "source": manifest["source"],
                "frequency": manifest["frequency"],
                "adjustment": manifest["adjustment"],
                "coverage_complete": manifest.get("coverage_complete"),
            }
        )
    )

def publish_market_data_bundle(
        bundle: MarketDataBundle,
        *,
        root: Path,
        spec: MarketDataPublishSpec,
        coverage_complete: bool | None = None,
) -> MarketDataPublication:
    """Publish one immutable close-and-volume market-data version.

    ``coverage_complete`` records whether the published frames already satisfy
    the market-data coverage policy.  It is provenance only: it is not part of
    the content hash, so a coverage verdict can be refreshed without
    re-publishing the frames.
    """

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

    if coverage_complete is not None:
        manifest["coverage_complete"] = bool(coverage_complete)

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

    # A coverage verdict may be refined after publication.  Keep the freshest
    # knowledge rather than failing the run that learned it.
    if (
        "coverage_complete" in expected_manifest
        and existing.get("coverage_complete")
        != expected_manifest["coverage_complete"]
    ):
        existing = {
            **existing,
            "coverage_complete": expected_manifest["coverage_complete"],
        }
        manifest_path.write_text(
            json.dumps(
                existing,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )

    return _publication_from_manifest(
        output_dir,
        existing,
    )

def _publication_from_manifest(
        output_dir: Path,
        manifest: dict[str, object]
) -> MarketDataPublication:
    coverage_complete = manifest.get("coverage_complete")

    return MarketDataPublication(
        output_dir = output_dir,
        close_path = output_dir / "close.parquet",
        volume_path= output_dir / "volume.parquet",
        manifest_path = output_dir /"manifest.json",
        date_count= int(manifest["date_count"]),
        ticker_count = int(manifest["ticker_count"]),
        content_sha256=str(manifest["content_sha256"]),
        coverage_complete=(
            None if coverage_complete is None else bool(coverage_complete)
        ),
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

def resolve_latest_market_data_version(
    root: Path,
    *,
    dataset_id: str,
    as_of_date: pd.Timestamp | str,
) -> str | None:
    """Return the highest immutable base/revision version through a date."""
    date = pd.Timestamp(as_of_date).normalize()
    if pd.isna(date):
        raise ValueError("as_of_date must not be NaT")

    loaded = load_latest_market_data_before(
        root,
        dataset_id=dataset_id,
        as_of_date=date + pd.Timedelta(days=1),
    )
    if loaded is None:
        return None

    publication, _bundle = loaded
    return publication.output_dir.name