"""Unified error responses and trace-id middleware.

Design:
- TraceIdMiddleware generates (or reuses upstream `x-trace-id`) at request entry and writes
  it to `request.state.trace_id`, then calls `call_next`.
- Success path: append `x-trace-id` to the `Response` header.
- Error path: exception handlers read directly from `request.state.trace_id` so it always
  matches the response header.

`install_*` functions are invoked in order by `create_app`:
    1. install_trace_id_middleware  (first; ensures request.state has trace_id)
    2. add CORS                     (then; CORS preflight also carries trace-id)
    3. install_exception_handlers   (last; unified error format)
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import FastAPI, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from .schemas import ApiError, FieldError

logger = logging.getLogger("quantmine.webapi")

TRACE_ID_HEADER = "x-trace-id"


def _resolve_trace_id(request: Request) -> str:
    """Read from request.state; fall back to a generated value if missing (should not happen)."""
    existing = getattr(request.state, "trace_id", None)
    if isinstance(existing, str) and existing:
        return existing
    incoming = request.headers.get(TRACE_ID_HEADER)
    return incoming or uuid.uuid4().hex


def _error_response(
    *,
    status_code: int,
    code: str,
    title: str,
    detail: str | None = None,
    trace_id: str,
    field_errors: list[FieldError] | None = None,
) -> JSONResponse:
    payload = ApiError(
        code=code,  # type: ignore[arg-type]
        title=title,
        detail=detail,
        traceId=trace_id,
        status=status_code,
        fieldErrors=field_errors,
    )
    return JSONResponse(
        status_code=status_code,
        content=payload.model_dump(by_alias=True),
        headers={TRACE_ID_HEADER: trace_id},
    )


class TraceIdMiddleware(BaseHTTPMiddleware):
    """Generate/reuse a trace-id per request and write it into successful response headers."""

    def __init__(self, app: ASGIApp, header_name: str = TRACE_ID_HEADER) -> None:
        super().__init__(app)
        self.header_name = header_name

    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        incoming = request.headers.get(self.header_name)
        request.state.trace_id = incoming or uuid.uuid4().hex
        response: Response = await call_next(request)
        # Error responses already carry the header via _error_response; overwriting again is harmless
        response.headers[self.header_name] = request.state.trace_id
        return response


def install_trace_id_middleware(app: FastAPI) -> None:
    """Register the global trace-id middleware; must run before CORS / exception handlers."""
    app.add_middleware(TraceIdMiddleware)


def install_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def _validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        trace_id = _resolve_trace_id(request)
        field_errors = [
            FieldError(field=".".join(str(p) for p in err["loc"]), message=err["msg"]) for err in exc.errors()
        ]
        return _error_response(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code="VALIDATION_FAILED",
            title="Validation failed",
            detail="Request did not pass schema validation",
            trace_id=trace_id,
            field_errors=field_errors,
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        trace_id = _resolve_trace_id(request)
        code_map: dict[int, str] = {
            400: "VALIDATION_FAILED",
            401: "UNAUTHENTICATED",
            403: "FORBIDDEN",
            404: "NOT_FOUND",
            409: "CONFLICT",
            422: 'VALIDATION_FAILED',
            429: "RATE_LIMITED",
            502: 'UPSTREAM_FAILURE'
        }
        title_map: dict[int, str] = {
            400: "Bad request",
            401: "Not authenticated",
            403: "Forbidden",
            404: "Not found",
            409: "Conflict",
            422: "Validation failed",
            429: "Too many requests",
            502: "Upstream service error"
        }
        code = code_map.get(exc.status_code, "INTERNAL_ERROR")
        title = title_map.get(exc.status_code, "Internal server error")
        return _error_response(
            status_code=exc.status_code,
            code=code,
            title=title,
            detail=str(exc.detail) if exc.detail else None,
            trace_id=trace_id,
        )

    @app.exception_handler(Exception)
    async def _unhandled_handler(request: Request, exc: Exception) -> JSONResponse:
        trace_id = _resolve_trace_id(request)
        logger.exception("[%s] unhandled error", trace_id, exc_info=exc)
        return _error_response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="INTERNAL_ERROR",
            title="Internal server error",
            detail="Please retry later; contact the administrator if it persists",
            trace_id=trace_id,
        )


def api_error_response(
    *,
    status_code: int,
    code: str,
    title: str,
    detail: str | None,
    trace_id: str,
    field_errors: list[FieldError] | None = None,
) -> JSONResponse:
    """Convenience helper for business code to build a unified error response manually.

    Endpoints normally raise HTTPException (the handler normalizes the format); use this
    only when a custom code or field_errors is needed.
    """
    return _error_response(
        status_code=status_code,
        code=code,
        title=title,
        detail=detail,
        trace_id=trace_id,
        field_errors=field_errors,
    )
