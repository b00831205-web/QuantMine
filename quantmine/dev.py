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


def main() -> None:
    """Start both servers and shut them down together.

    Exits as soon as either side stops, terminating the other, so a crashed
    backend does not leave an orphan vite process behind.
    """
    env = _load_env()

    # 后端: 用 webapi 自己的 venv, 绑 0.0.0.0 让 Windows 浏览器/vite proxy 能访问 WSL 的 8000
    api = subprocess.Popen(
        [str(ROOT / "webapi" / ".venv" / "bin" / "python"), "-m", "uvicorn",
         "app.main:app", "--reload", "--host", "0.0.0.0", "--port", "8000"],
        cwd=ROOT / "webapi", env=env,
    )
    # 前端: vite dev (HMR)
    web = subprocess.Popen(
        ["npm", "run", "dev"], cwd=ROOT / "frontend", env=env,
    )
    procs = [("api", api), ("web", web)]

    try:
        # 任一进程退出就整体收尾, 不留孤儿
        while all(p.poll() is None for _, p in procs):
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        for _, p in procs:
            if p.poll() is None:
                p.send_signal(signal.SIGTERM)
        for _, p in procs:
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()
    # 传播非零退出码, 方便发现某一端崩了
    sys.exit(next((p.returncode for _, p in procs if p.returncode), 0))


if __name__ == "__main__":
    main()
