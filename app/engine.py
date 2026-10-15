from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.models import (
    Confidence,
    RankingMode,
    SegmentRecord,
    StationPoint,
    VacancyClass,
)
from app.route import interval_distance_km, station_index
from app.vacancy import occupancy_status


@dataclass
class LongestRun:
    from_station: str | None
    to_station: str | None
    consecutive_segments: int
    distance_km: float | None
    coverage_percent: float | None
    covers_full_journey: bool
    vacancy_class: VacancyClass
    confidence: Confidence
    warnings: list[str]
    missing_data_reasons: list[str]
    segments: list[SegmentRecord]
    ranking_mode: RankingMode
    ranking_rationale: str
    distance_source: str


def _clip_segment_to_journey(
    seg_from_idx: int,
    seg_to_idx: int,
    journey_from_idx: int,
    journey_to_idx: int,
) -> tuple[int, int] | None:
    start = max(seg_from_idx, journey_from_idx)
    end = min(seg_to_idx, journey_to_idx)
    if end <= start:
        return None
    return start, end


def normalize_berth_segments(
    raw_segments: list[dict[str, Any]] | None,
    route: list[StationPoint],
    journey_from: str,
    journey_to: str,
) -> tuple[list[SegmentRecord], list[str]]:
    warnings: list[str] = []
    by_code = station_index(route)
    if journey_from not in by_code or journey_to not in by_code:
        return [], ["journey stations missing from route"]
    j_from = by_code[journey_from].index
    j_to = by_code[journey_to].index
    records: list[SegmentRecord] = []
    if not isinstance(raw_segments, list) or not raw_segments:
        return [], ["berth has no bsd[] segment array"]

    prepared: list[tuple[int, dict[str, Any]]] = []
    for offset, item in enumerate(raw_segments):
        if not isinstance(item, dict):
            warnings.append("non-object segment skipped")
            continue
        split = item.get("splitNo")
        order = split if isinstance(split, int) else offset
        prepared.append((order, item))
    prepared.sort(key=lambda pair: pair[0])

    last_to: str | None = None
    last_to_idx: int | None = None
    for _order, item in prepared:
        frm = str(item.get("from") or "").strip().upper()
        to = str(item.get("to") or "").strip().upper()
        if frm not in by_code or to not in by_code:
            warnings.append(f"segment {frm}->{to} not on verified route")
            records.append(
                SegmentRecord(
                    split_no=item.get("splitNo") if isinstance(item.get("splitNo"), int) else None,
                    from_station=frm,
                    to_station=to,
                    quota=item.get("quota"),
                    occupancy_raw=item.get("occupancy"),
                    status="unknown",
                    reason="station not on verified route",
                )
            )
            last_to = None
            last_to_idx = None
            continue
        frm_idx = by_code[frm].index
        to_idx = by_code[to].index
        if to_idx <= frm_idx:
            warnings.append(f"segment {frm}->{to} is not forward on the route")
            last_to = None
            last_to_idx = None
            continue
        if last_to is not None and frm != last_to:
            warnings.append(f"gap or non-adjacent segments at {last_to} -> {frm}")
        if last_to_idx is not None and frm_idx < last_to_idx:
            warnings.append(f"overlapping or reversed segment at {frm}")
        status, occ_bool, reason = occupancy_status(item.get("occupancy"))
        clip = _clip_segment_to_journey(frm_idx, to_idx, j_from, j_to)
        if clip is None:
            last_to = to
            last_to_idx = to_idx
            continue
        clip_from_idx, clip_to_idx = clip
        records.append(
            SegmentRecord(
                split_no=item.get("splitNo") if isinstance(item.get("splitNo"), int) else None,
                from_station=frm,
                to_station=to,
                quota=item.get("quota"),
                occupancy_raw=item.get("occupancy"),
                occupancy_bool=occ_bool,
                from_index=frm_idx,
                to_index=to_idx,
                eligible=status == "eligible",
                status=status,  # type: ignore[arg-type]
                clipped_from=route[clip_from_idx].code,
                clipped_to=route[clip_to_idx].code,
                reason=reason,
            )
        )
        last_to = to
        last_to_idx = to_idx
    return records, warnings


def longest_eligible_run(
    segments: list[SegmentRecord],
    route: list[StationPoint],
    journey_from: str,
    journey_to: str,
    distance_available: bool,
) -> LongestRun:
    warnings: list[str] = []
    missing: list[str] = []
    by_code = station_index(route)
    journey_km = interval_distance_km(route, journey_from, journey_to)
    ranking_mode = RankingMode.kilometres if distance_available and journey_km is not None else RankingMode.segments
    distance_source = (
        "schedule.stationList[].distance"
        if ranking_mode is RankingMode.kilometres
        else "unavailable; ranking by consecutive segments"
    )

    if not segments:
        missing.append("no usable journey segments")
        return LongestRun(
            from_station=None,
            to_station=None,
            consecutive_segments=0,
            distance_km=None,
            coverage_percent=None,
            covers_full_journey=False,
            vacancy_class=VacancyClass.unknown,
            confidence=Confidence.none,
            warnings=warnings,
            missing_data_reasons=missing,
            segments=segments,
            ranking_mode=ranking_mode,
            ranking_rationale="No segment data; berth is not labelled available.",
            distance_source=distance_source,
        )

    # Walk in route order using clipped interval endpoints.
    ordered = sorted(
        [s for s in segments if s.clipped_from and s.clipped_to],
        key=lambda s: (by_code[s.clipped_from].index if s.clipped_from in by_code else 10_000, s.split_no or 0),
    )

    best: list[SegmentRecord] = []
    current: list[SegmentRecord] = []

    def current_score(run: list[SegmentRecord]) -> tuple[float, int]:
        if not run:
            return (0.0, 0)
        start = run[0].clipped_from
        end = run[-1].clipped_to
        km = interval_distance_km(route, start or "", end or "") if distance_available else None
        return (km or 0.0, len(run))

    def consider(run: list[SegmentRecord]) -> None:
        nonlocal best
        if current_score(run) > current_score(best):
            best = list(run)

    for seg in ordered:
        if seg.status == "eligible":
            if current and current[-1].clipped_to != seg.clipped_from:
                consider(current)
                current = []
            if current and current[-1].clipped_to == seg.clipped_from:
                current.append(seg)
            else:
                current = [seg]
        else:
            consider(current)
            current = []
    consider(current)

    unknown_in_journey = any(s.status == "unknown" for s in ordered)
    occupied_in_journey = any(s.status == "occupied" for s in ordered)
    eligible_in_journey = any(s.status == "eligible" for s in ordered)

    if not best:
        if unknown_in_journey and not eligible_in_journey:
            vacancy = VacancyClass.unknown
            confidence = Confidence.none
            rationale = "Journey interval has unknown occupancy; berth is not labelled available."
        elif occupied_in_journey:
            vacancy = VacancyClass.occupied
            confidence = Confidence.high if not unknown_in_journey else Confidence.low
            rationale = "No consecutive eligible run inside the requested journey."
        else:
            vacancy = VacancyClass.unknown
            confidence = Confidence.none
            rationale = "No confirmed eligible segments."
        if unknown_in_journey:
            missing.append("unknown occupancy values in journey interval")
        return LongestRun(
            from_station=None,
            to_station=None,
            consecutive_segments=0,
            distance_km=None,
            coverage_percent=0.0 if journey_km is not None else None,
            covers_full_journey=False,
            vacancy_class=vacancy,
            confidence=confidence,
            warnings=warnings,
            missing_data_reasons=missing,
            segments=segments,
            ranking_mode=ranking_mode,
            ranking_rationale=rationale,
            distance_source=distance_source,
        )

    run_from = best[0].clipped_from
    run_to = best[-1].clipped_to
    km = interval_distance_km(route, run_from or "", run_to or "") if distance_available else None
    coverage = None
    covers_full = False
    if journey_km and km is not None:
        coverage = round((km / journey_km) * 100.0, 2)
        covers_full = abs(km - journey_km) < 0.01
    elif ranking_mode is RankingMode.segments:
        # Coverage by station span when kilometres are unavailable.
        span = (by_code[run_to].index - by_code[run_from].index) if run_from in by_code and run_to in by_code else 0
        journey_span = by_code[journey_to].index - by_code[journey_from].index
        if journey_span:
            coverage = round((span / journey_span) * 100.0, 2)
            covers_full = span == journey_span

    if covers_full and not unknown_in_journey:
        vacancy = VacancyClass.confirmed_eligible
        confidence = Confidence.high
    elif best and not covers_full:
        vacancy = VacancyClass.partial
        confidence = Confidence.medium if not unknown_in_journey else Confidence.low
    else:
        vacancy = VacancyClass.uncertain
        confidence = Confidence.low

    if unknown_in_journey:
        warnings.append("Some journey segments have unknown occupancy.")
        vacancy = VacancyClass.uncertain
        confidence = Confidence.low

    if ranking_mode is RankingMode.kilometres and km is not None:
        rationale = (
            f"Longest confirmed vacant run {run_from}->{run_to} covers {km:g} verified km "
            f"across {len(best)} consecutive segment(s)."
        )
    else:
        rationale = (
            f"Distance unavailable; longest confirmed vacant run {run_from}->{run_to} "
            f"spans {len(best)} consecutive segment(s)."
        )

    return LongestRun(
        from_station=run_from,
        to_station=run_to,
        consecutive_segments=len(best),
        distance_km=km if ranking_mode is RankingMode.kilometres else None,
        coverage_percent=coverage,
        covers_full_journey=covers_full,
        vacancy_class=vacancy,
        confidence=confidence,
        warnings=warnings,
        missing_data_reasons=missing,
        segments=segments,
        ranking_mode=ranking_mode,
        ranking_rationale=rationale,
        distance_source=distance_source,
    )


def ranking_key(run: Any, coach_name: str, berth_no: int) -> tuple:
    """Deterministic sort: km desc, segments desc, coverage desc, coach, berth."""
    km = run.distance_km if getattr(run, "distance_km", None) is not None else -1.0
    coverage = run.coverage_percent if getattr(run, "coverage_percent", None) is not None else -1.0
    mode = getattr(run, "ranking_mode", RankingMode.segments)
    return (
        0 if mode is RankingMode.kilometres and getattr(run, "distance_km", None) is not None else 1,
        -km,
        -getattr(run, "consecutive_segments", 0),
        -coverage,
        coach_name,
        berth_no,
    )
