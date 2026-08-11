from __future__ import annotations

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse

from ...errors import TRACE_ID_HEADER

router = APIRouter()


@router.get("/health", summary="Health check")
async def health(request: Request) -> Response:
    """Health check endpoint.

    Explicitly returns a JSON response with an `x-trace-id` header; the middleware
    overwrites it again for consistency.

    This is a shallow probe: it only means the process is alive, not that the DB or
    Airflow are reachable; returning ok does not imply dependencies are available.
    """
    payload = {"status": "ok"}
    trace_id = getattr(request.state, "trace_id", None) or ""
    return JSONResponse(content=payload, headers={TRACE_ID_HEADER: trace_id} if trace_id else None)
