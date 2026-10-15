from __future__ import annotations

from app.integration.auto_client import AutoChartsClient
from app.integration.base import FetchResult
from app.integration.fixture_client import FixtureNotFound
from app.integration.live_client import LiveAccessError
from app.service import analyze_payload


class FakeLive:
    source_kind = "live"

    def __init__(self) -> None:
        self.calls: list[str] = []

    def train_composition(self, train_no, journey_date, boarding_station):
        self.calls.append("train")
        return FetchResult(
            payload={
                "trainNo": train_no,
                "trainName": "KALINDI EXPRESS",
                "from": "DLI",
                "to": "PRYJ",
                "remote": "DLI",
                "error": None,
                "cdd": [
                    {"coachName": "S1", "classCode": "SL", "positionFromEngine": 1, "vacantBerths": 0}
                ],
                "chartStatusResponseDto": {"messageType": "S"},
            },
            retrieved_at="t",
            source="live",
        )

    def train_schedule(self, train_no):
        self.calls.append("schedule")
        return FetchResult(
            payload={
                "stationList": [
                    {"stationCode": "DLI", "distance": "0", "stnSerialNumber": "1"},
                    {"stationCode": "MNQ", "distance": "200", "stnSerialNumber": "2"},
                ]
            },
            retrieved_at="t",
            source="live",
        )

    def coach_composition(self, **kwargs):
        self.calls.append("coach")
        return FetchResult(
            payload={
                "bdd": [
                    {
                        "berthNo": 1,
                        "berthCode": "LB",
                        "enable": True,
                        "bsd": [{"splitNo": 1, "from": "DLI", "to": "MNQ", "quota": "GN", "occupancy": False}],
                    }
                ]
            },
            retrieved_at="t",
            source="live",
        )


def test_auto_client_uses_live_when_fixture_missing(monkeypatch):
    live = FakeLive()
    client = AutoChartsClient(live_factory=lambda: live)
    result = analyze_payload(
        {
            "train_no": "14118",
            "boarding_station": "DLI",
            "destination_station": "MNQ",
            "journey_date": "2026-10-14",
            "classes": ["SL"],
        },
        client=client,
    )
    assert result.ok is True
    assert result.train_name == "KALINDI EXPRESS"
    assert result.results[0].distance_km == 200
    assert "train" in live.calls
    assert "coach" in live.calls


def test_auto_client_keeps_fixture_when_present():
    live = FakeLive()
    client = AutoChartsClient(live_factory=lambda: live)
    result = analyze_payload(
        {
            "train_no": "18609",
            "boarding_station": "RNC",
            "destination_station": "GAYA",
            "journey_date": "2026-10-14",
            "classes": ["1A"],
        },
        client=client,
    )
    assert result.ok is True
    assert result.train_name == "RNC LTT EXP"
    assert live.calls == []


def test_auto_client_skips_live_after_first_failure():
    calls = {"n": 0}

    class Boom:
        def train_composition(self, *args, **kwargs):
            calls["n"] += 1
            raise LiveAccessError("Timeout calling trainComposition")

        def coach_composition(self, **kwargs):
            calls["n"] += 1
            raise LiveAccessError("should not be called")

        def train_schedule(self, *args, **kwargs):
            calls["n"] += 1
            raise LiveAccessError("should not be called")

    client = AutoChartsClient(live_factory=lambda: Boom())
    try:
        client.train_composition("14118", "2026-10-14", "DLI")
    except LiveAccessError:
        pass
    try:
        client.train_composition("14118", "2026-10-14", "DLI")
    except LiveAccessError as exc:
        assert "skipped" in str(exc).lower()
    assert calls["n"] == 1


def test_auto_client_does_not_reuse_another_train_coach_fixture():
    live = FakeLive()
    client = AutoChartsClient(live_factory=lambda: live)
    result = client.coach_composition(
        train_no="14118",
        boarding_station="DLI",
        remote_station="DLI",
        train_source_station="DLI",
        journey_date="2026-10-14",
        coach="S3",
        cls="SL",
    )
    assert result.source == "live"
    assert "coach" in live.calls


def test_auto_client_keeps_fetching_coaches_after_schedule_failure():
    class Live:
        def train_composition(self, *args, **kwargs):
            raise AssertionError("not used")

        def train_schedule(self, train_no):
            raise LiveAccessError("Malformed JSON from schedule")

        def coach_composition(self, **kwargs):
            return FetchResult(payload={"bdd": []}, retrieved_at="t", source="live")

    client = AutoChartsClient(live_factory=lambda: Live())
    try:
        client.train_schedule("14118")
    except LiveAccessError:
        pass
    coach = client.coach_composition(
        train_no="14118",
        boarding_station="DLI",
        remote_station="DLI",
        train_source_station="DLI",
        journey_date="2026-10-14",
        coach="S1",
        cls="SL",
    )
    assert coach.source == "live"
    assert coach.payload == {"bdd": []}


def test_auto_client_combines_missing_fixture_and_live_failure():
    class Boom:
        def train_composition(self, *args, **kwargs):
            raise LiveAccessError("Timeout calling /online-charts/api/trainComposition")

    client = AutoChartsClient(live_factory=lambda: Boom())
    try:
        client.train_composition("14118", "2026-10-14", "DLI")
        raise AssertionError("expected failure")
    except (LiveAccessError, FixtureNotFound) as exc:
        text = str(exc).lower()
        assert "14118" in text
        assert "timeout" in text or "live" in text or "fixture" in text
