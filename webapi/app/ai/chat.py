from __future__ import annotations

import json
from uuid import uuid4
import httpx
from app.api.v1.data.catalog import DATA_CATALOG

_QUERY_DATABASE_TOOL = {
    'type': 'function',
    'function': {
        'name': 'query_database',
        'description': "对研究数据库执行只读SQL查询（仅SELECT，最多100行）。",
        'parameters': {
            'type': 'object',
            'properties': {
                'sql': {'type': 'string', 'description': '只读 SELECT 语句'}
            },
            'required': ['sql'],
        },
    },
}

def build_system_prompt(base_prompt: str) -> str:
    """系统提示词：基础角色 + 数据库目录 + 强制查库规则。"""
    lines = [
        base_prompt,
        "",
        "你可以使用 query_database 工具对研究数据库执行只读 SQL 查询。",
        "规则：",
        "- 涉及数据/数字的问题，必须先调用 query_database 查询，再基于结果回答；",
        "- 禁止只描述查询计划而不执行工具；",
        "- 查询结果最多返回 100 行；",
        "- 数据库表结构如下：",
    ]
    for resource in DATA_CATALOG:
        fields = ", ".join(field["name"] for field in resource["fields"])
        lines.append(f"- {resource['resource']}（{resource['label']}）：{fields}")
    return "\n".join(lines)

def complete_chat(
        *,
        system_prompt:str,
        history: list[dict],
        model_id: str|None,
        temperature: float,
        base_url: str|None =None,
        api_key: str|None = None,
        allow_query_database : bool =False,
)->dict:
    if not model_id:
        raise RuntimeError('未配置模型')
    if not api_key:
        raise RuntimeError('未配置 API Key（环境变量 OPENAI_API_KEY 或 provider.apiKeyEnv）')
    messages = [{'role': 'system', 'content': system_prompt}]   
    for message in history:
        role = message.get('role')
        content = message.get('content', '')
        if role == 'tool':
            messages.append({'role': 'user', 'content': f'工具结果: {content}'})
        elif role in {'user', 'assistant', 'system'}:
            messages.append({'role': role, 'content': content}) 

    url = (
        f'{base_url.rstrip('/')}/chat/completions'
        if base_url
        else 'https://api.openai.com/v1/chat/completions'
    )
    payload: dict = {
        'model': model_id,
        'messages': messages,
        'temperature': temperature,
        'stream': False,
    }
    if allow_query_database:
        payload['tools'] = [_QUERY_DATABASE_TOOL]

    response = httpx.post(
        url,
        headers = {'Authorization': f'Bearer {api_key}'},
        json = payload,
        timeout = 60.0
    )
    if response.status_code >= 400:
        raise RuntimeError(
            f"模型接口返回 {response.status_code}: {response.text[:500]}"
        )
    data = response.json()

    message = data['choices'][0]['message']
    content = message.get('content') or ''
    tool_calls = []
    for call in message.get('tool_calls') or []:
        try:
            args = json.loads(call['function'].get('arguments') or '{}')
        except json.JSONDecodeError:
            args = {}
        tool_calls.append({
            'toolCallId': call.get('id') or f'tc-{uuid4().hex[:8]}',
            'toolName': call['function'].get('name', ''),
            'argsSummary': json.dumps(args, ensure_ascii=False)[:120],
            'args': args,
            'status' : 'pending',
        })
    return {'content': content, 'tool_calls': tool_calls}
