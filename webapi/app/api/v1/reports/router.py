"""Report history endpoints: paginated list."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.engine import Engine

from ....dependencies import get_request_engine
from .db import fetch_report_history

router = APIRouter()


@router.get("/reports")
def get_reports(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100, alias="pageSize"),
    engine: Engine = Depends(get_request_engine),
):
    items, total = fetch_report_history(engine, page=page, page_size=page_size)
    return {
        "items": [
            {
                "reportId": f"report-{row['id']}",
                "runId": row["run_id"],
                "testId": row["test_id"],
                "lang": row["lang"],
                "ai": row["ai"],
                "createdAt": str(row["created_at"]),
                "status": row["status"],
            }
            for row in items
        ],
        "total": total,
        "page": page,
        "pageSize": page_size,
    }