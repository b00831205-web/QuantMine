-- 2026-08-07 登录鉴权：用户表（多用户 + 密码哈希）
-- 密码只存哈希，格式为带方案前缀的自描述串（bcrypt$... / scrypt$...），
-- 校验时按前缀分派，便于将来无缝从 scrypt 升级到 bcrypt。

CREATE TABLE IF NOT EXISTS auth_users (
    id SERIAL PRIMARY KEY,
    username VARCHAR NOT NULL UNIQUE,
    password_hash VARCHAR NOT NULL,
    display_name VARCHAR,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_login_at TIMESTAMPTZ
);

-- 与其它迁移一致：给最小权限 web 角色授权（若 web 直接以 owner 连接可忽略本段）
GRANT SELECT, INSERT, UPDATE, DELETE ON auth_users TO quantmine_web;
GRANT USAGE, SELECT ON SEQUENCE auth_users_id_seq TO quantmine_web;
