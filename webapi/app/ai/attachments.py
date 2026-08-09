"""AI 附件：上传存储 + 按类型提取文本（图片只存不解析，走视觉模型）。"""
from __future__ import annotations

import uuid
from io import BytesIO
from pathlib import Path

from sqlalchemy import MetaData, Table, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import Engine

# data/attachments 在项目根（与 artifacts 平级）
PROJECT_ROOT = Path(__file__).resolve().parents[3]
ATTACHMENT_DIR = PROJECT_ROOT / "data" / "attachments"

TEXT_EXTENSIONS = {".txt", ".md", ".csv", ".json", ".log", ".yaml", ".yml"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
MAX_TEXT_BYTES = 1_000_000  # 文本解析上限 1MB


def _kind_for(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    if ext in IMAGE_EXTENSIONS:
        return "image"
    if ext in TEXT_EXTENSIONS:
        return "text"
    if ext in {".pdf", ".docx", ".xlsx", ".xls"}:
        return "document"
    return "unsupported"


def extract_text(filename: str, data: bytes) -> str | None:
    """按类型提取文本；图片/不支持的类型返回 None。"""
    ext = Path(filename).suffix.lower()
    try:
        if ext in TEXT_EXTENSIONS:
            return data.decode("utf-8", errors="replace")[:MAX_TEXT_BYTES]
        if ext == ".pdf":
            from pypdf import PdfReader  # type: ignore[import-not-found]
            reader = PdfReader(BytesIO(data))
            pages = [page.extract_text() or "" for page in reader.pages]
            return "\n".join(pages)[:MAX_TEXT_BYTES] or None
        if ext == ".docx":
            import docx  # type: ignore[import-not-found]
            document = docx.Document(BytesIO(data))
            return "\n".join(p.text for p in document.paragraphs)[:MAX_TEXT_BYTES] or None
        if ext in {".xlsx", ".xls"}:
            import pandas as pd
            frame = pd.read_excel(BytesIO(data))
            return frame.head(200).to_csv(index=False)[:MAX_TEXT_BYTES] or None
    except Exception:
        return None
    return None


def save_attachment(
    engine: Engine,
    *,
    conversation_id: int,
    filename: str,
    content_type: str,
    data: bytes,
) -> dict:
    ATTACHMENT_DIR.mkdir(parents=True, exist_ok=True)
    stored_name = f"{uuid.uuid4().hex}_{Path(filename).name}"
    path = ATTACHMENT_DIR / stored_name
    path.write_bytes(data)

    kind = _kind_for(filename)
    extracted = extract_text(filename, data) if kind != "image" else None

    metadata = MetaData()
    table = Table("ai_attachments", metadata, autoload_with=engine)
    statement = (
        pg_insert(table)
        .values(
            conversation_id=conversation_id,
            filename=filename,
            content_type=content_type,
            kind=kind,
            size_bytes=len(data),
            path=str(path),
            extracted_text=extracted,
        )
        .returning(*table.c)
    )
    with engine.begin() as connection:
        row = connection.execute(statement).mappings().one()
    return {
        "attachmentId": f"att-{row['id']}",
        "filename": row["filename"],
        "contentType": row["content_type"],
        "kind": row["kind"],
        "sizeBytes": row["size_bytes"],
    }


def get_attachment(engine: Engine, attachment_id: int) -> dict | None:
    table = Table("ai_attachments", MetaData(), autoload_with=engine)
    statement = select(table).where(table.c.id == attachment_id)
    with engine.connect() as connection:
        row = connection.execute(statement).mappings().first()
    if row is None:
        return None
    return {
        "attachmentId": f"att-{row['id']}",
        "filename": row["filename"],
        "contentType": row["content_type"],
        "kind": row["kind"],
        "sizeBytes": row["size_bytes"],
        "path": row["path"],
        "extractedText": row["extracted_text"],
        "conversationId": row["conversation_id"],
    }

def load_attachment_records(engine: Engine, attachments: list[dict]) -> list[dict]:
    """把消息里的精简附件 [{attachmentId, filename, kind}] 展开成完整记录。"""
    records = []
    for item in attachments or []:
        raw = str(item.get("attachmentId") or "").removeprefix("att-")
        try:
            aid = int(raw)
        except ValueError:
            continue
        record = get_attachment(engine, aid)
        if record:
            records.append(record)
    return records