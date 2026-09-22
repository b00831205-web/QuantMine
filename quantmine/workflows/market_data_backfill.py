"""Plan-driven, resumable staging for historical market-data backfills."""

from __future__ import annotations

from dataclasses import dataclass, replace
from hashlib import sha256
import json
from pathlib import Path
import re
import shutil
from uuid import uuid4

import pandas as pd

from ..datareader import MarketData
from ..plugins.context import SourceContext
from ..plugins.contracts import (
    DataBinding,
    DataSourceComponent,
    MarketDataBundle,
)
from .coverage_audit import BackfillTask
from .market_data_refresh import (
    MarketDataRefreshPolicy,
    load_market_data_batches,
)

_SAFE_SEGMENT = re.compile(r"[A-Za-z0-9_.-]+\Z")
_ALLOWED_FIELDS = frozenset({"close", "volume", "market_cap"})

@dataclass(frozen=True)
class BackfillStagingResult:
    plan_id: str
    checkpoint_key: str
    output_dir: Path
    manifest_path: Path
    fields: tuple[str, ...]
    content_sha256: str

def stage_market_data_backfill(
    context: SourceContext,
    *,
    source_component: DataSourceComponent,
    binding_template: DataBinding,
    policy: MarketDataRefreshPolicy,
    plan_id: str,
    task: BackfillTask,
    staging_connection_ref: str,
) -> BackfillStagingResult:
    """Load exactly one persisted repair task into an idempotent staging area."""
    _validate_plan_id(plan_id)
    _validate_task(task)

    output_dir = _staging_dir(
        context,
        plan_id=plan_id,
        checkpoint_key=task.checkpoint_key,
        staging_connection_ref=staging_connection_ref,
    )

    if output_dir.exists():
        return _load_existing_result(
            output_dir,
            plan_id=plan_id,
            task=task,
        )

    binding = replace(
        binding_template,
        start=task.start.date().isoformat(),
        end=task.end.date().isoformat(),
        tickers=task.symbols,
    )

    bundle = load_market_data_batches(
        context,
        source_component=source_component,
        binding=binding,
        # The backfill staging directory itself is the durable checkpoint.
        # Avoid the daily publication checkpoint namespace here.
        policy=replace(policy, checkpoint_connection_ref=None),
    )

    field_frames = _requested_frames(bundle, task)
    content_sha256 = _content_sha256(field_frames)

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging_dir = output_dir.parent / (
        f".{task.checkpoint_key}.staging-{uuid4().hex}"
    )
    staging_dir.mkdir()

    manifest = {
        "schema_version": 1,
        "plan_id": plan_id,
        "checkpoint_key": task.checkpoint_key,
        "start": task.start.date().isoformat(),
        "end": task.end.date().isoformat(),
        "symbols": list(task.symbols),
        "fields": list(task.fields),
        "reason": task.reason,
        "content_sha256": content_sha256,
    }

    try:
        for field_name, frame in field_frames.items():
            frame.to_parquet(staging_dir / f"{field_name}.parquet")

        (staging_dir / "manifest.json").write_text(
            json.dumps(
                manifest,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )

        try:
            staging_dir.rename(output_dir)
        except OSError:
            if not output_dir.exists():
                raise
            shutil.rmtree(staging_dir)
            return _load_existing_result(
                output_dir,
                plan_id=plan_id,
                task=task,
            )
    except Exception:
        if staging_dir.exists():
            shutil.rmtree(staging_dir)
        raise

    return BackfillStagingResult(
        plan_id=plan_id,
        checkpoint_key=task.checkpoint_key,
        output_dir=output_dir,
        manifest_path=output_dir / "manifest.json",
        fields=task.fields,
        content_sha256=content_sha256,
    )

def load_staged_market_data_backfill(
    context: SourceContext,
    *,
    plan_id: str,
    task: BackfillTask,
    staging_connection_ref: str,
) -> MarketDataBundle:
    """Load a completed staged repair without contacting the data source."""
    _validate_plan_id(plan_id)
    _validate_task(task)

    output_dir = _staging_dir(
        context,
        plan_id=plan_id,
        checkpoint_key=task.checkpoint_key,
        staging_connection_ref=staging_connection_ref,
    )
    _load_existing_result(
        output_dir,
        plan_id=plan_id,
        task=task,
    )

    fields: dict[str, pd.DataFrame] = {}
    for field_name in task.fields:
        path = output_dir / f"{field_name}.parquet"
        if not path.is_file():
            raise FileNotFoundError(
                f"staged backfill field is missing: {path}"
            )
        fields[field_name] = pd.read_parquet(path)

    close = fields.get("close")
    if close is None:
        raise ValueError("staged backfill requires close data")

    return MarketDataBundle(
        market=MarketData(
            close=close,
            volume=fields.get("volume"),
            market_cap=fields.get("market_cap"),
        ),
        calendar=pd.DatetimeIndex(close.index),
        metadata={
            "plan_id": plan_id,
            "checkpoint_key": task.checkpoint_key,
            "staged_backfill": True,
        },
    )

def _staging_dir(
    context: SourceContext,
    *,
    plan_id: str,
    checkpoint_key: str,
    staging_connection_ref: str,
) -> Path:
    root = context.connections.writable_parquet_root(
        staging_connection_ref
    )
    return (
        root
        / "market_data_backfill"
        / plan_id
        / checkpoint_key
    )

def _requested_frames(
    bundle: MarketDataBundle,
    task: BackfillTask,
) -> dict[str, pd.DataFrame]:
    result: dict[str, pd.DataFrame] = {}

    for field_name in task.fields:
        frame = getattr(bundle.market, field_name, None)
        if not isinstance(frame, pd.DataFrame):
            raise ValueError(
                f"backfill source did not provide required field "
                f"{field_name!r}"
            )

        normalized = frame.copy()
        normalized.index = pd.DatetimeIndex(
            pd.to_datetime(normalized.index, errors="raise"),
        ).normalize()

        if normalized.empty:
            raise ValueError(
                f"backfill source returned no rows for {field_name!r}"
            )

        if normalized.index.min() < task.start or normalized.index.max() > task.end:
            raise ValueError(
                f"backfill source returned dates outside the requested "
                f"window for {field_name!r}"
            )

        missing_symbols = set(task.symbols) - set(normalized.columns)
        if missing_symbols:
            raise ValueError(
                f"backfill source omitted requested symbols for "
                f"{field_name!r}: {sorted(missing_symbols)}"
            )

        result[field_name] = normalized.loc[
            task.start:task.end,
            list(task.symbols),
        ]

    return result

def _load_existing_result(
    output_dir: Path,
    *,
    plan_id: str,
    task: BackfillTask,
) -> BackfillStagingResult:
    manifest_path = output_dir / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(
            f"staged backfill manifest is missing: {manifest_path}"
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
            f"staged backfill manifest is invalid: {manifest_path}"
        ) from error

    expected = {
        "plan_id": plan_id,
        "checkpoint_key": task.checkpoint_key,
        "start": task.start.date().isoformat(),
        "end": task.end.date().isoformat(),
        "symbols": list(task.symbols),
        "fields": list(task.fields),
        "reason": task.reason,
    }

    if any(manifest.get(key) != value for key, value in expected.items()):
        raise FileExistsError(
            "staged backfill checkpoint already exists with "
            "different task metadata"
        )

    content_sha256 = manifest.get("content_sha256")
    if not isinstance(content_sha256, str) or not content_sha256:
        raise ValueError(
            "staged backfill manifest has no content checksum"
        )

    for field_name in task.fields:
        if not (output_dir / f"{field_name}.parquet").is_file():
            raise FileNotFoundError(
                f"staged backfill field is missing: "
                f"{output_dir / f'{field_name}.parquet'}"
            )

    return BackfillStagingResult(
        plan_id=plan_id,
        checkpoint_key=task.checkpoint_key,
        output_dir=output_dir,
        manifest_path=manifest_path,
        fields=task.fields,
        content_sha256=content_sha256,
    )

def _content_sha256(fields: dict[str, pd.DataFrame]) -> str:
    digest = sha256()

    for field_name in sorted(fields):
        digest.update(field_name.encode("utf-8"))
        digest.update(
            pd.util.hash_pandas_object(
                fields[field_name],
                index=True,
            ).to_numpy().tobytes()
        )

    return digest.hexdigest()

def _validate_plan_id(plan_id: str) -> None:
    if (
        not isinstance(plan_id, str)
        or not plan_id
        or not _SAFE_SEGMENT.fullmatch(plan_id)
    ):
        raise ValueError("plan_id must be a safe non-empty path segment")


def _validate_task(task: BackfillTask) -> None:
    if not isinstance(task, BackfillTask):
        raise TypeError("task must be a BackfillTask")
    if task.end < task.start:
        raise ValueError("backfill task end must not precede start")
    if not task.symbols:
        raise ValueError("backfill task must contain symbols")
    if not task.fields:
        raise ValueError("backfill task must contain fields")
    if any(field not in _ALLOWED_FIELDS for field in task.fields):
        raise ValueError(
            f"unsupported backfill fields: {task.fields!r}"
        )
    if not _SAFE_SEGMENT.fullmatch(task.checkpoint_key):
        raise ValueError(
            "checkpoint_key must be a safe path segment"
        )