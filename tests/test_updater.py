import io
import json

import pytest

from apptrackr.updater import check


def test_parse_version():
    assert check.parse_version("v1.2") == (1, 2, 0)
    assert check.parse_version("1.10.3-beta") == (1, 10, 3)
    assert check.is_newer("v1.10.0", "1.9.9")
    assert not check.is_newer("1.1.0", "1.1.0")
    with pytest.raises(ValueError):
        check.parse_version("latest")


def _fake_urlopen(payload):
    class Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    return lambda req, timeout=0: Resp(json.dumps(payload).encode())


def test_check_reports_newer_release(monkeypatch):
    payload = {
        "tag_name": "v9.0.0",
        "html_url": "https://example/rel",
        "assets": [
            {"name": "AppTrackr_Portable.zip", "browser_download_url": "zip"},
            {"name": "AppTrackr_Setup.exe", "browser_download_url": "exe", "size": 42},
        ],
    }
    monkeypatch.setattr(check, "urlopen", _fake_urlopen(payload))
    info = check.check_for_update("https://feed")
    assert info == check.UpdateInfo("9.0.0", "exe", "https://example/rel", 42)


def test_check_up_to_date(monkeypatch):
    monkeypatch.setattr(check, "urlopen", _fake_urlopen({"tag_name": "v0.1.0"}))
    assert check.check_for_update("https://feed") is None


def test_check_errors_are_not_reported_as_up_to_date(monkeypatch):
    def boom(req, timeout=0):
        raise OSError("offline")

    monkeypatch.setattr(check, "urlopen", boom)
    with pytest.raises(check.UpdateError):
        check.check_for_update("https://feed")


def test_resolve_url(monkeypatch):
    monkeypatch.delenv("APPTRACKR_UPDATE_URL", raising=False)
    assert check.resolve_url("") == check.DEFAULT_UPDATE_URL
    monkeypatch.setenv("APPTRACKR_UPDATE_URL", "https://env")
    assert check.resolve_url("") == "https://env"
    assert check.resolve_url(" https://cfg ") == "https://cfg"
