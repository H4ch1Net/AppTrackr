"""OS integration: which app has focus, how long the user has been idle, lock state.

Tracking is implemented for Windows. Other platforms get a NullPlatform so the
UI can still run (useful for development, demos and screenshots).
"""

from __future__ import annotations

import ctypes
import logging
import sys
import time
from dataclasses import dataclass
from typing import Protocol

import psutil

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ForegroundApp:
    pid: int
    exe_name: str
    exe_path: str | None


class Platform(Protocol):
    supported: bool

    def foreground_app(self) -> ForegroundApp | None: ...

    def idle_seconds(self) -> float: ...

    def is_locked(self) -> bool: ...


class NullPlatform:
    """No-op platform: nothing is ever in focus."""

    supported = False

    def foreground_app(self) -> ForegroundApp | None:
        return None

    def idle_seconds(self) -> float:
        return 0.0

    def is_locked(self) -> bool:
        return False


class DemoPlatform:
    """Pretends a fixed rotation of apps has focus. Used by --demo."""

    supported = True
    ROTATION = (
        ("code.exe", 1500),
        ("chrome.exe", 600),
        ("windowsterminal.exe", 420),
        ("slack.exe", 300),
        ("figma.exe", 480),
    )

    def __init__(self, start: float | None = None) -> None:
        self._start = time.time() if start is None else start

    def foreground_app(self) -> ForegroundApp | None:
        cycle = sum(sec for _, sec in self.ROTATION)
        pos = (time.time() - self._start) % cycle
        for exe, sec in self.ROTATION:
            if pos < sec:
                return ForegroundApp(0, exe, None)
            pos -= sec
        return None

    def idle_seconds(self) -> float:
        return 0.0

    def is_locked(self) -> bool:
        return False


class _LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]


class _RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long), ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


class _MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_ulong), ("rcMonitor", _RECT), ("rcWork", _RECT), ("dwFlags", ctypes.c_ulong)]


class WindowsPlatform:
    """Win32 implementation using user32/kernel32 through ctypes."""

    supported = True
    _DESKTOP_READOBJECTS = 0x0001
    _UWP_HOST = "applicationframehost.exe"
    _GWL_STYLE = -16
    _WS_CAPTION = 0x00C00000
    _MONITOR_DEFAULTTONEAREST = 2

    def __init__(self) -> None:
        from ctypes import wintypes

        self._wt = wintypes
        u = self._user32 = ctypes.WinDLL("user32", use_last_error=True)  # type: ignore[attr-defined]
        k = self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)  # type: ignore[attr-defined]

        u.GetForegroundWindow.argtypes = []
        u.GetForegroundWindow.restype = wintypes.HWND
        u.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        u.GetWindowThreadProcessId.restype = wintypes.DWORD
        u.GetLastInputInfo.argtypes = [ctypes.POINTER(_LASTINPUTINFO)]
        u.GetLastInputInfo.restype = wintypes.BOOL
        u.OpenInputDesktop.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        u.OpenInputDesktop.restype = wintypes.HANDLE
        u.CloseDesktop.argtypes = [wintypes.HANDLE]
        u.CloseDesktop.restype = wintypes.BOOL
        self._enum_proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)  # type: ignore[attr-defined]
        u.EnumChildWindows.argtypes = [wintypes.HWND, self._enum_proc, wintypes.LPARAM]
        u.EnumChildWindows.restype = wintypes.BOOL
        u.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(_RECT)]
        u.GetWindowRect.restype = wintypes.BOOL
        u.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
        u.GetWindowLongW.restype = ctypes.c_long
        u.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
        u.MonitorFromWindow.restype = wintypes.HANDLE
        u.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.POINTER(_MONITORINFO)]
        u.GetMonitorInfoW.restype = wintypes.BOOL
        u.GetShellWindow.argtypes = []
        u.GetShellWindow.restype = wintypes.HWND
        u.GetDesktopWindow.argtypes = []
        u.GetDesktopWindow.restype = wintypes.HWND
        k.GetTickCount.argtypes = []
        k.GetTickCount.restype = wintypes.DWORD

        self._last_key: tuple[int, int] | None = None
        self._last_app: ForegroundApp | None = None

    def _pid_of(self, hwnd) -> int:
        pid = self._wt.DWORD()
        self._user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        return int(pid.value)

    def _uwp_child_pid(self, hwnd, host_pid: int) -> int:
        """UWP apps are hosted by ApplicationFrameHost; find the real app process."""
        found: list[int] = []

        def callback(child, _lparam):
            pid = self._pid_of(child)
            if pid and pid != host_pid:
                found.append(pid)
                return False
            return True

        self._user32.EnumChildWindows(hwnd, self._enum_proc(callback), 0)
        return found[0] if found else host_pid

    def foreground_app(self) -> ForegroundApp | None:
        hwnd = self._user32.GetForegroundWindow()
        if not hwnd:
            return None
        pid = self._pid_of(hwnd)
        if not pid:
            return None
        key = (int(hwnd), pid)
        if key == self._last_key and self._last_app is not None:
            return self._last_app
        try:
            proc = psutil.Process(pid)
            name = proc.name()
            if name.lower() == self._UWP_HOST:
                child = self._uwp_child_pid(hwnd, pid)
                if child != pid:
                    proc = psutil.Process(child)
                    name = proc.name()
            try:
                path = proc.exe()
            except (psutil.AccessDenied, psutil.ZombieProcess, OSError):
                path = None  # elevated or protected process: still track by name
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            return None
        app = ForegroundApp(proc.pid, name, path)
        # A UWP frame can be sampled before its app window attaches; retry next time.
        if name.lower() != self._UWP_HOST:
            self._last_key, self._last_app = key, app
        return app

    def foreground_fullscreen(self) -> bool:
        """True while the foreground window covers its whole monitor (a game, a video, a slideshow)."""
        u = self._user32
        hwnd = u.GetForegroundWindow()
        if not hwnd or hwnd in (u.GetShellWindow(), u.GetDesktopWindow()):
            return False
        rect = _RECT()
        info = _MONITORINFO()
        info.cbSize = ctypes.sizeof(_MONITORINFO)
        monitor = u.MonitorFromWindow(hwnd, self._MONITOR_DEFAULTTONEAREST)
        if not u.GetWindowRect(hwnd, ctypes.byref(rect)) or not u.GetMonitorInfoW(monitor, ctypes.byref(info)):
            return False
        m = info.rcMonitor
        exact = (rect.left, rect.top, rect.right, rect.bottom) == (m.left, m.top, m.right, m.bottom)
        covers = rect.left <= m.left and rect.top <= m.top and rect.right >= m.right and rect.bottom >= m.bottom
        # A maximized window overhangs the monitor by its borders but keeps its title bar.
        captionless = (u.GetWindowLongW(hwnd, self._GWL_STYLE) & self._WS_CAPTION) != self._WS_CAPTION
        return exact or (covers and captionless)

    def idle_seconds(self) -> float:
        info = _LASTINPUTINFO()
        info.cbSize = ctypes.sizeof(_LASTINPUTINFO)
        if not self._user32.GetLastInputInfo(ctypes.byref(info)):
            return 0.0
        # Both values are 32-bit tick counts; mask to survive the 49.7 day wrap.
        millis = (int(self._kernel32.GetTickCount()) - int(info.dwTime)) & 0xFFFFFFFF
        return millis / 1000.0

    def is_locked(self) -> bool:
        # OpenInputDesktop fails while the lock screen or a secure desktop is active.
        hdesk = self._user32.OpenInputDesktop(0, False, self._DESKTOP_READOBJECTS)
        if not hdesk:
            return True
        self._user32.CloseDesktop(hdesk)
        return False


def create_platform(demo: bool = False) -> Platform:
    if demo:
        return DemoPlatform()
    if sys.platform.startswith("win"):
        try:
            return WindowsPlatform()
        except Exception:
            log.exception("Win32 integration unavailable; tracking disabled")
    else:
        log.warning("Foreground tracking is only implemented for Windows (running on %s)", sys.platform)
    return NullPlatform()
