import os
import tempfile

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# Never let a test fall back to the real per-user data folder.
os.environ["APPTRACKR_DATA_DIR"] = tempfile.mkdtemp(prefix="apptrackr-tests-")

from apptrackr import paths  # noqa: E402
from apptrackr.data import db  # noqa: E402


@pytest.fixture(autouse=True)
def temp_db(tmp_path):
    """Every test gets an empty, migrated database in a temp directory."""
    paths.set_data_dir(tmp_path)
    db.configure(tmp_path / "data.sqlite")
    db.init_db()
    from apptrackr.ui import motion

    motion.force(None)
    motion._cached = None
    yield tmp_path / "data.sqlite"
    motion.force(None)
    motion._cached = None
    db.close()
    db.configure(None)
    paths.set_data_dir(None)
