"""Pydantic schemas mirroring docs/api/openapi.yaml.

契约的唯一来源：端点的请求/响应模型都在这里定义，改动需同步 openapi.yaml。
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints


# —— Errors ——


ErrorCode = Literal[
    "UNAUTHENTICATED",
    "FORBIDDEN",
    "NOT_FOUND",
    "VALIDATION_FAILED",
    "CONFLICT",
    "RATE_LIMITED",
    "UPSTREAM_FAILURE",
    "TASK_RUNNING",
    "INTERNAL_ERROR",
]


class FieldError(BaseModel):
    field: str
    message: str


class ApiError(BaseModel):
    code: ErrorCode
    title: str
    detail: str | None = None
    trace_id: str | None = Field(default=None, alias="traceId")
    status: int
    field_errors: list[FieldError] | None = Field(default=None, alias="fieldErrors")

    model_config = {"populate_by_name": True}


# —— Common ——


SymbolStr = Annotated[str, StringConstraints(min_length=1, max_length=16, pattern=r"^[A-Z0-9.\-]+$")]


# —— Market ——


class Ticker(BaseModel):
    symbol: str
    name: str
    exchange: Literal["NASDAQ", "NYSE", "SP500"]
    sector: str | None = None
    in_sp500: bool = Field(alias="inSp500")

    model_config = {"populate_by_name": True}


class SeriesPoint(BaseModel):
    date: date
    value: float


class SeriesEntry(BaseModel):
    symbol: str
    points: list[SeriesPoint]


class SeriesResponse(BaseModel):
    base_date: date = Field(alias="baseDate")
    series: list[SeriesEntry]

    model_config = {"populate_by_name": True}

class MarketLatestDateResponse(BaseModel):
    latest_trade_date: date = Field(alias = 'latestTradeDate')
    model_config = {'populate_by_name' : True}


class MarketOverviewResponse(BaseModel):
    latest_trade_date: date = Field(alias="latestTradeDate")
    advancers: int
    decliners: int
    total: int
    breadth: float

    model_config = {"populate_by_name": True}


# --- Research ---

class ResearchRunOption(BaseModel):
    run_id: int = Field(alias="runId")
    created_at: datetime = Field(alias="createdAt")

    model_config = {"populate_by_name": True}


class ResearchFilterOptions(BaseModel):
    default_run_id: int | None = Field(alias="defaultRunId")
    runs: list[ResearchRunOption]
    variants: list[str]
    test_ids: list[str] = Field(alias="testIds")
    sample_scopes: list[str] = Field(alias="sampleScopes")

    model_config = {"populate_by_name": True}

class FactorResultRow(BaseModel):
    factor_name: str = Field(alias= 'factorName')
    period: int
    variant_name: str = Field(alias ='variantName')
    test_id: str = Field(alias ='testId')
    sample_scope: str = Field(alias ='sampleScope')
    ic_mean: float | None = Field(alias ='icMean')
    ic_std: float | None = Field(alias ='icStd')
    ir: float | None
    n: int | None
    t_stat: float | None = Field(alias ='tStat')
    p_value: float | None = Field(alias='pValue')
    significant: bool | None
    bh_significant:bool | None = Field(alias='bhSignificant')

    model_config = {'populate_by_name' : True}

class FactorResultsResponse(BaseModel):
    items: list[FactorResultRow]
    total: int
    page : int
    page_size: int = Field(alias='pageSize')

    model_config = {'populate_by_name': True}

class BacktestSummaryRow(BaseModel):
    variant_name: str = Field(alias = 'variantName')
    backtest_id: str = Field(alias = 'backtestId')
    test_id : str = Field(alias = 'testId')
    factor_name : str = Field(alias = 'factorName')
    period: int
    quantile_yearly_returns : dict[str,float] = Field(alias = 'quantileYearlyReturns')
    sharpe: float | None
    max_drawdown: float| None = Field(alias = 'maxDrawdown')
    win_rate : float | None = Field(alias= 'winRate')

    model_config = {'populate_by_name': True}

class BacktestSummariesResponse(BaseModel):
    items: list[BacktestSummaryRow]
    total: int
    page: int
    page_size: int = Field(alias ='pageSize')

    model_config = {'populate_by_name': True}

class BacktestSeriesResponse(BaseModel):
    base_date: date|None = Field(alias='baseDate')
    series : list[SeriesEntry]
    model_config = {'populate_by_name': True}

class IcSeriesResponse(BaseModel):
    base_date: date| None = Field(alias = 'baseDate')
    series: list[SeriesEntry]

    model_config = {'populate_by_name': True}
    
