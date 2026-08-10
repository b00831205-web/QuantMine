"""Excel report export endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.engine import Engine

from ....dependencies import get_request_engine
from ....reports import assemble_context, resolve_lang
from ....reports.excel import build_xlsx
from ..reports.db import insert_report_history
from .results import research_run_exists

router = APIRouter()


@router.get("/research/report.xlsx")
def get_research_report_xlsx(
    run_id: int = Query(..., alias="runId"),
    test_id: str | None = Query(None, alias="testId"),
    lang: str | None = Query(None),
    ai: bool = Query(False),
    engine: Engine = Depends(get_request_engine),
) -> Response:
    if not research_run_exists(engine, run_id):
        raise HTTPException(status_code=404, detail="Research run not found")

    language = resolve_lang(lang, None)
    context = assemble_context(
        engine,
        run_id=run_id,
        test_id=test_id,
        lang=language,
        include_ai=ai,
    )
    xlsx_bytes = build_xlsx(context)

    insert_report_history(
        engine,
        run_id=run_id,
        test_id=test_id,
        lang=language,
        ai=ai,
    )

    filename = f"report_{test_id or run_id}_{language}.xlsx"
    return Response(
        content=xlsx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )