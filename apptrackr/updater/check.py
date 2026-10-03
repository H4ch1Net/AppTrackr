"""Check GitHub releases for a newer version."""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from urllib.error import URLError
from urllib.request import Request, urlopen

from .. import __version__

log = logging.getLogger(__name__)

DEFAULT_UPDATE_URL = "https://api.github.com/repos/H4ch1Net/AppTrackr/releases/latest"
INSTALLER_NAME = "AppTrackr_Setup.exe"


class UpdateError(Exception):
    """The update feed could not be reached or understood."""


@dataclass(frozen=True)
class UpdateInfo:
    version: str
    download_url: str
    page_url: str
    size: int = 0


def resolve_url(configured: str = "") -> str:
    """Configured URL, then the APPTRACKR_UPDATE_URL environment variable, then the default."""
    return (configured or "").strip() or os.environ.get("APPTRACKR_UPDATE_URL", "").strip() or DEFAULT_UPDATE_URL


def parse_version(text: str) -> tuple[int, ...]:
    """Parse "v1.2.3", "1.2" or "1.2.3-beta" into a comparable tuple of ints."""
    match = re.match(r"\s*v?(\d+(?:\.\d+)*)", text or "")
    if not match:
        raise ValueError(f"Unrecognised version: {text!r}")
    parts = [int(p) for p in match.group(1).split(".")]
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts)


def is_newer(remote: str, current: str = __version__) -> bool:
    return parse_version(remote) > parse_version(current)


def _pick_asset(assets: list[dict]) -> dict | None:
    exes = [a for a in assets if str(a.get("name", "")).lower().endswith(".exe")]
    for asset in exes:
        if asset.get("name") == INSTALLER_NAME:
            return asset
    return exes[0] if exes else None


def check_for_update(url: str = "", current: str = __version__, timeout: float = 10) -> UpdateInfo | None:
    """Return UpdateInfo when a newer release exists, None when up to date.

    Raises UpdateError when the feed cannot be read.
    """
    feed = resolve_url(url)
    req = Request(feed, headers={"Accept": "application/vnd.github+json", "User-Agent": f"AppTrackr/{current}"})
    try:
        with urlopen(req, timeout=timeout) as resp:  # noqa: S310 - https feed chosen by the user
            data = json.loads(resp.read().decode("utf-8"))
    except (URLError, OSError) as exc:
        raise UpdateError(f"Could not reach the update server ({exc}).") from exc
    except ValueError as exc:
        raise UpdateError("The update server returned an unexpected response.") from exc

    tag = str(data.get("tag_name") or "")
    try:
        newer = is_newer(tag, current)
    except ValueError as exc:
        raise UpdateError(f"The latest release has an unrecognised version ({tag!r}).") from exc
    if not newer:
        return None
    asset = _pick_asset(data.get("assets") or [])
    return UpdateInfo(
        version=tag.lstrip("v"),
        download_url=(asset or {}).get("browser_download_url", ""),
        page_url=str(data.get("html_url") or ""),
        size=int((asset or {}).get("size") or 0),
    )
