from __future__ import annotations

import json
from pathlib import Path

from app.integration.fixture_client import FixtureChartsClient, FixtureNotFound
from app.models import DataSourceKind, VacancyClass
from app.service import analyze_payload, normalize_train_composition

ROOT = Path(__file__).resolve().parents[1]


class MappingClient(FixtureChartsClient):
    def __init__(self, mapping: dict[str, dict]):
        super().__init__(ROOT / "fixtures" / "synthetic")
        self.mapping = mapping
        self.calls: list[str] = []

    def train_composition(self, train_no, journey_date, boarding_station):
        self.calls.append("trainComposition")
        if "train" in self.mapping:
            from app.integration.base import FetchResult

            return FetchResult(payload=self.mapping["train"], retrieved_at="t", source="fixture")
        return super().train_composition(train_no, journey_date, boarding_station)

    def coach_composition(self, **kwargs):
        self.calls.append(f"coachComposition:{kwargs['coach']}")
        if "coach" in self.mapping:
            from app.integration.base import FetchResult

            return FetchResult(payload=self.mapping["coach"], retrieved_at="t", source="fixture")
        return super().coach_composition(**kwargs)

    def train_schedule(self, train_no):
        self.calls.append("trnscheduleenquiry")
        if "schedule" in self.mapping:
            from app.integration.base import FetchResult

            return FetchResult(payload=self.mapping["schedule"], retrieved_at="t", source="fixture")
        return super().train_schedule(train_no)


def test_train_composition_missing_cdd():
    meta, coaches, warnings = normalize_train_composition({"trainNo": "1"})
    assert coaches == []
    assert any("cdd" in w for w in warnings)


def test_coach_missing_bdd_does_not_crash():
    client = MappingClient(
        {
            "coach": {"coachName": "S1", "error": None},
        }
    )
    result = analyze_payload(
        {
            "train_no": "99999",
            "boarding_station": "AAA",
            "destination_station": "DDD",
            "journey_date": "2026-10-14",
            "classes": ["SL"],
        },
        client=client,
    )
    assert result.ok is True or result.errors == []
    assert result.coaches
    assert result.coaches[0].fetch_ok is False
    assert result.coaches[0].error == "missing bdd[]"


def test_unknown_train_reports_composition_failure_not_filter_miss():
    result = analyze_payload(
        {
            "train_no": "14118",
            "boarding_station": "DLI",
            "destination_station": "MNQ",
            "journey_date": "2026-10-14",
            "classes": ["1A"],
        },
        client=FixtureChartsClient(),
    )
    assert result.ok is False
    assert result.results == []
    assert any("14118" in e for e in result.errors)
    assert any("composition" in e.lower() or "chart" in e.lower() for e in result.errors)
    joined = " ".join(result.errors).lower()
    assert "filters" not in joined


def test_selected_class_missing_falls_back_to_discovered_classes():
    result = analyze_payload(
        {
            "train_no": "18609",
            "boarding_station": "RNC",
            "destination_station": "GAYA",
            "journey_date": "2026-10-14",
            "classes": ["2S"],
        }
    )
    assert result.ok is True
    assert result.results
    assert any("not on this train" in w.lower() or "discovered classes" in w.lower() for w in result.warnings)
    assert {row.class_code for row in result.results} <= set(result.discovered_classes)


def test_stale_or_integration_failure_is_reported():
    class Boom(FixtureChartsClient):
        source_kind = "fixture"

        def train_composition(self, *args, **kwargs):
            raise OSError("upstream timeout")

    result = analyze_payload(
        {
            "train_no": "99999",
            "boarding_station": "AAA",
            "destination_station": "DDD",
            "journey_date": "2026-10-14",
            "classes": ["SL"],
        },
        client=Boom(ROOT / "fixtures" / "synthetic"),
    )
    assert result.ok is False
    assert any("Train composition failed" in e for e in result.errors)


def test_fixture_mode_is_labelled_not_live():
    result = analyze_payload(
        {
            "train_no": "99999",
            "boarding_station": "AAA",
            "destination_station": "DDD",
            "journey_date": "2026-10-14",
            "classes": ["SL"],
        },
        client=FixtureChartsClient(ROOT / "fixtures" / "synthetic"),
    )
    assert result.data_source is DataSourceKind.fixture
    assert "fixture" in result.freshness_label
    assert result.ok is True
    top = result.results[0]
    assert top.berth_no == 3
    assert top.vacancy_class is VacancyClass.confirmed_eligible
    assert top.distance_km == 40
    gap_berth = next(item for item in result.results if item.berth_no == 4)
    assert gap_berth.consecutive_segments == 1
    assert gap_berth.vacancy_class is VacancyClass.partial


def test_no_booking_paths_are_invoked():
    client = MappingClient({})
    analyze_payload(
        {
            "train_no": "99999",
            "boarding_station": "AAA",
            "destination_station": "DDD",
            "journey_date": "2026-10-14",
            "classes": ["SL"],
        },
        client=client,
    )
    assert all("book" not in call.lower() and "payment" not in call.lower() for call in client.calls)
    assert "trainComposition" in client.calls
    assert any(call.startswith("coachComposition") for call in client.calls)


def test_destination_before_boarding_is_an_error():
    result = analyze_payload(
        {
            "train_no": "18609",
            "boarding_station": "LTT",
            "destination_station": "RNC",
            "journey_date": "2026-10-14",
            "classes": ["1A"],
        },
        client=FixtureChartsClient(),
    )
    assert result.ok is False
    assert any("precedes" in e for e in result.errors)


def test_missing_schedule_falls_back_without_inventing_km():
    class NoKm(FixtureChartsClient):
        def train_schedule(self, train_no):
            raise FixtureNotFound("no schedule")

    result = analyze_payload(
        {
            "train_no": "99999",
            "boarding_station": "AAA",
            "destination_station": "DDD",
            "journey_date": "2026-10-14",
            "classes": ["SL"],
        },
        client=NoKm(ROOT / "fixtures" / "synthetic"),
    )
    assert result.ok is True
    assert result.ranking_mode.value == "segments"
    assert any("kilometre" in w.lower() or "reconstructed" in w.lower() for w in result.warnings)
    assert result.results
    assert all(row.distance_km is None for row in result.results)


def test_captured_train_does_not_use_synthetic_coach_stations():
    result = analyze_payload(
        {
            "train_no": "18609",
            "boarding_station": "RNC",
            "destination_station": "GAYA",
            "journey_date": "2026-10-14",
            "classes": ["SL"],
        }
    )
    assert result.ok is True
    s3 = next(c for c in result.coaches if c.coach_name == "S3")
    assert s3.fetch_ok is True
    s1 = next(c for c in result.coaches if c.coach_name == "S1")
    assert s1.fetch_ok is False
    assert all("AAA" not in w for w in result.warnings)


def test_captured_fixture_shape_loads():
    payload = json.loads((ROOT / "fixtures" / "train_composition_18609.json").read_text())
    _, coaches, _ = normalize_train_composition(payload)
    assert {c.class_code for c in coaches} == {"1A", "2A", "3A", "SL"}
