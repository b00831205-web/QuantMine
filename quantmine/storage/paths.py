"""Resolve artifact paths written by a different host or operating system.

Backtest and IC writers store absolute paths in ``*_artifacts.path``. A pipeline
may write a Windows path such as ``E:\\...\\data\\artifacts\\...`` while the Web
API reads it in WSL, where that path does not exist. Rather than trusting the
stored absolute prefix, extract the platform-independent portion after
``data/artifacts/`` and attach it to the local project root or the
``QUANTMINE_ARTIFACT_DIR`` override. Return unrecognized paths unchanged.
"""

from __future__ import annotations

import os
from pathlib import Path

# quantmine/storage/paths.py -> parents[2] is the project root.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_MARKER = "data/artifacts/"


def artifacts_root() -> Path:
    """Return the configured artifact root, defaulting to ``data/artifacts``."""
    override = os.environ.get("QUANTMINE_ARTIFACT_DIR")
    return Path(override) if override else (_PROJECT_ROOT / "data" / "artifacts")


def resolve_artifact_path(stored: str | os.PathLike[str]) -> Path:
    """Rebase a stored artifact path locally; return it unchanged if unknown."""
    posix = str(stored).replace("\\", "/")
    idx = posix.find(_MARKER)
    if idx == -1:
        return Path(stored)
    rel = posix[idx + len(_MARKER):]
    return artifacts_root() / rel
