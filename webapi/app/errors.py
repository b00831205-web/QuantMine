"""统一错误响应、trace-id 中间件。

设计：
- TraceIdMiddleware 在请求入口生成（或沿用上游 `x-trace-id`）并写入
  `request.state.trace_id`，再调用 `call_next`。
- 成功路径：在 `Response` header 上追加 `x-trace-id`。
- 错误路径：异常处理器直接从 `request.state.trace_id` 读取，确保与
  响应 header 完全一致。

`install_*` 函数在 `create_app` 中按正确顺序调用：
    1. install_trace_id_middleware  (最先，确保 request.state 有 trace_id)
    2. add CORS                     (随后，CORS preflight 也带 trace-id)
    3. install_exception_handlers   (最后，统一错误格式)
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
    """从 request.state 读；如缺失（理论上不应发生），兜底生成。"""
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
    """为每个请求生成/沿用 trace-id，并写入成功响应的 header。"""

    def __init__(self, app: ASGIApp, header_name: str = TRACE_ID_HEADER) -> None:
        super().__init__(app)
        self.header_name = header_name

    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        incoming = request.headers.get(self.header_name)
        request.state.trace_id = incoming or uuid.uuid4().hex
        response: Response = await call_next(request)
        # 错误响应已由 _error_response 自带 header；这里再覆盖一次也无副作用
        response.headers[self.header_name] = request.state.trace_id
        return response


def install_trace_id_middleware(app: FastAPI) -> None:
    """注册全局 trace-id 中间件；必须在 CORS / exception handler 之前。"""
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
            title="参数校验失败",
            detail="请求参数未通过 schema 校验",
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
            400: "请求参数错误",
            401: "未登录",
            403: "没有权限",
            404: "资源不存在",
            409: "状态冲突",
            422: '参数校验失败',
            429: "请求过于频繁",
            502: '上游服务错误'
        }
        code = code_map.get(exc.status_code, "INTERNAL_ERROR")
        title = title_map.get(exc.status_code, "服务器内部错误")
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
            title="服务器内部错误",
            detail="请稍后重试；如持续发生请联系管理员",
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
    """供业务代码手动抛出统一错误的便捷方法（阶段 0 暂不强制使用）。"""
    return _error_response(
        status_code=status_code,
        code=code,
        title=title,
        detail=detail,
        trace_id=trace_id,
        field_errors=field_errors,
    )
