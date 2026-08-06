"""PDF research-report export endpoint.

``GET /api/v1/research/report.pdf`` assembles a run's IC / backtest / attribution
results into a localized PDF. Language: explicit ``lang`` query param wins, else
the request's ``Accept-Language`` header, else English. ``ai=true`` renders the
per-section AI-analysis blocks (filled once the AI module is wired; empty blocks
are omitted). The frontend download page calls this directly.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.engine import Engine

from ....dependencies import get_request_engine
from ....reports import assemble_context, html_to_pdf, render_html, resolve_lang
from .results import research_run_exists
from ..reports.db import insert_report_history

from ....reports.chart_data import build_report_charts

router = APIRouter()


@router.get("/research/report.pdf")
def get_research_report_pdf(
    run_id: int = Query(..., alias="runId"),
    test_id: str | None = Query(None, alias="testId"),
    lang: str | None = Query(None),
    ai: bool = Query(False),
    inline: bool = Query(False),
    accept_language: str | None = Header(None, alias="Accept-Language"),
    engine: Engine = Depends(get_request_engine),
) -> Response:
    if not research_run_exists(engine, run_id):
        raise HTTPException(status_code=404, detail="Research run not found")

    language = resolve_lang(lang, accept_language)
    context = assemble_context(
        engine, run_id=run_id, test_id=test_id, lang=language, include_ai=ai, charts = build_report_charts(engine, run_id, test_id)
    )
    html = render_html(context)

    try:
        pdf_bytes = html_to_pdf(html)
    except RuntimeError as error:  # WeasyPrint not installed in this environment
        raise HTTPException(status_code=503, detail=str(error)) from error

    filename = f"report_{test_id or run_id}_{language}.pdf"
    disposition = "inline" if inline else "attachment"
    insert_report_history(
        engine,
        run_id=run_id,
        test_id=test_id,
        lang=language,
        ai=ai,
    )

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'{disposition}; filename="{filename}"'},
    )
