-- AI 附件表 + 消息附件列 + 视觉模型配置列
CREATE TABLE IF NOT EXISTS ai_attachments (
    id BIGSERIAL PRIMARY KEY,
    conversation_id INT NOT NULL REFERENCES ai_conversations(id) ON DELETE CASCADE,
    message_id INT REFERENCES ai_messages(id) ON DELETE SET NULL,
    filename VARCHAR NOT NULL,
    content_type VARCHAR NOT NULL DEFAULT 'application/octet-stream',
    kind VARCHAR NOT NULL CHECK (kind IN ('image', 'text', 'document', 'unsupported')),
    size_bytes BIGINT NOT NULL DEFAULT 0,
    path VARCHAR NOT NULL,
    extracted_text TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT now()
);

ALTER TABLE ai_messages ADD COLUMN IF NOT EXISTS attachments JSONB NOT NULL DEFAULT '[]'::jsonb;

ALTER TABLE ai_config ADD COLUMN IF NOT EXISTS vision_model VARCHAR;

-- web 用户授权（表由 postgres 超级用户创建时默认无权限）
GRANT SELECT, INSERT, UPDATE, DELETE ON ai_attachments TO quantmine_web;
GRANT USAGE, SELECT ON SEQUENCE ai_attachments_id_seq TO quantmine_web;
