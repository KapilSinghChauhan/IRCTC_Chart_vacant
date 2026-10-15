from __future__ import annotations

from app.engine import normalize_berth_segments
from app.route import reconstruct_route_from_segments


def test_reconstructed_route_keeps_occupancy_hops_forward():
    pairs = [
        ("BNW", "DLI", 1),
        ("DLI", "PRYJ", 2),
        ("BNW", "SSB", 1),
        ("SSB", "BGQ", 2),
        ("BGQ", "PRYJ", 3),
        ("BNW", "DLI", 1),
        ("DLI", "MNQ", 2),
        ("MNQ", "PRYJ", 3),
        ("BNW", "PRYJ", 1),
        ("DLI", "FBD", 2),
        ("FBD", "PRYJ", 3),
    ]
    route = reconstruct_route_from_segments(pairs)
    assert route is not None
    codes = [station.code for station in route]
    assert codes.index("BNW") < codes.index("DLI") < codes.index("MNQ") < codes.index("PRYJ")
    assert codes.index("SSB") < codes.index("BGQ") < codes.index("PRYJ")
    assert codes.index("DLI") < codes.index("FBD") < codes.index("PRYJ")
    assert all(station.distance_km is None for station in route)

    raw = [
        {"splitNo": 1, "from": "BNW", "to": "SSB", "occupancy": False},
        {"splitNo": 2, "from": "SSB", "to": "BGQ", "occupancy": True},
        {"splitNo": 3, "from": "BGQ", "to": "PRYJ", "occupancy": False},
    ]
    _segs, warnings = normalize_berth_segments(raw, route, "DLI", "MNQ")
    assert all("not forward" not in w for w in warnings)


def test_reconstructed_linear_fixture_order_is_preserved():
    pairs = [("AAA", "BBB", 1), ("BBB", "CCC", 2), ("CCC", "DDD", 3)]
    route = reconstruct_route_from_segments(pairs)
    assert [station.code for station in route] == ["AAA", "BBB", "CCC", "DDD"]
