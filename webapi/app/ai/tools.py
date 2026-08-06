from __future__ import annotations

import json
from fastapi import HTTPException
from sqlalchemy.engine import Engine

from app.api.v1.data.db import run_sql_query

def _query_database(engine: Engine, tool_call: dict)->str:
    args = tool_call.get('args') or {}
    sql = args.get('sql')
    if not sql:
        return '缺少sql参数'
    result = run_sql_query(engine, sql)
    return json.dumps(result, ensure_ascii=False, default=str)[:8000]

TOOL_EXECUTORS ={
    'query_database': _query_database,
}

def execute_tool_call(engine: Engine, tool_call: dict)-> str:
    name  = tool_call.get('toolName')
    executor = TOOL_EXECUTORS.get(name)
    if executor is None:
        return f'未知工具:{name}'
    # 把工具错误当作结果字符串回传给 LLM，让它自我纠正（如把 significant=1 改成
    # significant=true）或据实说明，而不是让 /confirm 直接 500。
    try:
        return executor(engine, tool_call)
    except HTTPException as exc:
        return f'工具执行失败：{exc.detail}'
    except Exception as exc:  # noqa: BLE001 — 需要把任何 DB/参数错误反馈给模型
        return f'工具执行失败：{type(exc).__name__}: {str(exc)[:400]}'
