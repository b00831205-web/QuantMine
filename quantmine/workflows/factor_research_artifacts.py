"""Immutable artifacts produced by one configured factor-research run"""

from __future__ import annotations

import json
import re
import shutil
from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any
from uuid import uuid4

import pandas as pd

from ..research import FactorResearchResult


_SAFE_SIGNAL = re.compile(r"[A-Za-z][A-Za-z0-9_.-]*\Z")

@dataclass(frozen = True)
class FactorResearchPublication:
    """Locations and summary of one immutable factor artifact set."""

    run_id: int
    output_dir: Path
    manifest_path: Path
    factor_paths: Mapping[str, Path]
    factor_count: int
    pending_count: int

    def __post_init__(self) -> None:
        if (
            not isinstance(self.run_id, int)
            or isinstance(self.run_id, bool)
            or self.run_id <1
        ):
            raise ValueError("run_id must be a positive integer")

        if self.factor_count != len(self.factor_paths):
            raise ValueError(
                "factor_count must match factor_paths"
            )

        if self.pending_count <0:
            raise ValueError(
                "pending_count must be non-negative"
            )

@dataclass(frozen= True)
class FactorResearchArtifacts:
    """Verified factor frames loaded from one immutable publication"""

    publication: FactorResearchPublication
    requested_signals: tuple[str, ...]
    pending: Mapping[str, str]
    factors: Mapping[str, pd.DataFrame]

    def __post_init__(self) -> None:
        if not isinstance(self.publication, FactorResearchPublication):
            raise TypeError(
                "publication must be a FactorResearchPublication"
            )

        if len(set(self.requested_signals))!=len(self.requested_signals):
            raise ValueError(
                "requested_signals must not contain duplicates"
            )

        accounted = set(self.pending).union(self.factors)
        if accounted != set(self.requested_signals):
            raise ValueError(
                "loaded factors and pending signals must account for every requested signal"
            )

        if set(self.pending).intersection(self.factors):
            raise ValueError(
                "a signal cannot be both pending and loaded"
            )

def _normalize_factor_frame(
        signal: str,
        frame: object,
) -> pd.DataFrame:
    """Validate one date-by-ticker factor frame before publication"""

    if (
        not isinstance(signal, str)
        or not _SAFE_SIGNAL.fullmatch(signal)
    ):
        raise ValueError(
            "factor signal must be a safe non-empty path segment"
        )

    if not isinstance(frame, pd.DataFrame):
        raise TypeError(
            f"factor {signal!r} must be a pandas DataFrame"
        )

    if frame.empty:
        raise ValueError(
            f"factor {signal!r} must not be empty"
        )

    normalized = frame.copy()
    normalized.index = pd.DatetimeIndex(
        pd.to_datetime(normalized.index, errors ="raise")
    )

    if normalized.index.tz is not None:
        normalized.index = normalized.index.tz_localize(None)

    if normalized.index.hasnans:
        raise ValueError(
            f"factor {signal!r} contains missing dates"
        )

    if normalized.index.has_duplicates:
        raise ValueError(
            f"factor {signal!r} contains duplicate dates"
        )

    normalized.columns = pd.Index(
        str(column).strip()
        for column in normalized.columns
    )

    if any(not column for column in normalized.columns):
        raise ValueError(
            f"factor {signal!r} contains an empty ticker"
        )

    if normalized.columns.has_duplicates:
        raise ValueError(
            f"factor {signal!r} contains duplicate tickers"
        )

    try:
        normalized = normalized.apply(
            pd.to_numeric,
            errors = "raise",
        )

    except(TypeError, ValueError) as error:
        raise ValueError(
            f"factor {signal!r} contains non-numeric values"
        ) from error

    normalized.index.name = "date"

    return normalized.sort_index().sort_index(axis = 1)

def _factor_content_sha256(
        signal: str,
        frame: pd.DataFrame,
) -> str:
    """Return a deterministic hash for one normalized factor frame."""

    normalized = _normalize_factor_frame(signal, frame)
    digest = sha256()

    digest.update(signal.encode("utf-8"))
    digest.update(
        json.dumps(
            normalized.columns.tolist(),
            ensure_ascii=False,
        ).encode("utf-8")
    )
    digest.update(
        pd.util.hash_pandas_object(
            normalized,
            index = True
        ).to_numpy().tobytes()
    )

    return digest.hexdigest()

def _build_factor_manifest(
        result: FactorResearchResult,
        *,
        run_id: int,
) -> dict[str, Any]:
    """Build deterministic metadata for one factor-research artifact set."""

    if (
        not isinstance(run_id, int)
        or isinstance(run_id, bool)
        or run_id < 1
    ):
        raise ValueError("run_id must be a positive integer")

    requested_signals = tuple(result.requested_signals)
    if not requested_signals:
        raise ValueError("research result must request at least one signale")

    if len(set(requested_signals)) != len(requested_signals):
        raise ValueError("research result contains duplicate signals")

    for signal in requested_signals:
        if (
            not isinstance(signal, str)
            or not _SAFE_SIGNAL.fullmatch(signal)
        ):
            raise ValueError(
                "research result contains an unsafe requested signal"
            )

    requested_set = set(requested_signals)
    pending = dict(result.pending)
    factors = dict(result.factors)

    unknown_signals = (
        set(pending).union(factors).difference(requested_set)
    )
    if unknown_signals:
        raise ValueError(
            "research result contains unknown signals: "
            f"{sorted(unknown_signals)!r}"
        )

    completed_and_pending = set(pending).intersection(factors)
    if completed_and_pending:
        raise ValueError(
            "research result contains signals both completed and pending: "
            f"{sorted(completed_and_pending)!r}"
        )

    accounted_signals = set(pending).union(factors)
    missing_signals = requested_set.difference(accounted_signals)
    if missing_signals:
        raise ValueError(
            "research result has requested signals not accounted for: "
            f"{sorted(missing_signals)!r}"
        )

    factor_entries: dict[str, dict[str, Any]] = {}
    for signal in requested_signals:
        if signal not in factors:
            continue

        normalized = _normalize_factor_frame(signal, factors[signal])
        factor_entries[signal] = {
            "path": f"{signal}.parquet",
            "content_sha256": _factor_content_sha256(signal, normalized),
            "date_count": len(normalized.index),
            "ticker_count": len(normalized.columns),
            "min_date": normalized.index.min().date().isoformat(),
            "max_date": normalized.index.max().date().isoformat(),
        }

    return {
        "schema_version": 1,
        "run_id": run_id,
        "requested_signals": list(requested_signals),
        "factor_count": len(factor_entries),
        "pending": {
            signal: pending[signal] for signal in requested_signals if signal in pending
        },
        "pending_count": len(pending),
        "factors": factor_entries,
    }

def _publication_from_manifest(
        output_dir: Path,
        manifest: Mapping[str, Any],
) -> FactorResearchPublication:
    factors = manifest.get("factors")
    if not isinstance(factors, Mapping):
        raise ValueError("factor research manifest has invalid factors")

    factor_paths = {
        signal: output_dir / entry["path"]
        for signal, entry in factors.items()
        if isinstance(signal, str)
        and isinstance(entry, Mapping)
        and isinstance(entry.get("path"), str)
    }

    return FactorResearchPublication(
        run_id = manifest["run_id"],
        output_dir = output_dir,
        manifest_path = output_dir /"manifest.json",
        factor_paths = factor_paths,
        factor_count = manifest["factor_count"],
        pending_count = manifest["pending_count"],
    )


def _load_matching_factor_research_publication(
        output_dir: Path,
        *,
        expected_manifest: Mapping[str, Any]
) -> FactorResearchPublication:
    manifest_path = output_dir / "manifest.json"
    if not manifest_path.is_file():
        raise FileExistsError(
            f"factor research run output already exists but is incomplete: "
            f"{output_dir}"
        )

    try:
        existing_manifest = json.loads(
            manifest_path.read_text(encoding = "utf-8")
        )

    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(
            f"factor research manifest is invalid: {manifest_path}"
        ) from error

    if existing_manifest != expected_manifest:
        raise FileExistsError(
            "factor research run output already exists with different content"
        )

    publication = _publication_from_manifest(output_dir, existing_manifest)
    missing_paths = [
        path for path in publication.factor_paths.values() if not path.is_file()
    ]
    if missing_paths:
        raise FileExistsError(
            "factor research run output already exists but is incomplete: "
            f"{output_dir}"
        )

    return publication


def publish_factor_research_artifacts(
        result: FactorResearchResult,
        *,
        run_id: int,
        root: Path
) -> FactorResearchPublication:
    """Atomically publish one immutable set of factor-research artifacts."""

    manifest = _build_factor_manifest(result, run_id=run_id)
    output_root = Path(root)
    output_dir = output_root / str(run_id)

    output_root.mkdir(parents=True, exist_ok=True)
    if output_dir.exists():
        return _load_matching_factor_research_publication(
            output_dir,
            expected_manifest=manifest,
        )
    staging_dir = output_root / f".{run_id}.staging-{uuid4().hex}"
    try:
        staging_dir.mkdir()

        for signal, entry in manifest["factors"].items():
            normalized = _normalize_factor_frame(
                signal,
                result.factors[signal],
            )
            normalized.to_parquet(
                staging_dir/entry["path"],
            )

        (staging_dir / "manifest.json").write_text(
            json.dumps(
                manifest,
                ensure_ascii= False,
                sort_keys= True,
                indent = 2,
            ),
            encoding = "utf-8",
        )

        try:
            staging_dir.rename(output_dir)
        except FileExistsError:
            return _load_matching_factor_research_publication(
                output_dir,
                expected_manifest=manifest,
            )

        return _publication_from_manifest(output_dir, manifest)

    finally:
        if staging_dir.exists():
            shutil.rmtree(staging_dir)

def load_factor_research_artifacts(*, root: Path, run_id: int) -> FactorResearchArtifacts:
    """Load and verify one immutable factor-research publication"""

    if not isinstance(run_id, int) or isinstance(run_id, bool) or run_id < 1:
        raise ValueError("run_id must be a positive integer")

    output_dir = Path(root) / str(run_id)
    manifest_path = output_dir / "manifest.json"

    if not manifest_path.is_file():
        raise FileNotFoundError(
            f"factor research manifest does not exist: {manifest_path}"
        )

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f"factor research manifest is invalid: {manifest_path}") from error

    if not isinstance(manifest, Mapping):
        raise ValueError("factor research manifest must be a JSON object")

    if manifest.get("schema_version") != 1:
        raise ValueError("unsupported factor research manifest schema")

    if manifest.get("run_id") != run_id:
        raise ValueError(
            "factor research manifest run_id does not match request"
        )

    requested_payload = manifest.get("requested_signals")
    if not isinstance(requested_payload, list) or not all(isinstance(signal, str) and _SAFE_SIGNAL.fullmatch(signal) for signal in requested_payload) or len(set(requested_payload)) != len(requested_payload):
        raise ValueError(
            "factor research manifest has invalid requested signals"
        )

    requested_signals = tuple(requested_payload)

    pending_payload = manifest.get("pending")

    if not isinstance(pending_payload, Mapping) or not all(isinstance(signal,str) and bool(_SAFE_SIGNAL.fullmatch(signal)) and isinstance(reason, str) for signal, reason in pending_payload.items()):
        raise ValueError("factor research manifest has invalid pending signals")

    pending = dict(pending_payload)

    factor_entries = manifest.get("factors")
    if not isinstance(factor_entries, Mapping):
        raise ValueError(
            "factor research manifest has invalid factors"
        )

    if manifest.get("factor_count") != len(factor_entries):
        raise ValueError(
            "factor research manifest factor_count is inconsistent"
        )

    if manifest.get("pending_count") != len(pending):
        raise ValueError(
            "factor research manifest pending_count is inconsistent"
        )

    loaded_factors: dict[str, pd.DataFrame]= {}
    for signal, entry in factor_entries.items():
        if (
            not isinstance(signal, str)
            or not _SAFE_SIGNAL.fullmatch(signal)
            or not isinstance(entry, Mapping)
        ):
            raise ValueError(
                "factor research manifest contains an invalid factor"
            )

        relative_path = entry.get("path")
        expected_path = f"{signal}.parquet"

        if relative_path != expected_path:
            raise ValueError(
                f"factor {signal!r} has an unsafe artifact path"
            )

        factor_path = output_dir / expected_path
        if not factor_path.is_file():
            raise FileNotFoundError(
                f"factor artifact does not exist: {factor_path}"
            )

        try:
            frame = pd.read_parquet(factor_path)
        except (OSError, ValueError) as error:
            raise ValueError(
                f"factor artifact cannot be read: {factor_path}"
            ) from error

        normalized = _normalize_factor_frame(signal, frame)
        actual_hash = _factor_content_sha256(signal, normalized)

        if entry.get("content_sha256") != actual_hash:
            raise ValueError(
                f"factor {signal!r} content hash does not match its manifest"
            )

        if entry.get("date_count") != len(normalized.index):
            raise ValueError(
                f"factor {signal!r} date_count does not match"
            )

        if entry.get("ticker_count") != len(normalized.columns):
            raise ValueError(
                f"factor {signal!r} ticker_count does not match"
            )
        loaded_factors[signal] = normalized

    accounted = set(pending).union(loaded_factors)
    if accounted != set(requested_signals):
        raise ValueError(
            "factor research manifest does not account for every requested signal"
        )

    publication = _publication_from_manifest(
        output_dir, manifest
    )

    return FactorResearchArtifacts(
        publication = publication,
        requested_signals= requested_signals,
        pending = pending,
        factors = loaded_factors
    )
