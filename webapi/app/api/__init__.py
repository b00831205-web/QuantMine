"""API route aggregation (single source of truth).

When adding a domain: create `app/api/v1/<domain>/` with a `router` exposed,
then `include_router` it here.
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
from .v1.services.router import router as services_router

api_router = APIRouter()

# Open endpoints: health check + auth itself (otherwise users could never log in)
api_router.include_router(health_router, tags=["health"])
api_router.include_router(auth_router, tags=["auth"])

# Protected endpoints: all share the require_user dependency; unauthenticated/expired -> 401
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
# 注意：目前 auth_users 没有角色列，protected 里所有路由权限相同 —— 任何登录用户
# 都能改开机自启。单用户自托管下可接受；将来加多用户时这组路由应先收紧。
protected.include_router(services_router, tags=["services"])
api_router.include_router(protected)
