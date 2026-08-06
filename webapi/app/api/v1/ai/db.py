from __future__ import annotations
from sqlalchemy import MetaData, Table, func, select, update
from sqlalchemy.dialects.postgresql import insert

from sqlalchemy.engine import Engine

DEFAULT_CAPABILITIES = {
    'read_research': True,
    'read_market': True,
    'read_reports': True,
    'query_database': True,
    'use_chat_history': True,
    'rag_corpus': False
}

def _conversation_row(row) -> dict:
    return{
        'conversationId': f'conv-{row['id']}',
        'title': row['title'],
        'researchRunIds': row['research_run_ids'] or [],
        'modelId': row['model_id'],
        'updatedAt': str(row['updated_at']),
    }

def _message_row(row)->dict:
    message = {
        'messageId': f'msg-{row['id']}',
        'conversationId': f'conv-{row['conversation_id']}',
        'role': row['role'],
        'content': row['content'],
        'createdAt': str(row['created_at']),
    }
    if row['citations']:
        message['citations'] = row['citations']

    if row['tool_calls']:
        message['toolCalls'] = row['tool_calls']

    if row['confirm_request']:
        message['confirmRequest'] = row['confirm_request']

    return message

def list_conversations(engine: Engine, *, limit: int = 50)-> list[dict]:
    table = Table('ai_conversations', MetaData(), autoload_with=engine)
    statement = (
        select(table)
        .order_by(table.c.updated_at.desc())
        .limit(limit)
    )
    with engine.connect() as connection:
        rows = connection.execute(statement).mappings().all()
    return [_conversation_row(row) for row in rows]

def get_conversation(engine: Engine, conversation_id: int)->dict | None:
    table = Table('ai_conversations', MetaData(), autoload_with=engine)
    statement = select(table).where(table.c.id == conversation_id)
    with engine.connect() as connection:
        row = connection.execute(statement).mappings().first()
    return _conversation_row(row) if row else None

def create_conversation(engine: Engine, *, model_id: str|None) -> dict:
    table = Table('ai_conversations', MetaData(), autoload_with=engine)
    statement = (
        insert(table)
        .values(title = '新对话', model_id = model_id)
        .returning(*table.c)
    )
    with engine.begin() as connection:
        row =connection.execute(statement).mappings().one()
    return _conversation_row(row)

def list_messages(engine: Engine, conversation_id: int)->list[dict]:
    table = Table('ai_messages', MetaData(), autoload_with=engine)
    statement = (
        select(table)
        .where(table.c.conversation_id == conversation_id)
        .order_by(table.c.id)
    )
    with engine.connect() as connection:
        rows = connection.execute(statement).mappings().all()
    return [_message_row(row) for row in rows]

def create_message(
        engine: Engine,
        *,
        conversation_id: int,
        role: str,
        content: str,
        citations: list|None = None,
        tool_calls: list|None =None,
        confirm_request: dict | None = None,
) -> dict:
    messages = Table('ai_messages', MetaData(), autoload_with=engine)
    conversations = Table('ai_conversations', MetaData(), autoload_with=engine)

    statement = (
        insert(messages)
        .values(conversation_id = conversation_id,
                role = role,
                content = content,
                citations = citations or [],
                tool_calls = tool_calls or [],
                confirm_request = confirm_request)
    ).returning(*messages.c)
    with engine.begin() as connection:
        row = connection.execute(statement).mappings().one()
        connection.execute(
            update(conversations)
            .where(conversations.c.id == conversation_id)
            .values(updated_at = func.now())
        )
        return _message_row(row)

def update_tool_call_status(
        engine: Engine,
        *,
        conversation_id:int,
        tool_call_id: str,
        approved: bool
)-> dict|None:
    table = Table('ai_messages', MetaData(), autoload_with=engine)
    statement = (
        select(table)
        .where(table.c.conversation_id == conversation_id)
        .order_by(table.c.id.desc())
    )
    with engine.connect() as connection:
        rows = connection.execute(statement).mappings().all()

    status = 'confirmed' if approved else 'rejected'
    for row in rows:
        tool_calls = row['tool_calls'] or []
        for call in tool_calls:
            if call.get('toolCallId') != tool_call_id:
                continue
            call['status'] = status
            confirm_request = row['confirm_request']
            if confirm_request:
                confirm_request = {**confirm_request, 'status': status}
            update_statement = (
                update(table)
                .where(table.c.id == row['id'])
                .values(tool_calls = tool_calls, confirm_request = confirm_request)
                .returning(*table.c)
            )
            with engine.begin() as connection2:
                updated = connection2.execute(update_statement).mappings().one()
            return _message_row(updated)
    return None

def _default_config()->dict:
    return{
        'providers': [],
        'defaultModel': '',
        'systemPrompt': '你是一名量化研究助手，回答要简洁，基于数据',
        'temperature': 0.7,
        'capabilities': dict(DEFAULT_CAPABILITIES)
    }

def _config_row(row)->dict:
    return{
        'providers': row['providers'] or [],
        'defaultModel': row['default_model'],
        'systemPrompt': row['system_prompt'],
        'temperature': float(row['temperature']),
        'capabilities': {**DEFAULT_CAPABILITIES, **(row['capabilities'] or {})}
    }


def get_config(engine: Engine) -> dict:
    table = Table('ai_config', MetaData(), autoload_with=engine)
    statement = select(table).where(table.c.id == 1)
    with engine.connect() as connection:
        row = connection.execute(statement).mappings().first()
    if row is None:
        return _default_config()
    return _config_row(row)

def save_config(engine: Engine, config: dict) -> dict:
    table = Table('ai_config', MetaData(), autoload_with=engine)
    values = {
        'id': 1,
        'providers': config.get('providers', []),
        'default_model': config.get('defaultModel'),
        'system_prompt': config.get('systemPrompt',''),
        'temperature': config.get('temperature', 0.7),
        'capabilities': config.get('capabilities') or dict(DEFAULT_CAPABILITIES)
    }
    statement = (
        insert(table)
        .values(**values)
        .on_conflict_do_update(
            index_elements = [table.c.id],
            set_ = {key: value for key, value in values.items() if key !="id"},
        ).returning(*table.c)
    )
    with engine.begin() as connection:
        row = connection.execute(statement).mappings().one()
    return _config_row(row)

def list_models(engine: Engine) -> list[str]:
    config = get_config(engine)
    models: list[str] = []
    for provider in config['providers']:
        for model in provider.get('models', []):
            if model not in models:
                models.append(model)
    return models

def find_tool_call(
        engine:Engine,
        *,
        conversation_id:int,
        tool_call_id:str
)->tuple[dict, dict] | None:
    table = Table('ai_messages', MetaData(), autoload_with=engine)
    statement = (
        select(table)
        .where(table.c.conversation_id == conversation_id)
        .order_by(table.c.id.desc())
    )
    with engine.connect() as connection:
        rows = connection.execute(statement).mappings().all()
    for row in rows:
        for call in row['tool_calls'] or []:
            if call.get('toolCallId') == tool_call_id:
                return _message_row(row), call
    return None

def effective_capabilities(config: dict, provider_id: str| None = None)->dict:
    merged = dict(DEFAULT_CAPABILITIES)
    merged.update(config.get('capabilities') or {})
    if provider_id:
        provider = next(
            (p for p in config.get('providers', []) if p.get('providerId') == provider_id), None
        )
        if provider and provider.get('capabilities'):
            merged.update(provider['capabilities'])
    return merged
