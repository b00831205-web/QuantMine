from __future__ import annotations

import json
from uuid import uuid4
import httpx
from app.api.v1.data.catalog import DATA_CATALOG

from pathlib import Path

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

# 常见视觉模型关键词：模型名包含这些时才会把图片发给 LLM
VISION_HINTS = ("vl", "vision", "4o", "glm-4v", "qwen2.5-vl", "gpt-4o")


def _model_supports_images(model_id: str | None) -> bool:
    lowered = (model_id or "").lower()
    return any(hint in lowered for hint in VISION_HINTS)

def build_system_prompt(
    base_prompt: str,
    catalog: list[dict] | None = None,
    rag_context: list[dict] | None = None,
    attached_context: dict |None = None,
) -> str:
    """系统提示词：基础角色 + 数据库目录（动态）+ RAG 历史语料片段。"""
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
    if attached_context and attached_context.get('page'):
        lines.append("")
        lines.append(
            f'用户当前正在查看页面：{attached_context['page']}'
            '（回答时可以优先考虑该页面相关的数据）'
        )

    for resource in catalog or DATA_CATALOG:
        fields = ", ".join(field["name"] for field in resource["fields"])
        lines.append(f"- {resource['resource']}（{resource.get('label', '')}）：{fields}")
    if rag_context:
        lines.append("")
        lines.append("以下是从历史对话中检索到的相关片段（可能来自多个会话、包含多个问题）")
        for index, item in enumerate(rag_context, 1):
            role_label = '用户问' if item['role'] == 'user' else '助手答'
            lines.append(f"[{index}] ({item['title']}) {role_label}: {item['content'][:500]}")
    return "\n".join(lines)

    

def summarize_title(
        first_message: str,
        *,
        model_id: str | None,
        base_url: str | None = None,
        api_key: str | None = None,
        max_len: int = 20,
) -> str:
    """用一次极小的 LLM 调用，把首条用户消息总结成一个短标题。

    不带工具、低温度、限制长度。任何失败（未配置 Key/模型、接口报错、
    返回为空）都回退到截取首条消息，保证一定能拿到非空标题。
    """
    fallback = _truncate_title(first_message, max_len)
    if not model_id or not api_key:
        return fallback

    system_prompt = (
        f"你是会话标题助手。根据用户的第一句话，生成一个不超过 {max_len} 个字的简洁标题，"
        "概括对话主题。只输出标题本身，不要引号、标点结尾或任何多余文字。"
    )
    url = (
        f'{base_url.rstrip('/')}/chat/completions'
        if base_url
        else 'https://api.openai.com/v1/chat/completions'
    )
    payload = {
        'model': model_id,
        'messages': [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': first_message[:500]},
        ],
        'temperature': 0.3,
        'stream': False,
    }
    try:
        response = httpx.post(
            url,
            headers={'Authorization': f'Bearer {api_key}'},
            json=payload,
            timeout=30.0,
        )
        if response.status_code >= 400:
            return fallback
        content = (
            response.json()['choices'][0]['message'].get('content') or ''
        ).strip().strip('"“”\'《》 ')
        return _truncate_title(content, max_len) if content else fallback
    except Exception:
        return fallback


def _truncate_title(text: str, max_len: int) -> str:
    """把任意文本压成单行短标题：去换行、取首 max_len 字、超长加省略号。"""
    single_line = ' '.join(text.split())
    if not single_line:
        return '新对话'
    return single_line if len(single_line) <= max_len else single_line[:max_len] + '…'

def _message_content(message: dict, supports_images: bool) -> str | list:
    """把消息的文本 + 附件组装成 OpenAI 兼容 content。

    图片附件转 data URI（走视觉模型）；文本/文档附件把提取的文本附在后面。
    模型不支持图片时跳过 image part，改为文本提示，避免 400。
    """
    content = message.get('content', '')
    attachments = message.get('attachments') or []
    text_parts = [content] if content else []
    image_parts = []
    for att in attachments:
        kind = att.get('kind')
        if kind == 'image':
            if not supports_images:
                text_parts.append(
                    f"（用户上传了图片附件：{att.get('filename', '')}，"
                    "当前模型不支持图片识别）"
                )
                continue
            path = Path(att.get('path', ''))
            if path.exists():
                import base64
                mime = att.get('contentType') or 'image/png'
                encoded = base64.b64encode(path.read_bytes()).decode('ascii')
                image_parts.append({
                    'type': 'image_url',
                    'image_url': {'url': f'data:{mime};base64,{encoded}'},
                })
        else:
            text = att.get('extractedText')
            if text:
                text_parts.append(
                    f"【附件 {att.get('filename', '')} 内容】\n{text[:8000]}"
                )
    if not image_parts:
        return "\n".join(text_parts)
    return [
        {'type': 'text', 'text': "\n".join(text_parts) or '（图片附件）'},
        *image_parts,
    ]

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
            if role == 'user' and message.get('attachments'):
                messages.append({
                    'role': role,
                    'content': _message_content(
                        message,
                        _model_supports_images(model_id),
                    ),
                })
            else:
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
