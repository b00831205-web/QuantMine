from __future__ import annotations

import hashlib
import time
from pathlib import Path

CACHE_DIR = Path(__file__).resolve().parent.parent.parent.parent /'data' /'reports'

TTL_SECONDS = 24*60*60

def _cache_filename(run_id: int, test_id: str | None, lang: str, ai: bool)-> str:
    raw = f'{run_id}|{test_id or 'all'}|{lang}|{ai}'
    digest = hashlib.sha1(raw.encode('utf-8')).hexdigest()[:16]
    return f'report_{digest}.pdf'

def _cache_path(run_id: int, test_id: str|None, lang: str, ai: bool) ->Path:
    return CACHE_DIR / _cache_filename(run_id, test_id ,lang, ai)

def get_cached_pdf(run_id: int, test_id: str|None, lang: str, ai:bool) ->bytes | None:
    path = _cache_path(run_id, test_id, lang, ai)
    if not path.exists():
        return None

    if time.time() - path.stat().st_mtime > TTL_SECONDS:
        return None

    return path.read_bytes()

def save_cached_pdf(
        pdf_bytes: bytes,
        run_id: int,
        test_id : str|None,
        lang : str,
        ai: bool,
) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = _cache_path(run_id, test_id, lang, ai)
    tmp = path.with_suffix('.tmp')
    tmp.write_bytes(pdf_bytes)
    tmp.replace(path)