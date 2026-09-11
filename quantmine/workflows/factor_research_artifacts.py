"""Immutable artifacts produced by one configured factor-research run"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Any

import re
import pandas as pd
from hashlib import sha256
import json
import shutil
from uuid import uuid4

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