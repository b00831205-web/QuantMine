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
from .portfolio_execution import PortfolioState

_SAFE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*\Z")
_ARTIFACT_FILES: dict[str, str]={
    "equity_curve": "equity_curve.parquet",
    "daily_returns" : "daily_returns.parquet",
    "cash_curve": "cash_curve.parquet",
    "positions": "positions.parquet",
    "sellable_positions": "sellable_positions.parquet",
    "requested_shares": "requested_shares.parquet",
    "executed_shares": "executed_shares.parquet",
    "fees": "fees.parquet",
    "reasons": "reasons.parquet",
    "valuation_prices": "valuation_prices.parquet",
    "tradable": "tradable.parquet",
    "price_sources": "price_sources.parquet"
}

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
        ("price_sources", result.price_sources),
        ("executed_shares", result.executed_shares)
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
        raise TypeError("position-backtest manifest has invalid files")

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

@dataclass(frozen=True)
class PositionBacktestArtifacts:
    """Verified immutable files and their reconstructed backtest result."""

    publication: PositionBacktestPublication
    result: PositionBacktestResult

def _artifact_output_dir(*, root: Path, run_id: int, job_id: str, factor_name: str, period: int) -> Path:
    return Path(root) / str(run_id) / job_id / f"{factor_name}-{period}"

def _read_manifest(manifest_path: Path) -> dict[str, object]:
    if not manifest_path.is_file():
        raise FileNotFoundError(
            f"position-backtest manifest does not exist: {manifest_path}"
        )

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(
            f"position-backtest manifest is invalid: {manifest_path}"
        ) from error

    if not isinstance(manifest, dict):
        raise TypeError("position-backtest manifest must be an object")

    return manifest

def _require_exact_identity(
        manifest: dict[str, object],
        *,
        run_id: int,
        job_id: str,
        factor_name: str,
        period: int
) -> None:
    if manifest.get("schema_version") != 1:
        raise ValueError("unsupported position-backtest manifest schema_version")

    expected = {
        "run_id": run_id,
        "job_id": job_id,
        "factor_name": factor_name,
        "period": period,
    }

    actual = {
        field: manifest.get(field) for field in expected
    }

    if actual != expected:
        raise ValueError(
            "position-backtest manifest identity does not match requested artifact"
        )

def _verified_artifact_paths(*, output_dir: Path, manifest: dict[str, object]) -> dict[str, Path]:
    files = manifest.get("files")
    if not isinstance(files, dict):
        raise TypeError("position-backtest manifest files must be an object")

    expected_paths = set(_ARTIFACT_FILES.values())
    if set(files) != expected_paths:
        raise ValueError("position-backtest manifest contain exactly the expected artifacts")

    paths: dict[str, Path] = {}

    for artifact_name, relative_path in _ARTIFACT_FILES.items():
        expected_digest = files.get(relative_path)

        if not isinstance(expected_digest, str) or len(expected_digest) != 64:
            raise ValueError(
                f"position-backtest manifest has invalid digest for {relative_path}"
            )

        relative= Path(relative_path)
        if relative.is_absolute() or len(relative.parts) != 1 or relative.name != relative_path:
            raise ValueError(
                f"position-backtest artifact path is unsafe: {relative_path}"
            )

        path = output_dir / relative

        if not path.is_file():
            raise FileNotFoundError(
                f"position-backtest artifact does not exist: {path}"
            )

        if _file_sha256(path) != expected_digest:
            raise ValueError(
                f"position-backtest artifact checksum mismatch: {relative_path}"
            )

        paths[artifact_name] = path
    return paths

def _read_series(path: Path, *, column: str)->pd.Series:
    frame = pd.read_parquet(path)

    if not isinstance(frame, pd.DataFrame) or list(frame.columns) != [column]:
        raise ValueError(f"position-backtest series artifact must contain only {column!r}: {path}")

    series = frame[column].copy()
    series.name = column
    series.index.name = "date"

    if not isinstance(series.index, pd.DatetimeIndex):
        raise TypeError(
            f"position-backtest series artifact has non-datetime index: {path}"
        )

    return series

def _read_frame(path: Path) -> pd.DataFrame:
    frame = pd.read_parquet(path)

    if not isinstance(frame, pd.DataFrame):
        raise TypeError(f"position-backtest artifact is not a DataFrame: {path}")

    if not isinstance(frame.index, pd.DatetimeIndex):
        raise TypeError(
            f"position-backtest artifact has non-datetim index: {path}"
        )

    frame.index.name = "date"
    return frame

def _restore_final_state(
        *,
        manifest: dict[str, object],
        positions: pd.DataFrame,
        sellable_positions: pd.DataFrame,
        cash_curve: pd.Series
) -> PortfolioState:
    payload = manifest.get("final_state")
    if not isinstance(payload, dict):
        raise TypeError("position-backtest manifest final_state must be an object")

    cash = payload.get("cash")
    position_values = payload.get("positions")
    sellable_values = payload.get("sellable_positions")

    if isinstance(cash, bool) or not isinstance(cash, (int, float)):
        raise TypeError("position-backtest final_state.cash must be numeric")

    if not isinstance(position_values, dict):
        raise TypeError(
            "position-backtest final_state.positions must be an object"
        )

    if not isinstance(sellable_values, dict):
        raise TypeError(
            "position-backtest final_state.sellable_positions must be an object"
        )

    tickers = positions.columns

    if set(position_values) != set(tickers):
        raise ValueError(
            "position-backtest final_state.positions tickers do not match artifact"
        )

    if set(sellable_values) != set(tickers):
        raise ValueError(
            "position-backtest final_state.sellable_positions tickers do not match artifact"
        )

    state = PortfolioState(
        cash = float(cash),
        positions = pd.Series(
            position_values,
            index = tickers,
            dtype=float,
        ),
        sellable_positions = pd.Series(
            sellable_values,
            index = tickers,
            dtype= float,
        )
    )

    if not state.positions.equals(positions.iloc[-1].astype(float)):
        raise ValueError("position-backtest final_state.positions disagree with positions")

    if not state.sellable_positions.equals(
        sellable_positions.iloc[-1].astype(float)
    ):
        raise ValueError(
            "position-backtest final_state.sellable_positions disagrees with sellable_positions"
        )

    if float(state.cash) != float(cash_curve.iloc[-1]):
        raise ValueError(
            "position-backtest final_state.cash disagrees with cash_curve"
        )

    return state

def load_position_backtest_artifact(
        *,
        root: Path,
        run_id: int,
        job_id: str,
        factor_name: str,
        period: int,
) -> PositionBacktestArtifacts:
    """Load one published result after identity and checksum verification"""

    run_id = _require_run_id(run_id)
    job_id = _require_safe_name(job_id, label="job_id")
    factor_name = _require_safe_name(factor_name, label="factor_name")
    period = _require_period(period)

    output_dir = _artifact_output_dir(
        root = root,
        run_id = run_id,
        job_id = job_id,
        factor_name= factor_name,
        period = period,
    )
    manifest = _read_manifest(output_dir / "manifest.json")

    _require_exact_identity(
        manifest,
        run_id = run_id,
        job_id= job_id,
        factor_name= factor_name,
        period= period,
    )

    paths = _verified_artifact_paths(
        output_dir= output_dir,
        manifest = manifest
    )
    equity_curve = _read_series(paths["equity_curve"], column="equity")
    daily_returns = _read_series(paths["daily_returns"], column="return")
    cash_curve = _read_series(paths["cash_curve"], column="cash")

    positions = _read_frame(paths["positions"])
    sellable_positions = _read_frame(paths["sellable_positions"])
    requested_shares = _read_frame(paths["requested_shares"])
    executed_shares = _read_frame(paths["executed_shares"])
    fees = _read_frame(paths["fees"])
    reasons = _read_frame(paths["reasons"])
    valuation_prices = _read_frame(paths["valuation_prices"])
    tradable = _read_frame(paths["tradable"])
    price_sources = _read_frame(paths["price_sources"])

    if len(equity_curve) < 1:
        raise ValueError("position-backtest artifact must contain at least one date")

    if not positions.columns.equals(sellable_positions.columns):
        raise ValueError(
            "position-backtest positions and sellable_positions columns differ"
        )

    final_state = _restore_final_state(
        manifest=manifest,
        positions=positions,
        sellable_positions=sellable_positions,
        cash_curve=cash_curve,
    )

    result = PositionBacktestResult(
        equity_curve=equity_curve,
        daily_returns=daily_returns,
        cash_curve=cash_curve,
        positions=positions,
        sellable_positions=sellable_positions,
        requested_shares=requested_shares,
        executed_shares=executed_shares,
        fees=fees,
        reasons=reasons,
        final_state=final_state,
        valuation_prices=valuation_prices,
        tradable=tradable,
        price_sources=price_sources,
    )

    publication = _publication_from_manifest(output_dir, manifest)

    if publication.date_count != len(result.equity_curve):
        raise ValueError(
            "position-backtest manifest date_count does not match artifact"
        )

    if publication.ticker_count != len(result.positions.columns):
        raise ValueError(
            "position-backtest manifest ticker_count does not match artifact"
        )

    return PositionBacktestArtifacts(
        publication=publication,
        result=result,
    )

@dataclass(frozen=True)
class PositionBacktestRunPublication:
    """Derived index of every verified position-backtest artifact in one run."""

    run_id: int
    output_dir: Path
    manifest_path: Path
    artifact_count: int

def _run_manifest_entry(
        *,
        run_dir: Path,
        output_dir: Path,
        manifest: dict[str, object]
) -> dict[str, object]:
    publication = _publication_from_manifest(output_dir, manifest)

    _require_exact_identity(
        manifest,
        run_id=publication.run_id,
        job_id=publication.job_id,
        factor_name= publication.factor_name,
        period=publication.period,
    )
    _verified_artifact_paths(
        output_dir=output_dir,
        manifest=manifest
    )

    return {
        "job_id": publication.job_id,
        "factor_name": publication.factor_name,
        "period": publication.period,
        "artifact_dir": output_dir.relative_to(run_dir).as_posix(),
        "manifest_sha256": _file_sha256(publication.manifest_path),
        "date_count": publication.date_count,
        "ticker_count": publication.ticker_count,
    }

def _collect_run_manifest_entries(
        *,
        run_dir: Path,
        run_id: int
) -> list[dict[str, object]]:
    entries: list[dict[str, object]] = []

    if not run_dir.is_dir():
        raise FileNotFoundError(
            f"position-backtest run directory does not exist: {run_dir}"
        )

    for job_dir in sorted(run_dir.iterdir(), key= lambda path: path.name):
        if not job_dir.is_dir() or job_dir.name.startswith("."):
            continue

        job_id = _require_safe_name(job_dir.name, label="job_id")

        for output_dir in sorted(
            job_dir.iterdir(),
            key = lambda path: path.name
        ):
            if not output_dir.is_dir() or output_dir.name.startswith("."):
                continue

            manifest_path = output_dir / "manifest.json"
            if not manifest_path.is_file():
                continue

            manifest = _read_manifest(manifest_path)

            if manifest.get("run_id") != run_id:
                raise ValueError("position-bakctest artifact run_id disagrees with its directory")

            if manifest.get("job_id") != job_id:
                raise ValueError("position-backtest artifact job_id disagrees with its directory")

            entries.append(
                _run_manifest_entry(
                    run_dir= run_dir,
                    output_dir= output_dir,
                    manifest= manifest
                )
            )

    if not entries:
        raise ValueError(f"position-backtest run contains no published artifacts: {run_dir}")

    return sorted(
        entries,
        key = lambda item: (
            str(item["job_id"]),
            str(item["factor_name"]),
            int(item["period"])
        )
    )

def publish_position_backtest_run_manifest(
        *,
        root: Path,
        run_id: int
) -> PositionBacktestRunPublication:
    """Atomically publish the derived, verified index for one backtest run."""

    run_id = _require_run_id(run_id)
    run_dir = Path(root) / str(run_id)
    entries = _collect_run_manifest_entries(
        run_dir= run_dir,
        run_id = run_id,
    )
    payload = {
        "schema_version": 1,
        "artifact_type": "position_backtest_run",
        "run_id": run_id,
        "artifact_count": len(entries),
        "artifacts":entries,
    }

    manifest_path = run_dir / "run_manifest.json"
    staging_path = run_dir / f".run_manifest-{uuid4().hex}.json"

    try:
        staging_path.write_text(
            json.dumps(
                payload,
                ensure_ascii=False,
                sort_keys=True,
                indent=2,
                allow_nan=False,
            ),
            encoding="utf-8"
        )
        staging_path.replace(manifest_path)

    finally:
        if staging_path.exists():
            staging_path.unlink()

    return PositionBacktestRunPublication(
        run_id= run_id,
        output_dir= run_dir,
        manifest_path= manifest_path,
        artifact_count= len(entries)
    )