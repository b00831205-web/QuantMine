#!/usr/bin/env bash
# 开发态一行起前后端(都在 WSL 里): ./dev.sh
# 前端 vite(HMR) + 后端 uvicorn(--reload), 共用一个终端, Ctrl-C 一起收掉。
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# 载入 .env, 后端要 QUANTMINE_DATABASE_URL 等(source 比 export $(xargs) 更能处理带引号的值)
if [ -f "$ROOT/.env" ]; then
  set -a; . "$ROOT/.env"; set +a
fi

# 后端: uvicorn 绑 0.0.0.0, 这样 Windows 浏览器/vite proxy 也能访问 WSL 的 8000
( cd "$ROOT/webapi" && exec ./.venv/bin/python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 ) &
API_PID=$!

# 前端: vite dev
( cd "$ROOT/frontend" && exec npm run dev ) &
WEB_PID=$!

# 任一进程退出(崩溃或 Ctrl-C)就把另一个也收掉, 不留孤儿
trap 'kill "$API_PID" "$WEB_PID" 2>/dev/null || true' INT TERM EXIT
wait -n
