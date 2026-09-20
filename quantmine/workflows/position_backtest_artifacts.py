"""Immutable artifacts for one position-based backtest portfolio"""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

import pandas as pd

from .position_backtest import PositionBacktestResult

_SAFE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*\Z")


def _require_safe_name(value: object, *, label: str) -> str:
    if not isinstance(value, str) or not _SAFE_NAME.fullmatch(value):
        raise ValueError(f"{label} must be a safe non-empty path segment")

    return value


def _require_run_id(run_id: object) -> int:
    if not isinstance(run_id, int) or isinstance(run_id, bool) or run_id < 1:
        raise ValueError("run_id must be a positive integer")

    return run_id

def _require_period(period: object) -> int:
    if not isinstance(period, int) or isinstance(period, bool) or period < 1:
        raise ValueError("period must be a positive integer")

    return period


def _file_sha256(path: Path) -> str:
    digest = sha256()

    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest()

def _series_frame(
        series: pd.Series,
        *,
        column: str
) -> pd.DataFrame:
    frame = series.to_frame(name=column)
    frame.index.name = "date"
    return frame


def _write_frame(
        frame: pd.DataFrame,
        *,
        staging_dir: Path,
        relative_path: str,
        files: dict[str, str]
) -> None:
    if not isinstance(frame, pd.DataFrame):
        raise TypeError(f"artifact {relative_path!r} must be a pandas DataFrame")

    path = staging_dir / relative_path
    frame.to_parquet(path)
    files[relative_path] = _file_sha256(path)

@dataclass(frozen=True)
class PositionBacktestPublication:
    """Location and identity of one immutable portfolio artifact"""

    run_id: int
    job_id: str
    factor_name: str
    period: int
    output_dir: Path
    manifest_path: Path
    date_count: int
    ticker_count: int

    def __post_init__(self) -> None:
        _require_run_id(self.run_id)
        _require_safe_name(self.job_id, label="job_id")
        _require_safe_name(self.factor_name, label = "factor_name")
        _require_period(self.period)

        if self.date_count < 1:
            raise ValueError("date_count must be positive")

        if self.ticker_count <1:
            raise ValueError("ticker_count must be positive")

def _manifest(
        result: PositionBacktestResult,
        *,
        run_id: int,
        job_id: str,
        factor_name: str,
        period: int,
        staging_dir: Path
) -> dict[str, object]:
    files: dict[str, str] = {}

    artifacts: tuple[tuple[str, pd.DataFrame], ...] = (
        ("equity_curve", _series_frame(result.equity_curve, column = "equity")),
        ("daily_returns", _series_frame(result.daily_returns, column = "return")),
        ("cash_curve", _series_frame(result.cash_curve, column = "cash")),
        ("positions", result.positions),
        ("sellable_positions", result.sellable_positions),
        ("requested_shares", result.requested_shares),
        ("fees", result.fees),
        ("reasons", result.reasons),
        ("valuation_prices", result.valuation_prices),
        ("tradable", result.tradable),
        ("price_sources", result.price_sources)
    )

    for name, frame in artifacts:
        _write_frame(frame, staging_dir= staging_dir, relative_path=f"{name}.parquet", files = files)

    final_state = result.final_state
    return {
        "schema_version": 1,
        "run_id": run_id,
        "job_id": job_id,
        "factor_name": factor_name,
        "period": period,
        "date_count": len(result.equity_curve),
        "ticker_count": len(result.positions.columns),
        "files": files,
        "final_state": {
            "cash": float(final_state.cash),
            "positions": {
                str(ticker): float(value)
                for ticker, value in final_state.positions.items()
            },
            "sellable_positions": {
                str(ticker): float(value)
                for ticker, value in final_state.sellable_positions.items()
            }
        }
    }

def _publication_from_manifest(output_dir: Path, manifest: dict[str, object]) -> PositionBacktestPublication:
    return PositionBacktestPublication(
        run_id = _require_run_id(manifest["run_id"]),
        job_id = _require_safe_name(manifest["job_id"], label = "job_id"),
        factor_name = _require_safe_name(manifest["factor_name"], label="factor_name"),
        period = _require_period(manifest["period"]),
        output_dir= output_dir,
        manifest_path= output_dir / "manifest.json",
        date_count= int(manifest["date_count"]),
        ticker_count= int(manifest["ticker_count"])
    )

def _load_matching_publication(output_dir: Path, *, expected_manifest: dict[str, object]) -> PositionBacktestPublication:
    manifest_path = output_dir / "manifest.json"
    if not manifest_path.is_file():
        raise FileExistsError(f"position-backtest output exists but is incomplete: {output_dir}")

    try:
        existing_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f"position-backtest manifest is invalid: {manifest_path}") from error

    if existing_manifest != expected_manifest:
        raise FileExistsError("position-backtest output already exists with different content")

    files = existing_manifest.get("files")
    if not isinstance(files, dict):
        raise ValueError("position-backtest manifest has invalid files")

    for relative_path in files:
        if not (output_dir / relative_path).is_file():
            raise FileExistsError(f"position-backtest output exists but is incomplete {output_dir}")

    return _publication_from_manifest(output_dir, existing_manifest)

def publish_position_backtest_artifact(
        result: PositionBacktestResult,
        *,
        run_id: int,
        job_id: str,
        factor_name: str,
        period: int,
        root: Path,
) -> PositionBacktestPublication:
    """Atomically publish one immutable position-backtest result."""

    if not isinstance(result, PositionBacktestResult):
        raise TypeError("result must be a PositionBacktestResult")

    run_id = _require_run_id(run_id)
    job_id = _require_safe_name(job_id, label = "job_id")
    factor_name = _require_safe_name(factor_name, label = "factor_name")
    period = _require_period(period)

    output_root = Path(root)
    output_dir = output_root / str(run_id) / job_id / f"{factor_name}-{period}"

    output_root.mkdir(parents=True, exist_ok=True)
    staging_dir = output_root / (f".{run_id}-{job_id}-{factor_name}-{period}.staging-{uuid4().hex}")

    try:
        staging_dir.mkdir()
        manifest = _manifest(
            result,
            run_id = run_id,
            job_id = job_id,
            factor_name = factor_name,
            period = period,
            staging_dir = staging_dir,
        )

        if output_dir.exists():
            return _load_matching_publication(output_dir, expected_manifest=manifest)

        (staging_dir / "manifest.json").write_text(
            json.dumps(
                manifest,
                ensure_ascii=False,
                sort_keys=True,
                indent=2,
                allow_nan=False,
            ),
            encoding="utf-8"
        )

        output_dir.parent.mkdir(parents=True, exist_ok=True)
        try:
            staging_dir.rename(output_dir)

        except FileExistsError:
            return _load_matching_publication(output_dir, expected_manifest=manifest)

        return _publication_from_manifest(output_dir, manifest)

    finally:
        if staging_dir.exists():
            shutil.rmtree(staging_dir)