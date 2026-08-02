"""API 路由聚合（唯一来源）。

新增业务域时：在 `app/api/v1/<domain>/` 下新增模块并暴露 `router`，
然后在这里 `include_router` 即可。
"""

from __future__ import annotations

from fastapi import APIRouter

from .v1.health import router as health_router
from .v1.market.series import router as market_series_router
from .v1.research.results import router as research_results_router
from .v1.research.backtest_series import router as backtest_series_router
from .v1.research.ic_series import router as ic_series_router

api_router = APIRouter()
api_router.include_router(health_router, tags=["health"])
api_router.include_router(market_series_router, tags=["market"])
api_router.include_router(research_results_router, tags=["research"])
api_router.include_router(backtest_series_router, tags=['backtest'])
api_router.include_router(ic_series_router, tags =['research'])
