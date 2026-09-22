"""Sandbox-only pytest plugin: make pytest's temp directories usable again.

Why this exists
---------------
pytest creates its session temp directories with ``mode=0o700``::

    rootdir.mkdir(mode=0o700, exist_ok=True)      # _pytest/tmpdir.py (getbasetemp)
    new_path.mkdir(mode=mode)                     # _pytest/pathlib.py (make_numbered_dir)

On Windows CPython maps the POSIX ``mode`` onto ``SetFileAttributesW``: the
read-only attribute follows the *write* bit, and ``0o700`` -- which has no
group/other bits -- marks the newly created directory read-only.  On an
ordinary account that is harmless; inside the DSH file sandbox, opening a
read-only directory handle is denied, so every later scandir/iteration over the
directory fails::

    PermissionError: [WinError 5] ...\\pytest-of-<user>

That makes every fixture-backed test error during setup, even though the code
under test is fine.  ``--basetemp`` does not help because pytest cleans up the
given directory with ``Path.iterdir()`` at session finish.

What it does
------------
Normalises the mode of pytest-owned temp directories to ``0o777``, and extends
the session temp root cleanup so it survives the same sandbox restriction.
Nothing in the quantmine test suite depends on the access bits of ``tmp_path``.

Usage (the plugin is not auto-loaded)::

    $env:PYTHONPATH = "test"
    .venv-win\\Scripts\\python.exe -m pytest -p _sandbox_pytest_plugin -q
"""

from __future__ import annotations

import pathlib

_ORIGINAL_MKDIR = pathlib.Path.mkdir


def _mkdir(self: pathlib.Path, mode: int = 0o777, parents: bool = False, exist_ok: bool = False):
    """Create a directory, but never as read-only."""

    if mode & 0o200 == 0 or mode in (0o700, 0o755):
        mode = 0o777
    return _ORIGINAL_MKDIR(self, mode=mode, parents=parents, exist_ok=exist_ok)


def pytest_configure(config) -> None:
    pathlib.Path.mkdir = _mkdir  # type: ignore[method-assign]

    import _pytest.pathlib
    import _pytest.tmpdir

    def _cleanup_dead_symlinks(root: pathlib.Path) -> None:
        try:
            entries = list(root.iterdir())
        except OSError:
            return
        for left_dir in entries:
            try:
                if left_dir.is_symlink() and not left_dir.resolve().exists():
                    left_dir.unlink()
            except OSError:
                continue

    _pytest.pathlib.cleanup_dead_symlinks = _cleanup_dead_symlinks
    _pytest.tmpdir.cleanup_dead_symlinks = _cleanup_dead_symlinks
