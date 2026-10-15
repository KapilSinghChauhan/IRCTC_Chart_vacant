from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.forbidden import FORBIDDEN_PATH_FRAGMENTS
from app.integration.live_client import LiveAccessError, LiveChartsClient


def test_live_client_allows_charts_without_session(monkeypatch):
    monkeypatch.delenv("IRCTC_COOKIES", raising=False)
    monkeypatch.delenv("IRCTC_COOKIE_FILE", raising=False)
    client = LiveChartsClient()
    assert "cookie" not in {k.lower() for k in client._headers}


def test_live_client_posts_only_verified_read_paths(monkeypatch):
    monkeypatch.setenv("IRCTC_COOKIES", "session=test")
    recorded: list[str] = []

    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.headers = {"content-type": "application/json", "set-cookie": "should-not-log"}
    fake_response.json.return_value = {"cdd": [], "trainNo": "18609"}

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, url, json=None, headers=None):
            recorded.append(url)
            assert "cookie" in headers
            return fake_response

        def get(self, url, headers=None):
            recorded.append(url)
            fake_response.json.return_value = {"stationList": []}
            return fake_response

    with patch("app.integration.live_client.httpx.Client", FakeClient):
        client = LiveChartsClient()
        client.train_composition("18609", "2026-10-14", "RNC")
        client.coach_composition("18609", "RNC", "RNC", "RNC", "2026-10-14", "S3", "SL")
        client.train_schedule("18609")

    assert all(frag not in url for url in recorded for frag in FORBIDDEN_PATH_FRAGMENTS)
    assert any("trainComposition" in url for url in recorded)
    assert any("coachComposition" in url for url in recorded)
