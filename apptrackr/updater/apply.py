"""Download and launch an installer."""

from __future__ import annotations

import logging
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from typing import Callable
from urllib.request import Request, urlopen

from .. import __version__

log = logging.getLogger(__name__)


class DownloadCancelled(Exception):
    pass


def download(
    url: str,
    progress: Callable[[int, int], None] | None = None,
    cancel: threading.Event | None = None,
    dest_dir: Path | None = None,
) -> Path:
    """Stream *url* to a temp file, reporting (received, total) bytes."""
    dest = (dest_dir or Path(tempfile.gettempdir())) / "AppTrackr_Setup.exe"
    partial = dest.with_suffix(".part")
    req = Request(url, headers={"User-Agent": f"AppTrackr/{__version__}"})
    try:
        with urlopen(req, timeout=60) as resp, open(partial, "wb") as out:  # noqa: S310
            total = int(resp.headers.get("Content-Length") or 0)
            received = 0
            while True:
                if cancel is not None and cancel.is_set():
                    raise DownloadCancelled()
                chunk = resp.read(256 * 1024)
                if not chunk:
                    break
                out.write(chunk)
                received += len(chunk)
                if progress:
                    progress(received, total)
        if total and received != total:
            raise OSError(f"Download incomplete ({received} of {total} bytes)")
    except BaseException:
        partial.unlink(missing_ok=True)
        raise
    partial.replace(dest)
    return dest


def launch_installer(path: Path) -> None:
    """Start the installer detached from this process."""
    flags = 0
    if sys.platform.startswith("win"):
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
    subprocess.Popen([str(path)], creationflags=flags, close_fds=True)  # noqa: S603
