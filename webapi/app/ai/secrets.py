from __future__ import annotations

import os
import time
from pathlib import Path

from dotenv import dotenv_values

# 热更新 API Key 的来源文件。Docker 部署里由 docker-compose 把宿主机的
# .env.docker 以只读方式挂载到 /app/.env.docker，改宿主机文件即可生效、无需
# 重建容器（TTL 几秒）。原生开发没有该文件，会自然 fallback 为空 dict，此时
# key 仍走 os.environ（load_dotenv 或容器 env_file 注入的那条路径）。
# 可用环境变量 QUANT_AI_ENV_FILE 覆盖默认路径。
_ENV_FILE = Path(os.environ.get('QUANT_AI_ENV_FILE') or '/app/.env.docker')

_TTL_SECONDS = 3.0
_cache: dict[str, tuple[float, dict[str, str]]] = {}


def _file_values() -> dict[str, str]:
    """Read the mounted env file, cached briefly so edits land without a restart."""
    now = time.monotonic()
    hit = _cache.get('data')
    if hit is not None and now - hit[0] < _TTL_SECONDS:
        return hit[1]
    try:
        values = dotenv_values(_ENV_FILE, interpolate=False)
    except (OSError, ValueError):
        values = {}
    _cache['data'] = (now, values)
    return values


def resolve_api_key(env_name: str | None) -> str | None:
    """Resolve an API key by its env-var name, hot-reloading from the mounted file.

    优先级：进程环境变量（Docker env_file / 原生 load_dotenv）优先；
    读不到时再回落读挂载文件。空字符串视同未配置。
    """
    if not env_name:
        return None
    value = os.environ.get(env_name)
    if value:
        return value
    return _file_values().get(env_name) or None
