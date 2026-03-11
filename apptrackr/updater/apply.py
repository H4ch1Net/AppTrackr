"""Apply downloaded updates."""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.request import urlopen, Request

log = logging.getLogger(__name__)


def download_and_apply(url: str) -> str | None:
    """Download installer from *url* and launch it, then exit the current app."""
    if not url:
        return None
    try:
        req = Request(url)
        with urlopen(req, timeout=120) as resp:  # noqa: S310 — URL comes from configured update manifest
            data = resp.read()

        tmp = Path(tempfile.gettempdir()) / "apptrackr_update.exe"
        tmp.write_bytes(data)

        # Launch installer and exit
        subprocess.Popen([str(tmp)], creationflags=subprocess.DETACHED_PROCESS)  # noqa: S603
        return str(tmp)
    except Exception:
        log.exception("Failed to download/apply update")
        return None
