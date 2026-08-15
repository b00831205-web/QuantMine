"""Data explorer query layer: whitelist validation, filtering/sorting/pagination, structured queries, read-only SQL.

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
    """Look up a resource in the whitelist; 404 if not present."""
    for entry in DATA_CATALOG:
        if entry["resource"] == resource:
            return entry
    raise HTTPException(status_code=404, detail=f"Unknown data resource: {resource}")


def catalog_field(catalog: dict[str, Any], name: str) -> dict[str, Any]:
    """Look up a field in the catalog declaration; 400 for unknown fields."""
    for field in catalog["fields"]:
        if field["name"] == name:
            return field
    raise HTTPException(status_code=400, detail=f"Unknown field: {name}")


def _typed_value(field: dict[str, Any], value: Any) -> Any:
    """Convert a string filter value to a Python value by field type, for SQLAlchemy comparisons."""
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
    """Convert {field: value|list} into SQLAlchemy conditions; only filterable fields are allowed."""
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
    """Filter + sort + paginate a whitelist resource; returns (items, total)."""
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
    """Return up to limit rows without pagination (for CSV export)."""
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
    """Structured query: select fields + eq/ne/gt/lt/contains conditions; returns {columns, rows}."""
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


def _referenced_tables(engine: Engine, sql: str) -> set[str]:
    """Return base table names referenced by a SELECT, via EXPLAIN (Postgres parses it).

    EXPLAIN only plans the statement — it does not execute it — so this is a safe way
    to enumerate the tables a query touches. On parse/plan errors we return an empty
    set and let the real execution raise the actual error.
    """
    try:
        with engine.connect() as connection:
            raw = connection.execute(text(f"EXPLAIN (FORMAT JSON) {sql}")).scalar_one()
    except Exception:
        return set()
    plan = json.loads(raw) if isinstance(raw, str) else raw
    tables: set[str] = set()

    def walk(node: object) -> None:
        if isinstance(node, dict):
            relation = node.get("Relation Name")
            if relation:
                tables.add(relation)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(plan)
    return tables


def run_sql_query(
    engine: Engine,
    sql: str,
    allowed_tables: set[str] | None = None,
) -> dict[str, Any]:
    """Read-only SQL: only a single SELECT is allowed, at most MAX_SQL_ROWS rows.

    When ``allowed_tables`` is provided, the statement is rejected unless every base
    table it references is in the set (used by the AI query_database tool to enforce
    the read_market / read_research / read_reports capabilities).
    """
    stripped = sql.strip().rstrip(";").strip()
    if not _SELECT_RE.match(stripped):
        raise HTTPException(status_code=403, detail="Only SELECT queries are allowed")
    if ";" in stripped:
        raise HTTPException(status_code=403, detail="Multiple statements are not allowed")

    if allowed_tables is not None:
        referenced = _referenced_tables(engine, stripped)
        forbidden = referenced - set(allowed_tables)
        if forbidden:
            raise HTTPException(
                status_code=403,
                detail=f"Table access not allowed: {', '.join(sorted(forbidden))}",
            )

    with engine.connect() as connection:
        result = connection.execute(text(stripped))
        columns = list(result.keys())
        rows = [dict(row) for row in result.mappings().fetchmany(MAX_SQL_ROWS + 1)]
    return {"columns": columns, "rows": rows[:MAX_SQL_ROWS]}


def parse_filters(raw: str | None) -> dict[str, Any]:
    """Parse the JSON filter string from the frontend; 400 for invalid JSON."""
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as error:
        raise HTTPException(status_code=400, detail="filters must be valid JSON") from error
    if not isinstance(parsed, dict):
        raise HTTPException(status_code=400, detail="filters must be a JSON object")
    return parsed
