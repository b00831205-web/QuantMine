"""Automatic market-data coverage audit and bounded history-backfill planning"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
from typing import Mapping

import pandas as pd


@dataclass(frozen=True)
class CoverageAuditPolicy:
    minimum_coverage_ratio: float
    max_backfill_tasks: int
    max_symbols_per_task: int

    def __post_init__(self) -> None:
        if not 0.0 <= self.minimum_coverage_ratio <= 1.0:
            raise ValueError("minimum_coverage_ratio must be between 0 and 1")
        if self.max_backfill_tasks <= 0:
            raise ValueError("max_backfill_tasks must be positive")
        if self.max_symbols_per_task <= 0:
            raise ValueError("max_symbols_per_task must be positive")

@dataclass(frozen=True)
class BackfillTask:
    start: pd.Timestamp
    end: pd.Timestamp
    symbols: tuple[str, ...]
    fields: tuple[str, ...]
    reason: str
    checkpoint_key: str

    def to_mapping(self) -> dict[str, object]:
        return {
            "start": self.start.date().isoformat(),
            "end": self.end.date().isoformat(),
            "symbols": list(self.symbols),
            "fields": list(self.fields),
            "reason": self.reason,
            "checkpoint_key": self.checkpoint_key,
        }

@dataclass(frozen=True)
class BackfillPlan:
    plan_id: str
    tasks: tuple[BackfillTask , ...]
    deferred_gap_count: int

    def to_mapping(self) -> dict[str, object]:
        return {
            "plan_id": self.plan_id,
            "deferred_gap_count": self.deferred_gap_count,
            "tasks": [task.to_mapping() for task in self.tasks]
        }

@dataclass(frozen=True)
class CoverageAudit:
    market: str
    published_version: str
    coverage_ratio: float
    gap_count: int
    missing_dates: tuple[pd.Timestamp, ...]
    missing_symbols: tuple[str, ...]
    missing_fields: tuple[str, ...]
    complete: bool
    daily_production_ready: bool
    backfill_plan: BackfillPlan

    def to_mapping(self) -> dict[str, object]:
        return {
            "market": self.market,
            "published_version": self.published_version,
            "coverage_ratio": self.coverage_ratio,
            "gap_count": self.gap_count,
            "missing_dates": [
                value.date().isoformat()
                for value in self.missing_dates
            ],
            "missing_symbols": list(self.missing_symbols),
            "missing_fields": list(self.missing_fields),
            "complete": self.complete,
            "daily_production_ready": self.daily_production_ready,
            "backfill_plan": self.backfill_plan.to_mapping(),
        }


def persist_coverage_audit(
    audit: CoverageAudit,
    *,
    artifact_dir: Path | str,
) -> Path:
    """Persist one audit and its plan atomically for later worker consumption."""
    if not isinstance(audit, CoverageAudit):
        raise TypeError("audit must be a CoverageAudit")

    root = Path(artifact_dir)
    root.mkdir(parents=True, exist_ok=True)

    output = root / "coverage_audit.json"
    staging = root / ".coverage_audit.json.staging"

    staging.write_text(
        json.dumps(
            audit.to_mapping(),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    staging.replace(output)
    return output

def _normalize_sessions(values: pd.DatetimeIndex) -> pd.DatetimeIndex:
    sessions = pd.DatetimeIndex(
        pd.to_datetime(values, errors="raise"),
    ).normalize().sort_values()

    if sessions.empty:
        raise ValueError("expected_sessions must not be empty")
    if sessions.has_duplicates:
        raise ValueError("expected_sessions contains duplicate dates")

    return sessions

def _normalize_symbols(values: tuple[str, ...]) -> tuple[str, ...]:
    symbols = tuple(sorted({
        str(symbol).strip()
        for symbol in values
        if str(symbol).strip()
    }))

    if not symbols:
        raise ValueError("eligible_symbols must not be empty")

    return symbols

def _normalize_field(
    frame: pd.DataFrame,
    *,
    sessions: pd.DatetimeIndex,
    symbols: tuple[str, ...],
) -> pd.DataFrame:
    if not isinstance(frame, pd.DataFrame):
        raise TypeError("every field must be a pandas DataFrame")

    normalized = frame.copy()
    normalized.index = pd.DatetimeIndex(
        pd.to_datetime(normalized.index, errors="raise"),
    ).normalize()

    if normalized.index.has_duplicates:
        raise ValueError("field contains duplicate dates")

    normalized.columns = pd.Index(
        str(value).strip()
        for value in normalized.columns
    )

    if normalized.columns.has_duplicates:
        raise ValueError("field contains duplicate symbols")

    return normalized.reindex(
        index=sessions,
        columns=pd.Index(symbols),
    )

def _contiguous_windows(
    *,
    sessions: pd.DatetimeIndex,
    missing_dates: list[pd.Timestamp],
) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    missing = {
        pd.Timestamp(value).normalize()
        for value in missing_dates
    }

    windows: list[tuple[pd.Timestamp, pd.Timestamp]] = []
    current: list[pd.Timestamp] = []

    for session in sessions:
        if session in missing:
            current.append(session)
            continue

        if current:
            windows.append((current[0], current[-1]))
            current = []

    if current:
        windows.append((current[0], current[-1]))

    return windows

def _checkpoint_key(
    *,
    market: str,
    published_version: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
    symbols: tuple[str, ...],
    fields: tuple[str, ...],
) -> str:
    payload = {
        "market": market,
        "published_version": published_version,
        "start": start.date().isoformat(),
        "end": end.date().isoformat(),
        "symbols": symbols,
        "fields": fields,
    }
    return sha256(
        json.dumps(payload, sort_keys=True).encode("utf-8")
    ).hexdigest()

def _plan_id(
    *,
    market: str,
    published_version: str,
    tasks: list[BackfillTask],
) -> str:
    payload = {
        "market": market,
        "published_version": published_version,
        "tasks": [task.to_mapping() for task in tasks],
    }
    return sha256(
        json.dumps(payload, sort_keys=True).encode("utf-8")
    ).hexdigest()

def _build_gap_tasks(
    *,
    market: str,
    published_version: str,
    sessions: pd.DatetimeIndex,
    missing_by_symbol_field: Mapping[
        tuple[str, str], list[pd.Timestamp]
    ],
    max_symbols_per_task: int
) -> list[BackfillTask]:
    grouped_symbols: dict[
        tuple[pd.Timestamp, pd.Timestamp, tuple[str, ...]],
        list[str],
    ] = defaultdict(list)

    for (symbol, field), missing_dates in missing_by_symbol_field.items():
        for start, end in _contiguous_windows(
            sessions=sessions,
            missing_dates=missing_dates,
        ):
            grouped_symbols[(start, end, (field,))].append(symbol)

    tasks: list[BackfillTask] = []

    for (start, end, fields), symbols in grouped_symbols.items():
        for offset in range(0, len(symbols), max_symbols_per_task):
            batch = tuple(sorted(symbols[offset: offset + max_symbols_per_task]))
            checkpoint_key = _checkpoint_key(
                market=market,
                published_version=published_version,
                start=start,
                end=end,
                symbols=batch,
                fields=fields,
            )
            tasks.append(
                BackfillTask(
                    start=start,
                    end=end,
                    symbols=batch,
                    fields=fields,
                    reason="coverage_gap",
                    checkpoint_key=checkpoint_key,
                )
            )

    return sorted(
        tasks,
        key=lambda task: (
            task.start,
            task.end,
            task.fields,
            task.symbols,
        ),
    )

def audit_market_data_coverage(
    *,
    market: str,
    published_version: str,
    expected_sessions: pd.DatetimeIndex,
    eligible_symbols: tuple[str, ...],
    fields: Mapping[str, pd.DataFrame],
    policy: CoverageAuditPolicy,
) -> CoverageAudit:
    """Derive missing historical data and create bounded repair tasks.

    No historical date is supplied by the caller. Missing date windows are
    derived solely from the expected market calendar, eligible symbol set, and
    the published data-version fields.
    """
    if not market or market.strip() != market:
        raise ValueError("market must be a non-empty trimmed string")
    if not published_version or published_version.strip() != published_version:
        raise ValueError("published_version must be a non-empty trimmed string")
    if not isinstance(policy, CoverageAuditPolicy):
        raise TypeError("policy must be a CoverageAuditPolicy")
    if not fields:
        raise ValueError("fields must not be empty")

    sessions = _normalize_sessions(expected_sessions)
    symbols = _normalize_symbols(eligible_symbols)

    expected_cells = len(sessions) * len(symbols) * len(fields)
    present_cells = 0

    missing_by_symbol_field: dict[
        tuple[str, str], list[pd.Timestamp]
    ] = defaultdict(list)

    for field_name, frame in fields.items():
        if not isinstance(field_name, str) or not field_name.strip():
            raise ValueError("field names must be non-empty strings")

        normalized = _normalize_field(
            frame,
            sessions=sessions,
            symbols=symbols,
        )

        present_cells += int(normalized.notna().sum().sum())

        for symbol in symbols:
            missing = normalized.index[normalized[symbol].isna()]
            if not missing.empty:
                missing_by_symbol_field[(symbol, field_name)].extend(missing)

    coverage_ratio = (
        1.0 if expected_cells == 0
        else present_cells / expected_cells
    )

    gaps = _build_gap_tasks(
        market=market,
        published_version=published_version,
        sessions=sessions,
        missing_by_symbol_field=missing_by_symbol_field,
        max_symbols_per_task=policy.max_symbols_per_task,
    )

    scheduled = gaps[:policy.max_backfill_tasks]
    plan_id = _plan_id(
        market=market,
        published_version=published_version,
        tasks=scheduled,
    )

    missing_dates = tuple(sorted({
        date
        for dates in missing_by_symbol_field.values()
        for date in dates
    }))
    missing_symbols = tuple(sorted({
        symbol
        for symbol, _field in missing_by_symbol_field
    }))
    missing_fields = tuple(sorted({
        field
        for _symbol, field in missing_by_symbol_field
    }))

    gap_count = sum(
        len(dates)
        for dates in missing_by_symbol_field.values()
    )

    complete = (
        gap_count == 0
        and coverage_ratio >= policy.minimum_coverage_ratio
    )

    return CoverageAudit(
        market=market,
        published_version=published_version,
        coverage_ratio=coverage_ratio,
        gap_count=gap_count,
        missing_dates=missing_dates,
        missing_symbols=missing_symbols,
        missing_fields=missing_fields,
        complete=complete,
        # Historical repair is asynchronous and must never invalidate the
        # already-finished daily production task.
        daily_production_ready=True,
        backfill_plan=BackfillPlan(
            plan_id=plan_id,
            tasks=tuple(scheduled),
            deferred_gap_count=max(0, len(gaps) - len(scheduled)),
        ),
    )

def load_coverage_audit(path: Path | str) -> CoverageAudit:
    """Restore a persisted coverage audit for a later backfill worker."""
    source = Path(path)

    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (
        OSError,
        UnicodeError,
        json.JSONDecodeError,
    ) as error:
        raise ValueError(
            f"coverage audit is unreadable: {source}"
        ) from error

    if not isinstance(payload, dict):
        raise ValueError("coverage audit must be a JSON object")

    try:
        plan_payload = payload["backfill_plan"]
        if not isinstance(plan_payload, dict):
            raise TypeError("backfill_plan must be an object")

        tasks_payload = plan_payload["tasks"]
        if not isinstance(tasks_payload, list):
            raise TypeError("backfill_plan.tasks must be a list")

        tasks = tuple(
            BackfillTask(
                start=pd.Timestamp(item["start"]).normalize(),
                end=pd.Timestamp(item["end"]).normalize(),
                symbols=tuple(str(symbol) for symbol in item["symbols"]),
                fields=tuple(str(field) for field in item["fields"]),
                reason=str(item["reason"]),
                checkpoint_key=str(item["checkpoint_key"]),
            )
            for item in tasks_payload
        )

        return CoverageAudit(
            market=str(payload["market"]),
            published_version=str(payload["published_version"]),
            coverage_ratio=float(payload["coverage_ratio"]),
            gap_count=int(payload["gap_count"]),
            missing_dates=tuple(
                pd.Timestamp(value).normalize()
                for value in payload["missing_dates"]
            ),
            missing_symbols=tuple(
                str(value)
                for value in payload["missing_symbols"]
            ),
            missing_fields=tuple(
                str(value)
                for value in payload["missing_fields"]
            ),
            complete=bool(payload["complete"]),
            daily_production_ready=bool(
                payload["daily_production_ready"]
            ),
            backfill_plan=BackfillPlan(
                plan_id=str(plan_payload["plan_id"]),
                tasks=tasks,
                deferred_gap_count=int(
                    plan_payload["deferred_gap_count"]
                ),
            ),
        )
    except (
        KeyError,
        TypeError,
        ValueError,
    ) as error:
        raise ValueError(
            f"coverage audit has an invalid schema: {source}"
        ) from error