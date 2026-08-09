"""API 路由聚合（唯一来源）。

新增业务域时：在 `app/api/v1/<domain>/` 下新增模块并暴露 `router`，
然后在这里 `include_router` 即可。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ..security import require_user
from .v1.health import router as health_router
from .v1.auth.router import router as auth_router
from .v1.market.series import router as market_series_router
from .v1.research.results import router as research_results_router
from .v1.research.backtest_series import router as backtest_series_router
from .v1.research.ic_series import router as ic_series_router
from .v1.research.report import router as report_router
from .v1.workflows.router import router as workflows_router
from .v1.rebalances.router import router as rebalances_router
from .v1.data.router import router as data_router
from .v1.reports.router import router as reports_router
from .v1.research.report_xlsx import router as report_xlsx_router
from .v1.ai.router import router as ai_router

api_router = APIRouter()

# 开放端点：健康检查 + 登录鉴权本身（否则没登录就永远登不进来）
api_router.include_router(health_router, tags=["health"])
api_router.include_router(auth_router, tags=["auth"])

# 受保护端点：统一挂 require_user 依赖，未登录/会话过期一律 401
protected = APIRouter(dependencies=[Depends(require_user)])
protected.include_router(market_series_router, tags=["market"])
protected.include_router(research_results_router, tags=["research"])
protected.include_router(backtest_series_router, tags=['backtest'])
protected.include_router(ic_series_router, tags =['research'])
protected.include_router(report_router, tags=['research'])
protected.include_router(workflows_router, tags=['workflows'])
protected.include_router(rebalances_router, tags=['rebalances'])
protected.include_router(data_router, tags=['data'])
protected.include_router(reports_router, tags=["reports"])
protected.include_router(report_xlsx_router, tags=["research"])
protected.include_router(ai_router, tags=["ai"])
api_router.include_router(protected)
