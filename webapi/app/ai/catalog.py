from __future__ import annotations

import time

from sqlalchemy import text
from sqlalchemy.engine import Engine

INTERNAL_TABLES = {
    'ai_config',
    'ai_conversations',
    'ai_messages',
    'ai_message_embeddings',
}

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
        if name in INTERNAL_TABLES:
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
