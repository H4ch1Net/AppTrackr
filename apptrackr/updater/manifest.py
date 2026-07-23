"""Update manifest and version checking."""

from __future__ import annotations

import os

from .. import __version__

# Single source of truth: the app version lives in apptrackr.__version__.
CURRENT_VERSION = __version__

# Default release feed so update checks work out of the box. Overridable via the
# Settings screen (``update_url`` setting) or the APPTRACKR_UPDATE_URL env var.
UPDATE_URL = "https://api.github.com/repos/H4ch1Net/AppTrackr/releases/latest"


def get_update_url() -> str:
    """Return configured update URL from environment or built-in default."""
    return os.environ.get("APPTRACKR_UPDATE_URL", "").strip() or UPDATE_URL
