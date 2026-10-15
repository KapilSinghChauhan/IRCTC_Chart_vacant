from __future__ import annotations

from app.engine import longest_eligible_run, normalize_berth_segments, ranking_key
from app.models import RankingMode, VacancyClass
from tests.helpers import seg, tiny_route


def _run(raw, journey=("AAA", "DDD"), distance=True):
    route = tiny_route()
    segs, _ = normalize_berth_segments(raw, route, journey[0], journey[1])
    return longest_eligible_run(segs, route, journey[0], journey[1], distance_available=distance)


def test_merges_adjacent_eligible_segments():
    run = _run(
        [
            seg("AAA", "BBB", False, 1),
            seg("BBB", "CCC", False, 2),
            seg("CCC", "DDD", True, 3),
        ]
    )
    assert run.from_station == "AAA"
    assert run.to_station == "CCC"
    assert run.consecutive_segments == 2
    assert run.distance_km == 25
    assert run.vacancy_class is VacancyClass.partial
    assert run.covers_full_journey is False


def test_does_not_merge_across_gap():
    run = _run(
        [
            seg("AAA", "BBB", False, 1),
            seg("BBB", "CCC", True, 2),
            seg("CCC", "DDD", False, 3),
        ]
    )
    assert run.from_station == "CCC"
    assert run.to_station == "DDD"
    assert run.consecutive_segments == 1
    assert run.distance_km == 15


def test_longest_run_prefers_greater_distance():
    run = _run(
        [
            seg("AAA", "BBB", False, 1),
            seg("BBB", "CCC", True, 2),
            seg("CCC", "DDD", False, 3),
        ]
    )
    assert run.distance_km == 15
    longer = _run(
        [
            seg("AAA", "BBB", False, 1),
            seg("BBB", "CCC", False, 2),
            seg("CCC", "DDD", True, 3),
        ]
    )
    assert longer.distance_km == 25


def test_full_journey_coverage():
    run = _run(
        [
            seg("AAA", "BBB", False, 1),
            seg("BBB", "CCC", False, 2),
            seg("CCC", "DDD", False, 3),
        ]
    )
    assert run.covers_full_journey is True
    assert run.coverage_percent == 100
    assert run.vacancy_class is VacancyClass.confirmed_eligible
    assert run.distance_km == 40


def test_occupied_entire_journey():
    run = _run([seg("AAA", "DDD", True, 1)])
    assert run.vacancy_class is VacancyClass.occupied
    assert run.consecutive_segments == 0
    assert run.from_station is None


def test_unknown_status_not_labelled_available():
    run = _run([seg("AAA", "DDD", None, 1)])
    assert run.vacancy_class is VacancyClass.unknown
    assert run.consecutive_segments == 0


def test_kilometre_first_ranking():
    short = _run([seg("AAA", "BBB", False, 1), seg("BBB", "DDD", True, 2)])
    long = _run([seg("AAA", "CCC", False, 1), seg("CCC", "DDD", True, 2)])
    ordered = sorted(
        [(short, "S1", 2), (long, "S1", 1)],
        key=lambda item: ranking_key(*item),
    )
    assert ordered[0][0].distance_km == 25
    assert ordered[1][0].distance_km == 10


def test_segment_count_secondary_ranking():
    one = _run([seg("AAA", "DDD", False, 1)])
    two = _run(
        [
            seg("AAA", "BBB", False, 1),
            seg("BBB", "DDD", False, 2),
        ]
    )
    assert one.distance_km == two.distance_km == 40
    ordered = sorted(
        [(one, "S1", 1), (two, "S1", 2)],
        key=lambda item: ranking_key(*item),
    )
    assert ordered[0][0].consecutive_segments == 2
    assert ordered[1][0].consecutive_segments == 1


def test_missing_distance_fallback_does_not_invent_km():
    run = _run(
        [
            seg("AAA", "BBB", False, 1),
            seg("BBB", "CCC", False, 2),
        ],
        distance=False,
    )
    assert run.distance_km is None
    assert run.ranking_mode is RankingMode.segments
    assert "unavailable" in run.distance_source
    assert run.consecutive_segments == 2


def test_deterministic_tie_break_uses_coach_then_berth():
    run_a = _run([seg("AAA", "DDD", False, 1)])
    run_b = _run([seg("AAA", "DDD", False, 1)])
    ordered = sorted(
        [(run_a, "S2", 4), (run_b, "S1", 9), (run_a, "S1", 2)],
        key=lambda item: ranking_key(*item),
    )
    assert [item[1:] for item in ordered] == [("S1", 2), ("S1", 9), ("S2", 4)]


def test_restricts_analysis_to_requested_interval():
    run = _run(
        [
            seg("AAA", "BBB", False, 1),
            seg("BBB", "CCC", False, 2),
            seg("CCC", "DDD", False, 3),
        ],
        journey=("BBB", "CCC"),
    )
    assert run.from_station == "BBB"
    assert run.to_station == "CCC"
    assert run.distance_km == 15
    assert run.covers_full_journey is True
