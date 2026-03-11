"""Check for updates from a remote manifest."""

from __future__ import annotations

import json
import logging
from urllib.request import urlopen, Request
from urllib.error import URLError

from .manifest import CURRENT_VERSION, get_update_url

log = logging.getLogger(__name__)


def parse_version(v: str) -> tuple[int, ...]:
    return tuple(int(x) for x in v.strip().lstrip("v").split("."))


def check_for_update(update_url: str | None = None) -> dict | None:
    """Return {'version': str, 'url': str} if an update is available, else None."""
    resolved_url = (update_url or get_update_url()).strip()
    if not resolved_url:
        return None
    try:
        req = Request(resolved_url, headers={"Accept": "application/json"})
        with urlopen(req, timeout=10) as resp:  # noqa: S310 — URL is configured by the developer
            data = json.loads(resp.read())
        remote_version = data.get("tag_name", "").lstrip("v")
        if parse_version(remote_version) > parse_version(CURRENT_VERSION):
            assets = data.get("assets", [])
            download_url = ""
            for asset in assets:
                if asset.get("name", "").endswith(".exe"):
                    download_url = asset["browser_download_url"]
                    break
            return {"version": remote_version, "url": download_url}
    except (URLError, ValueError, KeyError):
        log.debug("Update check failed", exc_info=True)
    return None
