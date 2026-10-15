from __future__ import annotations

from typing import Any

from app.models import StationPoint
from app.route import normalize_schedule


def tiny_route() -> list[StationPoint]:
    return normalize_schedule(
        {
            "stationList": [
                {"stationCode": "AAA", "distance": "0", "stnSerialNumber": "1"},
                {"stationCode": "BBB", "distance": "10", "stnSerialNumber": "2"},
                {"stationCode": "CCC", "distance": "25", "stnSerialNumber": "3"},
                {"stationCode": "DDD", "distance": "40", "stnSerialNumber": "4"},
            ]
        }
    )


def seg(frm: str, to: str, occupancy: Any, split: int = 1, quota: str = "GN") -> dict[str, Any]:
    item: dict[str, Any] = {"splitNo": split, "from": frm, "to": to, "quota": quota}
    if occupancy is not Ellipsis:
        item["occupancy"] = occupancy
    return item
