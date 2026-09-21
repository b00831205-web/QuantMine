"""Research readiness gate for immutable market-data base/revision versions.

Implements ``NEXT_PHASE_ENGINEERING_DESIGN_v2026.09.21-r1.md`` section 5:

* research, IC, and backtest only consume the latest version through the run
  date, resolved by ``(trading date, revision)``;
* when the base version is incomplete and its same-day revision has not been
  published, downstream stages must be skipped rather than fed partial data;
* the resolved version exposes its coverage ratio, gap count, and revision so
  an API or front end can display them without re-deriving the version name.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

import pandas as pd

from .coverage_audit import (
    CoverageAudit,
    load_coverage_audit,
)
from .market_data_publication import (
    load_latest_market_data_before,
    resolve_latest_market_data_version,
)


_VERSION = re.compile(r"(?P<date>\d{8})(?:-r(?P<revision>[1-9]\d*))?\Z")

READY = "ready"
NO_VERSION = "no_published_version"
AUDIT_MISSING = "coverage_audit_missing"
AUDIT_INVALID = "coverage_audit_invalid"
COVERAGE_INCOMPLETE = "coverage_incomplete"
COVERAGE_PENDING = "coverage_pending"


@dataclass(frozen=True)
class MarketDataReadiness:
    """Resolved market-data version and its fitness for a research run."""

    market: str
    dataset_id: str
    as_of_date: pd.Timestamp
    resolved_version: str | None
    base_version: str | None
    revision: int
    ready: bool
    reason: str
    coverage_ratio: float | None = None
    gap_count: int | None = None
    deferred_gap_count: int | None = None
    audit_path: Path | None = None

    def to_mapping(self) -> dict[str, object]:
        """Return a JSON-safe summary for a pipeline stage result."""

        return {
            "market": self.market,
            "dataset_id": self.dataset_id,
            "as_of_date": self.as_of_date.date().isoformat(),
            "market_data_version": self.resolved_version,
            "base_market_data_version": self.base_version,
            "revision": self.revision,
            "research_ready": self.ready,
            "reason": self.reason,
            "coverage_ratio": self.coverage_ratio,
            "gap_count": self.gap_count,
            "deferred_gap_count": self.deferred_gap_count,
            "coverage_audit_path": (
                None if self.audit_path is None else str(self.audit_path)
            ),
        }


def readiness_audit_path(
    root: Path | str,
    *,
    market: str,
    version: str,
) -> Path:
    """Return the coverage-audit file belonging to one market-data version."""

    for label, value in (("market", market), ("version", version)):
        if not isinstance(value, str) or not value or value.strip() != value:
            raise ValueError(f"{label} must be a non-empty trimmed string")
        if "/" in value or "\\" in value or value in {".", ".."}:
            raise ValueError(f"{label} must be a safe path segment")

    return (
        Path(root)
        / f"market={market}"
        / f"version={version}"
        / "coverage_audit.json"
    )


def split_market_data_version(version: str) -> tuple[str, int]:
    """Split ``YYYYMMDD`` or ``YYYYMMDD-rN`` into its date and revision."""

    match = _VERSION.fullmatch(version or "")
    if match is None:
        raise ValueError(
            "market-data version must use YYYYMMDD or YYYYMMDD-rN"
        )

    return match.group("date"), int(match.group("revision") or 0)


def assess_market_data_readiness(
    root: Path | str,
    *,
    dataset_id: str,
    market: str,
    as_of_date: pd.Timestamp | str,
    coverage_root: Path | str | None = None,
) -> MarketDataReadiness:
    """Decide whether research may consume the latest version through a date.

    ``root`` is the market-data lake root holding ``<dataset_id>/versions/``.
    ``coverage_root`` is the directory holding ``market=<M>/version=<V>/``
    coverage audits and defaults to the lake root.
    """

    date = pd.Timestamp(as_of_date)
    if pd.isna(date):
        raise ValueError("as_of_date must not be NaT")
    date = date.normalize()

    if not market or market.strip() != market:
        raise ValueError("market must be a non-empty trimmed string")

    lake_root = Path(root)
    audit_root = (
        lake_root if coverage_root is None else Path(coverage_root)
    )

    resolved = resolve_latest_market_data_version(
        lake_root,
        dataset_id=dataset_id,
        as_of_date=date,
    )

    if resolved is None:
        return MarketDataReadiness(
            market=market,
            dataset_id=dataset_id,
            as_of_date=date,
            resolved_version=None,
            base_version=None,
            revision=0,
            ready=False,
            reason=NO_VERSION,
        )

    base_version, revision = split_market_data_version(resolved)
    audit_path = readiness_audit_path(
        audit_root,
        market=market,
        version=resolved,
    )

    loaded = load_latest_market_data_before(
        lake_root,
        dataset_id=dataset_id,
        as_of_date=date + pd.Timedelta(days=1),
    )
    coverage_complete: bool | None = None
    if loaded is not None:
        coverage_complete = loaded[0].coverage_complete

    audit: CoverageAudit | None = None
    invalid_reason: str | None = None
    if audit_path.is_file():
        try:
            audit = load_coverage_audit(audit_path)
        except ValueError:
            invalid_reason = AUDIT_INVALID

    common = {
        "market": market,
        "dataset_id": dataset_id,
        "as_of_date": date,
        "resolved_version": resolved,
        "base_version": base_version,
        "revision": revision,
        "audit_path": audit_path,
    }

    if coverage_complete is False:
        # The publication itself declares that a repair revision is pending.
        return MarketDataReadiness(
            **common,
            ready=False,
            reason=COVERAGE_PENDING,
            coverage_ratio=None if audit is None else audit.coverage_ratio,
            gap_count=None if audit is None else audit.gap_count,
            deferred_gap_count=(
                None if audit is None else audit.backfill_plan.deferred_gap_count
            ),
        )

    if invalid_reason is not None:
        return MarketDataReadiness(
            **common,
            ready=False,
            reason=invalid_reason,
        )

    if audit is None:
        return MarketDataReadiness(
            **common,
            ready=False,
            reason=AUDIT_MISSING,
        )

    if not audit.complete:
        return MarketDataReadiness(
            **common,
            ready=False,
            reason=COVERAGE_INCOMPLETE,
            coverage_ratio=audit.coverage_ratio,
            gap_count=audit.gap_count,
            deferred_gap_count=audit.backfill_plan.deferred_gap_count,
        )

    return MarketDataReadiness(
        **common,
        ready=True,
        reason=READY,
        coverage_ratio=audit.coverage_ratio,
        gap_count=audit.gap_count,
        deferred_gap_count=audit.backfill_plan.deferred_gap_count,
    )
