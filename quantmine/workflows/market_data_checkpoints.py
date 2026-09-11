"""Recoverable checkpoint for batched market-data loading."""

from __future__ import annotations


from pathlib import Path
import re

import json
import shutil
from uuid import uuid4

import pandas as pd

from ..plugins.contracts import DataBinding, MarketDataBundle
from collections.abc import Mapping

from ..datareader import MarketData


_CHECKPOINT_ID_PATTERN = re.compile(r"[0-9a-f]{64}\Z")

def market_data_batch_checkpoint_dir(
        root: Path,
        *,
        checkpoint_id: str,
        batch_number: int
) -> Path:
    """Resolve one batch directory beneath a trusted checkpoint root."""

    checkpoint_root = Path(root).expanduser().resolve()

    if not checkpoint_root.is_dir():
        raise FileNotFoundError(
            f"checkpoint root does not exist or is not a directory: "
            f"{checkpoint_root}"
        )

    if (
        not isinstance(checkpoint_id, str)
        or not _CHECKPOINT_ID_PATTERN.fullmatch(checkpoint_id)
    ):
        raise ValueError(
            "checkpoint_id must be a 64-character lowercase SHA-256 value"
        )

    if(
        not isinstance(batch_number, int)
        or isinstance(batch_number, bool)
        or batch_number < 1
    ):
        raise ValueError(
            "batch_number must be a positive integer"
        )

    batch_dir = (
        checkpoint_root / "market_data_refresh" / checkpoint_id / f"batch_{batch_number:06d}"
    ).resolve()

    try:
        batch_dir.relative_to(checkpoint_root)

    except ValueError as error:
        raise ValueError(
            "market-data checkpoint path escapes its configured root"
        ) from error

    return batch_dir

def save_market_data_batch_checkpoint(
        root: Path,
        *,
        checkpoint_id: str,
        batch_number: int,
        binding: DataBinding,
        bundle: MarketDataBundle,
) -> Path:
    """Atomically persist one completed market-data batch."""

    if not isinstance(binding, DataBinding):
        raise TypeError("binding must be a DataBinding")

    if not isinstance(bundle, MarketDataBundle):
        raise TypeError("bundle must be a MarketDataBundle")

    if bundle.universe is not None or bundle.benchmark is not None:
        raise ValueError(
            "market-data checkpoints do not persist universe or benchmark"
        )

    output_dir = market_data_batch_checkpoint_dir(
        root,
        checkpoint_id= checkpoint_id,
        batch_number = batch_number
    )

    if output_dir.exists():
        raise FileExistsError(
            f"market-data batch checkpoint already exists: {output_dir}"
        )

    expected_tickers = set(binding.tickers)
    frames: dict[str, pd.DataFrame] = {}

    for field_name in ("close", "volume", "market_cap"):
        frame = getattr(bundle.market, field_name)

        if frame is None:
            continue

        if not isinstance(frame, pd.DataFrame):
            raise TypeError(
                f"bundle.market.{field_name} must be a DataFrame or None"
            )

        if frame.empty:
            raise ValueError(
                f"bundle.market.{field_name} must be a DataFrame or None"
            )

        if frame.columns.has_duplicates:
            raise ValueError(
                f"bundle.market.{field_name} contains duplicate tickers"
            )

        actual_tickers = {
            str(column) for column in frame.columns
        }

        if actual_tickers != expected_tickers:
            raise ValueError(
                f"bundle.market.{field_name} tickers do not match "
                "the batch binding"
            )

        frames[field_name] = frame

    if not frames:
        raise ValueError(
            "market-data batch checkpoint requires at least one field"
        )

    manifest = {
        "schema_version": "market_data_batch_checkpoint_v1",
        "checkpoint_id": checkpoint_id,
        "batch_number": batch_number,
        "tickers": list(binding.tickers),
        "fields": sorted(frames),
        "has_calendar": bundle.calendar is not None,
        "metadata": dict(bundle.metadata)
    }

    try:
        manifest_text = json.dumps(
            manifest,
            ensure_ascii=False,
            indent = 2,
            sort_keys= True,
        )

    except(TypeError, ValueError) as error:
        raise TypeError(
            "market-data checkpoint metadata must be JSON serializable"
        ) from error


    output_dir.parent.mkdir(parents = True, exist_ok= True)
    checkpoint_root = Path(root).expanduser().resolve()
    staging_dir = (
        checkpoint_root / f".market-data-staging-{uuid4().hex}"
    )
    staging_dir.mkdir()

    try:
        for field_name, frame in frames.items():
            frame.to_parquet(
                staging_dir / f"{field_name}.parquet",
                index = True,
            )

        if bundle.calendar is not None:
            pd.DataFrame(
                {"date": pd.DatetimeIndex(bundle.calendar)}
            ).to_parquet(
                staging_dir / "calendar.parquet",
                index = False,
            )

        (staging_dir / "manifest.json").write_text(
            manifest_text,
            encoding = "utf-8"
        )
        staging_dir.rename(output_dir)

    except Exception:
        if staging_dir.exists():
            shutil.rmtree(staging_dir)

        raise
    return output_dir

def load_market_data_batch_checkpoint(
        root: Path,
        *,
        checkpoint_id: str,
        batch_number: int,
        binding: DataBinding,
) -> MarketDataBundle | None:
    """Load one completed checkpoint, or return None when absent."""

    if not isinstance(binding, DataBinding):
        raise TypeError("binding must be a DataBinding")

    checkpoint_dir = market_data_batch_checkpoint_dir(
        root,
        checkpoint_id = checkpoint_id,
        batch_number = batch_number,
    )

    if not checkpoint_dir.exists():
        return None

    if not checkpoint_dir.is_dir():
        raise ValueError(
            f"market-data checkpoint is not a directory: "
            f"{checkpoint_dir}"
        )

    manifest_path = checkpoint_dir / "manifest.json"
    if not manifest_path.is_file():
        raise ValueError(
            f"market-data check is incomplete: {checkpoint_dir}"
        )

    try:
        manifest = json.loads(
            manifest_path.read_text(encoding = "utf-8")
        )

    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(
            f"market-data checkpoint manifest is invalid: "
            f"{manifest_path}"
        ) from error

    if not isinstance(manifest, Mapping):
        raise ValueError(
            "market-data checkpoint manifest must be a JSON object"
        )

    expected_header = {
        "schema_version": "market_data_batch_checkpoint_v1",
        "checkpoint_id": checkpoint_id,
        "batch_number": batch_number,
        "tickers": list(binding.tickers),
    }

    for key, expected_value in expected_header.items():
        if manifest.get(key) != expected_value:
            raise ValueError(
                f"market-data checkpoint manifest has invalid {key}"
            )

    fields = manifest.get("fields")
    supported_fields = {"close", "volume", "market_cap"}

    if (
        not isinstance(fields, list)
        or not fields
        or len(fields) != len(set(fields))
        or any(field not in supported_fields for field in fields)
    ):
        raise ValueError(
            "market-data checkpoint manifest has invali fields"
        )

    frames: dict[str, pd.DataFrame] = {}

    for field_name in fields:
        field_path = checkpoint_dir / f"{field_name}.parquet"

        if not field_path.is_file():
            raise ValueError(
                f"market-data checkpoint is missing {field_name}.parquet"
            )

        frame = pd.read_parquet(field_path)

        if frame.empty:
            raise ValueError(
                f"market-data checkpoint {field_name} is empty"
            )

        if frame.columns.has_duplicates:
            raise ValueError(
                f"market-data checkpoint {field_name}"
                "contains duplicate tickers"
            )

        if {
            str(column)
            for column in frame.columns
        } != set(binding.tickers):
            raise ValueError(
                f"market-data checkpoint {field_name} tickers "
                "do not match the batch binding"
            )

        frame.columns = pd.Index(
            str(column) for column in frame.columns
        )
        frames[field_name] = frame.loc[:, list(binding.tickers)]

    has_calendar = manifest.get("has_calendar")
    if not isinstance(has_calendar, bool):
        raise ValueError(
            "market-data checkpoint manifest has invalid has_calendar"
        )

    calendar: pd.DatetimeIndex | None = None
    if has_calendar:
        calendar_path = checkpoint_dir / "calendar.parquet"

        if not calendar_path.is_file():
            raise ValueError(
                "market-data checkpoint is missing calendar.parquet"
            )

        calendar_frame = pd.read_parquet(calendar_path)
        if list(calendar_frame.columns) != ["date"]:
            raise ValueError(
                "market-data checkpoint calendar has invalid schema"
            )

        calendar = pd.DatetimeIndex(
            pd.to_datetime(
                calendar_frame["date"],
                errors= "raise",
            )
        )

    metadata = manifest.get("metadata", {})
    if not isinstance(metadata, Mapping):
        raise ValueError(
            "market-data checkpoint metadata must be a JSON object."
        )

    return MarketDataBundle(
        market = MarketData(**frames),
        calendar = calendar,
        metadata = dict(metadata),
    )