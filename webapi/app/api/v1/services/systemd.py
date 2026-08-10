"""Read and toggle boot autostart for the quantmine systemd **user** units.

Why `--user` and not system units: toggling a system unit needs root, which
would mean giving this network-facing process a passwordless sudo rule. The
services run under the same user the webapi does, so `systemctl --user` needs no
privilege escalation at all. `deploy/install-services.sh` installs them that
way; see the README's operations section for the tradeoff that buys.

Only autostart is exposed. Deliberately no start/stop: `quantmine-api` is the
process serving the request, so a stop would kill the caller and leave no route
back in. Enable/disable only changes the next boot, so the running session is
never at risk.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass

SYSTEMCTL_TIMEOUT = 15


@dataclass(frozen=True)
class ManagedUnit:
    """One unit this API is allowed to touch."""

    name: str
    label: str
    description: str
    #: True for the unit running this very process.
    is_self: bool = False


# Fixed allowlist. Names are never taken from the request -- the path parameter
# is looked up here and the *stored* name is what reaches subprocess. Passing a
# caller-supplied string to systemctl would hand over control of every unit the
# user owns, and `--user` units include anything they have ever installed.
MANAGED_UNITS: tuple[ManagedUnit, ...] = (
    ManagedUnit(
        "quantmine-api",
        "Web 服务",
        "提供 API 与前端页面。关掉开机自启后，下次开机需要手动启动才能打开本页面。",
        is_self=True,
    ),
    ManagedUnit(
        "quantmine-airflow-scheduler",
        "Airflow 调度器",
        "按计划触发每日数据管道。关掉后不再自动跑数据。",
    ),
    ManagedUnit(
        "quantmine-airflow-apiserver",
        "Airflow API 服务",
        "Airflow 自身的 UI 与 REST 接口。",
    ),
    ManagedUnit(
        "quantmine-airflow-dag-processor",
        "Airflow DAG 解析器",
        "解析 DAG 文件；Airflow 3.x 起为独立进程，缺它调度器看不到 DAG 变更。",
    ),
)

_BY_NAME = {unit.name: unit for unit in MANAGED_UNITS}


class SystemdUnavailable(RuntimeError):
    """systemctl is missing, or there is no user manager to talk to."""


def find_unit(name: str) -> ManagedUnit | None:
    """Resolve a request-supplied name against the allowlist."""
    return _BY_NAME.get(name)


def _env() -> dict[str, str]:
    """Environment `systemctl --user` needs to reach the user manager.

    Without ``XDG_RUNTIME_DIR`` systemctl cannot find the user bus and fails
    with "Failed to connect to bus". A process started by the user manager
    inherits it, but one started from a bare shell (or by `uv run dev`) may not,
    so fill it in rather than fail confusingly.
    """
    env = dict(os.environ)
    env.setdefault("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
    return env


def _run(*args: str) -> subprocess.CompletedProcess:
    binary = shutil.which("systemctl")
    if binary is None:
        raise SystemdUnavailable(
            "systemctl 不可用；本功能需要启用了 systemd 的 Linux/WSL 环境"
        )
    try:
        return subprocess.run(
            [binary, "--user", *args],
            capture_output=True,
            text=True,
            timeout=SYSTEMCTL_TIMEOUT,
            env=_env(),
        )
    except subprocess.TimeoutExpired as exc:
        raise SystemdUnavailable(
            f"systemctl --user {' '.join(args)} 超时（{SYSTEMCTL_TIMEOUT}s）"
        ) from exc
    except OSError as exc:
        raise SystemdUnavailable(f"无法执行 systemctl：{exc}") from exc


def read_state(unit: ManagedUnit) -> dict:
    """Report one unit's autostart and running state.

    Returns:
        ``autostart`` is None when the unit is not installed at all, which is a
        different situation from "installed but disabled" and the UI should say
        so rather than render an off switch that cannot be turned on.
    """
    enabled = _run("is-enabled", f"{unit.name}.service")
    active = _run("is-active", f"{unit.name}.service")
    raw = enabled.stdout.strip() or enabled.stderr.strip()

    if raw in {"", "not-found"} or "not-found" in raw:
        autostart = None
    else:
        autostart = raw == "enabled"

    return {
        "name": unit.name,
        "label": unit.label,
        "description": unit.description,
        "isSelf": unit.is_self,
        "installed": autostart is not None,
        "autostart": autostart,
        "active": active.stdout.strip() == "active",
        "state": raw,
    }


def list_states() -> list[dict]:
    """Report every managed unit."""
    return [read_state(unit) for unit in MANAGED_UNITS]


def set_autostart(unit: ManagedUnit, enabled: bool) -> dict:
    """Enable or disable a unit's autostart, then report its new state.

    Raises:
        SystemdUnavailable: If systemctl cannot run, or refuses the change.

    Notes:
        No ``--now``: this must not start or stop anything. Changing only the
        boot behaviour keeps the running session -- including the process
        answering this request -- untouched.
    """
    current = read_state(unit)
    if not current["installed"]:
        raise SystemdUnavailable(
            f"{unit.name} 尚未安装；先运行 deploy/install-services.sh"
        )

    result = _run("disable" if not enabled else "enable", f"{unit.name}.service")
    if result.returncode != 0:
        raise SystemdUnavailable(
            (result.stderr or result.stdout).strip()
            or f"systemctl --user {'enable' if enabled else 'disable'} 失败"
        )
    return read_state(unit)
