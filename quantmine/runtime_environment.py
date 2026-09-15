"""Load non-persistent runtime variable from a local environment file"""

from __future__ import annotations

import os
from pathlib import Path


def load_environment_file(
        environment_file: Path | str | None,
) -> bool:
    """Fill missing process variables from an optional ``.env`` file.

    Existing process variables always take precedence. The file contents are
    never returned or persisted in pipeline snapshots.
    """

    if environment_file is None:
        return False

    path = Path(environment_file).expanduser()
    if not path.is_file():
        return False

    for raw_line in path.read_text(encoding = "utf-8").splitlines():
        line = raw_line.strip()

        if not line or line.startswith("#") or "=" not in line:
            continue

        if line.startswith("export "):
            line = line[len("export "):].strip()

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")

        if key:
            os.environ.setdefault(key,value)

    _merge_proxy_bypass_hosts()

    return True

def _merge_proxy_bypass_hosts() -> None:
    """Merge configured bypass hosts into both proxy variable spellings."""

    values = (
        os.environ.get("NO_PROXY", ""),
        os.environ.get("no_proxy", ""),
        os.environ.get("QUANTMINE_NO_PROXY_HOSTS", "")
    )

    hosts: list[str] = []
    seen: set[str] = set()

    for value in values:
        for raw_host in value.split(","):
            host = raw_host.strip()
            if host and host not in seen:
                hosts.append(host)
                seen.add(host)

    if not hosts:
        return

    merged = ",".join(hosts)
    os.environ["NO_PROXY"] = merged
    os.environ["no_proxy"] = merged

