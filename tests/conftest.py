"""Windows test-environment parity shims.

The suite is written for POSIX CI. On Windows two platform differences break
test setup rather than Autopilot behavior, so this module narrows them only
when the tests run on Windows:

1. Home lookup: tests clear ``os.environ``. POSIX ``Path.home()`` then falls
   back to the password database, but Windows raises ``RuntimeError``. The
   shim falls back to the profile directory captured at startup, which is the
   Windows counterpart of the POSIX fallback.
2. Symlink creation: without Developer Mode or administrator rights Windows
   refuses ``os.symlink`` (WinError 1314). The shim creates a directory
   junction for directories and a hard link for files instead. Tests that
   assert symlink-only semantics can still fail and stay visible.

Nothing here changes production modules or POSIX runs.
"""

from __future__ import annotations

import ntpath
import os
import shutil
import sys
from pathlib import Path

if sys.platform == "win32":
    _PROFILE = os.environ.get("USERPROFILE") or os.path.expanduser("~")
    _original_expanduser = ntpath.expanduser

    def _expanduser(path):
        result = _original_expanduser(path)
        if isinstance(result, (str, bytes)) and result[:1] in ("~", b"~") and _PROFILE:
            # Fall back only when the environment no longer names a home.
            env_home = any(os.environ.get(key) for key in ("USERPROFILE", "HOME", "HOMEPATH"))
            if not env_home:
                home = _PROFILE if isinstance(result, str) else os.fsencode(_PROFILE)
                sep = ("\\", "/") if isinstance(result, str) else (b"\\", b"/")
                rest = result[1:]
                if not rest or rest[:1] in sep:
                    return home + rest
        return result

    ntpath.expanduser = _expanduser
    os.path.expanduser = _expanduser

    _original_os_symlink = os.symlink

    def _symlink(src, dst, target_is_directory=False, *, dir_fd=None):
        try:
            return _original_os_symlink(src, dst, target_is_directory, dir_fd=dir_fd)
        except OSError as error:
            if getattr(error, "winerror", None) != 1314 or dir_fd is not None:
                raise
        source = Path(src)
        if not source.is_absolute():
            source = Path(dst).parent / source
        if target_is_directory or source.is_dir():
            import _winapi

            _winapi.CreateJunction(str(source.resolve()), str(dst))
        elif source.exists():
            try:
                os.link(source, dst)
            except OSError:
                shutil.copy2(source, dst)
        else:
            raise OSError(1314, "symlink privilege unavailable and target missing", str(dst))

    os.symlink = _symlink
