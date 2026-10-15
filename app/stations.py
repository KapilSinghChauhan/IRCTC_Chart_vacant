from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATIONS_PATH = ROOT / "fixtures" / "stations.json"

EXTRA_DEMO = (
    {"code": "AAA", "name": "ALPHA"},
    {"code": "BBB", "name": "BRAVO"},
    {"code": "CCC", "name": "CHARLIE"},
    {"code": "DDD", "name": "DELTA"},
)


@lru_cache(maxsize=1)
def all_stations() -> list[dict[str, str]]:
    if not STATIONS_PATH.exists():
        return list(EXTRA_DEMO)
    payload = json.loads(STATIONS_PATH.read_text(encoding="utf-8"))
    stations: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in payload:
        code = str(item.get("code") or "").strip().upper()
        name = str(item.get("name") or "").strip()
        if not code or not name or code in seen:
            continue
        seen.add(code)
        stations.append({"code": code, "name": name})
    for extra in EXTRA_DEMO:
        if extra["code"] not in seen:
            stations.append(extra)
            seen.add(extra["code"])
    return stations


def search_stations(query: str, limit: int = 12) -> list[dict[str, str]]:
    needle = query.strip().upper()
    if not needle:
        return []
    scored: list[tuple[int, str, dict[str, str]]] = []
    for station in all_stations():
        code = station["code"]
        name = station["name"].upper()
        if needle == code:
            rank = 0
        elif code.startswith(needle):
            rank = 1
        elif name.startswith(needle):
            rank = 2
        elif needle in name:
            rank = 3
        elif needle in code:
            rank = 4
        else:
            continue
        scored.append((rank, name, station))
    scored.sort(key=lambda item: (item[0], item[1], item[2]["code"]))
    return [item[2] for item in scored[: max(1, min(limit, 25))]]
