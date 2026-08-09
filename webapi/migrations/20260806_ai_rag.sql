-- 2026-08-06 AI RAG：pgvector + 历史消息向量索引
CREATE EXTENSION IF NOT EXISTS vector;

-- ai_config 增加 embedding 配置列（JSONB，和 providers 平级）
ALTER TABLE ai_config ADD COLUMN IF NOT EXISTS embedding_config jsonb;

-- 历史消息向量表（embedding 固定 1024 维，对应 bge-m3）
CREATE TABLE IF NOT EXISTS ai_message_embeddings (
    id BIGSERIAL PRIMARY KEY,
    conversation_id INTEGER NOT NULL REFERENCES ai_conversations(id) ON DELETE CASCADE,
    message_id INTEGER NOT NULL REFERENCES ai_messages(id) ON DELETE CASCADE UNIQUE,
    role VARCHAR(16) NOT NULL,
    content TEXT NOT NULL,
    embedding vector(1024) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    updated_at TIMESTAMP NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_ai_message_embeddings_conversation
    ON ai_message_embeddings(conversation_id);

-- 给 web 用户授权（以 postgres 超级用户执行时默认 owner 是 postgres）
GRANT SELECT, INSERT, UPDATE, DELETE ON ai_message_embeddings TO quantmine_web;
GRANT USAGE, SELECT ON SEQUENCE ai_message_embeddings_id_seq TO quantmine_web;