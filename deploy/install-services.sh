#!/usr/bin/env bash
# 在 WSL 里把 quantmine 装成开机自启的 systemd **user** 服务。
#
#   bash deploy/install-services.sh            # 安装 + enable + 启动
#   bash deploy/install-services.sh --dry-run  # 只渲染 unit 并校验，不改系统
#   bash deploy/install-services.sh --status   # 看状态
#   bash deploy/install-services.sh --remove   # 卸载
#
# 为什么是 user unit 而不是 system unit：webapi 需要在前端开关这些服务的开机自启。
# system unit 的 enable/disable 要 root，那就得给一个对外服务的进程配免密 sudo ——
# 一旦 webapi 被攻破，那是现成的落脚点。user unit 由用户自己的 systemd 实例管理，
# webapi 以同一用户身份运行，控制它们不需要任何提权。
#
# 代价（README「运维」一节也写了）：systemd 的系统实例与用户实例互相隔离，user unit
# **无法**声明 After=postgresql.service —— 写了也只会去找同名的 user unit，找不到就
# 静默失效。所以开机时这些服务可能早于 Postgres 就绪而启动失败，靠 Restart=on-failure
# 重试补上。表现为开机头 10~30 秒日志里有几条连库失败，之后自愈；没有数据影响。
#
# 装出四个 unit，由 quantmine.target 统一管：
#   quantmine-api                    uvicorn，同时提供 API 与前端（同源，不需要 vite/nginx）
#   quantmine-airflow-apiserver      Airflow UI / REST
#   quantmine-airflow-scheduler      调度
#   quantmine-airflow-dag-processor  Airflow 3.x 把 DAG 解析拆成了独立进程
#
# 不装 triggerer：它只服务 deferrable operator，本项目的 DAG 全是 BashOperator。
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UNIT_DIR="$HOME/.config/systemd/user"
UNITS=(quantmine-api quantmine-airflow-apiserver quantmine-airflow-scheduler quantmine-airflow-dag-processor)
DRY_RUN=0

require_systemd() {
    if [ ! -d /run/systemd/system ]; then
        echo "错误：这个 WSL 发行版没有启用 systemd。" >&2
        echo "在 /etc/wsl.conf 里加 [boot] systemd=true，然后 wsl --shutdown 重启发行版。" >&2
        exit 1
    fi
}

enable_linger() {
    # 没有 linger，用户实例会在最后一个登录会话结束时被销毁，服务也就停了；
    # 开机（无人登录 WSL）更是压根不会启动。这是整套方案唯一需要 root 的一步，
    # 且只做一次。
    if [ "$(loginctl show-user "$USER" -p Linger --value 2>/dev/null)" = "yes" ]; then
        echo "linger 已开启"
        return
    fi
    echo "开启 linger（需要一次 sudo，之后不再需要）"
    sudo loginctl enable-linger "$USER"
}

status() {
    systemctl --user --no-pager --lines=0 status quantmine.target "${UNITS[@]}" 2>&1 |
        grep -E '●|Active:|Loaded:' || true
    echo
    echo "开机自启状态："
    for u in "${UNITS[@]}"; do
        printf '  %-34s %s\n' "$u" "$(systemctl --user is-enabled "$u" 2>&1)"
    done
}

remove() {
    systemctl --user disable --now quantmine.target "${UNITS[@]}" 2>/dev/null || true
    for u in "${UNITS[@]}"; do rm -f "$UNIT_DIR/$u.service"; done
    rm -f "$UNIT_DIR/quantmine.target"
    systemctl --user daemon-reload
    echo "已卸载（linger 未关闭，如需关闭：sudo loginctl disable-linger $USER）"
}

write_unit() {
    local name="$1" description="$2" workdir="$3" exec_start="$4"
    cat > "$UNIT_DIR/$name.service" <<UNIT
[Unit]
Description=$description
PartOf=quantmine.target
# 这里刻意没有 After=postgresql.service：user unit 引用不到系统实例的 unit，
# 写了也是静默无效。改由下面的 Restart 重试兜住「Postgres 还没起来」这段。
# StartLimit* 必须在 [Unit] 段；放进 [Service] 会被静默忽略。
# 额度给得比默认宽：开机时 /mnt/e（drvfs）挂载和 Postgres 就绪都可能慢。
StartLimitBurst=10
StartLimitIntervalSec=300

[Service]
Type=simple
WorkingDirectory=$workdir
Environment=AIRFLOW_HOME=$REPO/airflow
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
            echo "dry-run：unit 写到 $UNIT_DIR，不改系统"
            ;;
    esac

    [ "$DRY_RUN" -eq 1 ] || require_systemd
    mkdir -p "$UNIT_DIR"

    local api_python="$REPO/webapi/.venv/bin/python"
    local airflow_bin="$REPO/.venv/bin/airflow"
    [ -x "$api_python" ]  || { echo "找不到 $api_python（cd webapi && uv sync --extra webapi）" >&2; exit 1; }
    [ -x "$airflow_bin" ] || { echo "找不到 $airflow_bin（uv sync --group pipeline）" >&2; exit 1; }
    if [ ! -f "$REPO/webapi/app/static/index.html" ]; then
        echo "警告：webapi/app/static/index.html 不存在，uvicorn 只提供 API，浏览器打开会是 404。" >&2
        echo "      先构建前端：cd frontend && npm run build && cp -r dist/* ../webapi/app/static/" >&2
    fi

    cat > "$UNIT_DIR/quantmine.target" <<'TARGET'
[Unit]
Description=quantmine (webapi + airflow)

[Install]
WantedBy=default.target
TARGET

    # --reload 会另起 reloader 进程监视 /mnt/e 的文件变化，drvfs 上开销大且常驻态
    # 没有意义，故不带。
    write_unit quantmine-api "quantmine webapi (API + 前端)" \
        "$REPO/webapi" \
        "$api_python -m uvicorn app.main:app --host 0.0.0.0 --port 8000"
    write_unit quantmine-airflow-apiserver "Airflow API server" \
        "$REPO" "$airflow_bin api-server"
    write_unit quantmine-airflow-scheduler "Airflow scheduler" \
        "$REPO" "$airflow_bin scheduler"
    write_unit quantmine-airflow-dag-processor "Airflow DAG processor" \
        "$REPO" "$airflow_bin dag-processor"

    if [ "$DRY_RUN" -eq 1 ]; then
        echo
        for u in "${UNITS[@]}"; do
            echo "--- $u ---"
            systemd-analyze verify "$UNIT_DIR/$u.service" 2>&1 |
                grep -v "quantmine.target" || echo "  verify 通过"
        done
        echo
        echo "unit 保留在 $UNIT_DIR 供查看"
        exit 0
    fi

    enable_linger
    systemctl --user daemon-reload
    systemctl --user enable quantmine.target "${UNITS[@]}"
    systemctl --user restart quantmine.target
    echo
    echo "已安装并启动。检查："
    echo "  bash deploy/install-services.sh --status"
    echo "  journalctl --user -u quantmine-api -f"
    echo
    echo "注意：WSL 不随 Windows 开机启动，还需在 Windows 侧注册登录触发任务："
    echo "  powershell -File deploy\\register-startup-task.ps1"
}

main "$@"
