"""数据速查查询层：白名单校验、筛选/排序/分页、结构化查询、只读 SQL。

设计约束：
- 资源名即表名，但只暴露 DATA_CATALOG 里声明的字段，其余列一律不返回；
- 筛选/排序字段必须先在 catalog 中声明为可筛/存在，否则 400；
- SQL 查询只允许单条 SELECT，且最多返回 MAX_SQL_ROWS 行。
"""

from __future__ import annotations

import json
import re
from datetime import date
from typing import Any

from fastapi import HTTPException
from sqlalchemy import Date, MetaData, String, Table, cast, func, select, text
from sqlalchemy.engine import Engine

from .catalog import DATA_CATALOG

MAX_EXPORT_ROWS = 10_000
MAX_SQL_ROWS = 100

_SELECT_RE = re.compile(r"^\s*select\b", re.IGNORECASE)


def catalog_entry(resource: str) -> dict[str, Any]:
    """按资源名查白名单；不在名单内直接 404。"""
    for entry in DATA_CATALOG:
        if entry["resource"] == resource:
            return entry
    raise HTTPException(status_code=404, detail=f"Unknown data resource: {resource}")


def catalog_field(catalog: dict[str, Any], name: str) -> dict[str, Any]:
    """按字段名查 catalog 声明；未知字段 400。"""
    for field in catalog["fields"]:
        if field["name"] == name:
            return field
    raise HTTPException(status_code=400, detail=f"Unknown field: {name}")


def _typed_value(field: dict[str, Any], value: Any) -> Any:
    """把字符串筛选值按字段类型转成 Python 值，便于 SQLAlchemy 比较。"""
    if field["type"] == "number":
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return value
        try:
            return float(value)
        except (TypeError, ValueError) as error:
            raise HTTPException(
                status_code=400, detail=f"Invalid number for field {field['name']}: {value!r}"
            ) from error
    if field["type"] == "boolean":
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"true", "1", "yes"}:
                return True
            if normalized in {"false", "0", "no"}:
                return False
        raise HTTPException(
            status_code=400, detail=f"Invalid boolean for field {field['name']}: {value!r}"
        )
    if field["type"] == "date":
        if isinstance(value, date):
            return value
        try:
            return date.fromisoformat(str(value))
        except ValueError as error:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid date for field {field['name']}: {value!r}, expected YYYY-MM-DD",
            ) from error
    return str(value)


def _filter_clauses(
    table: Table,
    catalog: dict[str, Any],
    filters: dict[str, Any] | None,
) -> list:
    """把 {字段: 值|值列表} 转成 SQLAlchemy 条件；只允许 filterable 字段。"""
    clauses = []
    for name, raw in (filters or {}).items():
        field = catalog_field(catalog, name)
        if not field["filterable"]:
            raise HTTPException(status_code=400, detail=f"Field is not filterable: {name}")

        values = raw if isinstance(raw, list) else [raw]
        typed = [_typed_value(field, value) for value in values if value != ""]
        if not typed:
            continue

        column = table.c[name]
        if field["type"] == "date":
            column = cast(column, Date)
        if len(typed) == 1:
            clauses.append(column == typed[0])
        else:
            clauses.append(column.in_(typed))
    return clauses


def _order_by(
    table: Table,
    catalog: dict[str, Any],
    sort_by: str | None,
    sort_dir: str | None,
):
    if sort_by is None:
        sort_by = catalog["fields"][0]["name"]
    else:
        catalog_field(catalog, sort_by)
    column = table.c[sort_by]
    return column.desc() if sort_dir == "desc" else column.asc()


def fetch_resource_page(
    engine: Engine,
    *,
    resource: str,
    filters: dict[str, Any] | None,
    sort_by: str | None,
    sort_dir: str | None,
    page: int,
    page_size: int,
) -> tuple[list[dict], int]:
    """白名单资源的筛选 + 排序 + 分页，返回 (items, total)。"""
    catalog = catalog_entry(resource)
    table = Table(resource, MetaData(), autoload_with=engine)
    columns = [table.c[field["name"]] for field in catalog["fields"]]
    clauses = _filter_clauses(table, catalog, filters)

    statement = (
        select(*columns)
        .where(*clauses)
        .order_by(_order_by(table, catalog, sort_by, sort_dir))
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    count_statement = select(func.count()).select_from(table).where(*clauses)

    with engine.connect() as connection:
        rows = connection.execute(statement).mappings().all()
        total = connection.execute(count_statement).scalar_one()
    return [dict(row) for row in rows], total


def fetch_resource_rows(
    engine: Engine,
    *,
    resource: str,
    filters: dict[str, Any] | None,
    sort_by: str | None,
    sort_dir: str | None,
    limit: int,
) -> list[dict]:
    """不分页取前 limit 行，CSV 导出用。"""
    catalog = catalog_entry(resource)
    table = Table(resource, MetaData(), autoload_with=engine)
    columns = [table.c[field["name"]] for field in catalog["fields"]]
    clauses = _filter_clauses(table, catalog, filters)

    statement = (
        select(*columns)
        .where(*clauses)
        .order_by(_order_by(table, catalog, sort_by, sort_dir))
        .limit(limit)
    )
    with engine.connect() as connection:
        rows = connection.execute(statement).mappings().all()
    return [dict(row) for row in rows]


def run_structured_query(
    engine: Engine,
    *,
    resource: str,
    fields: list[str],
    conditions: list[dict[str, Any]],
    limit: int,
) -> dict[str, Any]:
    """结构化查询：选字段 + eq/ne/gt/lt/contains 条件，返回 {columns, rows}。"""
    catalog = catalog_entry(resource)
    table = Table(resource, MetaData(), autoload_with=engine)

    selected = fields or [field["name"] for field in catalog["fields"]]
    for name in selected:
        catalog_field(catalog, name)

    clauses = []
    for condition in conditions:
        field = catalog_field(catalog, condition["field"])
        column = table.c[condition["field"]]
        value = _typed_value(field, condition["value"])
        op = condition["op"]

        if field["type"] == "date":
            column = cast(column, Date)
        if op == "eq":
            clauses.append(column == value)
        elif op == "ne":
            clauses.append(column != value)
        elif op == "gt":
            clauses.append(column > value)
        elif op == "lt":
            clauses.append(column < value)
        elif op == "contains":
            clauses.append(cast(column, String).ilike(f"%{value}%"))
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported operator: {op}")

    statement = (
        select(*[table.c[name] for name in selected])
        .where(*clauses)
        .limit(limit)
    )
    with engine.connect() as connection:
        rows = connection.execute(statement).mappings().all()
    return {"columns": selected, "rows": [dict(row) for row in rows]}


def run_sql_query(engine: Engine, sql: str) -> dict[str, Any]:
    """只读 SQL：仅允许单条 SELECT，最多返回 MAX_SQL_ROWS 行。"""
    stripped = sql.strip().rstrip(";").strip()
    if not _SELECT_RE.match(stripped):
        raise HTTPException(status_code=403, detail="Only SELECT queries are allowed")
    if ";" in stripped:
        raise HTTPException(status_code=403, detail="Multiple statements are not allowed")

    with engine.connect() as connection:
        result = connection.execute(text(stripped))
        columns = list(result.keys())
        rows = [dict(row) for row in result.mappings().fetchmany(MAX_SQL_ROWS + 1)]
    return {"columns": columns, "rows": rows[:MAX_SQL_ROWS]}


def parse_filters(raw: str | None) -> dict[str, Any]:
    """解析前端传来的 JSON 筛选串；非法 JSON 给 400。"""
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as error:
        raise HTTPException(status_code=400, detail="filters must be valid JSON") from error
    if not isinstance(parsed, dict):
        raise HTTPException(status_code=400, detail="filters must be a JSON object")
    return parsed
