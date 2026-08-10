-- quantmine 应用库的唯一建表真相源。
--
-- 全文幂等（IF NOT EXISTS），初始化脚本每次都可原样重放：新库一次建全，老库只补
-- 缺失对象。不含 GRANT——最小权限角色由 docker/postgres/init.sh 与 scripts/setup.py
-- 统一授权（含 ALTER DEFAULT PRIVILEGES，覆盖未来新表）。
--
-- 需以超级用户执行（CREATE EXTENSION）。

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS research_runs (
    run_id SERIAL PRIMARY KEY,
    run_timestamp TIMESTAMP DEFAULT NOW(),
    config_snapshot JSONB NOT NULL DEFAULT '{}',
    git_commit VARCHAR
);

-- Factor files produced by a research run.
CREATE TABLE IF NOT EXISTS factor_artifacts (
    id SERIAL PRIMARY KEY,
    run_id INT REFERENCES research_runs(run_id),
    factor_name VARCHAR NOT NULL,
    params JSONB NOT NULL DEFAULT '{}',
    path VARCHAR NOT NULL,
    UNIQUE (run_id, factor_name, params)
);

-- Cleaned daily market history. One row per ticker and trading day.
CREATE TABLE IF NOT EXISTS market_bars (
    trade_date DATE NOT NULL,
    ticker VARCHAR NOT NULL,
    close NUMERIC(20, 8),
    volume BIGINT,
    shares_outstanding NUMERIC,
    market_cap NUMERIC,
    source_run_id INT REFERENCES research_runs(run_id),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    PRIMARY KEY (trade_date, ticker)
);
CREATE INDEX IF NOT EXISTS idx_market_bars_ticker_date
    ON market_bars (ticker, trade_date DESC);

-- One latest cleaned observation per ticker, optimized for dashboard reads.
CREATE TABLE IF NOT EXISTS market_latest (
    ticker VARCHAR PRIMARY KEY,
    trade_date DATE NOT NULL,
    close NUMERIC(20, 8),
    volume BIGINT,
    shares_outstanding NUMERIC,
    market_cap NUMERIC,
    source_run_id INT REFERENCES research_runs(run_id),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Full IC time-series live in Parquet; this table registers their paths.
CREATE TABLE IF NOT EXISTS ic_artifacts (
    id SERIAL PRIMARY KEY,
    run_id INT NOT NULL REFERENCES research_runs(run_id),
    variant_name VARCHAR NOT NULL,
    sample_scope VARCHAR NOT NULL
        CHECK (sample_scope IN ('train', 'test')),
    transforms JSONB NOT NULL DEFAULT '[]'::jsonb,
    path VARCHAR NOT NULL,
    UNIQUE (run_id, variant_name, sample_scope)
);

-- Compact statistical IC test results.
CREATE TABLE IF NOT EXISTS test_results (
    id SERIAL PRIMARY KEY,
    run_id INT REFERENCES research_runs(run_id),
    factor_name VARCHAR NOT NULL,
    period INT NOT NULL,
    variant_name VARCHAR NOT NULL,
    test_id VARCHAR NOT NULL,
    test_method VARCHAR NOT NULL,
    sample_scope VARCHAR NOT NULL
        CHECK (sample_scope IN ('train', 'test')),
    transforms JSONB NOT NULL DEFAULT '[]'::jsonb,
    ic_mean FLOAT,
    ic_std FLOAT,
    ir FLOAT,
    n INT,
    t_stat FLOAT,
    p_value FLOAT,
    significant BOOLEAN,
    bh_significant BOOLEAN,
    UNIQUE (
        run_id,
        variant_name,
        test_id,
        sample_scope,
        factor_name,
        period
    )
);
CREATE INDEX IF NOT EXISTS idx_test_result
    ON test_results(run_id, variant_name, factor_name, period);

-- Quantile backtest results; rank 0 represents long-short.
CREATE TABLE IF NOT EXISTS backtest_results (
    id SERIAL PRIMARY KEY,
    run_id INT REFERENCES research_runs(run_id),
    variant_name VARCHAR NOT NULL,
    backtest_id VARCHAR NOT NULL,
    test_id VARCHAR NOT NULL,
    factor_name VARCHAR NOT NULL,
    period INT NOT NULL,
    trade_date DATE NOT NULL,
    quantile_rank INT NOT NULL
        CHECK (quantile_rank = 0 OR quantile_rank >=1 ),
    return_value FLOAT,
    weighting VARCHAR NOT NULL DEFAULT 'equal',
    UNIQUE (
        run_id,
        variant_name,
        backtest_id,
        test_id,
        factor_name,
        period,
        trade_date,
        quantile_rank
    )
);
CREATE INDEX IF NOT EXISTS idx_backtest_lookup
    ON backtest_results(
        run_id,
        variant_name,
        factor_name,
        period,
        trade_date
    );

CREATE TABLE IF NOT EXISTS backtest_metrics (
    id SERIAL PRIMARY KEY,
    run_id INT NOT NULL REFERENCES research_runs(run_id),

    variant_name VARCHAR NOT NULL,
    backtest_id VARCHAR NOT NULL,
    test_id VARCHAR NOT NULL,

    factor_name VARCHAR NOT NULL,
    period INT NOT NULL,

    quantile_rank INT NOT NULL DEFAULT 0,
    metric_name VARCHAR NOT NULL,
    metric_value FLOAT,
    metric_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,

    UNIQUE (
        run_id,
        variant_name,
        backtest_id,
        test_id,
        factor_name,
        period,
        quantile_rank,
        metric_name
    )
);

CREATE TABLE IF NOT EXISTS backtest_artifacts (
    id SERIAL PRIMARY KEY,
    run_id INT NOT NULL REFERENCES research_runs(run_id),

    variant_name VARCHAR NOT NULL,
    backtest_id VARCHAR NOT NULL,

    artifact_type VARCHAR NOT NULL,
    artifact_key VARCHAR NOT NULL DEFAULT 'global',

    path VARCHAR NOT NULL,
    row_count INT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,

    UNIQUE (
        run_id,
        variant_name,
        backtest_id,
        artifact_type,
        artifact_key
    )
);

-- Carhart 四因子归因结果（报告 03 节数据源）。
CREATE TABLE IF NOT EXISTS attribution_results (
    id SERIAL PRIMARY KEY,
    run_id INT NOT NULL REFERENCES research_runs(run_id),

    variant_name VARCHAR NOT NULL,
    test_id VARCHAR NOT NULL,
    factor_name VARCHAR NOT NULL,
    period INT NOT NULL,

    term VARCHAR NOT NULL,          -- Alpha, Mkt-RF, SMB, HML, Mom

    coef FLOAT,
    std_err FLOAT,
    t_stat FLOAT,                   -- HAC (Newey-West) t
    p_value FLOAT,
    ci_lo FLOAT,
    ci_hi FLOAT,

    -- model-level stats, denormalized onto every term row for trivial reads
    r2 FLOAT,
    adj_r2 FLOAT,
    n INT,
    alpha_annual FLOAT,
    maxlags INT,

    UNIQUE (
        run_id,
        variant_name,
        test_id,
        factor_name,
        period,
        term
    )
);

-- Optional interaction audit log.
CREATE TABLE IF NOT EXISTS interaction_logs (
    id SERIAL PRIMARY KEY,
    conversation_turn_id UUID NOT NULL,
    interaction_timestamp TIMESTAMP DEFAULT NOW(),
    run_id INT REFERENCES research_runs(run_id),
    action_type VARCHAR NOT NULL,
    user_message TEXT,
    agent_response TEXT,
    tool_name VARCHAR,
    tool_params JSONB,
    tool_result JSONB
);

CREATE TABLE IF NOT EXISTS test_result_artifacts (
    id SERIAL PRIMARY KEY,
    run_id INT NOT NULL REFERENCES research_runs(run_id),
    variant_name VARCHAR NOT NULL,
    test_id VARCHAR NOT NULL,
    sample_scope VARCHAR NOT NULL
        CHECK (sample_scope IN ('train', 'test')),
    artifact_type VARCHAR NOT NULL
        CHECK (artifact_type IN ('summary', 'multiple_testing')),
    path VARCHAR NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,

    UNIQUE (
        run_id,
        variant_name,
        test_id,
        sample_scope,
        artifact_type
    )
);

CREATE TABLE IF NOT EXISTS report_history (
    id SERIAL PRIMARY KEY,
    run_id INT NOT NULL REFERENCES research_runs(run_id),
    test_id VARCHAR,
    lang VARCHAR(2) NOT NULL,
    ai BOOLEAN NOT NULL DEFAULT FALSE,
    status VARCHAR NOT NULL DEFAULT 'ready' CHECK (status IN ('ready', 'failed')),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS ai_conversations (
    id SERIAL PRIMARY KEY,
    title VARCHAR NOT NULL DEFAULT '新对话',
    model_id VARCHAR,
    research_run_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS ai_messages (
    id SERIAL PRIMARY KEY,
    conversation_id INT NOT NULL REFERENCES ai_conversations(id),
    role VARCHAR NOT NULL CHECK (role IN ('user', 'assistant', 'system', 'tool')),
    content TEXT NOT NULL DEFAULT '',
    citations JSONB NOT NULL DEFAULT '[]'::jsonb,
    tool_calls JSONB NOT NULL DEFAULT '[]'::jsonb,
    attachments JSONB NOT NULL DEFAULT '[]'::jsonb,
    confirm_request JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);

-- 历史消息向量索引（embedding 固定 1024 维，对应 bge-m3）。
CREATE TABLE IF NOT EXISTS ai_message_embeddings (
    id BIGSERIAL PRIMARY KEY,
    conversation_id INTEGER NOT NULL REFERENCES ai_conversations(id) ON DELETE CASCADE,
    message_id INTEGER NOT NULL REFERENCES ai_messages(id) ON DELETE CASCADE UNIQUE,
    role VARCHAR(16) NOT NULL,
    content TEXT NOT NULL,
    embedding vector(1024) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_ai_message_embeddings_conversation
    ON ai_message_embeddings(conversation_id);

-- 对话附件：原文落盘，文本抽取结果随行存储供模型引用。
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
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS ai_config (
    id INT PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    providers JSONB NOT NULL DEFAULT '[]'::jsonb,
    default_model VARCHAR,
    vision_model VARCHAR,
    embedding_config JSONB,
    system_prompt TEXT NOT NULL DEFAULT '',
    temperature NUMERIC(3,2) NOT NULL DEFAULT 0.7,
    capabilities JSONB NOT NULL DEFAULT '{"read_research": true, "read_market": true, "read_reports": true, "query_database": true, "use_chat_history": true, "rag_corpus": false}'::jsonb
);

-- 登录鉴权用户表。密码只存哈希，格式为带方案前缀的自描述串
-- （bcrypt$... / scrypt$...），校验时按前缀分派，便于将来无缝升级哈希方案。
CREATE TABLE IF NOT EXISTS auth_users (
    id SERIAL PRIMARY KEY,
    username VARCHAR NOT NULL UNIQUE,
    password_hash VARCHAR NOT NULL,
    display_name VARCHAR,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_login_at TIMESTAMPTZ
);
