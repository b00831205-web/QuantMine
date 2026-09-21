"""Publish immutable same-day market-data revisions from staged repairs."""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Iterable

import pandas as pd

from ..datareader import MarketData
from ..plugins.contracts import MarketDataBundle
from .market_data_publication import (
    MarketDataPublication,
    MarketDataPublishSpec,
    _content_sha256,
    _publication_from_manifest,
    publish_market_data_bundle,
)


_VERSION = re.compile(
    r"(?P<date>\d{8})(?:-r(?P<revision>[1-9]\d*))?\Z"
)

def publish_market_data_repair_revision(
    *,
    root: Path | str,
    dataset_id: str,
    base_version: str,
    repairs: Iterable[MarketDataBundle],
    coverage_complete: bool | None = None,
) -> MarketDataPublication:
    """Fill missing cells from repairs and publish a new immutable ``-rN`` version.

    Existing non-null values from the base version always win. A repair can only
    fill null cells or add a date/symbol absent from the base version.

    ``coverage_complete`` is the coverage verdict *after* applying the staged
    repairs. ``False`` marks the revision as still incomplete, so the research
    readiness gate keeps downstream research skipped.
    """
    root_path = Path(root)
    base_date = _version_date(base_version)
    base_bundle, base_manifest = _load_version(
        root_path,
        dataset_id=dataset_id,
        version=base_version,
    )

    repair_bundles = tuple(repairs)
    if not repair_bundles:
        raise ValueError("repairs must not be empty")

    merged = base_bundle
    for repair in repair_bundles:
        if not isinstance(repair, MarketDataBundle):
            raise TypeError("every repair must be a MarketDataBundle")
        merged = _merge_repair(merged, repair)

    if coverage_complete is None:
        # A merge that leaves any cell empty is not a complete version; the
        # readiness gate must keep consuming the pending repair plan.
        coverage_complete = not _has_cells_awaiting_repair(merged)

    merged_close = _required_frame(merged.market.close, label="merged close")
    merged_volume = _required_frame(
        merged.market.volume,
        label="merged volume",
    )
    merged_content_sha256 = _content_sha256(
        close=merged_close,
        volume=merged_volume,
    )

    # A repair that changes nothing must not mint a new revision: an existing
    # same-day version with identical content already describes this data.
    base_content_sha256 = _content_sha256(
        close=_required_frame(base_bundle.market.close, label="base close"),
        volume=_required_frame(base_bundle.market.volume, label="base volume"),
    )
    duplicate = _version_with_content(
        root_path,
        dataset_id=dataset_id,
        date_text=base_date,
        content_sha256=merged_content_sha256,
    )

    if duplicate is not None:
        duplicate_bundle, duplicate_manifest = _load_version(
            root_path,
            dataset_id=dataset_id,
            version=duplicate,
        )
        return publish_market_data_bundle(
            duplicate_bundle,
            root=root_path,
            spec=_publication_spec(
                dataset_id=dataset_id,
                manifest=duplicate_manifest,
                version=duplicate,
            ),
            coverage_complete=coverage_complete,
        )

    if merged_content_sha256 == base_content_sha256:
        # The staged repair filled nothing. Report the immutable base version
        # exactly as published instead of creating an empty revision.
        return _publication_from_manifest(
            root_path / dataset_id / "versions" / base_version,
            base_manifest,
        )

    revision = _next_revision(
        root_path,
        dataset_id=dataset_id,
        date_text=base_date,
    )

    spec = _publication_spec(
        dataset_id=dataset_id,
        manifest=base_manifest,
        version=f"{base_date}-r{revision}",
    )

    return publish_market_data_bundle(
        merged,
        root=root_path,
        spec=spec,
        coverage_complete=coverage_complete,
    )

def _publication_spec(
    *,
    dataset_id: str,
    manifest: dict[str, object],
    version: str,
) -> MarketDataPublishSpec:
    return MarketDataPublishSpec(
        dataset_id=dataset_id,
        market=str(manifest["market"]),
        version=version,
        source="coverage_backfill",
        frequency=str(manifest["frequency"]),
        adjustment=manifest.get("adjustment"),
        schema_version=str(
            manifest.get(
                "schema_version",
                "market_data_bundle_v1",
            )
        ),
    )

def _version_with_content(
    root: Path,
    *,
    dataset_id: str,
    date_text: str,
    content_sha256: str,
) -> str | None:
    """Return an existing same-day revision whose frames match this content."""

    versions_dir = root / dataset_id / "versions"
    if not versions_dir.is_dir():
        return None

    revision_pattern = re.compile(
        re.escape(date_text) + r"-r(?P<revision>[1-9]\d*)\Z"
    )
    matches: list[tuple[int, str]] = []

    for candidate in versions_dir.iterdir():
        if not candidate.is_dir():
            continue
        match = revision_pattern.fullmatch(candidate.name)
        if match is None:
            continue
        manifest_path = candidate / "manifest.json"
        if not manifest_path.is_file():
            continue
        try:
            manifest = json.loads(
                manifest_path.read_text(encoding="utf-8")
            )
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        if manifest.get("content_sha256") != content_sha256:
            continue
        matches.append((int(match.group("revision")), candidate.name))

    if not matches:
        return None

    return max(matches)[1]

def _has_cells_awaiting_repair(bundle: MarketDataBundle) -> bool:
    """Return whether the merged bundle still contains an empty market cell."""

    frames: list[pd.DataFrame] = []

    close = getattr(bundle.market, "close", None)
    if isinstance(close, pd.DataFrame):
        frames.append(close)

    volume = getattr(bundle.market, "volume", None)
    if isinstance(volume, pd.DataFrame):
        frames.append(volume)

    return any(bool(frame.isna().to_numpy().any()) for frame in frames)


def _load_version(
    root: Path,
    *,
    dataset_id: str,
    version: str,
) -> tuple[MarketDataBundle, dict[str, object]]:
    version_root = root / dataset_id / "versions" / version
    close_path = version_root / "close.parquet"
    volume_path = version_root / "volume.parquet"
    manifest_path = version_root / "manifest.json"

    if not (
        close_path.is_file()
        and volume_path.is_file()
        and manifest_path.is_file()
    ):
        raise FileNotFoundError(
            f"market-data version is incomplete: {version_root}"
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
            f"market-data manifest is invalid: {manifest_path}"
        ) from error

    if (
        not isinstance(manifest, dict)
        or manifest.get("dataset_id") != dataset_id
        or manifest.get("version") != version
    ):
        raise ValueError(
            f"market-data manifest does not match version: {version_root}"
        )

    close = pd.read_parquet(close_path)
    volume = pd.read_parquet(volume_path)

    return (
        MarketDataBundle(
            market=MarketData(close=close, volume=volume),
            calendar=pd.DatetimeIndex(close.index),
            metadata={"version": version},
        ),
        manifest,
    )

def _version_date(version: str) -> str:
    match = _VERSION.fullmatch(version)
    if match is None:
        raise ValueError(
            "base_version must use YYYYMMDD or YYYYMMDD-rN"
        )
    return match.group("date")

def _next_revision(
    root: Path,
    *,
    dataset_id: str,
    date_text: str,
) -> int:
    versions_dir = root / dataset_id / "versions"
    if not versions_dir.is_dir():
        raise FileNotFoundError(
            f"market-data versions directory is missing: {versions_dir}"
        )

    highest = 0
    for candidate in versions_dir.iterdir():
        if not candidate.is_dir():
            continue

        match = _VERSION.fullmatch(candidate.name)
        if match is None or match.group("date") != date_text:
            continue

        highest = max(
            highest,
            int(match.group("revision") or 0),
        )

    return highest + 1

def _required_frame(
    frame: pd.DataFrame | None,
    *,
    label: str,
) -> pd.DataFrame:
    if not isinstance(frame, pd.DataFrame):
        raise ValueError(f"{label} must be a DataFrame")

    result = frame.copy()
    result.index = pd.DatetimeIndex(
        pd.to_datetime(result.index, errors="raise"),
    ).normalize()

    if result.index.has_duplicates:
        raise ValueError(f"{label} contains duplicate dates")

    result.columns = pd.Index(
        str(column).strip()
        for column in result.columns
    )

    if result.columns.has_duplicates:
        raise ValueError(f"{label} contains duplicate symbols")

    return result

def _fill_missing(
    base: pd.DataFrame,
    repair: pd.DataFrame,
) -> pd.DataFrame:
    """Keep existing values; only use the repair for missing base cells."""
    normalized_base = _required_frame(base, label="base field")
    normalized_repair = _required_frame(repair, label="repair field")

    return (
        normalized_base
        .combine_first(normalized_repair)
        .sort_index()
        .sort_index(axis=1)
    )

def _merge_repair(
    base: MarketDataBundle,
    repair: MarketDataBundle,
) -> MarketDataBundle:
    base_close = _required_frame(base.market.close, label="base close")
    base_volume = _required_frame(base.market.volume, label="base volume")
    repair_close = _required_frame(
        repair.market.close,
        label="repair close",
    )

    close = _fill_missing(base_close, repair_close)

    if repair.market.volume is None:
        volume = base_volume
    else:
        volume = _fill_missing(
            base_volume,
            _required_frame(
                repair.market.volume,
                label="repair volume",
            ),
        )

    if not close.index.equals(volume.index) or not close.columns.equals(
        volume.columns
    ):
        raise ValueError(
            "repair merge produced misaligned close and volume frames"
        )

    return MarketDataBundle(
        market=MarketData(close=close, volume=volume),
        calendar=pd.DatetimeIndex(close.index),
        metadata=dict(base.metadata),
    )