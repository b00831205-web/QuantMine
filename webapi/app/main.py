"""FastAPI app factory."""

from __future__ import annotations
from pathlib import Path
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT/'.env')

from fastapi import FastAPI, HTTPException
from fastapi.middleware .cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .api import api_router
from .errors import install_exception_handlers, install_trace_id_middleware



def create_app() -> FastAPI:
    app = FastAPI(
        title="QUANTMINE Web API",
        version="0.0.0",
        description="阶段 0 最小壳；具体端点见 docs/api/openapi.yaml",
    )

    # 顺序：
    #   1. trace-id 中间件——确保 request.state 有 trace_id（错误处理依赖它）
    #   2. CORS——preflight 与真实请求均需带 trace-id
    #   3. 异常处理器——错误响应也带 trace-id
    #   4. 业务路由
    install_trace_id_middleware(app)

    # 开发态允许 Vite dev server 5173；阶段 8 收紧
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
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
            if full_path.startswith('api/'):
                raise HTTPException(status_code=404)
            candidate = static_dir / full_path
            if candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(index_file)
    return app


app = create_app()
