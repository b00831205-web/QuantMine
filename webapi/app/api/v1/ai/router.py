from __future__ import annotations

from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.engine import Engine

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pathlib import Path

from ....ai.attachments import get_attachment, load_attachment_records, save_attachment

from ....dependencies import get_request_engine
from .db import(
    create_conversation,
    create_message,
    find_tool_call,
    get_config as fetch_config,
    get_conversation,
    list_conversations,
    list_messages,
    list_models,
    is_default_conversation_title,
    save_config as persist_config,
    update_conversation_title,
    update_tool_call_status,
    effective_capabilities,
    delete_conversation as remove_conversation
)

from ....ai.tools import execute_tool_call
from ....ai.chat import build_system_prompt, complete_chat, summarize_title
from ....ai.catalog import get_database_catalog
from ....ai.rag import index_message, search_messages
from ....ai.skills import discover_skills, skill_definitions
from ....ai.secrets import resolve_api_key

router = APIRouter()

class SendMessageBody(BaseModel):
    content: str = Field(min_length = 1)
    modelId: str = ''
    attachedContext: dict[str, Any] | None = None
    attachments: list[dict[str, Any]] | None = None

class ConfirmActionBody(BaseModel):
    toolCallId: str
    approved: bool

class ProviderBody(BaseModel):
    providerId: str
    name: str
    configured: bool
    baseUrl: str
    models: list[str]
    apiKeyEnv : str|None = None
    capabilities: dict[str, bool] | None = None

class EmbeddingBody(BaseModel):
    provider: str = 'none'
    baseUrl: str = ''
    model: str = ''
    apiKeyEnv: str| None = None
    dimensions: int = 1024

class ConfigBody(BaseModel):
    providers: list[ProviderBody]
    defaultModel: str = ''
    systemPrompt: str = ''
    temperature: float = Field(default = 0.7, ge= 0, le =2)
    capabilities: dict[str, bool] | None = None
    embeddingConfig: EmbeddingBody | None = None
    skills: list[dict[str, Any]] | None = None

def _resolve_provider(config: dict, model_id: str) -> dict|None:
    for provider in config.get('providers', []):
        if model_id in provider.get('models', []):
            return provider
    return None

def _mark_configured(config: dict)->dict:
    for provider in config.get('providers', []):
        env_name = provider.get('apiKeyEnv') or 'OPENAI_API_KEY'
        provider['configured'] = bool(resolve_api_key(env_name))
    embedding = config.get('embeddingConfig') or {}
    if embedding.get('provider') == 'none':
        embedding['configured'] = True
    elif embedding.get('provider') == 'ollama':
        embedding['configured'] = bool(embedding.get('baseUrl'))
    else:
        env_name = embedding.get('apiKeyEnv') or 'SILICONFLOW_API_KEY'
        embedding['configured'] = bool(resolve_api_key(env_name))
    config['embeddingConfig'] = embedding
    return config

def _parse_conversation_id(conversation_id: str) -> int:
    value = conversation_id.removeprefix('conv-')
    try:
        return int(value)
    except ValueError as error:
        raise HTTPException(status_code=404, detail = 'Conversation not found') from error

def _persist_reply(engine: Engine, cid: int, config: dict, *, content: str, index_rag: bool =False) -> dict:
    message = create_message(engine, conversation_id = cid, role = 'assistant', content = content)
    embedding_config = config.get('embeddingConfig') or {}
    if index_rag and embedding_config.get('provider') != 'none':
        index_message(
            engine,
            conversation_id = cid,
            message_id = int(message['messageId'].removeprefix('msg-')),
            role = 'assistant',
            content = content,
            embedding_config = embedding_config,
        )
    return message

def _assistant_from_reply(engine: Engine, cid: int, config: dict, reply: dict, index_rag: bool = False) -> dict:
    """Persist one LLM reply as an assistant message.

    With tool_calls -> attach a confirmation card (pending); execute after user confirms;
    otherwise persist the final text reply.
    **post_message and confirm both use it**, so follow-up tool calls in multi-step queries
    """
    tool_calls = reply.get('tool_calls')
    if tool_calls:
        first = tool_calls[0]
        content = reply.get('content') or '我需要查询数据库来回答你的问题，请确认以下工具调用：'
        confirm_request = {
            'toolCallId': first['toolCallId'],
            'title': f"执行工具{first['toolName']}",
            'description': first.get('argsSummary', ''),
            'status': 'pending',
        }
        return create_message(
            engine, conversation_id=cid, role='assistant', content=content,
            tool_calls=tool_calls, confirm_request=confirm_request,
        )
    return _persist_reply(engine, cid, config, content=reply.get('content') or '（未返回内容）', index_rag=index_rag)


# Tool approval lists:
#   Whitelist TOOL_WHITELIST — read-only/safe tools, auto-executed without a confirmation card;
#   Graylist TOOL_GRAYLIST  — high-impact/write tools, must be confirmed by the user first;
#   Unknown tools not in any list are treated as "needs confirmation" by default for safety.
TOOL_WHITELIST = {'query_database'}
TOOL_GRAYLIST: set[str] = set()  # e.g. {'trigger_backtest', 'write_config'} — no write tools yet
MAX_AGENT_STEPS = 12             # max automatic tool calls per turn, avoids infinite loops


def _needs_confirm(tool_name: str) -> bool:
    """Whitelist tools run directly; everything else (graylist or unknown) needs user confirmation."""
    return tool_name not in TOOL_WHITELIST


def _run_agent(engine: Engine, cid: int, config: dict, capabilities: dict, model_id: str | None, attached_context: dict | None = None) -> dict:
    index_rag = capabilities.get('rag_corpus', False)
    provider = _resolve_provider(config, model_id or config.get('defaultModel') or '')
    api_key = resolve_api_key((provider or {}).get('apiKeyEnv') or 'OPENAI_API_KEY')
    allow_db = capabilities.get('query_database', True)

    catalog = get_database_catalog(engine)
    rag_context: list[dict] = []

    if capabilities.get('rag_corpus', False):
        history = list_messages(engine, cid)
        latest_user = next(
            (m for m in reversed(history) if m['role'] == 'user'),
            None,
        )
        rag_context = search_messages(
            engine,
            query=latest_user['content'] if latest_user else '',
            embedding_config=config.get('embeddingConfig') or {},
            top_k=10,
            exclude_message_id=(
                int(latest_user['messageId'].removeprefix('msg-'))
                if latest_user else None
            ),
            
            
        )

    system_prompt = build_system_prompt(
        config['systemPrompt'],
        catalog=catalog,
        rag_context=rag_context,
        attached_context=attached_context,
    )
    enabled_skill_names = {
                    skill.get('name') for skill in config.get('skills') or []
                    if skill.get('enabled')
                }
    skill_tools = skill_definitions(discover_skills(), enabled_skill_names)

    def _enrich_history() -> list[dict]:
        history = list_messages(engine, cid) if capabilities.get('use_chat_history', True) else []
        for message in history:
            if message.get('attachments'):
                message['attachments'] = load_attachment_records(engine, message['attachments'])
        return history
    

    for _ in range(MAX_AGENT_STEPS):
        history = _enrich_history()
        try:
            reply = complete_chat(
                system_prompt=system_prompt,
                history=history,
                model_id=model_id or config.get('defaultModel') or None,
                temperature=config['temperature'],
                base_url=(provider or {}).get('baseUrl'),
                api_key=api_key,
                allow_query_database=allow_db,
                extra_tools=skill_tools
            )
        except Exception as error:
            raise HTTPException(status_code=502, detail=str(error)) from error

        tool_calls = reply.get('tool_calls')
        if not tool_calls:
            return _persist_reply(
                engine, cid, config,
                content=reply.get('content') or '（未返回内容）',
                index_rag=index_rag,
            )

        first = tool_calls[0]
        if not _needs_confirm(first['toolName']):
            create_message(
                engine, conversation_id=cid, role='assistant',
                content=reply.get('content') or '',
                tool_calls=[{**first, 'status': 'done'}],
            )
            result = execute_tool_call(engine, first)
            create_message(engine, conversation_id=cid, role='tool', content=result)
            continue

        return _assistant_from_reply(engine, cid, config, reply, index_rag=index_rag)

    return _persist_reply(
        engine, cid, config,
        content='（连续工具调用达到上限，请缩小问题范围或稍后重试）',
        index_rag=index_rag,
    )

@router.get('/ai/conversations')
def get_conversations(engine: Engine = Depends(get_request_engine)):
    return list_conversations(engine)


@router.post('/ai/conversations')
def post_conversation(engine: Engine = Depends(get_request_engine)):
    config = fetch_config(engine)
    return create_conversation(engine, model_id=config['defaultModel'] or None)

@router.post("/ai/attachments")
async def upload_attachment(
    conversation_id: str = Form(..., alias="conversationId"),
    file: UploadFile = File(...),
    engine: Engine = Depends(get_request_engine),
):
    cid = _parse_conversation_id(conversation_id)
    if get_conversation(engine, cid) is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="empty file")
    if len(data) > 20 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="file too large (max 20MB)")
    return save_attachment(
        engine,
        conversation_id=cid,
        filename=file.filename or "attachment",
        content_type=file.content_type or "application/octet-stream",
        data=data,
    )


@router.get("/ai/attachments/{attachment_id}/file")
def get_attachment_file(
    attachment_id: str,
    engine: Engine = Depends(get_request_engine),
):
    try:
        aid = int(attachment_id.removeprefix("att-"))
    except ValueError:
        raise HTTPException(status_code=404, detail="Attachment not found")
    record = get_attachment(engine, aid)
    if record is None:
        raise HTTPException(status_code=404, detail="Attachment not found")
    path = Path(record["path"])
    if not path.exists():
        raise HTTPException(status_code=404, detail="Attachment file missing")
    return Response(
        content=path.read_bytes(),
        media_type=record["contentType"],
        headers={"Content-Disposition": f'inline; filename="{record["filename"]}"'},
    )

@router.delete('/ai/conversations/{conversation_id}')
def delete_conversation_endpoint(
    conversation_id: str,
    engine: Engine = Depends(get_request_engine)
):
    cid = _parse_conversation_id(conversation_id)
    deleted = remove_conversation(engine, cid)
    if not deleted:
        raise HTTPException(status_code=404, detail='Conversation not found')
    return {'deleted': True, 'conversationId': conversation_id}


@router.get('/ai/models')
def get_models(engine: Engine = Depends(get_request_engine)):
    return list_models(engine)


@router.get('/ai/conversations/{conversation_id}/messages')
def get_messages(conversation_id: str, engine: Engine = Depends(get_request_engine)):
    cid = _parse_conversation_id(conversation_id)
    if get_conversation(engine, cid) is None:
        raise HTTPException(status_code= 404, detail = 'Conversation not found')
    return list_messages(engine, cid)

def _generate_title(engine: Engine, cid: int, config: dict, first_message: str) -> None:
    """Background task: summarize a conversation title from the first user message and write it back (fail silently, keep the default title)."""
    provider = _resolve_provider(config, config.get('defaultModel') or '')
    api_key = resolve_api_key((provider or {}).get('apiKeyEnv') or 'OPENAI_API_KEY')
    title = summarize_title(
        first_message,
        model_id=config.get('defaultModel') or None,
        base_url=(provider or {}).get('baseUrl'),
        api_key=api_key,
    )
    update_conversation_title(engine, cid, title)


@router.post('/ai/conversations/{conversation_id}/messages')
def post_message(
    conversation_id: str,
    body: SendMessageBody,
    background_tasks: BackgroundTasks,
    engine: Engine = Depends(get_request_engine)
):
    cid = _parse_conversation_id(conversation_id)
    conversation = get_conversation(engine, cid)
    if conversation is None:
        raise HTTPException(status_code=404, detail='Conversation not Found')

    user_attachments = []
    for item in body.attachments or []:
        raw = str(item.get('attachmentId') or '').removeprefix('att-')
        try:
            aid = int(raw)
        except ValueError:
            raise HTTPException(status_code=400, detail='invalid attachmentId')
        record = get_attachment(engine, aid)
        if record is None or record['conversationId'] != cid:
            raise HTTPException(status_code=400, detail='attachment not found for this conversation')
        user_attachments.append({
            'attachmentId': record['attachmentId'],
            'filename': record['filename'],
            'kind': record['kind'],
        })

    user_message = create_message(
        engine, conversation_id=cid, role='user', content=body.content,
        attachments=user_attachments,
    )

    config = fetch_config(engine)
    capabilities = effective_capabilities(config)

    # First message (conversation still has the default title) -> summarize title in the background without blocking this reply
    if is_default_conversation_title(conversation['title']):
        background_tasks.add_task(_generate_title, engine, cid, config, body.content)

    if capabilities.get('rag_corpus', False):
        index_message(
            engine,
            conversation_id = cid,
            message_id = int(user_message['messageId'].removeprefix('msg-')),
            role = 'user',
            content = body.content,
            embedding_config = config.get('embeddingConfig') or {},
        )
    return _run_agent(engine, cid, config, capabilities, body.modelId or config.get('defaultModel'), attached_context = body.attachedContext)

@router.post('/ai/conversations/{conversation_id}/confirm')
def confirm_action(
    conversation_id: str,
    body: ConfirmActionBody,
    engine: Engine = Depends(get_request_engine)
):
    cid = _parse_conversation_id(conversation_id)
    found = find_tool_call(engine,
                           conversation_id= cid,
                           tool_call_id= body.toolCallId)
    if found is None:
        raise HTTPException(status_code=404, detail= 'Tool call not found')
    _message, tool_call = found
    update_tool_call_status(
        engine,
        conversation_id = cid,
        tool_call_id = body.toolCallId,
        approved = body.approved
    )

    if not body.approved:
        return create_message(
            engine,
            conversation_id=cid,
            role = 'assistant',
            content = '已拒绝执行该操作'
        )

    config = fetch_config(engine)
    capabilities = effective_capabilities(config)
    if not capabilities.get('query_database', True):
        return create_message(
            engine,
            conversation_id = cid,
            role='assistant',
            content = '当前配置禁止数据库查询'
        )

    # User confirmed this (graylist) tool -> execute, persist the result, then continue the agent loop
    result_text = execute_tool_call(engine, tool_call)
    create_message(engine, conversation_id=cid, role='tool', content=result_text)
    return _run_agent(engine, cid, config, capabilities, config.get('defaultModel'))

@router.get('/ai/config')
def get_ai_config(engine: Engine = Depends(get_request_engine)):
    config = _mark_configured(fetch_config(engine))
    discovered = discover_skills()
    enabled_map = {
        skill.get('name'): bool(skill.get('enabled'))
        for skill in config.get('skills') or []
        if isinstance(skill, dict) and skill.get('name')
    }
    config['skills'] = [{
        **skill, 'enabled': bool(enabled_map.get(skill['name'], False))
    } for skill in discovered]
    return config

@router.put('/ai/config')
def put_ai_config(body: ConfigBody, engine: Engine =Depends(get_request_engine)):
    return _mark_configured(persist_config(engine, body.model_dump()))
