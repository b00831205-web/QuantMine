from __future__ import annotations

import json
from fastapi import HTTPException
from sqlalchemy.engine import Engine

from app.api.v1.data.db import run_sql_query

from .skills import execute_skill

def _query_database(engine: Engine, tool_call: dict)->str:
    args = tool_call.get('args') or {}
    sql = args.get('sql')
    if not sql:
        return 'Missing sql parameter'
    result = run_sql_query(engine, sql)
    return json.dumps(result, ensure_ascii=False, default=str)[:8000]

TOOL_EXECUTORS ={
    'query_database': _query_database,
}

def execute_tool_call(engine: Engine, tool_call: dict)-> str:
    name  = tool_call.get('toolName')
    executor = TOOL_EXECUTORS.get(name)
    if executor is None:
        if name:
            return execute_skill(engine, name, tool_call.get('args') or {})
        return f'unknown tool:{name}'
    # Return tool errors to the LLM as result strings so it can self-correct
    # (e.g. significant=1 -> significant=true) or explain, instead of letting /confirm 500.
    try:
        return executor(engine, tool_call)
    except HTTPException as exc:
        return f'tool execute failed:{exc.detail}'
    except Exception as exc:  # noqa: BLE001 — feed any DB/parameter error back to the model
        return f'tool excute failed:{type(exc).__name__}: {str(exc)[:400]}'
