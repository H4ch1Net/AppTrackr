"""Update manifest and version checking."""

from __future__ import annotations

import os

CURRENT_VERSION = "1.0.0"
UPDATE_URL = ""  # Set to GitHub releases URL when ready, e.g.: https://api.github.com/repos/user/apptrackr/releases/latest


def get_update_url() -> str:
	"""Return configured update URL from environment or built-in default."""
	return os.environ.get("APPTRACKR_UPDATE_URL", "").strip() or UPDATE_URL
