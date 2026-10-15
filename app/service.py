from __future__ import annotations

import os
from typing import Any

from app.engine import longest_eligible_run, normalize_berth_segments, ranking_key
from app.integration.auto_client import AutoChartsClient
from app.integration.base import ChartsClient, FetchResult
from app.integration.cdp_client import CdpChartsClient
from app.integration.fixture_client import FixtureChartsClient, FixtureNotFound
from app.integration.live_client import LiveAccessError, LiveChartsClient
from app.logging_util import configure_logging
from app.models import (
    AnalysisRequest,
    AnalysisResponse,
    BerthLayoutCell,
    CoachLayout,
    CoachMeta,
    DataSourceKind,
    RankedBerth,
    RankingMode,
)
from app.route import normalize_schedule, reconstruct_route_from_segments
from app.validation import InputError, parse_request, validate_route_interval

logger = configure_logging()

VACANT_BERTHS_TRUSTED = False  # capture evidence: all coaches reported 0 while vacant splits existed


def select_client(explicit: str | None = None) -> ChartsClient:
    source = (explicit or os.environ.get("DATA_SOURCE") or "auto").strip().lower()
    if source == "live":
        return CdpChartsClient()
    if source == "http":
        return LiveChartsClient()
    if source == "synthetic":
        from app.integration.fixture_client import SYNTHETIC_DIR

        return FixtureChartsClient(SYNTHETIC_DIR)
    if source == "fixture":
        return FixtureChartsClient()
    return AutoChartsClient()


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def normalize_train_composition(payload: dict[str, Any]) -> tuple[dict[str, Any], list[CoachMeta], list[str]]:
    warnings: list[str] = []
    meta = {
        "train_no": payload.get("trainNo"),
        "train_name": payload.get("trainName"),
        "from": payload.get("from"),
        "to": payload.get("to"),
        "train_start_date": payload.get("trainStartDate"),
        "remote": payload.get("remote"),
        "next_remote": payload.get("nextRemote"),
        "chart_one_date": payload.get("chartOneDate"),
        "chart_two_date": payload.get("chartTwoDate"),
        "error": payload.get("error"),
        "chart_status": payload.get("chartStatusResponseDto"),
    }
    coaches: list[CoachMeta] = []
    cdd = payload.get("cdd")
    if not isinstance(cdd, list):
        warnings.append("train composition is missing cdd[]")
        return meta, coaches, warnings
    for item in cdd:
        if not isinstance(item, dict):
            continue
        name = str(item.get("coachName") or "").strip()
        cls = str(item.get("classCode") or "").strip().upper()
        if not name or not cls:
            warnings.append("coach record missing coachName or classCode")
            continue
        position = item.get("positionFromEngine")
        coaches.append(
            CoachMeta(
                coach_name=name,
                class_code=cls,
                position_from_engine=position if isinstance(position, int) else None,
                vacant_berths_raw=item.get("vacantBerths"),
            )
        )
    return meta, coaches, warnings


def analyze_payload(payload: dict[str, Any], client: ChartsClient | None = None) -> AnalysisResponse:
    try:
        request = parse_request(payload)
    except InputError as exc:
        return AnalysisResponse(
            ok=False,
            data_source=DataSourceKind.fixture,
            freshness_label="invalid-input",
            ranking_mode=RankingMode.segments,
            errors=[str(exc)],
        )
    client = client or select_client()
    source_kind = DataSourceKind.fixture if client.source_kind in {"fixture", "auto"} else DataSourceKind.live
    freshness = (
        "fixture-based (not live IRCTC data)"
        if client.source_kind == "fixture"
        else ("live charts, with saved fixtures used when they exist" if client.source_kind == "auto" else "live")
    )
    warnings: list[str] = []
    errors: list[str] = []
    retrieved_at = None

    try:
        train_fetch = client.train_composition(request.train_no, request.journey_date, request.boarding_station)
    except (LiveAccessError, FixtureNotFound, OSError) as exc:
        logger.info("train composition failed: %s", exc)
        detail = str(exc)
        if "No train composition fixture" in detail and "Live chart lookup also failed" not in detail:
            detail = (
                f"No saved chart for train {request.train_no}. "
                "Live IRCTC chart lookup was not used or also failed."
            )
        elif "Live chart lookup also failed" in detail:
            detail = (
                f"No saved chart for train {request.train_no}, and live IRCTC chart lookup failed. "
                f"{exc}"
            )
        else:
            detail = f"Train composition failed: {exc}"
        return AnalysisResponse(
            ok=False,
            data_source=source_kind,
            freshness_label=freshness,
            ranking_mode=RankingMode.segments,
            errors=[detail],
            train_no=request.train_no,
            journey_date=request.journey_date,
            boarding_station=request.boarding_station,
            destination_station=request.destination_station,
        )

    retrieved_at = train_fetch.retrieved_at
    if getattr(client, "last_source", None) == "live" or train_fetch.source == "live":
        source_kind = DataSourceKind.live
        freshness = "live"
    elif train_fetch.source == "fixture":
        source_kind = DataSourceKind.fixture
        freshness = "fixture-based (not live IRCTC data)"
    train_meta, coaches, train_warnings = normalize_train_composition(train_fetch.payload)
    warnings.extend(train_warnings)
    if train_meta.get("error"):
        warnings.append(f"train composition error field: {train_meta['error']}")

    discovered = sorted({c.class_code for c in coaches})
    selected_coaches = [c for c in coaches if c.class_code in request.classes]
    if coaches and not selected_coaches:
        warnings.append(
            "Selected class "
            + ", ".join(request.classes)
            + " is not on this train. Using discovered classes: "
            + ", ".join(discovered)
            + "."
        )
        selected_coaches = list(coaches)

    route: list = []
    ranking_mode = RankingMode.segments
    try:
        schedule_fetch = client.train_schedule(request.train_no)
        route = normalize_schedule(schedule_fetch.payload)
        if any(s.distance_km is not None for s in route):
            ranking_mode = RankingMode.kilometres
        else:
            warnings.append("Schedule has no kilometre values; ranking falls back to consecutive segments.")
    except (LiveAccessError, FixtureNotFound, InputError, OSError) as exc:
        warnings.append(f"Verified kilometre source unavailable ({exc}); ranking by consecutive segments.")
        ranking_mode = RankingMode.segments

    if route:
        try:
            validate_route_interval(route, request.boarding_station, request.destination_station)
        except InputError as exc:
            return AnalysisResponse(
                ok=False,
                data_source=source_kind,
                freshness_label=freshness,
                retrieved_at=retrieved_at,
                ranking_mode=ranking_mode,
                train_no=str(train_meta.get("train_no") or request.train_no),
                train_name=train_meta.get("train_name"),
                journey_date=request.journey_date,
                boarding_station=request.boarding_station,
                destination_station=request.destination_station,
                discovered_classes=discovered,
                route=route,
                chart_status=_as_dict(train_meta.get("chart_status")) or None,
                errors=[str(exc)],
                warnings=warnings,
            )

    remote = str(train_meta.get("remote") or request.boarding_station)
    source_station = str(train_meta.get("from") or request.boarding_station)
    layouts: list[CoachLayout] = []
    ranked: list[RankedBerth] = []
    fetched: list[tuple[CoachMeta, FetchResult | None, str | None]] = []

    for coach in selected_coaches:
        try:
            coach_fetch = client.coach_composition(
                train_no=request.train_no,
                boarding_station=request.boarding_station,
                remote_station=remote,
                train_source_station=source_station,
                journey_date=request.journey_date,
                coach=coach.coach_name,
                cls=coach.class_code,
            )
            fetched.append((coach, coach_fetch, None))
        except (LiveAccessError, FixtureNotFound, OSError) as exc:
            warnings.append(f"Coach {coach.coach_name} ({coach.class_code}) failed: {exc}")
            fetched.append((coach, None, str(exc)))

    if not route:
        pairs: list[tuple[str, str, int | None]] = []
        for _coach, coach_fetch, _err in fetched:
            if coach_fetch is None:
                continue
            for berth in _as_list(coach_fetch.payload.get("bdd")):
                if not isinstance(berth, dict):
                    continue
                for item in _as_list(berth.get("bsd")):
                    if not isinstance(item, dict):
                        continue
                    frm = str(item.get("from") or "").strip().upper()
                    to = str(item.get("to") or "").strip().upper()
                    split = item.get("splitNo") if isinstance(item.get("splitNo"), int) else None
                    if frm and to:
                        pairs.append((frm, to, split))
        reconstructed = reconstruct_route_from_segments(pairs)
        if reconstructed:
            route = reconstructed
            warnings.append(
                "Station order reconstructed from berth segments; kilometres unavailable. Ranking uses consecutive segments."
            )
            ranking_mode = RankingMode.segments

    if route:
        try:
            validate_route_interval(route, request.boarding_station, request.destination_station)
        except InputError as exc:
            return AnalysisResponse(
                ok=False,
                data_source=source_kind,
                freshness_label=freshness,
                retrieved_at=retrieved_at,
                ranking_mode=ranking_mode,
                train_no=str(train_meta.get("train_no") or request.train_no),
                train_name=train_meta.get("train_name"),
                journey_date=request.journey_date,
                boarding_station=request.boarding_station,
                destination_station=request.destination_station,
                discovered_classes=discovered,
                route=route,
                chart_status=_as_dict(train_meta.get("chart_status")) or None,
                errors=[str(exc)],
                warnings=warnings,
            )

    distance_available = ranking_mode is RankingMode.kilometres

    for coach, coach_fetch, fetch_error in fetched:
        if coach_fetch is None:
            layouts.append(
                CoachLayout(
                    coach_name=coach.coach_name,
                    class_code=coach.class_code,
                    position_from_engine=coach.position_from_engine,
                    vacant_berths_raw=coach.vacant_berths_raw,
                    vacant_berths_trusted=VACANT_BERTHS_TRUSTED,
                    berths=[],
                    fetch_ok=False,
                    error=fetch_error,
                )
            )
            continue

        payload = coach_fetch.payload
        if payload.get("error"):
            warnings.append(f"Coach {coach.coach_name} error field: {payload.get('error')}")
        bdd = payload.get("bdd")
        if not isinstance(bdd, list):
            warnings.append(f"Coach {coach.coach_name} is missing bdd[]")
            layouts.append(
                CoachLayout(
                    coach_name=coach.coach_name,
                    class_code=coach.class_code,
                    position_from_engine=coach.position_from_engine,
                    vacant_berths_raw=coach.vacant_berths_raw,
                    vacant_berths_trusted=VACANT_BERTHS_TRUSTED,
                    berths=[],
                    fetch_ok=False,
                    error="missing bdd[]",
                )
            )
            continue

        cells: list[BerthLayoutCell] = []
        for berth in bdd:
            if not isinstance(berth, dict):
                continue
            berth_no = berth.get("berthNo")
            if not isinstance(berth_no, int):
                warnings.append(f"Coach {coach.coach_name} berth missing berthNo")
                continue
            enable = berth.get("enable") if isinstance(berth.get("enable"), bool) else None
            segs, seg_warnings = normalize_berth_segments(
                _as_list(berth.get("bsd")),
                route,
                request.boarding_station,
                request.destination_station,
            )
            warnings.extend(f"{coach.coach_name}-{berth_no}: {w}" for w in seg_warnings)
            run = longest_eligible_run(
                segs,
                route,
                request.boarding_station,
                request.destination_station,
                distance_available=distance_available,
            )
            cells.append(
                BerthLayoutCell(
                    berth_no=berth_no,
                    berth_code=berth.get("berthCode"),
                    cabin=berth.get("cabinCoupeNameNo"),
                    vacancy_class=run.vacancy_class,
                    enable=enable,
                )
            )
            ranked.append(
                RankedBerth(
                    rank=0,
                    train_no=str(train_meta.get("train_no") or request.train_no),
                    train_name=train_meta.get("train_name"),
                    journey_date=request.journey_date,
                    boarding_station=request.boarding_station,
                    destination_station=request.destination_station,
                    class_code=coach.class_code,
                    coach_name=coach.coach_name,
                    coach_position=coach.position_from_engine,
                    berth_no=berth_no,
                    berth_code=berth.get("berthCode"),
                    cabin=berth.get("cabinCoupeNameNo"),
                    enable=enable,
                    run_from=run.from_station,
                    run_to=run.to_station,
                    distance_km=run.distance_km,
                    consecutive_segments=run.consecutive_segments,
                    coverage_percent=run.coverage_percent,
                    covers_full_journey=run.covers_full_journey,
                    vacancy_class=run.vacancy_class,
                    confidence=run.confidence,
                    ranking_mode=run.ranking_mode,
                    ranking_rationale=run.ranking_rationale,
                    distance_source=run.distance_source,
                    warnings=run.warnings,
                    missing_data_reasons=run.missing_data_reasons,
                    segments=run.segments,
                    retrieved_at=coach_fetch.retrieved_at,
                )
            )
        layouts.append(
            CoachLayout(
                coach_name=coach.coach_name,
                class_code=coach.class_code,
                position_from_engine=coach.position_from_engine,
                vacant_berths_raw=coach.vacant_berths_raw,
                vacant_berths_trusted=VACANT_BERTHS_TRUSTED,
                berths=cells,
                fetch_ok=True,
            )
        )

    ranked.sort(key=lambda item: ranking_key(item, item.coach_name, item.berth_no))
    for index, item in enumerate(ranked, start=1):
        item.rank = index

    ok = not errors and bool(route)
    if not route:
        errors.append("Cannot analyse vacancy without a verified station order.")
        ok = False

    return AnalysisResponse(
        ok=ok,
        data_source=source_kind,
        freshness_label=freshness,
        retrieved_at=retrieved_at,
        stale=False,
        ranking_mode=ranking_mode,
        train_no=str(train_meta.get("train_no") or request.train_no),
        train_name=train_meta.get("train_name"),
        journey_date=request.journey_date,
        boarding_station=request.boarding_station,
        destination_station=request.destination_station,
        discovered_classes=discovered,
        coaches=layouts,
        results=ranked,
        route=route,
        warnings=warnings,
        errors=errors,
        chart_status=_as_dict(train_meta.get("chart_status")) or None,
    )
