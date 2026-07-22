"""Check for updates from a remote manifest."""

from __future__ import annotations

import json
import logging
from urllib.request import urlopen, Request
from urllib.error import URLError

from .manifest import CURRENT_VERSION, get_update_url

log = logging.getLogger(__name__)


def parse_version(v: str) -> tuple[int, ...]:
    """Parse a semver-ish string into a comparable tuple.

    Tolerates a leading ``v``, pre-release/build suffixes (``1.2.0-beta``),
    empty or missing components, and stray whitespace. Non-numeric parts are
    treated as ``0`` so a malformed remote version can never crash the check.
    """
    core = (v or "").strip().lstrip("vV").split("-")[0].split("+")[0]
    parts: list[int] = []
    for chunk in core.split("."):
        leading = ""
        for c in chunk:
            if not c.isdigit():
                break
            leading += c
        parts.append(int(leading) if leading else 0)
    return tuple(parts) or (0,)


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
