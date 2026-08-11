#!/usr/bin/env bash
# Build the WSL service environments in Ubuntu's native Linux filesystem.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNTIME_DIR="${QUANTMINE_RUNTIME_DIR:-$HOME/.local/share/quantmine}"
API_VENV="$RUNTIME_DIR/venvs/webapi"
PIPELINE_VENV="$RUNTIME_DIR/venvs/pipeline"
UV_BIN="${UV_BIN:-$(command -v uv || true)}"
UV_ARGS=(--frozen)

if [ "${1:-}" = "--offline" ]; then
    UV_ARGS+=(--offline)
elif [ -n "${1:-}" ]; then
    echo "usage: bash deploy/sync-runtime-envs.sh [--offline]" >&2
    exit 2
fi

if [ -z "$UV_BIN" ]; then
    echo "error: uv is not installed in Ubuntu" >&2
    exit 1
fi

mkdir -p "$RUNTIME_DIR/venvs"

echo "Syncing Web API runtime: $API_VENV"
UV_PROJECT_ENVIRONMENT="$API_VENV" "$UV_BIN" sync \
    --project "$REPO/webapi" --no-install-project "${UV_ARGS[@]}"

echo "Syncing pipeline/Airflow runtime: $PIPELINE_VENV"
UV_PROJECT_ENVIRONMENT="$PIPELINE_VENV" "$UV_BIN" sync \
    --project "$REPO" --no-install-project \
    --extra data --extra db --group pipeline "${UV_ARGS[@]}"

echo
echo "Runtime environments are ready under $RUNTIME_DIR/venvs"
echo "They are isolated from Windows and from repository-local .venv directories."
