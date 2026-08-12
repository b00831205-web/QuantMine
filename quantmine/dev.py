"""Dev entry point: start the webapi (uvicorn --reload) and the frontend (vite)
together with one command.

Registered as a console script so it runs like ``uv run quantmine-dev`` — the same
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
    two disagree, ``uv run quantmine-dev`` starts a scheduler the API cannot then drive,
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
            f"[dev] Skipping Airflow: {binary} was not found.\n"
            "[dev]   The API and frontend will still start; only pause/trigger "
            "actions on Workflows will return 502.\n"
            "[dev]   The DAG list remains readable because it queries the metadata "
            "database directly.\n"
            "[dev]   Install it with: uv sync --group pipeline, or set "
            "QUANT_AIRFLOW_BIN to an existing CLI.",
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
    print(f"[dev] Starting Airflow standalone ({binary})")
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
            "[dev] Node.js was not found. Install Node in WSL or ensure the "
            "Windows node.exe is accessible from WSL."
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

    # Use webapi's own venv and bind 0.0.0.0 so the Windows browser and Vite
    # proxy can reach port 8000 inside WSL.
    api_python = ROOT / "webapi" / ".venv" / "bin" / "python"
    try:
        usable = api_python.exists()
    except OSError:
        # On Windows this may be a symlink into WSL whose stat() raises
        # WinError 1920 instead of returning False. Preserve the useful message.
        usable = False
    if not usable:
        # bin/python is a Linux layout. Explain the WSL requirement before
        # Popen emits an opaque FileNotFoundError on Windows.
        sys.exit(
            f"[dev] Backend interpreter not found: {api_python}\n"
            "      webapi/.venv is a Linux venv; run this command inside WSL:\n"
            "      wsl -d Ubuntu -- bash -lc 'cd <repo> && uv run quantmine-dev'"
        )
    api = subprocess.Popen(
        [str(api_python), "-m", "uvicorn",
         "app.main:app", "--reload", "--host", "0.0.0.0", "--port", "8000"],
        cwd=ROOT / "webapi", env=env,
    )
    # Frontend: Vite development server with HMR.
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
        # Shut down the whole stack when any child exits; leave no orphan.
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

    # Do not propagate a child's exit code: uvicorn's reload supervisor can
    # return 0 after an app import failure because it considers itself stopped
    # as requested. Any unprompted child exit is an error during development.
    name, code = casualty
    print(
        f"\n[dev] {name} exited first (exit={code}); the remaining services "
        "were stopped.\n"
        f"[dev] Exit code 0 does not guarantee success. If {name} is the API, "
        "look above for a traceback; uvicorn may return 0 after an app import failure.",
        file=sys.stderr,
    )
    sys.exit(1)


if __name__ == "__main__":
    main()
