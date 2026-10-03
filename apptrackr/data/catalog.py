"""Knowledge about Windows executables: aliases, friendly names and noise filters.

Shared by the tracker (what to record) and the queries (what to list), so both
agree on which processes count as real apps.
"""

from __future__ import annotations

import re
from pathlib import PurePath

# Shell surfaces and OS overlays. Focus on these is never attributed to an app.
SYSTEM_EXES = frozenset(
    {
        "explorer.exe",
        "searchui.exe",
        "searchhost.exe",
        "searchapp.exe",
        "shellexperiencehost.exe",
        "startmenuexperiencehost.exe",
        "shellhost.exe",
        "textinputhost.exe",
        "lockapp.exe",
        "logonui.exe",
        "widgets.exe",
        "widgetservice.exe",
        "applicationframehost.exe",
        "consent.exe",
        "dwm.exe",
        "taskmgr.exe.mui",
    }
)

# Processes that may own a focused window briefly or appear in launch counts
# but are not apps a person "uses". Hidden from every list.
BACKGROUND_EXES = frozenset(
    {
        "system",
        "registry",
        "idle",
        "taskhostw.exe",
        "runtimebroker.exe",
        "searchindexer.exe",
        "conhost.exe",
        "svchost.exe",
        "sihost.exe",
        "ctfmon.exe",
        "csrss.exe",
        "winlogon.exe",
        "fontdrvhost.exe",
        "smartscreen.exe",
        "securityhealthsystray.exe",
    }
)

BACKGROUND_SUBSTRINGS = ("crashpad", "crashhandler", "updater", "helper")

# Helper processes that host an app's main UI are folded into the app.
EXE_ALIASES = {
    "steamwebhelper.exe": "steam.exe",
    "msedgewebview2.exe": "msedge.exe",
}

NAME_OVERRIDES = {
    "code.exe": "VS Code",
    "code - insiders.exe": "VS Code Insiders",
    "cursor.exe": "Cursor",
    "devenv.exe": "Visual Studio",
    "pycharm64.exe": "PyCharm",
    "idea64.exe": "IntelliJ IDEA",
    "windowsterminal.exe": "Windows Terminal",
    "wt.exe": "Windows Terminal",
    "powershell.exe": "PowerShell",
    "pwsh.exe": "PowerShell",
    "cmd.exe": "Command Prompt",
    "claude.exe": "Claude",
    "chatgpt.exe": "ChatGPT",
    "steam.exe": "Steam",
    "discord.exe": "Discord",
    "slack.exe": "Slack",
    "spotify.exe": "Spotify",
    "obsidian.exe": "Obsidian",
    "notion.exe": "Notion",
    "figma.exe": "Figma",
    "zoom.exe": "Zoom",
    "chrome.exe": "Google Chrome",
    "firefox.exe": "Firefox",
    "msedge.exe": "Microsoft Edge",
    "brave.exe": "Brave",
    "opera.exe": "Opera",
    "vivaldi.exe": "Vivaldi",
    "teams.exe": "Microsoft Teams",
    "ms-teams.exe": "Microsoft Teams",
    "outlook.exe": "Outlook",
    "olk.exe": "Outlook",
    "winword.exe": "Word",
    "excel.exe": "Excel",
    "powerpnt.exe": "PowerPoint",
    "onenote.exe": "OneNote",
    "notepad.exe": "Notepad",
    "notepad++.exe": "Notepad++",
    "vlc.exe": "VLC",
    "obs64.exe": "OBS Studio",
    "taskmgr.exe": "Task Manager",
    "apptrackr.exe": "AppTrackr",
}


def canonical_exe(exe_name: str) -> str:
    """Lowercase, strip directories and fold helper aliases into their app."""
    key = PurePath((exe_name or "").strip()).name.lower()
    return EXE_ALIASES.get(key, key)


def is_system(exe_name: str) -> bool:
    return canonical_exe(exe_name) in SYSTEM_EXES


def is_background(exe_name: str) -> bool:
    name = canonical_exe(exe_name)
    if not name or name in BACKGROUND_EXES:
        return True
    return any(token in name for token in BACKGROUND_SUBSTRINGS)


def is_trackable(exe_name: str) -> bool:
    """True when focus on this executable should be recorded."""
    name = canonical_exe(exe_name)
    return bool(name) and not is_system(name) and not is_background(name)


def is_listable(exe_name: str) -> bool:
    """True when the app should appear in lists and totals."""
    return is_trackable(exe_name)


def friendly_name(exe_name: str) -> str:
    """Turn an executable name into a readable label ("my_tool.exe" -> "My Tool")."""
    key = canonical_exe(exe_name)
    if not key:
        return "Unknown App"
    if key in NAME_OVERRIDES:
        return NAME_OVERRIDES[key]
    raw = key[:-4] if key.endswith(".exe") else key
    raw = re.sub(r"[_\-.]+", " ", raw)
    raw = re.sub(r"\s+", " ", raw).strip()
    if not raw:
        return "Unknown App"
    return " ".join(part[:1].upper() + part[1:] for part in raw.split(" "))


def display_name(app: dict) -> str:
    """Name to show for an app row, falling back to a friendly exe name."""
    shown = (app.get("display_name") or "").strip()
    exe = (app.get("exe_name") or "").strip().lower()
    if not shown or shown.lower() == exe:
        return friendly_name(exe)
    return shown
