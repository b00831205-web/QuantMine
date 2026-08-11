#!/usr/bin/env bash
# Install QuantMine as systemd user services inside WSL/Ubuntu.
#
# Runtime virtual environments deliberately live in the Linux filesystem, not
# under /mnt/c or /mnt/e. This prevents Windows tools and drvfs mount problems
# from corrupting Linux executables and symlinks.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UNIT_DIR="$HOME/.config/systemd/user"
RUNTIME_DIR="${QUANTMINE_RUNTIME_DIR:-$HOME/.local/share/quantmine}"
API_VENV="$RUNTIME_DIR/venvs/webapi"
PIPELINE_VENV="$RUNTIME_DIR/venvs/pipeline"
UNITS=(quantmine-api quantmine-airflow-apiserver quantmine-airflow-scheduler quantmine-airflow-dag-processor)
DRY_RUN=0

require_systemd() {
    if [ ! -d /run/systemd/system ]; then
        echo "error: systemd is not enabled in this WSL distribution" >&2
        echo "add '[boot] systemd=true' to /etc/wsl.conf, then run 'wsl --shutdown'" >&2
        exit 1
    fi
}

enable_linger() {
    if [ "$(loginctl show-user "$USER" -p Linger --value 2>/dev/null)" = "yes" ]; then
        echo "systemd linger is already enabled"
        return
    fi
    echo "Enabling systemd linger (one sudo prompt may be required)"
    sudo loginctl enable-linger "$USER"
}

status() {
    systemctl --user --no-pager --lines=0 status quantmine.target "${UNITS[@]}" 2>&1 |
        grep -E 'Active:|Loaded:' || true
    echo
    echo "Boot enablement:"
    for unit in "${UNITS[@]}"; do
        printf '  %-34s %s\n' "$unit" "$(systemctl --user is-enabled "$unit" 2>&1)"
    done
}

remove() {
    systemctl --user disable --now quantmine.target "${UNITS[@]}" 2>/dev/null || true
    for unit in "${UNITS[@]}"; do rm -f "$UNIT_DIR/$unit.service"; done
    rm -f "$UNIT_DIR/quantmine.target"
    systemctl --user daemon-reload
    echo "QuantMine user services removed; systemd linger was left unchanged."
}

write_unit() {
    local name="$1" description="$2" workdir="$3" exec_start="$4"
    cat > "$UNIT_DIR/$name.service" <<UNIT
[Unit]
Description=$description
PartOf=quantmine.target
StartLimitBurst=10
StartLimitIntervalSec=300

[Service]
Type=simple
WorkingDirectory=$workdir
Environment=AIRFLOW_HOME=$REPO/airflow
Environment=QUANT_PROJECT_ROOT=$REPO
Environment=QUANT_PYTHON_BIN=$PIPELINE_VENV/bin/python
Environment=QUANT_AIRFLOW_BIN=$PIPELINE_VENV/bin/airflow
Environment=QUANT_AIRFLOW_PYTHON=$PIPELINE_VENV/bin/python
ExecStart=$exec_start
Restart=on-failure
RestartSec=10
StandardOutput=append:$REPO/airflow/service-$name.log
StandardError=append:$REPO/airflow/service-$name.log

[Install]
WantedBy=quantmine.target
UNIT
}

main() {
    case "${1:-}" in
        --status) status; exit 0 ;;
        --remove) remove; exit 0 ;;
        --dry-run)
            DRY_RUN=1
            UNIT_DIR="$(mktemp -d)"
            echo "dry-run: units will be written to $UNIT_DIR"
            ;;
    esac

    [ "$DRY_RUN" -eq 1 ] || require_systemd
    mkdir -p "$UNIT_DIR"

    local api_python="$API_VENV/bin/python"
    local airflow_bin="$PIPELINE_VENV/bin/airflow"
    [ -x "$api_python" ] || {
        echo "error: $api_python does not exist" >&2
        echo "run: bash deploy/sync-runtime-envs.sh" >&2
        exit 1
    }
    [ -x "$airflow_bin" ] || {
        echo "error: $airflow_bin does not exist" >&2
        echo "run: bash deploy/sync-runtime-envs.sh" >&2
        exit 1
    }
    if [ ! -f "$REPO/webapi/app/static/index.html" ]; then
        echo "warning: frontend build is missing; http://localhost:8000 will not show the UI" >&2
        echo "run deploy/update-service.ps1 from Windows PowerShell" >&2
    fi

    cat > "$UNIT_DIR/quantmine.target" <<'TARGET'
[Unit]
Description=QuantMine (web API, frontend, and Airflow)

[Install]
WantedBy=default.target
TARGET

    write_unit quantmine-api "QuantMine API and production frontend (port 8000)" \
        "$REPO/webapi" \
        "$api_python -m uvicorn app.main:app --host 0.0.0.0 --port 8000"
    write_unit quantmine-airflow-apiserver "QuantMine Airflow API server" \
        "$REPO" "$airflow_bin api-server"
    write_unit quantmine-airflow-scheduler "QuantMine Airflow scheduler" \
        "$REPO" "$airflow_bin scheduler"
    write_unit quantmine-airflow-dag-processor "QuantMine Airflow DAG processor" \
        "$REPO" "$airflow_bin dag-processor"

    if [ "$DRY_RUN" -eq 1 ]; then
        for unit in "${UNITS[@]}"; do
            systemd-analyze verify "$UNIT_DIR/$unit.service" 2>&1 |
                grep -v "quantmine.target" || true
        done
        echo "dry-run units retained in $UNIT_DIR"
        exit 0
    fi

    enable_linger
    systemctl --user daemon-reload
    systemctl --user enable quantmine.target "${UNITS[@]}"
    systemctl --user restart quantmine.target
    echo "Installed and started. Production UI: http://localhost:8000"
    echo "Status: bash deploy/install-services.sh --status"
}

main "$@"
