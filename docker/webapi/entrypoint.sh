#!/usr/bin/env bash
# 等 Postgres 就绪 → 幂等创建首个管理员 → 启动 uvicorn。
set -euo pipefail

PG_HOST="${POSTGRES_HOST:-postgres}"
PG_PORT="${POSTGRES_PORT:-5432}"

echo "[webapi] 等待 Postgres ${PG_HOST}:${PG_PORT} …"
until pg_isready -h "$PG_HOST" -p "$PG_PORT" >/dev/null 2>&1; do
    sleep 1
done
echo "[webapi] Postgres 就绪"

# 首个管理员：提供了用户名/密码就幂等创建（已存在则脚本内跳过）
if [ -n "${QUANTMINE_ADMIN_USER:-}" ] && [ -n "${QUANTMINE_ADMIN_PASSWORD:-}" ]; then
    echo "[webapi] 确保管理员账号：${QUANTMINE_ADMIN_USER}"
    python /app/scripts/create_user.py "$QUANTMINE_ADMIN_USER" "$QUANTMINE_ADMIN_PASSWORD" 管理员 || true
fi

echo "[webapi] 启动 uvicorn"
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
