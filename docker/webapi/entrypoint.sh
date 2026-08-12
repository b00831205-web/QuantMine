#!/usr/bin/env bash
# 等 Postgres 就绪 → 幂等创建首个管理员 → 启动 uvicorn。
set -euo pipefail

for name in QUANT_AUTH_SECRET QUANTMINE_ADMIN_PASSWORD AIRFLOW__CORE__FERNET_KEY; do
    value="${!name:-}"
    if [ -z "$value" ] || [ "$value" = "REPLACE_ME" ]; then
        echo "[webapi] $name is missing or still uses the example placeholder" >&2
        echo "[webapi] run: python scripts/create_docker_env.py" >&2
        exit 1
    fi
done

PG_HOST="${POSTGRES_HOST:-postgres}"
PG_PORT="${POSTGRES_PORT:-5432}"

echo "[webapi] 等待 Postgres ${PG_HOST}:${PG_PORT} …"
until pg_isready -h "$PG_HOST" -p "$PG_PORT" >/dev/null 2>&1; do
    sleep 1
done
echo "[webapi] Postgres 就绪"

# 首个管理员：幂等创建（已存在则验证后继续）。Docker 密码由
# scripts/create_docker_env.py 预先生成并保存在宿主机 .env.docker，避免凭据只出现在日志。
ADMIN_USER="${QUANTMINE_ADMIN_USER:-admin}"
echo "[webapi] 确保管理员账号：${ADMIN_USER}"
if ! python /app/scripts/create_user.py "$ADMIN_USER" "${QUANTMINE_ADMIN_PASSWORD:-}" 管理员; then
    # Exit code 1 means the account already exists; verify that explicitly so
    # real failures (missing schema, bad DSN, import errors) do not get hidden.
    python - "$ADMIN_USER" <<'PY'
import sys
from sqlalchemy import MetaData, Table, select
from quantmine.storage.database import get_engine

username = sys.argv[1]
engine = get_engine()
users = Table("auth_users", MetaData(), autoload_with=engine)
with engine.connect() as conn:
    exists = conn.execute(select(users.c.id).where(users.c.username == username)).first()
if not exists:
    raise SystemExit(f"管理员创建失败且数据库中不存在：{username}")
print(f"[webapi] 管理员已存在：{username}")
PY
fi

echo "[webapi] 启动 uvicorn"
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
