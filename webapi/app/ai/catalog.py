from __future__ import annotations

import time

from sqlalchemy import text
from sqlalchemy.engine import Engine

# AI 可查询表按能力分域。deny-by-default：不在任何域里的表（auth_users、ai_*、
# interaction_logs 等）既不出现在系统提示词里，也不可被 query_database 查询。
# read_reports 对应报告历史表；报告正文是文件产物（PDF/Excel），不在库里。
CAPABILITY_TABLES: dict[str, set[str]] = {
    'read_market': {'market_latest', 'market_bars', 'index_membership'},
    'read_research': {
        'research_runs', 'test_results', 'backtest_results', 'backtest_metrics',
        'attribution_results', 'factor_artifacts', 'ic_artifacts',
        'test_result_artifacts', 'backtest_artifacts',
    },
    'read_reports': {'report_history'},
}

ALL_QUERYABLE_TABLES: set[str] = set().union(*CAPABILITY_TABLES.values())

TTL_SECONDS = 300
_cache: dict = {'data': None, 'ts': 0.0}

def _map_type(data_type: str)->str:
    mapping = {
        'integer': 'number',
        'bigint': 'number',
        'smallint': 'number',
        'numeric': 'number',
        'real': 'number',
        'double precision': 'number',
        'boolean': 'boolean',
        'timestamp without time zone': 'date',
        'timestamp with time zone': 'date',
        'date': 'date',
        'jsonb': 'json',
        'json': 'json',
    }
    return mapping.get(data_type, 'string')


def allowed_tables_for(capabilities: dict) -> set[str]:
    """由能力开关推导 AI 当前可查询的表集合。"""
    allowed: set[str] = set()
    for capability, tables in CAPABILITY_TABLES.items():
        if capabilities.get(capability, False):
            allowed |= tables
    return allowed


def get_database_catalog(engine: Engine)->list[dict]:
    now = time.monotonic()
    cached = _cache['data']
    if cached is not None and now - _cache['ts'] < TTL_SECONDS:
        return cached

    statement = text(
        '''
SELECT table_name, column_name, data_type
FROM information_schema.columns
WHERE table_schema = 'public'
ORDER BY table_name, ordinal_position
'''
    )
    with engine.connect() as connection:
        rows = connection.execute(statement).mappings().all()
    grouped: dict[str,list[dict]]={}
    for row in rows:
        name = row['table_name']
        if name not in ALL_QUERYABLE_TABLES:
            continue
        grouped.setdefault(name, []).append(
            {'name': row['column_name'], 'type': _map_type(row['data_type'])}
        )
    catalog = [{
        'resource': name,
        'label': name.replace('_',' ').title(),
        'fields': fields
    }
    for name, fields in grouped.items()]
    _cache['data'] = catalog
    _cache['ts'] = now
    return catalog
