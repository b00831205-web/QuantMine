from __future__ import annotations

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse

from ...errors import TRACE_ID_HEADER

router = APIRouter()


@router.get("/health", summary="健康检查")
async def health(request: Request) -> Response:
    """健康检查端点。

    显式返回带 `x-trace-id` header 的 JSON 响应；中间件会再覆盖一次以保证
    一致性。

    这是浅层探针：只表示进程存活，不探测 DB 与 Airflow 连通性，因此它返回
    ok 不代表依赖可用。
    """
    payload = {"status": "ok"}
    trace_id = getattr(request.state, "trace_id", None) or ""
    return JSONResponse(content=payload, headers={TRACE_ID_HEADER: trace_id} if trace_id else None)
