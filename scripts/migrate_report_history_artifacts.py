"""Add immutable artifact metadata to the existing report_history table.

Run this once before deploying the report-history artifact code. It is
idempotent. Legacy rows cannot distinguish PDF from XLSX because the old table
did not record the format; when a matching PDF cache file exists, the row is
backfilled as a PDF preview.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from sqlalchemy import inspect, text

from quantmine.storage.database import get_engine


ROOT = Path(__file__).resolve().parent.parent
REPORT_DIR = ROOT / "data" / "reports"


def _legacy_pdf_path(run_id: int, test_id: str | None, lang: str, ai: bool) -> Path:
    raw = f"{run_id}|{test_id or 'all'}|{lang}|{ai}"
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]
    return REPORT_DIR / f"report_{digest}.pdf"


def main() -> None:
    engine = get_engine()
    with engine.begin() as connection:
        existing_columns = {
            column["name"] for column in inspect(connection).get_columns("report_history")
        }
        required_columns = {"artifact_type", "artifact_path", "artifact_size"}
        if not required_columns.issubset(existing_columns):
            connection.execute(
                text(
                    """
                    ALTER TABLE report_history
                        ADD COLUMN IF NOT EXISTS artifact_type VARCHAR(8)
                            NOT NULL DEFAULT 'pdf'
                            CHECK (artifact_type IN ('pdf', 'xlsx')),
                        ADD COLUMN IF NOT EXISTS artifact_path VARCHAR,
                        ADD COLUMN IF NOT EXISTS artifact_size BIGINT
                            CHECK (artifact_size IS NULL OR artifact_size >= 0)
                    """
                )
            )
        rows = connection.execute(
            text(
                """
                SELECT id, run_id, test_id, lang, ai
                FROM report_history
                WHERE artifact_path IS NULL
                ORDER BY id
                """
            )
        ).mappings()
        backfilled = 0
        for row in rows:
            path = _legacy_pdf_path(
                row["run_id"], row["test_id"], row["lang"], row["ai"]
            )
            if not path.is_file():
                continue
            relative_path = path.relative_to(ROOT).as_posix()
            connection.execute(
                text(
                    """
                    UPDATE report_history
                    SET artifact_type = 'pdf',
                        artifact_path = :artifact_path,
                        artifact_size = :artifact_size
                    WHERE id = :report_id
                    """
                ),
                {
                    "artifact_path": relative_path,
                    "artifact_size": path.stat().st_size,
                    "report_id": row["id"],
                },
            )
            backfilled += 1

        columns = connection.execute(
            text(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'report_history'
                  AND column_name IN ('artifact_type', 'artifact_path', 'artifact_size')
                ORDER BY column_name
                """
            )
        ).scalars().all()

    expected = ["artifact_path", "artifact_size", "artifact_type"]
    if list(columns) != expected:
        raise RuntimeError(f"report_history migration verification failed: {columns}")
    print(f"report_history migrated; legacy PDF rows backfilled: {backfilled}")


if __name__ == "__main__":
    main()
