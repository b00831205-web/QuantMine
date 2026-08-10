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

# 首个管理员：幂等创建（已存在则脚本内跳过）。
# 密码留空时 create_user.py 会随机生成并打印，所以这里不再要求必须配 PASSWORD——
# 之前缺密码就整段跳过，结果是容器起来了、登录页立着、一个账号都没有，
# 而后端没有注册端点，等于没有自助补救路径。
# 随机密码只在容器日志里出现一次（容器内那份 JSON 随容器销毁，日志才是可靠渠道）：
#   docker compose logs webapi | grep -A6 登录凭据
ADMIN_USER="${QUANTMINE_ADMIN_USER:-admin}"
echo "[webapi] 确保管理员账号：${ADMIN_USER}"
python /app/scripts/create_user.py "$ADMIN_USER" "${QUANTMINE_ADMIN_PASSWORD:-}" 管理员 || true

echo "[webapi] 启动 uvicorn"
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
