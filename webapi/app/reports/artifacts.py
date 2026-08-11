"""Immutable files owned by report-history records."""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
REPORT_DIR = REPO_ROOT / "data" / "reports"
SUPPORTED_ARTIFACT_TYPES = {"pdf", "xlsx"}


def save_report_artifact(
    content: bytes,
    report_id: int,
    artifact_type: str,
) -> tuple[str, int]:
    if artifact_type not in SUPPORTED_ARTIFACT_TYPES:
        raise ValueError(f"unsupported report artifact type: {artifact_type}")
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORT_DIR / f"report-history-{report_id}.{artifact_type}"
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(content)
    temporary.replace(path)
    return path.relative_to(REPO_ROOT).as_posix(), len(content)


def resolve_report_artifact(relative_path: str | None) -> Path | None:
    if not relative_path:
        return None
    report_root = REPORT_DIR.resolve()
    candidate = (REPO_ROOT / relative_path).resolve()
    if not candidate.is_relative_to(report_root) or not candidate.is_file():
        return None
    return candidate
