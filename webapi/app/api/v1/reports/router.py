"""Report history endpoints: paginated list."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.engine import Engine

from ....dependencies import get_request_engine
from .db import fetch_report_history, fetch_report_history_item
from ....reports.artifacts import resolve_report_artifact

router = APIRouter()


@router.get("/reports")
def get_reports(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100, alias="pageSize"),
    run_id: int | None = Query(None, ge=1, alias="runId"),
    engine: Engine = Depends(get_request_engine),
):
    items, total = fetch_report_history(
        engine,
        page=page,
        page_size=page_size,
        run_id=run_id,
    )
    return {
        "items": [
            {
                "reportId": f"report-{row['id']}",
                "runId": row["run_id"],
                "testId": row["test_id"],
                "lang": row["lang"],
                "ai": row["ai"],
                "artifactType": row["artifact_type"],
                "artifactAvailable": resolve_report_artifact(row["artifact_path"]) is not None,
                "artifactSize": row["artifact_size"],
                "dataAvailable": bool(row["data_available"]),
                "createdAt": str(row["created_at"]),
                "status": row["status"],
            }
            for row in items
        ],
        "total": total,
        "page": page,
        "pageSize": page_size,
    }


@router.get("/reports/{report_id}/file")
def get_report_file(
    report_id: str,
    inline: bool = Query(False),
    engine: Engine = Depends(get_request_engine),
) -> Response:
    raw_id = report_id.removeprefix("report-")
    if not raw_id.isdigit():
        raise HTTPException(status_code=404, detail="Report not found")
    row = fetch_report_history_item(engine, int(raw_id))
    if row is None:
        raise HTTPException(status_code=404, detail="Report not found")
    path = resolve_report_artifact(row.get("artifact_path"))
    if path is None or row.get("status") != "ready":
        raise HTTPException(status_code=404, detail="Report artifact not available")

    artifact_type = row.get("artifact_type") or "pdf"
    media_type = (
        "application/pdf"
        if artifact_type == "pdf"
        else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    disposition = "inline" if inline and artifact_type == "pdf" else "attachment"
    filename = f"report_{row['test_id'] or row['run_id']}_{row['lang']}.{artifact_type}"
    return Response(
        content=path.read_bytes(),
        media_type=media_type,
        headers={"Content-Disposition": f'{disposition}; filename="{filename}"'},
    )
