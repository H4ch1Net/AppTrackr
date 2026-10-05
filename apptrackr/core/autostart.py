"""Launch-at-login integration (HKCU Run key on Windows)."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

log = logging.getLogger(__name__)

_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_VALUE = "AppTrackr"


def supported() -> bool:
    return sys.platform.startswith("win")


def command() -> str:
    """Command line stored in the Run key. Starts hidden in the tray."""
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" --minimized'
    exe = sys.executable
    if exe.lower().endswith("python.exe"):
        exe = exe[:-10] + "pythonw.exe"  # no console window at login
    return f'"{exe}" -m apptrackr --minimized'


def is_enabled() -> bool:
    if not supported():
        return False
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
            winreg.QueryValueEx(key, _VALUE)
            return True
    except FileNotFoundError:
        return False
    except OSError:
        log.exception("Could not read autostart entry")
        return False


def set_enabled(enable: bool) -> bool:
    """Create or remove the Run entry. Returns True on success."""
    if not supported():
        return False
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            if enable:
                winreg.SetValueEx(key, _VALUE, 0, winreg.REG_SZ, command())
            else:
                try:
                    winreg.DeleteValue(key, _VALUE)
                except FileNotFoundError:
                    pass
        return True
    except OSError:
        log.exception("Could not update autostart entry")
        return False


def _exe_in(cmd: str) -> str:
    """The program path at the start of a Run-key command line."""
    cmd = cmd.strip()
    if cmd.startswith('"'):
        end = cmd.find('"', 1)
        return cmd[1:end] if end > 0 else cmd[1:]
    return cmd.split(" ", 1)[0]


def needs_repair(current: str, ours: str, exists=lambda p: Path(p).exists()) -> bool:
    """True when an existing entry should be rewritten for this build.

    1.1 and later always add --minimized, so an entry without it was made by 1.0 (even
    when it points at an old portable copy) and is moved to this build. An entry whose
    program no longer exists is repaired too; one for another live 1.1+ copy is left alone.
    """
    if "--minimized" not in current:
        return True
    exe = _exe_in(current)
    return not exe or not exists(exe)


def repair() -> bool:
    """Bring an existing startup entry up to date after an upgrade. Returns True if rewritten."""
    if not supported() or not getattr(sys, "frozen", False):
        return False
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
            current, _kind = winreg.QueryValueEx(key, _VALUE)
    except FileNotFoundError:
        return False
    except OSError:
        log.exception("Could not read autostart entry")
        return False
    if not needs_repair(str(current), sys.executable):
        return False
    log.info("Updating the startup entry for this version (was %r)", current)
    return set_enabled(True)
