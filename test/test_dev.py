from pathlib import Path
from unittest.mock import Mock

from quantmine import dev


def test_airflow_standalone_children_can_find_cli(monkeypatch, tmp_path: Path):
    binary = tmp_path / "bin" / "airflow"
    binary.parent.mkdir()
    binary.touch()
    popen = Mock()
    monkeypatch.setattr(dev.subprocess, "Popen", popen)

    dev._start_airflow({"QUANT_AIRFLOW_BIN": str(binary), "PATH": "/usr/bin"})

    launched_env = popen.call_args.kwargs["env"]
    assert launched_env["PATH"].split(dev.os.pathsep)[0] == str(binary.parent)
    assert launched_env["AIRFLOW_HOME"] == str(dev.ROOT / "airflow")


def test_frontend_command_owns_vite_and_keeps_documented_port(monkeypatch):
    monkeypatch.setattr(dev.shutil, "which", lambda name: "/usr/bin/node" if name == "node" else None)

    command = dev._frontend_command()

    assert command[:2] == ["/usr/bin/node", "node_modules/vite/bin/vite.js"]
    assert command[command.index("--port") + 1] == "5173"
    assert "--strictPort" in command
