from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def test_health_and_analyze_fixture_consistency():
    client = TestClient(app)
    health = client.get("/api/health").json()
    assert health["read_only"] is True
    assert health["booking_disabled"] is True

    response = client.post(
        "/api/analyze",
        json={
            "train_no": "18609",
            "boarding_station": "RNC",
            "destination_station": "GAYA",
            "journey_date": "2026-10-14",
            "classes": ["1A"],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["data_source"] == "fixture"
    assert body["train_name"] == "RNC LTT EXP"
    table_classes = {row["vacancy_class"] for row in body["results"]}
    layout_classes = {cell["vacancy_class"] for coach in body["coaches"] for cell in coach["berths"]}
    assert table_classes == layout_classes
    assert body["coaches"][0]["coach_name"] == "H1"
    assert len(body["coaches"][0]["berths"]) == len([r for r in body["results"] if r["coach_name"] == "H1"])
    assert body["coaches"][0]["vacant_berths_trusted"] is False

    bad = client.post(
        "/api/analyze",
        json={
            "train_no": "18609",
            "boarding_station": "GAYA",
            "destination_station": "RNC",
            "journey_date": "2026-10-14",
            "classes": ["1A"],
        },
    ).json()
    assert bad["ok"] is False
    assert any("precedes" in e for e in bad["errors"])


def test_analyze_unexpected_exception_returns_json_error(monkeypatch):
    from app import main as main_mod

    def boom(payload):
        raise RuntimeError("cdp socket exploded")

    monkeypatch.setattr(main_mod, "analyze_payload", boom)
    client = TestClient(app)
    response = client.post(
        "/api/analyze",
        json={
            "train_no": "14118",
            "boarding_station": "DLI",
            "destination_station": "MNQ",
            "journey_date": "2026-10-14",
            "classes": ["SL"],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert any("exploded" in e.lower() or "failed" in e.lower() for e in body["errors"])
    assert "Internal Server Error" not in response.text


def test_unknown_train_api_does_not_look_like_empty_filters():
    client = TestClient(app)
    body = client.post(
        "/api/analyze",
        json={
            "train_no": "14118",
            "boarding_station": "DLI",
            "destination_station": "MNQ",
            "journey_date": "2026-10-14",
            "classes": ["1A"],
        },
    ).json()
    assert body["ok"] is False
    assert body["results"] == []
    assert any("14118" in e for e in body["errors"])
    assert all("no berths matched" not in e.lower() for e in body["errors"])
