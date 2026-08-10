#!/usr/bin/env bash
# Postgres 首次初始化（仅在数据卷为空时由官方镜像自动执行，以超级用户身份运行）。
# 建三个业务角色 + 两个库，应用 schema.sql（唯一建表真相源），最后统一授权。
#
# schema.sql 通过 compose 挂载到 /sql（不放 initdb.d，避免被镜像当作针对默认库
# 自动执行）。
set -euo pipefail

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-SQL
    CREATE ROLE quantmine_web       LOGIN PASSWORD '${QUANTMINE_WEB_PASSWORD}';
    CREATE ROLE quantmine_pipeline  LOGIN PASSWORD '${QUANTMINE_PIPELINE_PASSWORD}';
    CREATE ROLE airflow             LOGIN PASSWORD '${AIRFLOW_DB_PASSWORD}';
    CREATE DATABASE quantmine OWNER quantmine_web;
    CREATE DATABASE airflow   OWNER airflow;
SQL

# 建表（schema.sql 自带 CREATE EXTENSION vector，全文幂等）
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname quantmine -f /sql/schema.sql

# schema.sql 不带 GRANT：统一给最小权限角色授权（含未来新表默认权限）
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname quantmine <<-SQL
    GRANT USAGE ON SCHEMA public TO quantmine_web, quantmine_pipeline;
    GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO quantmine_web, quantmine_pipeline;
    GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO quantmine_web, quantmine_pipeline;
    ALTER DEFAULT PRIVILEGES IN SCHEMA public
        GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO quantmine_web, quantmine_pipeline;
    ALTER DEFAULT PRIVILEGES IN SCHEMA public
        GRANT USAGE, SELECT ON SEQUENCES TO quantmine_web, quantmine_pipeline;
SQL

echo "[postgres-init] done."
