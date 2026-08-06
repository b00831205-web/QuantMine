CREATE TABLE research_runs (
    run_id SERIAL PRIMARY KEY,
    run_timestamp TIMESTAMP DEFAULT NOW(),
    config_snapshot JSONB NOT NULL DEFAULT '{}',
    git_commit VARCHAR
);

-- Factor files produced by a research run.
CREATE TABLE factor_artifacts (
    id SERIAL PRIMARY KEY,
    run_id INT REFERENCES research_runs(run_id),
    factor_name VARCHAR NOT NULL,
    params JSONB NOT NULL DEFAULT '{}',
    path VARCHAR NOT NULL,
    UNIQUE (run_id, factor_name, params)
);

-- Cleaned daily market history. One row per ticker and trading day.
CREATE TABLE market_bars (
    trade_date DATE NOT NULL,
    ticker VARCHAR NOT NULL,
    close NUMERIC(20, 8),
    volume BIGINT,
    source_run_id INT REFERENCES research_runs(run_id),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    PRIMARY KEY (trade_date, ticker)
);
CREATE INDEX idx_market_bars_ticker_date
    ON market_bars (ticker, trade_date DESC);

-- One latest cleaned observation per ticker, optimized for dashboard reads.
CREATE TABLE market_latest (
    ticker VARCHAR PRIMARY KEY,
    trade_date DATE NOT NULL,
    close NUMERIC(20, 8),
    volume BIGINT,
    source_run_id INT REFERENCES research_runs(run_id),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Full IC time-series live in Parquet; this table registers their paths.
CREATE TABLE ic_artifacts (
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
CREATE TABLE test_results (
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
CREATE INDEX idx_test_result
    ON test_results(run_id, variant_name, factor_name, period);

-- Quantile backtest results; rank 0 represents long-short.
CREATE TABLE backtest_results (
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
CREATE INDEX idx_backtest_lookup
    ON backtest_results(
        run_id,
        variant_name,
        factor_name,
        period,
        trade_date
    );

CREATE TABLE backtest_metrics (
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

CREATE TABLE backtest_artifacts (
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

-- Optional interaction audit log.
CREATE TABLE interaction_logs (
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

CREATE TABLE test_result_artifacts (
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

CREATE TABLE report_history (
    id SERIAL PRIMARY KEY,
    run_id INT NOT NULL REFERENCES research_runs(run_id),
    test_id VARCHAR,
    lang VARCHAR(2) NOT NULL,
    ai BOOLEAN NOT NULL DEFAULT FALSE,
    status VARCHAR NOT NULL DEFAULT 'ready' CHECK (status IN ('ready', 'failed')),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE ai_conversations (
    id SERIAL PRIMARY KEY,
    title VARCHAR NOT NULL DEFAULT '新对话',
    model_id VARCHAR,
    research_run_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE ai_messages (
    id SERIAL PRIMARY KEY,
    conversation_id INT NOT NULL REFERENCES ai_conversations(id),
    role VARCHAR NOT NULL CHECK (role IN ('user', 'assistant', 'system', 'tool')),
    content TEXT NOT NULL DEFAULT '',
    citations JSONB NOT NULL DEFAULT '[]'::jsonb,
    tool_calls JSONB NOT NULL DEFAULT '[]'::jsonb,
    confirm_request JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE ai_config (
    id INT PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    providers JSONB NOT NULL DEFAULT '[]'::jsonb,
    default_model VARCHAR,
    system_prompt TEXT NOT NULL DEFAULT '',
    temperature NUMERIC(3,2) NOT NULL DEFAULT 0.7,
    capabilities JSONB NOT NULL DEFAULT '{"read_research": true, "read_market": true, "read_reports": true, "query_database": true, "use_chat_history": true, "rag_corpus": false}'::jsonb
);