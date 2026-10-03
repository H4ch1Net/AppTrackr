"""Launch-at-login integration (HKCU Run key on Windows)."""

from __future__ import annotations

import logging
import sys

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
