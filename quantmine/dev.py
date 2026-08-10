"""Dev entry point: start the webapi (uvicorn --reload) and the frontend (vite)
together with one command.

Registered as a console script so it runs like ``uv run dev`` — the same
mechanism Airflow uses for ``airflow standalone`` (a ``[project.scripts]`` entry
point resolved inside the project venv). Unlike Airflow's pure-Python case, this
orchestrates two runtimes (Python uvicorn + Node vite) across two venvs, so it
shells out to each rather than running in-process.
"""
import os
import signal
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_env() -> dict:
    """Return os.environ plus KEY=VALUE pairs from the repo-root .env."""
    env = os.environ.copy()
    env_file = ROOT / ".env"
    if not env_file.exists():
        return env
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def _airflow_bin(env: dict) -> Path:
    """Where the airflow CLI is expected, matching what the webapi looks for.

    Kept identical to ``webapi/app/api/v1/workflows/cli.py`` on purpose: if the
    two disagree, ``uv run dev`` starts a scheduler the API cannot then drive,
    and the Workflows page returns 502 on every pause/trigger while looking
    perfectly healthy on read (the DAG list comes from the metadata database,
    not the CLI).
    """
    override = env.get("QUANT_AIRFLOW_BIN")
    return Path(override) if override else ROOT / ".venv" / "bin" / "airflow"


def _start_airflow(env: dict) -> subprocess.Popen | None:
    """Start Airflow alongside the app, or explain why it is being skipped.

    Returns:
        The process, or None when the CLI is absent -- in which case the app
        still comes up. Airflow is optional for research and reporting; only
        the Workflows page needs it, so a missing install must not block dev.

    Notes:
        ``apache-airflow`` lives in the ``pipeline`` dependency group, which a
        plain ``uv sync`` drops. That is easy to do by accident and the symptom
        is remote from the cause, so say the fix here rather than let the user
        rediscover it from a 502.
    """
    binary = _airflow_bin(env)
    try:
        present = binary.exists()
    except OSError:
        present = False
    if not present:
        print(
            f"[dev] 跳过 Airflow: 找不到 {binary}\n"
            "[dev]   前后端照常启动; 只有 Workflows 页面的暂停/触发会返回 502\n"
            "[dev]   （DAG 列表仍可读, 它直接查元数据库, 不走 CLI）\n"
            "[dev]   装上: uv sync --group pipeline   或设 QUANT_AIRFLOW_BIN 指向已有 CLI",
            file=sys.stderr,
        )
        return None

    airflow_env = dict(env)
    airflow_env.setdefault("AIRFLOW_HOME", str(ROOT / "airflow"))
    # ``airflow standalone`` starts its four children with the bare command
    # name ``airflow``.  Finding the outer executable by absolute path is not
    # enough: its bin directory must also be on PATH for those children.
    current_path = airflow_env.get("PATH", "")
    airflow_env["PATH"] = str(binary.parent) + (os.pathsep + current_path if current_path else "")
    print(f"[dev] 启动 Airflow standalone ({binary})")
    return subprocess.Popen(
        [str(binary), "standalone"], cwd=ROOT, env=airflow_env,
    )


def _frontend_command() -> list[str]:
    """Return a Vite command whose process is owned directly by ``dev``.

    Calling ``npm run dev`` through WSL may insert a Windows npm wrapper
    between this process and Node.  Terminating the wrapper can leave Vite
    behind, occupying 5173 and making the next run silently move to 5174+.
    Running Vite with Node directly gives us the real long-lived child.  A
    strict port also makes the documented URL and CORS configuration reliable.
    """
    node = shutil.which("node") or shutil.which("node.exe")
    if not node:
        sys.exit(
            "[dev] 找不到 Node.js。请在 WSL 安装 node，或确保 Windows node.exe 可由 WSL 调用。"
        )
    return [
        node,
        "node_modules/vite/bin/vite.js",
        "--host", "0.0.0.0",
        "--port", "5173",
        "--strictPort",
    ]


def main() -> None:
    """Start the dev stack and shut it down together.

    Exits as soon as either side stops, terminating the other, so a crashed
    backend does not leave an orphan vite process behind.
    """
    env = _load_env()

    # 后端: 用 webapi 自己的 venv, 绑 0.0.0.0 让 Windows 浏览器/vite proxy 能访问 WSL 的 8000
    api_python = ROOT / "webapi" / ".venv" / "bin" / "python"
    try:
        usable = api_python.exists()
    except OSError:
        # Windows 上这是一个指向 WSL 文件系统的符号链接, stat() 抛 WinError 1920
        # 而不是返回 False。不接住的话这里就直接崩掉, 拿不到下面那句提示。
        usable = False
    if not usable:
        # bin/python 是 Linux 布局。从 Windows 跑到这里, Popen 会抛一句语焉不详的
        # FileNotFoundError, 先说清楚。
        sys.exit(
            f"[dev] 找不到后端解释器: {api_python}\n"
            "      webapi/.venv 是 Linux venv, 本命令须在 WSL 内运行:\n"
            "      wsl -d Ubuntu -- bash -lc 'cd <repo> && uv run dev'"
        )
    api = subprocess.Popen(
        [str(api_python), "-m", "uvicorn",
         "app.main:app", "--reload", "--host", "0.0.0.0", "--port", "8000"],
        cwd=ROOT / "webapi", env=env,
    )
    # 前端: vite dev (HMR)
    web = subprocess.Popen(
        _frontend_command(), cwd=ROOT / "frontend", env=env,
    )
    procs = [("api", api), ("web", web)]

    airflow = _start_airflow(env)
    if airflow is not None:
        procs.append(("airflow", airflow))

    interrupted = False
    casualty: tuple[str, int | None] | None = None
    try:
        # 任一进程退出就整体收尾, 不留孤儿
        while True:
            dead = [(name, p) for name, p in procs if p.poll() is not None]
            if dead:
                name, p = dead[0]
                casualty = (name, p.returncode)
                break
            time.sleep(0.5)
    except KeyboardInterrupt:
        interrupted = True
    finally:
        for _, p in procs:
            if p.poll() is None:
                p.send_signal(signal.SIGTERM)
        for _, p in procs:
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()

    if interrupted or casualty is None:
        sys.exit(0)

    # 不能沿用子进程的退出码: uvicorn 的 reload 监督进程在 app import 失败时也返回 0
    # (它认为"已按预期停止")。照搬就会把后端崩溃报成一次干净退出, 而真正的 traceback
    # 早被 vite 的输出刷走了。开发期任一端自行退出都是异常, 一律非零。
    name, code = casualty
    print(
        f"\n[dev] {name} 端先退出了 (exit={code}), 已一并停止另一端。\n"
        f"[dev] 退出码 0 不代表正常 —— 若 {name} 是后端, 请向上翻找 Traceback: "
        "app import 失败时 uvicorn 也返回 0。",
        file=sys.stderr,
    )
    sys.exit(1)


if __name__ == "__main__":
    main()
