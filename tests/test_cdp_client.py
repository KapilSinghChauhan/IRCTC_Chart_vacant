from __future__ import annotations

from pathlib import Path

import pytest

from app.forbidden import FORBIDDEN_PATH_FRAGMENTS
from app.integration.live_client import LiveAccessError
from app.service import select_client


ROOT = Path(__file__).resolve().parents[1]


def test_cdp_module_exists():
    from app.integration.cdp_client import CdpChartsClient

    assert CdpChartsClient.source_kind == "live"


def test_cdp_client_fetches_train_composition_inside_the_page():
    from app.integration.cdp_client import CdpChartsClient

    recorded: list[tuple[str, str, dict | None]] = []

    def page_fetch(method: str, path: str, body: dict | None = None):
        recorded.append((method, path, body))
        return {"cdd": [{"coachName": "S1", "classCode": "SL"}], "trainNo": "14118", "trainName": "KALINDI EXPRESS"}

    client = CdpChartsClient(page_fetch=page_fetch)
    result = client.train_composition("14118", "2026-10-14", "DLI")
    assert recorded == [
        ("POST", "/online-charts/api/trainComposition", {"trainNo": "14118", "jDate": "2026-10-14", "boardingStation": "DLI"})
    ]
    assert result.source == "live"
    assert result.payload["trainName"] == "KALINDI EXPRESS"


def test_cdp_client_fetches_coach_and_schedule_on_allowed_paths_only():
    from app.integration.cdp_client import CdpChartsClient

    recorded: list[str] = []

    def page_fetch(method: str, path: str, body: dict | None = None):
        recorded.append(f"{method} {path}")
        if "coachComposition" in path:
            return {"bdd": []}
        return {"stationList": []}

    client = CdpChartsClient(page_fetch=page_fetch)
    client.coach_composition(
        train_no="14118",
        boarding_station="DLI",
        remote_station="DLI",
        train_source_station="DLI",
        journey_date="2026-10-14",
        coach="S1",
        cls="SL",
    )
    client.train_schedule("14118")
    assert recorded == [
        "POST /online-charts/api/coachComposition",
        "GET /eticketing/protected/mapps1/trnscheduleenquiry/14118",
    ]
    assert all(frag not in path for path in recorded for frag in FORBIDDEN_PATH_FRAGMENTS)


def test_cdp_client_refuses_booking_paths_even_if_injected():
    from app.integration.cdp_client import CdpChartsClient

    def page_fetch(method: str, path: str, body: dict | None = None):
        raise AssertionError("must not reach page fetch")

    client = CdpChartsClient(page_fetch=page_fetch)
    with pytest.raises(RuntimeError, match="Refusing"):
        client._page_call("POST", "/eticketing/protected/mapps1/altAvlEnq/TC", {})


def test_page_fetch_expression_uses_in_page_window_fetch():
    from app.integration.cdp_session import page_fetch_expression

    expression = page_fetch_expression(
        "POST",
        "https://www.irctc.co.in/online-charts/api/trainComposition",
        {"trainNo": "14118"},
        timeout_ms=8000,
    )
    assert "fetch(" in expression
    assert "credentials: 'include'" in expression or 'credentials: "include"' in expression
    assert "Runtime.evaluate" not in expression
    assert "altAvlEnq" not in expression
    assert "bookingInitPayment" not in expression
    assert "trainComposition" in expression


def test_cdp_session_picks_irctc_origin_page():
    from app.integration.cdp_session import pick_irctc_page, pick_page_for_path

    pages = [
        {"type": "page", "url": "https://example.com/", "webSocketDebuggerUrl": "ws://a"},
        {"type": "page", "url": "https://www.irctc.co.in/nget/train-search", "webSocketDebuggerUrl": "ws://b"},
        {"type": "page", "url": "https://www.irctc.co.in/online-charts/", "webSocketDebuggerUrl": "ws://d"},
        {"type": "iframe", "url": "https://www.irctc.co.in/other", "webSocketDebuggerUrl": "ws://c"},
    ]
    chosen = pick_irctc_page(pages)
    assert chosen["webSocketDebuggerUrl"] == "ws://d"
    schedule = pick_page_for_path(pages, "/eticketing/protected/mapps1/trnscheduleenquiry/14118")
    assert schedule["webSocketDebuggerUrl"] == "ws://b"
    charts = pick_page_for_path(pages, "/online-charts/api/trainComposition")
    assert charts["webSocketDebuggerUrl"] == "ws://d"


def test_cdp_session_evaluate_uses_runtime_evaluate(monkeypatch):
    from app.integration import cdp_session

    sent: list[dict] = []

    class FakeSocket:
        def __init__(self, url):
            self.url = url
            self.closed = False

        def send(self, payload: str):
            import json

            sent.append(json.loads(payload))

        def recv(self, timeout=None):
            return '{"id":1,"result":{"result":{"value":{"status":200,"ok":true,"body":{"cdd":[]}}}}}'

        def close(self):
            self.closed = True

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.close()
            return False

    monkeypatch.setattr(cdp_session, "connect_ws", lambda url, timeout: FakeSocket(url))
    value = cdp_session.evaluate("ws://example/devtools/page/1", "1+1", timeout=2)
    assert sent[0]["method"] == "Runtime.evaluate"
    assert sent[0]["params"]["awaitPromise"] is True
    assert sent[0]["params"]["returnByValue"] is True
    assert value["ok"] is True


def test_select_client_live_and_auto_use_cdp(monkeypatch):
    monkeypatch.setenv("DATA_SOURCE", "live")
    from app.integration.cdp_client import CdpChartsClient

    client = select_client()
    assert isinstance(client, CdpChartsClient)

    monkeypatch.setenv("DATA_SOURCE", "auto")
    auto = select_client()
    from app.integration.auto_client import AutoChartsClient

    assert isinstance(auto, AutoChartsClient)
    assert auto._live_factory is CdpChartsClient


def test_cdp_empty_schedule_body_is_live_error():
    from app.integration.cdp_client import CdpChartsClient

    def page_fetch(method, path, body=None):
        return None

    client = CdpChartsClient(page_fetch=page_fetch)
    with pytest.raises(LiveAccessError, match="Malformed JSON"):
        client.train_schedule("14118")


def test_fetch_json_retries_failed_to_fetch_after_reload(monkeypatch):
    from app.integration import cdp_session

    calls = {"n": 0, "reloads": 0}

    monkeypatch.setattr(cdp_session, "window_up", lambda cdp=None, timeout=3.0: True)
    monkeypatch.setattr(cdp_session, "chrome_is_hidden", lambda cdp=None: True)
    monkeypatch.setattr(
        cdp_session,
        "ensure_irctc_page",
        lambda cdp, timeout=20.0, path=None: {"webSocketDebuggerUrl": "ws://page"},
    )

    def fake_evaluate(ws, expression, timeout=30.0):
        calls["n"] += 1
        if calls["n"] == 1:
            return {"error": "TypeError: Failed to fetch"}
        return {"status": 200, "ok": True, "body": {"cdd": [{"coachName": "S1"}]}}

    def fake_reload(cdp, page):
        calls["reloads"] += 1
        return page

    monkeypatch.setattr(cdp_session, "evaluate", fake_evaluate)
    monkeypatch.setattr(cdp_session, "reload_charts_page", fake_reload)
    payload = cdp_session.fetch_json(
        "POST",
        "/online-charts/api/trainComposition",
        {"trainNo": "14118"},
        cdp="http://127.0.0.1:9222",
        timeout=5,
    )
    assert payload["cdd"][0]["coachName"] == "S1"
    assert calls["n"] == 2
    assert calls["reloads"] == 1


def test_cdp_live_error_when_window_missing(monkeypatch):
    from app.integration.cdp_client import CdpChartsClient
    from app.integration import cdp_session

    monkeypatch.setattr(cdp_session, "window_up", lambda cdp=None, timeout=3.0: False)
    monkeypatch.setattr(cdp_session, "chrome_is_hidden", lambda cdp=None: False)
    monkeypatch.setattr(cdp_session, "ensure_window", lambda **kwargs: (False, "no attachable Chrome on CDP"))
    client = CdpChartsClient()
    with pytest.raises(LiveAccessError, match="Hidden Chrome CDP"):
        client.train_composition("14118", "2026-10-14", "DLI")


def test_chrome_is_hidden_requires_xvfb_not_headless(monkeypatch):
    from app.integration import cdp_session

    state = {"args": "--remote-debugging-port=9222"}
    monkeypatch.setattr(cdp_session, "_main_chrome_pid", lambda port: "605014")
    monkeypatch.setattr(cdp_session, "_process_display", lambda pid: ":99")

    def fake_read_bytes(self):
        if "cmdline" in str(self):
            return state["args"].encode()
        raise OSError("unused")

    monkeypatch.setattr(cdp_session.Path, "read_bytes", fake_read_bytes)
    assert cdp_session.chrome_is_hidden("http://127.0.0.1:9222") is True
    state["args"] = "--headless=new --remote-debugging-port=9222"
    assert cdp_session.chrome_is_hidden("http://127.0.0.1:9222") is False
    state["args"] = "--remote-debugging-port=9222"
    monkeypatch.setattr(cdp_session, "_process_display", lambda pid: ":0")
    assert cdp_session.chrome_is_hidden("http://127.0.0.1:9222") is False
