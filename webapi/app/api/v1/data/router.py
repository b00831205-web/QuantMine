"""Data explorer endpoints: whitelist browsing, CSV export, structured queries, read-only SQL."""

from __future__ import annotations

import csv
import io
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy.engine import Engine

from ....dependencies import get_request_engine
from .catalog import DATA_CATALOG
from .db import (
    MAX_EXPORT_ROWS,
    MAX_SQL_ROWS,
    fetch_resource_page,
    fetch_resource_rows,
    parse_filters,
    run_sql_query,
    run_structured_query,
)

router = APIRouter()


@router.get("/data/catalog")
def get_data_catalog():
    """Whitelist resources and field descriptions (data source for dynamic columns/filters)."""
    return DATA_CATALOG


class StructuredConditionBody(BaseModel):
    field: str
    op: Literal["eq", "ne", "gt", "lt", "contains"]
    value: str | int | float | bool


class StructuredQueryBody(BaseModel):
    resource: str
    fields: list[str] = Field(default_factory=list)
    conditions: list[StructuredConditionBody] = Field(default_factory=list)
    limit: int = Field(default=100, ge=1, le=1000)


class SqlQueryBody(BaseModel):
    sql: str = Field(min_length=1)


@router.get("/data/{resource}")
def get_resource_page(
    resource: str,
    filters: str | None = Query(default=None),
    sort_by: str | None = Query(default=None, alias="sortBy"),
    sort_dir: Literal["asc", "desc"] | None = Query(default=None, alias="sortDir"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200, alias="pageSize"),
    engine: Engine = Depends(get_request_engine),
):
    """Whitelist resource data: filters (JSON), sorting, pagination."""
    items, total = fetch_resource_page(
        engine,
        resource=resource,
        filters=parse_filters(filters),
        sort_by=sort_by,
        sort_dir=sort_dir,
        page=page,
        page_size=page_size,
    )
    return {"items": items, "total": total, "page": page, "pageSize": page_size}


@router.get("/data/{resource}/export")
def export_resource_csv(
    resource: str,
    filters: str | None = Query(default=None),
    sort_by: str | None = Query(default=None, alias="sortBy"),
    sort_dir: Literal["asc", "desc"] | None = Query(default=None, alias="sortDir"),
    engine: Engine = Depends(get_request_engine),
):
    """Export CSV for the current filters (at most MAX_EXPORT_ROWS rows)."""
    catalog = next((entry for entry in DATA_CATALOG if entry["resource"] == resource), None)
    if catalog is None:
        raise HTTPException(status_code=404, detail=f"Unknown data resource: {resource}")

    rows = fetch_resource_rows(
        engine,
        resource=resource,
        filters=parse_filters(filters),
        sort_by=sort_by,
        sort_dir=sort_dir,
        limit=MAX_EXPORT_ROWS,
    )
    field_names = [field["name"] for field in catalog["fields"]]

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(field_names)
    for row in rows:
        writer.writerow([row.get(name, "") for name in field_names])

    return Response(
        content=output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{resource}.csv"'},
    )


@router.post("/data/query/structured")
def post_structured_query(
    body: StructuredQueryBody,
    engine: Engine = Depends(get_request_engine),
):
    """Structured query: fields + conditions, returns {columns, rows}."""
    return run_structured_query(
        engine,
        resource=body.resource,
        fields=body.fields,
        conditions=[condition.model_dump() for condition in body.conditions],
        limit=body.limit,
    )


@router.post("/data/query/sql")
def post_sql_query(
    body: SqlQueryBody,
    engine: Engine = Depends(get_request_engine),
):
    """Read-only SQL query (SELECT only, at most MAX_SQL_ROWS rows)."""
    return run_sql_query(engine, body.sql)
