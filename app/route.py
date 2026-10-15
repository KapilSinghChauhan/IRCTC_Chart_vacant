from __future__ import annotations

from typing import Any, Iterable

from app.models import StationPoint
from app.validation import InputError


def parse_optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def normalize_schedule(payload: dict[str, Any]) -> list[StationPoint]:
    raw_list = payload.get("stationList")
    if not isinstance(raw_list, list) or not raw_list:
        raise InputError("Schedule response is missing stationList.")
    stations: list[StationPoint] = []
    for offset, item in enumerate(raw_list):
        if not isinstance(item, dict):
            continue
        code = str(item.get("stationCode") or "").strip().upper()
        if not code:
            continue
        serial = parse_optional_int(item.get("stnSerialNumber"))
        stations.append(
            StationPoint(
                code=code,
                name=item.get("stationName"),
                index=offset,
                distance_km=parse_optional_float(item.get("distance")),
                serial=serial,
            )
        )
    if len(stations) < 2:
        raise InputError("Schedule does not contain a usable ordered station list.")
    return stations


def station_index(route: list[StationPoint]) -> dict[str, StationPoint]:
    return {station.code: station for station in route}


def interval_distance_km(route: list[StationPoint], start_code: str, end_code: str) -> float | None:
    by_code = station_index(route)
    start = by_code.get(start_code)
    end = by_code.get(end_code)
    if start is None or end is None:
        return None
    if start.distance_km is None or end.distance_km is None:
        return None
    delta = end.distance_km - start.distance_km
    if delta < 0:
        return None
    return delta


def segments_are_adjacent(left_to: str, right_from: str) -> bool:
    return left_to == right_from


def reconstruct_route_from_segments(
    segments: Iterable[tuple[str, str, int | None]],
    existing: list[StationPoint] | None = None,
) -> list[StationPoint] | None:
    """Best-effort ordered unique stations from occupancy from/to hops.

    Used only when a schedule is unavailable. Distances stay None.
    Order is a topological sort of hops so later occupancy splits stay
    forward of earlier ones. Direct first-seen insertion is not enough
    when one berth jumps BNW→PRYJ while another walks BNW→DLI→MNQ→PRYJ.
    """
    if existing:
        return existing
    hops: list[tuple[str, str]] = []
    nodes: set[str] = set()
    for frm, to, _split in segments:
        if not frm or not to or frm == to:
            continue
        hops.append((frm, to))
        nodes.add(frm)
        nodes.add(to)
    if len(nodes) < 2:
        return None

    successors: dict[str, set[str]] = {code: set() for code in nodes}
    indegree: dict[str, int] = {code: 0 for code in nodes}
    for frm, to in hops:
        if to in successors[frm]:
            continue
        successors[frm].add(to)
        indegree[to] += 1

    # Prefer sources that occupancy chains start from, then remaining sources.
    start_counts: dict[str, int] = {}
    for frm, _to in hops:
        start_counts[frm] = start_counts.get(frm, 0) + 1
    ready = sorted(
        [code for code, degree in indegree.items() if degree == 0],
        key=lambda code: (-start_counts.get(code, 0), code),
    )
    ordered: list[str] = []
    while ready:
        current = ready.pop(0)
        ordered.append(current)
        next_ready: list[str] = []
        for nxt in sorted(successors[current]):
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                next_ready.append(nxt)
        ready.extend(sorted(next_ready, key=lambda code: (-start_counts.get(code, 0), code)))

    leftover = [code for code in nodes if code not in ordered]
    if leftover:
        leftover.sort()
        ordered.extend(leftover)
    if len(ordered) < 2:
        return None
    return [
        StationPoint(code=code, name=None, index=idx, distance_km=None, serial=None)
        for idx, code in enumerate(ordered)
    ]
