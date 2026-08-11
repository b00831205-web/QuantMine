-- Single source of truth for the QuantMine application database schema.
--
-- The file is idempotent through IF NOT EXISTS and may be replayed unchanged:
-- a fresh database is built in one pass and an existing database gains missing
-- objects. GRANT statements are intentionally excluded; docker/postgres/init.sh
-- and scripts/setup.py apply least-privilege grants and ALTER DEFAULT PRIVILEGES.
--
-- Run as a superuser because CREATE EXTENSION requires elevated privileges.
--
-- WARNING: This can add tables but cannot alter existing tables. CREATE TABLE
-- IF NOT EXISTS skips the entire statement when the table exists and does not
-- compare columns. Editing a column, type, constraint, or default here has no
-- effect on an existing database and fails silently.
--
-- To add a column to an existing table:
--   1. Back up first in WSL:
--      pg_dump "$url" -Fc -f /mnt/e/pgbackup/quantmine_$(date +%F).dump
--   2. As the table owner, run ALTER TABLE ... ADD COLUMN IF NOT EXISTS.
--      The quantmine_web role has DML privileges only and will report
--      "must be owner of table".
--   3. Update this file so fresh databases receive the same schema.
-- Do not rebuild the database for this: market_bars has roughly 1.65 million
-- rows and AI conversation history cannot be regenerated. If schema changes
-- become routine, introduce a schema_migrations ledger as described in the
-- SUPERSEDED section of docs/superpowers/specs/
-- 2026-08-09-operational-reliability-design.md.

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

-- Point-in-time index membership: which tickers were investable when.
--
-- One row per membership spell, not per ticker: a name that left the index and
-- later rejoined gets a second row, which is why start_date is in the key.
-- end_date NULL means "still a member"; MembershipTableSource reads it that way
-- and treats both bounds as inclusive.
--
-- Tickers are stored yfinance-style (BRK-B, not BRK.B) so they join straight
-- onto market_bars. Both the CSV importer and the wiki scraper canonicalize
-- before writing; otherwise one source switching punctuation would read as a
-- mass delisting plus a mass addition.
--
-- last_seen is the newest as-of date on which a scrape actually observed the
-- ticker in the index list, and missing_scrapes counts consecutive scrapes
-- since. Both exist so an absence is not immediately a deletion: a name gone
-- from one scrape is usually a scrape problem, so end_date is only written once
-- missing_scrapes clears the grace threshold, and it is written as last_seen --
-- the last confirmed member day, not the day the grace ran out. The counter is
-- scrape-based rather than date-based because the DAG's cadence is uneven
-- (weekends, retries), and calendar arithmetic would expire the grace after a
-- single real observation.
CREATE TABLE IF NOT EXISTS index_membership (
    index_name VARCHAR NOT NULL DEFAULT 'SP500',
    ticker VARCHAR NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE,
    last_seen DATE,
    missing_scrapes INT NOT NULL DEFAULT 0,
    source VARCHAR NOT NULL DEFAULT 'unknown',
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    PRIMARY KEY (index_name, ticker, start_date)
);
-- Covers the point-in-time slice query (start_date <= d AND end_date >= d).
CREATE INDEX IF NOT EXISTS idx_index_membership_window
    ON index_membership (index_name, start_date, end_date);

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

-- Carhart four-factor attribution results used by report section 03.
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
    artifact_type VARCHAR(8) NOT NULL DEFAULT 'pdf'
        CHECK (artifact_type IN ('pdf', 'xlsx')),
    artifact_path VARCHAR,
    artifact_size BIGINT CHECK (artifact_size IS NULL OR artifact_size >= 0),
    status VARCHAR NOT NULL DEFAULT 'ready' CHECK (status IN ('ready', 'failed')),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS ai_conversations (
    id SERIAL PRIMARY KEY,
    title VARCHAR NOT NULL DEFAULT 'New chat',
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

-- Historical-message vector index; bge-m3 embeddings use 1,024 dimensions.
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

-- Conversation attachments: persist originals and extracted text for model use.
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
    skills JSONB NOT NULL DEFAULT '[]'::jsonb,
    system_prompt TEXT NOT NULL DEFAULT '',
    temperature NUMERIC(3,2) NOT NULL DEFAULT 0.7,
    capabilities JSONB NOT NULL DEFAULT '{"read_research": true, "read_market": true, "read_reports": true, "query_database": true, "use_chat_history": true, "rag_corpus": false}'::jsonb
);

-- Authentication users. Passwords are stored only as self-describing hashes
-- prefixed with their scheme (bcrypt$... / scrypt$...), allowing verification
-- dispatch and future hash-scheme upgrades without a breaking migration.
CREATE TABLE IF NOT EXISTS auth_users (
    id SERIAL PRIMARY KEY,
    username VARCHAR NOT NULL UNIQUE,
    password_hash VARCHAR NOT NULL
        CHECK (password_hash ~ '^[A-Za-z0-9$.:/=+_-]+$'),
    display_name VARCHAR,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_login_at TIMESTAMPTZ
);
