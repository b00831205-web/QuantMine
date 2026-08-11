#!/usr/bin/env bash
# Postgres 首次初始化（仅在数据卷为空时由官方镜像自动执行，以超级用户身份运行）。
# 建三个业务角色 + 两个库，应用 schema.sql（唯一建表真相源），最后统一授权。
#
# schema.sql 通过 compose 挂载到 /sql（不放 initdb.d，避免被镜像当作针对默认库
# 自动执行）。
set -euo pipefail

for name in POSTGRES_PASSWORD QUANTMINE_WEB_PASSWORD QUANTMINE_PIPELINE_PASSWORD AIRFLOW_DB_PASSWORD; do
    value="${!name:-}"
    if [ -z "$value" ] || [ "$value" = "REPLACE_ME" ]; then
        echo "[postgres-init] $name is missing or still uses the example placeholder" >&2
        exit 1
    fi
done

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
    -v web_password="$QUANTMINE_WEB_PASSWORD" \
    -v pipeline_password="$QUANTMINE_PIPELINE_PASSWORD" \
    -v airflow_password="$AIRFLOW_DB_PASSWORD" <<-'SQL'
    CREATE ROLE quantmine_web       LOGIN PASSWORD :'web_password';
    CREATE ROLE quantmine_pipeline  LOGIN PASSWORD :'pipeline_password';
    CREATE ROLE airflow             LOGIN PASSWORD :'airflow_password';
    CREATE DATABASE quantmine OWNER quantmine_web;
    CREATE DATABASE airflow   OWNER airflow;
SQL

# 建表（schema.sql 自带 CREATE EXTENSION vector，全文幂等）
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname quantmine -f /sql/schema.sql

# schema.sql 不带 GRANT：web 只写应用状态表，pipeline 才能写研究/行情表。
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname quantmine <<-SQL
    GRANT USAGE ON SCHEMA public TO quantmine_web, quantmine_pipeline;
    REVOKE INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public FROM quantmine_web;
    GRANT SELECT ON ALL TABLES IN SCHEMA public TO quantmine_web;
    GRANT SELECT, INSERT, UPDATE, DELETE ON
        auth_users, report_history, interaction_logs, ai_conversations,
        ai_messages, ai_message_embeddings, ai_attachments, ai_config
        TO quantmine_web;
    GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO quantmine_pipeline;
    GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO quantmine_web, quantmine_pipeline;
    ALTER DEFAULT PRIVILEGES IN SCHEMA public
        REVOKE INSERT, UPDATE, DELETE ON TABLES FROM quantmine_web;
    ALTER DEFAULT PRIVILEGES IN SCHEMA public
        GRANT SELECT ON TABLES TO quantmine_web;
    ALTER DEFAULT PRIVILEGES IN SCHEMA public
        GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO quantmine_pipeline;
    ALTER DEFAULT PRIVILEGES IN SCHEMA public
        GRANT USAGE, SELECT ON SEQUENCES TO quantmine_web, quantmine_pipeline;
SQL

echo "[postgres-init] done."
