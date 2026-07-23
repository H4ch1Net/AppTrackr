"""Tests for data export/backup and the update version checker."""

from __future__ import annotations

import csv
import json

import pytest

from apptrackr.data import db, export, queries
from apptrackr.updater import check


def _seed():
    app_id = queries.get_or_create_app("code.exe")
    day = queries.today_str()
    queries.add_focused_time(day, app_id, 1234)
    queries.increment_opens(day, app_id)
    return app_id, day


class TestExport:
    def test_export_csv(self, tmp_path):
        _seed()
        out = tmp_path / "out.csv"
        export.export_csv(out)
        rows = list(csv.DictReader(out.open(encoding="utf-8")))
        assert len(rows) == 1
        assert rows[0]["exe_name"] == "code.exe"
        assert rows[0]["focused_ms"] == "1234"

    def test_export_json(self, tmp_path):
        _seed()
        out = tmp_path / "out.json"
        export.export_json(out)
        data = json.loads(out.read_text(encoding="utf-8"))
        assert data[0]["display_name"] == "VS Code"

    def test_backup_and_restore_roundtrip(self, tmp_path):
        _seed()
        backup = tmp_path / "backup.sqlite"
        export.backup_db(backup)
        assert backup.exists() and backup.stat().st_size > 0
        # Restore over the live DB should not raise.
        db.close_connection()
        export.restore_db(backup)


class TestParseVersion:
    @pytest.mark.parametrize(
        "raw, expected",
        [
            ("1.2.3", (1, 2, 3)),
            ("v1.2.3", (1, 2, 3)),
            ("V2.0", (2, 0)),
            ("1.2.0-beta", (1, 2, 0)),
            ("1.2.0+build.7", (1, 2, 0)),
            ("", (0,)),
            ("garbage", (0,)),
            ("1.0.0rc1", (1, 0, 0)),
        ],
    )
    def test_parse(self, raw, expected):
        assert check.parse_version(raw) == expected

    def test_ordering(self):
        assert check.parse_version("1.2.0") > check.parse_version("1.1.9")
        assert check.parse_version("2.0.0") > check.parse_version("1.9.9")
        assert not (check.parse_version("") > check.parse_version("1.0.0"))


class TestManifest:
    def test_version_matches_package(self):
        from apptrackr import __version__
        from apptrackr.updater import manifest
        assert manifest.CURRENT_VERSION == __version__

    def test_default_update_url_configured(self):
        from apptrackr.updater import manifest
        assert manifest.get_update_url().startswith("https://api.github.com/")

    def test_env_override_wins(self, monkeypatch):
        from apptrackr.updater import manifest
        monkeypatch.setenv("APPTRACKR_UPDATE_URL", "https://example.test/feed")
        assert manifest.get_update_url() == "https://example.test/feed"


class TestCheckForUpdate:
    def test_empty_url_returns_none(self):
        assert check.check_for_update("") is None

    def test_detects_newer_version(self, monkeypatch):
        payload = {
            "tag_name": "v9.9.9",
            "assets": [{"name": "AppTrackr_Setup.exe", "browser_download_url": "http://x/app.exe"}],
        }

        class FakeResp:
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def read(self): return json.dumps(payload).encode()

        monkeypatch.setattr(check, "urlopen", lambda *a, **k: FakeResp())
        info = check.check_for_update("http://example/releases/latest")
        assert info == {"version": "9.9.9", "url": "http://x/app.exe"}

    def test_ignores_same_or_older_version(self, monkeypatch):
        payload = {"tag_name": "v0.0.1", "assets": []}

        class FakeResp:
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def read(self): return json.dumps(payload).encode()

        monkeypatch.setattr(check, "urlopen", lambda *a, **k: FakeResp())
        assert check.check_for_update("http://example/releases/latest") is None
