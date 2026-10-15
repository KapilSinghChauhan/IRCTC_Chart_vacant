from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from app.stations import search_stations


def test_search_by_code_prefix():
    results = search_stations("RNC")
    assert results[0]["code"] == "RNC"
    assert "RANCHI" in results[0]["name"].upper()


def test_search_by_name_as_you_type():
    results = search_stations("ranch")
    codes = [item["code"] for item in results]
    assert "RNC" in codes
    names = " ".join(item["name"].upper() for item in results)
    assert "RANCHI" in names


def test_empty_query_returns_no_dropdown_rows():
    assert search_stations(" ") == []


def test_stations_api_filters_as_typed():
    client = TestClient(app)
    empty = client.get("/api/stations?q=").json()
    assert empty["results"] == []
    ranchi = client.get("/api/stations?q=ranch").json()["results"]
    assert any(item["code"] == "RNC" for item in ranchi)
    gaya = client.get("/api/stations?q=gaya").json()["results"]
    assert gaya[0]["code"] == "GAYA"
