from __future__ import annotations

import sys

from sqlalchemy import MetaData, Table, func, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import Engine

from .embeddings import embed_texts

def _vector_literal(vector: list[float]) -> str:
    return '[' + ','.join(repr(float(v)) for v in vector) + ']'

def index_message(
        engine: Engine,
        *,
        conversation_id: int,
        message_id: int,
        role: str,
        content: str,
        embedding_config: dict,
) -> None:
    config = embedding_config or {}
    if config.get('provider') == 'none' or not content:
        return
    try:
        vectors = embed_texts([content[:8000]], config)
        if not vectors:
            return
        table = Table('ai_message_embeddings', MetaData(), autoload_with=engine)
        statement = (
            insert(table)
            .values(conversation_id= conversation_id,
                    message_id = message_id,
                    role = role,
                    content = content[:8000],
                    embedding = _vector_literal(vectors[0]),
                    ).on_conflict_do_update(
                        index_elements=[table.c.message_id],
                        set_={
                            'role': role,
                            'content': content[:8000],
                            'embedding': _vector_literal(vectors[0]),
                            'updated_at': func.now(),
                        },
                    )
        )
        with engine.begin() as connection:
            connection.execute(statement)
    except Exception as exc:
        print(f'[rag] index_message failed: {type(exc).__name__}: {exc}', file = sys.stderr)

def search_messages(
        engine: Engine,
        *,
        query: str,
        embedding_config: dict,
        top_k: int = 5,
        exclude_message_id: int | None = None,
)-> list[dict]:
    config = embedding_config or {}
    if config.get('provider') == 'none' or not query:
        return []
    try:
        vectors = embed_texts([query[:8000]],config)
        if not vectors:
            return []
        statement = text(
            """
SELECT m.role, m.content, c.title, 1-(e.embedding <=> :query_vector) AS similarity
FROM ai_message_embeddings e
JOIN ai_messages m ON m.id =e.message_id
JOIN ai_conversations c ON c.id = e.conversation_id
WHERE (:exclude_message_id IS NULL OR e.message_id != :exclude_message_id)
ORDER BY e.embedding <=> :query_vector
LIMIT :top_k
            """
        )
        with engine.connect() as connection:
            rows = (connection.execute(
                statement,
                {'query_vector': _vector_literal(vectors[0]),
                 'top_k': top_k,
                 'exclude_message_id': exclude_message_id}
            ).mappings().all()
            )
        return [{
            'role': row['role'],
            'content': row['content'],
            'title': row['title'],
            'similarity': round(float(row['similarity']),4)
        } for row in rows]
    except Exception as exc:
        print(f'[rag] search_messages failed: {type(exc).__name__}: {exc}', file=sys.stderr)
        return []