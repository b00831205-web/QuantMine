from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.engine import Engine
import os

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
    save_config as persist_config,
    update_tool_call_status,
    effective_capabilities
)

from ....ai.tools import execute_tool_call
from ....ai.chat import build_system_prompt, complete_chat

router = APIRouter()

class SendMessageBody(BaseModel):
    content: str = Field(min_length = 1)
    modelId: str = ''
    attachedContext: dict[str, Any] | None = None

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

class ConfigBody(BaseModel):
    providers: list[ProviderBody]
    defaultModel: str = ''
    systemPrompt: str = ''
    temperature: float = Field(default = 0.7, ge= 0, le =2)
    capabilities: dict[str, bool] | None = None

def _resolve_provider(config: dict, model_id: str) -> dict|None:
    for provider in config.get('providers', []):
        if model_id in provider.get('models', []):
            return provider
    return None

def _mark_configured(config: dict)->dict:
    for provider in config.get('providers', []):
        env_name = provider.get('apiKeyEnv') or 'OPENAI_API_KEY'
        provider['configured'] = bool(os.environ.get(env_name))
    return config

def _parse_conversation_id(conversation_id: str) -> int:
    value = conversation_id.removeprefix('conv-')
    try:
        return int(value)
    except ValueError as error:
        raise HTTPException(status_code=404, detail = 'Conversation not found') from error


def _assistant_from_reply(engine: Engine, cid: int, reply: dict) -> dict:
    """把一次 LLM 回复落成 assistant 消息。

    有 tool_calls → 附确认卡（pending），等用户确认后再执行；否则落最终文本答复。
    **post_message 和 confirm 都用它**，这样多步查询（如"先查最新 run、再查显著因子"）
    的后续工具调用不会被丢弃。
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
    return create_message(
        engine, conversation_id=cid, role='assistant',
        content=reply.get('content') or '（未返回内容）',
    )


# 工具审批名单：
#   白名单 TOOL_WHITELIST —— 只读/安全工具，自动执行、不弹确认卡；
#   灰名单 TOOL_GRAYLIST  —— 高影响/写操作工具，必须用户确认后才执行；
#   不在任何名单里的未知工具，出于安全默认按“需确认”处理。
TOOL_WHITELIST = {'query_database'}
TOOL_GRAYLIST: set[str] = set()  # 例：{'trigger_backtest', 'write_config'}——目前尚无写操作工具
MAX_AGENT_STEPS = 6              # 单轮内最多自动工具调用次数，避免死循环


def _needs_confirm(tool_name: str) -> bool:
    """白名单直接放行；其余（灰名单或未知工具）都需要用户确认。"""
    return tool_name not in TOOL_WHITELIST


def _run_agent(engine: Engine, cid: int, config: dict, capabilities: dict, model_id: str | None) -> dict:
    """Agent 循环：自动执行只读工具（query_database），仅对高影响工具返回确认卡。

    返回最终展示给用户的 assistant 消息——最终文本答复，或需要用户确认的高影响工具卡。
    中间的工具调用/结果消息都会落库（前端刷新时可见）。
    """
    provider = _resolve_provider(config, model_id or config.get('defaultModel') or '')
    api_key = os.environ.get((provider or {}).get('apiKeyEnv') or 'OPENAI_API_KEY')
    allow_db = capabilities.get('query_database', True)

    for _ in range(MAX_AGENT_STEPS):
        history = list_messages(engine, cid) if capabilities.get('use_chat_history', True) else []
        try:
            reply = complete_chat(
                system_prompt=build_system_prompt(config['systemPrompt']),
                history=history,
                model_id=model_id or config['defaultModel'] or None,
                temperature=config['temperature'],
                base_url=(provider or {}).get('baseUrl'),
                api_key=api_key,
                allow_query_database=allow_db,
            )
        except Exception as error:
            raise HTTPException(status_code=502, detail=str(error)) from error

        tool_calls = reply.get('tool_calls')
        if not tool_calls:
            return create_message(
                engine, conversation_id=cid, role='assistant',
                content=reply.get('content') or '（未返回内容）',
            )

        first = tool_calls[0]
        if not _needs_confirm(first['toolName']):
            # 白名单工具：记录调用（状态 done，不弹确认卡）→ 执行 → 落结果 → 继续下一步
            create_message(
                engine, conversation_id=cid, role='assistant',
                content=reply.get('content') or '',
                tool_calls=[{**first, 'status': 'done'}],
            )
            result = execute_tool_call(engine, first)
            create_message(engine, conversation_id=cid, role='tool', content=result)
            continue

        # 高影响工具：返回确认卡，停下等用户确认
        return _assistant_from_reply(engine, cid, reply)

    return create_message(
        engine, conversation_id=cid, role='assistant',
        content='（连续工具调用达到上限，请缩小问题范围或稍后重试）',
    )

@router.get('/ai/conversations')
def get_conversations(engine: Engine = Depends(get_request_engine)):
    return list_conversations(engine)


@router.post('/ai/conversations')
def post_conversation(engine: Engine = Depends(get_request_engine)):
    config = fetch_config(engine)
    return create_conversation(engine, model_id=config['defaultModel'] or None)


@router.get('/ai/models')
def get_models(engine: Engine = Depends(get_request_engine)):
    return list_models(engine)


@router.get('/ai/conversations/{conversation_id}/messages')
def get_messages(conversation_id: str, engine: Engine = Depends(get_request_engine)):
    cid = _parse_conversation_id(conversation_id)
    if get_conversation(engine, cid) is None:
        raise HTTPException(status_code= 404, detail = 'Conversation not found')
    return list_messages(engine, cid)

@router.post('/ai/conversations/{conversation_id}/messages')
def post_message(
    conversation_id: str,
    body: SendMessageBody,
    engine: Engine = Depends(get_request_engine)
):
    cid = _parse_conversation_id(conversation_id)
    if get_conversation(engine, cid) is None:
        raise HTTPException(status_code=404, detail='Conversation not Found')

    create_message(engine, conversation_id=cid, role='user', content=body.content)

    config = fetch_config(engine)
    capabilities = effective_capabilities(config)
    return _run_agent(engine, cid, config, capabilities, body.modelId or config.get('defaultModel'))

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

    # 用户已确认这次（灰名单）工具 → 执行、落结果，然后继续 agent 循环
    result_text = execute_tool_call(engine, tool_call)
    create_message(engine, conversation_id=cid, role='tool', content=result_text)
    return _run_agent(engine, cid, config, capabilities, config.get('defaultModel'))

@router.get('/ai/config')
def get_ai_config(engine: Engine = Depends(get_request_engine)):
    return _mark_configured(fetch_config(engine))

@router.put('/ai/config')
def put_ai_config(body: ConfigBody, engine: Engine =Depends(get_request_engine)):
    return _mark_configured(persist_config(engine, body.model_dump()))
