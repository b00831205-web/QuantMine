"""Market-data readiness endpoint"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Query

from quantmine.storage.connections import ConnectionRegistry
from quantmine.workflows.market_data_readiness import assess_market_data_readiness

from ....schemas import MarketDataReadinessResponse

router = APIRouter()


def _market_roots() -> tuple[Path, Path]:
    connections = ConnectionRegistry.from_environment(
        ("cn_market_data", "cn_market_checkpoint")
    )
    return (
        connections.parquet_root("cn_market_data"),
        connections.parquet_root("cn_market_checkpoint")
    )

@router.get("/market/data-readiness", response_model=MarketDataReadinessResponse, summary="市场数据版本与研究就绪状态")
async def get_market_data_readiness(
        as_of_date: date | None = Query(default=None, alias="asOfDate")
) -> MarketDataReadinessResponse:
    resolved_as_of_date = as_of_date or datetime.now(ZoneInfo("Asia/Shanghai")).date()

    market_root, checkpoint_root = _market_roots()
    readiness = assess_market_data_readiness(
        market_root,
        dataset_id="cn_a_share_daily_bars",
        market="CN",
        as_of_date = resolved_as_of_date.isoformat(),
        coverage_root = checkpoint_root,
    )
    return MarketDataReadinessResponse.model_validate(readiness.to_mapping())

