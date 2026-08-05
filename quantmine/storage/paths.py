"""Artifact 路径解析：把数据库里存的（可能是别的机器写入的）绝对路径重挂到本机项目根。

背景：回测/IC 等产物写入时把**绝对路径**存进了 `*_artifacts` 表的 `path` 列。管线常在
Windows 跑（存成 ``E:\\Handout\\...\\data\\artifacts\\...``），而 webapi 后端在 WSL 跑，
这些 ``E:\\`` 路径不存在 → ``FileNotFoundError`` → 500。

做法：**不信任存的绝对路径**。截取 ``data/artifacts/`` 之后的 OS 无关相对部分，重挂到本机
项目根（或 ``QUANTMINE_ARTIFACT_DIR`` 覆盖的 artifacts 根）。找不到该标记时原样返回。
Windows 跑管线、WSL 跑后端都得到正确路径。
"""

from __future__ import annotations

import os
from pathlib import Path

# quantmine/storage/paths.py → parents[2] = 项目根
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_MARKER = "data/artifacts/"


def artifacts_root() -> Path:
    """artifacts 根目录：``QUANTMINE_ARTIFACT_DIR`` 优先，否则 ``<项目根>/data/artifacts``。"""
    override = os.environ.get("QUANTMINE_ARTIFACT_DIR")
    return Path(override) if override else (_PROJECT_ROOT / "data" / "artifacts")


def resolve_artifact_path(stored: str | os.PathLike[str]) -> Path:
    """把存储的 artifact 路径重挂到本机 artifacts 根；无法识别时原样返回。"""
    posix = str(stored).replace("\\", "/")
    idx = posix.find(_MARKER)
    if idx == -1:
        return Path(stored)
    rel = posix[idx + len(_MARKER):]
    return artifacts_root() / rel
