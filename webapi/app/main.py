"""FastAPI app factory.

Serves the JSON API under ``/api/v1``. When a built frontend is present at
``app/static`` (produced by ``npm run build`` and copied in), the same app also
serves it, so ``quantmine-web`` can run the whole product in one process.
"""

from __future__ import annotations
import os
from pathlib import Path
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT/'.env')

# 同源部署（quantmine-web）下前端与 API 同源，CORS 不参与；这里的默认值只服务
# 开发态直连 Vite 的情况。部署到独立域名时用 QUANT_CORS_ORIGINS 覆盖（逗号分隔）。
DEFAULT_CORS_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]

from fastapi import FastAPI, HTTPException
from fastapi.middleware .cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .api import api_router
from .errors import install_exception_handlers, install_trace_id_middleware



def create_app() -> FastAPI:
    """Build the ASGI app: middleware, error handlers, API routes, frontend."""
    app = FastAPI(
        title="QUANTMINE Web API",
        version="0.0.0",
        description="因子研究平台 API；具体端点见 docs/api/openapi.yaml",
    )

    # 顺序：
    #   1. trace-id 中间件——确保 request.state 有 trace_id（错误处理依赖它）
    #   2. CORS——preflight 与真实请求均需带 trace-id
    #   3. 异常处理器——错误响应也带 trace-id
    #   4. 业务路由
    install_trace_id_middleware(app)

    configured_origins = os.environ.get("QUANT_CORS_ORIGINS", "")
    allow_origins = (
        [origin.strip() for origin in configured_origins.split(",") if origin.strip()]
        or DEFAULT_CORS_ORIGINS
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allow_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["x-trace-id"],
    )

    install_exception_handlers(app)
    app.include_router(api_router, prefix="/api/v1")
    static_dir = Path(__file__).parent/'static'
    if static_dir.is_dir():
        app.mount("/assets", StaticFiles(directory = static_dir/'assets'), name = 'asset')
        index_file = static_dir / 'index.html'
        @app.get("/{full_path:path}", include_in_schema=False)
        async def spa(full_path: str):
            """Serve built frontend files, falling back to the SPA shell.

            Registered after the API router so real endpoints win. Unmatched
            ``/api/`` paths still 404 instead of receiving the HTML shell,
            which would otherwise turn a wrong URL into a confusing parse
            error at the caller.
            """
            if full_path.startswith('api/'):
                raise HTTPException(status_code=404)
            candidate = static_dir / full_path
            if candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(index_file)
    return app


app = create_app()
