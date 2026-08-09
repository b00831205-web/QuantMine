-- 2026-08-07 Carhart 四因子归因结果入库（报告 03 节数据源）
-- 每 (run, variant, factor, period, term) 一行；模型级统计反规范化到每行，读取简单。

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

-- 与 20260806_ai_rag.sql 一致：给最小权限 web 角色授权（若 web 直接以 owner 连接可忽略本段）
GRANT SELECT, INSERT, UPDATE, DELETE ON attribution_results TO quantmine_web;
GRANT USAGE, SELECT ON SEQUENCE attribution_results_id_seq TO quantmine_web;
