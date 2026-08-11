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

# Same-origin deployment (quantmine-web): frontend and API are same-origin, CORS is not
# involved; these defaults only serve the dev-mode direct-to-Vite case. Override with
# QUANT_CORS_ORIGINS (comma separated) for separate domains.
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
        description="Quant factor research platform API; see docs/api/openapi.yaml for endpoints",
    )

    # Order:
    #   1. trace-id middleware — ensures request.state has trace_id (error handling depends on it)
    #   2. CORS — preflight and real requests both carry trace-id
    #   3. exception handlers — error responses also carry trace-id
    #   4. business routes
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
