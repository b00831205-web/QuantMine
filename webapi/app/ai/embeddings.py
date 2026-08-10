from __future__ import annotations

import os

import httpx

DEFAULT_BASE_URL = 'https://api.siliconflow.cn/v1'
DEFAULT_MODEL = 'BAAI/bge-m3'

def embed_texts(texts: list[str], embedding_config: dict)->list[list[float]]:

    config = embedding_config or {}
    if config.get('provider') == 'none' or not texts:
        return []
    base_url = (config.get('baseUrl') or DEFAULT_BASE_URL).rstrip('/')
    model = config.get('model') or DEFAULT_MODEL
    headers: dict[str, str] = {}
    if config.get('provider') == 'openai_compatible':
        api_key = os.environ.get(config.get('apiKeyEnv') or 'SILICONFLOW_API_KEY')
        if not api_key:
            raise RuntimeError('Embedding API Key not configured (env SILICONFLOW_API_KEY)')
        headers['Authorization'] = f'Bearer {api_key}'
    response = httpx.post(
        f'{base_url}/embeddings',
        headers = headers,
        json = {'model': model, 'input': texts},
        timeout= 60.0,
    )
    if response.status_code >= 400:
        raise RuntimeError(
            f'Embedding API returned {response.status_code}: {response.text[:500]}'
        )

    items = sorted(response.json().get('data') or [], key=lambda x: x.get('index',0))
    vectors = [item['embedding'] for item in items]
    dimensions = int(config.get('dimensions') or 1024)
    for vector in vectors:
        if len(vector)!=dimensions:
            raise RuntimeError(
                f'Embedding dimension {len(vector)} does not match configured {dimensions}'
            )
    return vectors