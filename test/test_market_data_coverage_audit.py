"""Contract tests for automatic market-data coverage audit and backfill.

The caller supplies the expected calendar and eligible universe, never a
hand-picked historical date.  The audit derives old-data gaps from the
published version itself and emits bounded, resumable repair work.
"""

from __future__ import annotations

import pandas as pd

from quantmine.workflows.coverage_audit import (
    CoverageAuditPolicy,
    audit_market_data_coverage,
    load_coverage_audit,
    persist_coverage_audit,
)


SESSIONS = pd.bdate_range("2026-01-05", periods=5)
SYMBOLS = ("000001.SZ", "600000.SH")


def _field_frame(*, missing: dict[str, list[pd.Timestamp]] | None = None) -> pd.DataFrame:
    frame = pd.DataFrame(1.0, index=SESSIONS, columns=SYMBOLS)
    for symbol, dates in (missing or {}).items():
        frame.loc[dates, symbol] = float("nan")
    return frame


def _audit(
    *,
    close: pd.DataFrame | None = None,
    volume: pd.DataFrame | None = None,
    policy: CoverageAuditPolicy | None = None,
):
    return audit_market_data_coverage(
        market="CN",
        published_version="20260109",
        expected_sessions=SESSIONS,
        eligible_symbols=SYMBOLS,
        fields={
            "close": close if close is not None else _field_frame(),
            "volume": volume if volume is not None else _field_frame(),
        },
        policy=policy or CoverageAuditPolicy(
            minimum_coverage_ratio=1.0,
            max_backfill_tasks=10,
            max_symbols_per_task=100,
        ),
    )


def test_audit_derives_an_old_date_gap_without_a_caller_specifying_it() -> None:
    missing_date = SESSIONS[1]

    audit = _audit(close=_field_frame(missing={SYMBOLS[0]: [missing_date]}))

    assert audit.complete is False
    assert audit.coverage_ratio == 19 / 20
    assert audit.gap_count == 1
    assert audit.missing_dates == (missing_date,)
    assert audit.missing_symbols == (SYMBOLS[0],)
    assert audit.missing_fields == ("close",)


def test_audit_generates_a_backfill_task_from_the_derived_gap() -> None:
    missing_date = SESSIONS[1]

    audit = _audit(close=_field_frame(missing={SYMBOLS[0]: [missing_date]}))

    assert len(audit.backfill_plan.tasks) == 1
    task = audit.backfill_plan.tasks[0]
    assert task.start == missing_date
    assert task.end == missing_date
    assert task.symbols == (SYMBOLS[0],)
    assert task.fields == ("close",)
    assert task.reason == "coverage_gap"


def test_audit_combines_adjacent_missing_sessions_into_one_resumable_task() -> None:
    missing_dates = [SESSIONS[1], SESSIONS[2]]

    audit = _audit(
        volume=_field_frame(missing={SYMBOLS[1]: missing_dates}),
    )

    assert len(audit.backfill_plan.tasks) == 1
    task = audit.backfill_plan.tasks[0]
    assert (task.start, task.end) == (missing_dates[0], missing_dates[-1])
    assert task.symbols == (SYMBOLS[1],)
    assert task.fields == ("volume",)
    assert task.checkpoint_key


def test_audit_keeps_daily_production_ready_when_only_backfill_is_pending() -> None:
    audit = _audit(close=_field_frame(missing={SYMBOLS[0]: [SESSIONS[0]]}))

    assert audit.backfill_plan.tasks
    assert audit.daily_production_ready is True


def test_audit_applies_task_and_symbol_limits_without_losing_remaining_gaps() -> None:
    policy = CoverageAuditPolicy(
        minimum_coverage_ratio=1.0,
        max_backfill_tasks=1,
        max_symbols_per_task=1,
    )
    audit = _audit(
        close=_field_frame(
            missing={
                SYMBOLS[0]: [SESSIONS[0]],
                SYMBOLS[1]: [SESSIONS[-1]],
            }
        ),
        policy=policy,
    )

    assert len(audit.backfill_plan.tasks) == 1
    assert audit.backfill_plan.deferred_gap_count == 1
    assert audit.gap_count == 2


def test_audit_marks_a_complete_version_ready_without_backfill_work() -> None:
    audit = _audit()

    assert audit.complete is True
    assert audit.coverage_ratio == 1.0
    assert audit.gap_count == 0
    assert audit.backfill_plan.tasks == ()


def test_persisted_audit_round_trips_the_plan_for_a_later_backfill_worker(
    tmp_path,
) -> None:
    audit = _audit(
        close=_field_frame(missing={SYMBOLS[0]: [SESSIONS[1]]}),
    )

    path = persist_coverage_audit(audit, artifact_dir=tmp_path)
    restored = load_coverage_audit(path)

    assert restored.market == "CN"
    assert restored.published_version == "20260109"
    assert restored.backfill_plan.plan_id == audit.backfill_plan.plan_id
    assert restored.backfill_plan.tasks == audit.backfill_plan.tasks
